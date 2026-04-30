import hashlib
import os
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

from core.dispatch.comfy_client import ComfyUIClient
from core.prompts.prompt_compiler import compile_prompt_artifact
from core.bridge.runtime_config import get_raw_config

from .director_service import KimiDirectorService
from .state_machine import transition_shot


@dataclass
class CampaignRequest:
    brief: str
    bible_path: str = ""
    length: str = ""
    workflow_ids: Optional[List[str]] = None


class HermesCampaignService:
    def __init__(
        self,
        *,
        repo_root: Path,
        media_images: Path,
        shots_store: List[Dict[str, Any]],
        campaigns: Dict[str, Dict[str, Any]],
        now_iso: Callable[[], str],
        record_event: Callable[..., None],
        audit_render: Callable[[str, str, str], Awaitable[Dict[str, Any]]],
        workflow_file_for_id: Callable[[str], Optional[Path]],
        is_cancelled: Callable[[], bool],
        active_campaign_setter: Callable[[str], None],
        remediate_failed: Optional[Callable[[List[str]], Awaitable[Dict[str, Any]]]] = None,
    ) -> None:
        self.repo_root = repo_root
        self.media_images = media_images
        self.shots_store = shots_store
        self.campaigns = campaigns
        self.now_iso = now_iso
        self.record_event = record_event
        self.audit_render = audit_render
        self.workflow_file_for_id = workflow_file_for_id
        self.is_cancelled = is_cancelled
        self.active_campaign_setter = active_campaign_setter
        self.remediate_failed = remediate_failed
        self.director = KimiDirectorService()

    def _resolve_bible_text(self, bible_path: str) -> str:
        if not bible_path:
            return ""
        try:
            p = Path(bible_path)
            if not p.is_absolute():
                p = (self.repo_root / bible_path).resolve()
            if p.exists():
                return p.read_text(encoding="utf-8")
        except Exception:
            return ""
        return ""

    def _build_campaign_id(self, brief: str) -> str:
        """
        Create readable campaign ids/folder names from the prompt, with a
        short uniqueness suffix.
        """
        base = (brief or "").strip().lower()
        base = re.sub(r"[^a-z0-9]+", "_", base)
        base = re.sub(r"_+", "_", base).strip("_")
        if not base:
            base = "campaign"
        # Keep path/file friendly and concise.
        base = base[:48].rstrip("_")
        suffix = hashlib.sha1(f"{time.time()}:{brief}".encode("utf-8")).hexdigest()[:6]
        campaign_id = f"{base}__{suffix}"
        # Absolute guard to avoid accidental collisions in-memory.
        existing = set(self.campaigns.keys())
        if campaign_id in existing:
            campaign_id = f"{base}__{suffix}{random.randint(10, 99)}"
        return campaign_id

    def _write_campaign_manifest(self, campaign_id: str, brief: str, workflow_ids: List[str]) -> None:
        """Persist campaign metadata so full briefs survive restarts/reindex."""
        try:
            folder = self.media_images / campaign_id
            folder.mkdir(parents=True, exist_ok=True)
            manifest = {
                "campaign_id": campaign_id,
                "brief": brief,
                "workflow_ids": workflow_ids,
                "started_at": self.now_iso(),
            }
            (folder / "_campaign.json").write_text(
                json.dumps(manifest, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        except Exception:
            # Non-fatal metadata write.
            return

    @staticmethod
    def _exc_reason(e: Exception) -> str:
        msg = str(e).strip()
        if msg:
            return msg
        # Many network exceptions stringify to empty; keep this explicit.
        cls = e.__class__.__name__
        rep = repr(e).strip()
        if rep and rep != f"{cls}()":
            return f"{cls}: {rep}"
        return cls or "unknown_error"

    async def stream_campaign(self, req: CampaignRequest) -> AsyncIterator[Dict[str, Any]]:
        campaign_id = self._build_campaign_id(req.brief)
        self.active_campaign_setter(campaign_id)
        workflow_ids = req.workflow_ids or ["spark_image_z_image"]
        self.campaigns[campaign_id] = {
            "brief": req.brief,
            "started_at": self.now_iso(),
            "workflow_ids": workflow_ids,
        }
        self._write_campaign_manifest(campaign_id, req.brief, workflow_ids)
        bible_text = self._resolve_bible_text(req.bible_path)

        yield {"type": "kimi", "text": "Generating shot list..."}
        use_fallback = os.getenv("FORGE_DEV_FALLBACK", "false").lower() == "true"
        target_shots = self.director.requested_shot_count(req.brief, req.length)

        try:
            plan = await self.director.request_plan(
                req.brief,
                campaign_id,
                bible_text=bible_text,
                length=req.length,
                target_shots=target_shots,
            )
        except Exception as e:
            reason = self._exc_reason(e)
            yield {"type": "error", "text": f"Kimi shot generation failed: {reason}"}
            if not use_fallback:
                yield {"type": "done", "text": "Campaign stopped: Kimi failure before Spark dispatch."}
                return
            plan = self.director.build_dev_fallback_plan(req.brief, campaign_id)
            yield {"type": "error", "text": "Falling back to local synthetic shot list (FORGE_DEV_FALLBACK=true)"}

        raw_content = plan.get("__raw_content", "")
        self.campaigns[campaign_id]["kimi_raw_response"] = raw_content
        yield {"type": "kimi_raw", "campaign_id": campaign_id, "text": raw_content[:800]}

        try:
            kimi_shots = self.director.normalize_shots(plan, campaign_id)
        except Exception as e:
            yield {"type": "error", "text": f"Kimi plan parse failed: {e}"}
            yield {"type": "done", "text": "Campaign stopped: invalid Kimi plan."}
            return

        if len(kimi_shots) < target_shots:
            missing = target_shots - len(kimi_shots)
            yield {"type": "kimi", "text": f"Director returned {len(kimi_shots)}/{target_shots} shots. Requesting {missing} additional shots..."}
            try:
                top_up = await self.director.request_missing_shots(
                    brief=req.brief,
                    campaign_id=campaign_id,
                    existing_shots=kimi_shots,
                    target_shots=target_shots,
                    bible_text=bible_text,
                    length=req.length,
                )
                top_up_raw = top_up.get("__raw_content", "")
                if top_up_raw:
                    raw_content = f"{raw_content}\n\n---TOP_UP---\n{top_up_raw}"
                    self.campaigns[campaign_id]["kimi_raw_response"] = raw_content
                    yield {"type": "kimi_raw", "campaign_id": campaign_id, "text": top_up_raw[:800]}
                top_up_shots = self.director.normalize_shots(top_up, campaign_id)
                existing_ids = {s["shot_id"] for s in kimi_shots}
                existing_seq = {int(s["sequence"]) for s in kimi_shots}
                for s in top_up_shots:
                    if s["shot_id"] in existing_ids or int(s["sequence"]) in existing_seq:
                        continue
                    kimi_shots.append(s)
                    existing_ids.add(s["shot_id"])
                    existing_seq.add(int(s["sequence"]))
                kimi_shots = sorted(kimi_shots, key=lambda x: x["sequence"])
            except Exception as e:
                yield {"type": "error", "text": f"Kimi top-up failed: {e}"}

        if len(kimi_shots) < target_shots and not use_fallback:
            yield {
                "type": "error",
                "text": (
                    f"Kimi coverage incomplete: only {len(kimi_shots)} shots returned vs {target_shots} requested. "
                    "Campaign stopped before Spark."
                ),
            }
            yield {"type": "done", "text": "Campaign stopped: incomplete Kimi shot plan."}
            return

        review: Dict[str, Any] = {}
        try:
            review = await self.director.self_check_plan(req.brief, campaign_id, kimi_shots)
            self.campaigns[campaign_id]["kimi_review"] = review
            yield {
                "type": "kimi_review",
                "campaign_id": campaign_id,
                "score": review.get("score"),
                "status": review.get("status"),
                "director_notes": review.get("director_notes", ""),
                "coverage_gaps": review.get("coverage_gaps", []),
            }
            min_score = int(os.getenv("FORGE_KIMI_MIN_DIRECTOR_SCORE", "45"))
            score = self.director.score_from_review(review)
            if score is not None and score < min_score and not use_fallback:
                yield {
                    "type": "error",
                    "text": f"Kimi director self-check score {score} below threshold {min_score}. Campaign stopped before Spark.",
                }
                yield {"type": "done", "text": "Campaign stopped: Kimi self-check below threshold."}
                return
        except Exception as e:
            if os.getenv("FORGE_KIMI_REQUIRE_SELF_CHECK", "false").lower() == "true":
                yield {"type": "error", "text": f"Kimi self-check failed: {e}"}
                yield {"type": "done", "text": "Campaign stopped: Kimi self-check unavailable."}
                return
            yield {"type": "warning", "text": f"Kimi self-check unavailable: {e}"}

        yield {"type": "kimi_plan", "campaign_id": campaign_id, "count": len(kimi_shots), "shots": kimi_shots}
        yield {"type": "kimi", "text": f"Shot list ready: {len(kimi_shots)} shots (requested {target_shots})"}

        cfg = get_raw_config()
        host = (
            os.getenv("COMFYUI_PRIMARY", "")
            or str(cfg.get("COMFYUI_PRIMARY", ""))
            or "http://100.112.87.8:8188"
        ).rstrip("/")
        comfy = ComfyUIClient(host)
        rendered_count = 0
        source = "fallback" if use_fallback else "campaign"

        for shot in kimi_shots:
            if self.is_cancelled():
                yield {"type": "error", "text": "Campaign cancelled by user."}
                break
            for workflow_id in workflow_ids:
                if self.is_cancelled():
                    break

                record_id = f"{campaign_id}__{shot['shot_id']}__{workflow_id}"
                yield {"type": "hermes", "shot_id": shot["shot_id"], "text": f"Writing prompt for {shot['shot_id']}..."}

                artifact = compile_prompt_artifact(
                    raw_concept=req.brief,
                    workflow_id=workflow_id,
                    kimi_plan=shot,
                    character_names=shot.get("characters", []),
                    shot_meta={"campaign_id": campaign_id, "shot_id": shot["shot_id"], "sequence": shot["sequence"]},
                )
                yield {
                    "type": "compiler",
                    "shot_id": shot["shot_id"],
                    "workflow_id": workflow_id,
                    "profile_name": artifact.get("profile_name"),
                    "model_standard_name": artifact.get("model_standard_name"),
                    "model_standard_version": artifact.get("model_standard_version"),
                    "skills_used": artifact.get("skills_used", []),
                    "text": (
                        f"profile={artifact.get('profile_name')} "
                        f"standard={artifact.get('model_standard_name')}@{artifact.get('model_standard_version')} "
                        f"skills={','.join(artifact.get('skills_used', [])) or 'none'}"
                    ),
                }
                compiled_text = str(artifact.get("compiled_prompt", "") or "").strip()
                if compiled_text:
                    yield {
                        "type": "hermes",
                        "shot_id": shot["shot_id"],
                        "text": f"Compiled prompt ({workflow_id}): {compiled_text}",
                    }

                shot_record = {
                    "id": record_id,
                    "campaign_id": campaign_id,
                    "campaign_brief": req.brief,
                    "shot_id": shot["shot_id"],
                    "sequence": shot["sequence"],
                    "workflow_id": workflow_id,
                    "state": "planned",
                    "status": "planned",
                    "seed": random.randint(100000, 999999),
                    "prompt": artifact.get("compiled_prompt", ""),
                    "compiled_prompt": artifact.get("compiled_prompt", ""),
                    "negative_prompt": artifact.get("negative_prompt", ""),
                    "workflow_profile": artifact.get("profile_name", ""),
                    "skills_used": artifact.get("skills_used", []),
                    "compiler_version": artifact.get("compiler_version", ""),
                    "model_standard_name": artifact.get("model_standard_name", ""),
                    "model_standard_version": artifact.get("model_standard_version", ""),
                    "model_standard_source": artifact.get("model_standard_source", ""),
                    "model_standard_rules": artifact.get("model_standard_rules", []),
                    "sections": artifact.get("sections", {}),
                    "kimi_plan": shot,
                    "raw_kimi_prompt": shot.get("visual_brief", ""),
                    "kimi_rationale": shot.get("rationale", ""),
                    "kimi_constraints": shot.get("constraints", ""),
                    "kimi_raw_response": raw_content,
                    "kimi_review_score": review.get("score") if isinstance(review, dict) else None,
                    "audit_status": "",
                    "source": source,
                    "created_at": self.now_iso(),
                }
                self.shots_store.append(shot_record)
                self.record_event("shot_planned", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source)

                wf = self.workflow_file_for_id(workflow_id)
                if not wf:
                    transition_shot(shot_record, "final_fail")
                    yield {"type": "error", "shot_id": shot["shot_id"], "text": f"Workflow not found: {workflow_id}"}
                    self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": "workflow_missing"})
                    continue

                yield {"type": "spark", "shot_id": shot["shot_id"], "text": f"Dispatching {shot['shot_id']} to ComfyUI..."}
                transition_shot(shot_record, "queued")
                self.record_event("render_attempt", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source)
                try:
                    submit = await comfy.submit_prompt_for_shot(
                        shot_id=record_id,
                        prompt=artifact.get("compiled_prompt", ""),
                        workflow_path=str(wf),
                        seed=shot_record["seed"],
                        output_dir=str(self.media_images / campaign_id),
                    )
                except Exception as e:
                    transition_shot(shot_record, "final_fail")
                    msg = f"submit_exception:{e}"
                    yield {"type": "error", "shot_id": shot["shot_id"], "text": f"ComfyUI submission failed for {shot['shot_id']}: {msg}"}
                    self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": msg})
                    continue
                if submit.get("status") != "success":
                    transition_shot(shot_record, "final_fail")
                    msg = submit.get("error", "ComfyUI submission failed")
                    yield {"type": "error", "shot_id": shot["shot_id"], "text": f"ComfyUI submission failed for {shot['shot_id']}: {msg}"}
                    self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": msg})
                    continue

                rendered_count += 1
                prompt_id = submit.get("prompt_id", "")
                saved = submit.get("saved_files", [])
                image_path = saved[0] if saved else ""
                shot_record["prompt_id"] = prompt_id
                transition_shot(shot_record, "rendered")
                if image_path:
                    shot_record["image_path"] = image_path
                    try:
                        rel = Path(image_path).resolve().relative_to(self.media_images.resolve())
                        shot_record["image_url"] = f"/external-renders/{rel.as_posix()}"
                    except Exception:
                        shot_record["image_url"] = f"/external-renders/{Path(image_path).name}"
                yield {"type": "spark", "shot_id": shot["shot_id"], "status": "queued", "prompt_id": prompt_id, "text": f"Queued {shot['shot_id']} ({workflow_id})"}
                self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=True, extra={"prompt_id": prompt_id})

                if image_path:
                    transition_shot(shot_record, "audit_started")
                    self.record_event("audit_started", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source)
                    try:
                        audit = await self.audit_render(image_path, shot_record["compiled_prompt"], campaign_id)
                    except Exception as e:
                        transition_shot(shot_record, "final_fail")
                        self.record_event("audit_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": f"audit_exception:{e}"})
                        yield {"type": "error", "shot_id": shot["shot_id"], "text": f"Audit failed for {shot['shot_id']}: {e}"}
                        continue
                    score = float(audit.get("score", 0) or 0)
                    passed = bool(audit.get("passed", False))
                    shot_record["audit_model"] = os.getenv("KIMI_VISUAL_MODEL", os.getenv("LMSTUDIO_VISION_MODEL", "vision"))
                    shot_record["audit_status"] = "pass" if passed else "fail"
                    shot_record["audit_score"] = score
                    shot_record["audit_issues"] = audit.get("issues", [])
                    shot_record["audit_model_score"] = float(audit.get("model_score", score) or 0)
                    shot_record["audit_checks_score"] = float(audit.get("checks_score", 0) or 0)
                    shot_record["audit_confidence"] = float(audit.get("confidence", 0) or 0)
                    shot_record["audit_model_passed"] = bool(audit.get("model_passed", passed))
                    shot_record["audit_final_passed"] = bool(audit.get("final_passed", passed))
                    shot_record["audit_checks"] = audit.get("checks", {})
                    shot_record["audit_critical_failures"] = audit.get("critical_failures", [])
                    shot_record["audit_noncritical_issues"] = audit.get("noncritical_issues", [])
                    shot_record["audit_decision_reasons"] = audit.get("audit_decision_reasons", [])
                    shot_record["audit_raw_response"] = audit
                    shot_record["audit_timestamp"] = self.now_iso()
                    transition_shot(shot_record, "audited_pass" if passed else "audited_fail")
                    self.record_event("audit_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=passed, extra={"audit_score": score})
                    if passed:
                        yield {"type": "memory", "shot_id": shot["shot_id"], "text": f"Audit pass ({score:.1f})"}
                    else:
                        issues = shot_record.get("audit_issues") or []
                        reasons = shot_record.get("audit_decision_reasons") or []
                        critical = shot_record.get("audit_critical_failures") or []
                        feedback = str(audit.get("feedback", "") or "")
                        audit_error = str(audit.get("error", "") or "")
                        top = []
                        top.extend([str(x) for x in critical[:2]])
                        top.extend([str(x) for x in reasons[:2]])
                        if not top:
                            top.extend([str(x) for x in issues[:2]])
                        if not top and feedback:
                            top.append(feedback[:220])
                        if not top and audit_error:
                            top.append(audit_error[:220])
                        if not top and isinstance(audit, dict):
                            raw_hint = str(audit.get("detail") or audit.get("message") or "")
                            if raw_hint:
                                top.append(raw_hint[:220])
                        reason_text = "; ".join([t for t in top if t]) or "no_reason_returned"
                        yield {
                            "type": "error",
                            "shot_id": shot["shot_id"],
                            "text": f"Audit fail for {shot['shot_id']} ({score:.1f}): {reason_text}",
                        }
                        yield {"type": "memory", "shot_id": shot["shot_id"], "text": f"Audit fail ({score:.1f})"}
                        auto_remediate = os.getenv("FORGE_AUTO_REMEDIATE_ON_FAIL", "true").lower() == "true"
                        if auto_remediate and self.remediate_failed:
                            yield {"type": "hermes", "shot_id": shot["shot_id"], "text": f"Auto-remediation queued for {shot['shot_id']}..."}
                            try:
                                rem = await self.remediate_failed([record_id])
                                rlist = rem.get("results", []) if isinstance(rem, dict) else []
                                if rlist:
                                    r0 = rlist[0] or {}
                                    if r0.get("status") == "ok":
                                        yield {
                                            "type": "memory",
                                            "shot_id": shot["shot_id"],
                                            "text": f"Auto-remediation complete: retry={r0.get('retry_shot_id', 'n/a')} status={r0.get('retry_audit_status', 'n/a')}",
                                        }
                                    else:
                                        yield {
                                            "type": "error",
                                            "shot_id": shot["shot_id"],
                                            "text": f"Auto-remediation failed for {shot['shot_id']}: {r0.get('reason', r0.get('status', 'unknown'))}",
                                        }
                                else:
                                    yield {"type": "warning", "shot_id": shot["shot_id"], "text": f"Auto-remediation returned no result for {shot['shot_id']}"}
                            except Exception as e:
                                yield {"type": "error", "shot_id": shot["shot_id"], "text": f"Auto-remediation exception for {shot['shot_id']}: {self._exc_reason(e)}"}

        yield {"type": "done", "text": f"Campaign complete. {rendered_count} shots processed."}
