import hashlib
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

from core.dispatch.comfy_client import ComfyUIClient
from core.prompts.prompt_compiler import compile_prompt_artifact

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

    async def stream_campaign(self, req: CampaignRequest) -> AsyncIterator[Dict[str, Any]]:
        campaign_id = hashlib.sha1(f"{time.time()}:{req.brief}".encode("utf-8")).hexdigest()[:12]
        self.active_campaign_setter(campaign_id)
        workflow_ids = req.workflow_ids or ["spark_image_z_image"]
        self.campaigns[campaign_id] = {
            "brief": req.brief,
            "started_at": self.now_iso(),
            "workflow_ids": workflow_ids,
        }
        bible_text = self._resolve_bible_text(req.bible_path)

        yield {"type": "kimi", "text": "Generating shot list..."}
        use_fallback = os.getenv("FORGE_DEV_FALLBACK", "false").lower() == "true"

        try:
            plan = await self.director.request_plan(req.brief, campaign_id, bible_text=bible_text, length=req.length)
        except Exception as e:
            reason = str(e)
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
        yield {"type": "kimi", "text": f"Shot list ready: {len(kimi_shots)} shots"}

        host = os.getenv("COMFYUI_PRIMARY", "http://100.112.87.8:8188").rstrip("/")
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

                shot_record = {
                    "id": record_id,
                    "campaign_id": campaign_id,
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
                    yield {"type": "memory", "shot_id": shot["shot_id"], "text": f"Audit {shot_record['audit_status']} ({score:.1f})"}

        yield {"type": "done", "text": f"Campaign complete. {rendered_count} shots processed."}
