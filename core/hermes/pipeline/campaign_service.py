import asyncio
import hashlib
import json
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
from core.hermes.platform_skills import (
    apply_viral_hook_remediation_to_first_shot,
    detect_platform_skill,
    enrich_brief_with_platform,
    review_flags_low_watch_time,
)

from .director_service import KimiDirectorService
from .profile_cli import HermesProfileCLI
from .role_skill_mapper import role_skill_scope
from .state_machine import transition_shot


@dataclass
class CampaignRequest:
    brief: str
    bible_path: str = ""
    length: str = ""
    workflow_ids: Optional[List[str]] = None
    identity_pack: Optional[Dict[str, Any]] = None
    campaign_id: str = ""
    append_to_campaign: bool = False
    platform_mode: str = "auto"
    series_continuity: Optional[bool] = None


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
        get_hermes_bridge: Optional[Callable[[], Any]] = None,
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
        self.get_hermes_bridge = get_hermes_bridge
        self.director = KimiDirectorService()
        self.profile_cli = HermesProfileCLI()
        self._detached_tasks: set[asyncio.Task[Any]] = set()

    def _exchange_path(self, campaign_id: str) -> Path:
        return self.media_images / campaign_id / "_agent_exchanges.json"

    def _record_agent_exchange(self, campaign_id: str, exchange: Optional[Dict[str, Any]]) -> None:
        if not isinstance(exchange, dict) or not campaign_id:
            return
        entry = dict(exchange)
        entry["timestamp"] = self.now_iso()
        entry["campaign_id"] = campaign_id
        self.campaigns.setdefault(campaign_id, {}).setdefault("agent_exchanges", []).append(entry)
        path = self._exchange_path(campaign_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            if not isinstance(existing, list):
                existing = []
        except Exception:
            existing = []
        existing.append(entry)
        tmp = path.parent / f".{path.name}.tmp"
        tmp.write_text(json.dumps(existing, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(path)

    async def _build_auto_video_prompt(self, shot_record: Dict[str, Any]) -> str:
        """
        Build an LTX-oriented video prompt from the first-frame prompt/context.
        Profile CLI (compiler) is required. No production placeholder prompt is emitted.
        """
        compiled = str(shot_record.get("compiled_prompt") or shot_record.get("prompt") or "").strip()
        visual = str(shot_record.get("raw_kimi_prompt") or "").strip()
        rationale = str(shot_record.get("kimi_rationale") or "").strip()
        base = compiled or visual or "cinematic first frame with coherent motion"

        task = {
            "task": "ltx23_first_frame_to_video_prompt",
            "standard": "ltx23-prompting-workflow",
            "shot_id": shot_record.get("shot_id", ""),
            "workflow_id": shot_record.get("workflow_id", ""),
            "first_frame_prompt": base,
            "visual_brief": visual,
            "rationale": rationale,
            "skills_used": shot_record.get("skills_used", []),
            "instructions": (
                "Return JSON only with key 'video_prompt'. "
                "Prompt must be LTX2.3-oriented, preserve identity/geometry, "
                "and include temporal motion guidance for a 4-6s clip."
            ),
        }
        out = await self.profile_cli.run_json("compiler", task)
        if isinstance(out, dict):
            vp = str(out.get("video_prompt") or out.get("prompt") or "").strip()
            if vp:
                return vp

        return ""

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

    def _write_campaign_manifest(
        self,
        campaign_id: str,
        brief: str,
        workflow_ids: List[str],
        identity_pack: Optional[Dict[str, Any]] = None,
        platform_skill: Optional[Dict[str, Any]] = None,
    ) -> None:
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
            if identity_pack:
                manifest["identity_pack"] = identity_pack
            if platform_skill:
                manifest["platform_skill"] = platform_skill
            (folder / "_campaign.json").write_text(
                json.dumps(manifest, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
        except Exception:
            # Non-fatal metadata write.
            return

    def _campaign_exists(self, campaign_id: str) -> bool:
        if not campaign_id:
            return False
        if campaign_id in self.campaigns:
            return True
        if (self.media_images / campaign_id).exists():
            return True
        return any(str(s.get("campaign_id") or "") == campaign_id for s in self.shots_store)

    def _load_campaign_manifest(self, campaign_id: str) -> Dict[str, Any]:
        if not campaign_id:
            return {}
        path = self.media_images / campaign_id / "_campaign.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
        return {}

    def _persist_media_shot_metadata(self, shot_record: Dict[str, Any]) -> None:
        image_path = str(shot_record.get("image_path") or "").strip()
        if not image_path:
            return
        path = Path(image_path)
        if not path.exists():
            return
        fields = {
            "audit_status",
            "audit_score",
            "audit_issues",
            "audit_model_score",
            "audit_checks_score",
            "audit_confidence",
            "audit_model_passed",
            "audit_final_passed",
            "audit_checks",
            "audit_critical_failures",
            "audit_noncritical_issues",
            "audit_decision_reasons",
            "audit_raw_response",
            "audit_timestamp",
            "audit_model",
            "audit_error",
            "retry_of",
            "parent_shot_id",
            "remediation_reason",
            "remediated_prompt",
            "original_compiled_prompt",
            "remediation_model",
            "profile_used",
            "profile_backend",
            "skills_scope_role",
            "skills_scope_patterns",
            "skills_scope_version",
            "video_prompt",
            "video_prompt_source",
            "negative_prompt",
            "workflow_profile",
            "model_standard_name",
            "model_standard_version",
            "model_standard_source",
            "model_standard_rules",
            "sections",
            "kimi_plan",
            "kimi_rationale",
            "platform_skill",
            "platform_id",
            "platform_constraints",
            "viral_hook_remediated",
        }
        metadata_path = path.parent / "_shot_metadata.json"
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        existing = metadata.get(path.stem)
        if not isinstance(existing, dict):
            existing = {}
        for key in fields:
            if key in shot_record:
                existing[key] = shot_record.get(key)
        existing["updated_at"] = self.now_iso()
        metadata[path.stem] = existing
        tmp = path.parent / "._shot_metadata.json.tmp"
        tmp.write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(metadata_path)

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
        requested_id = (req.campaign_id or "").strip()
        append_requested = bool(req.append_to_campaign)
        if append_requested and not requested_id:
            yield {"type": "error", "text": "Append requested but no campaign_id was selected."}
            yield {"type": "done", "text": "Campaign stopped: append target missing."}
            return
        if append_requested and not self._campaign_exists(requested_id):
            yield {"type": "error", "text": f"Append target not found: {requested_id}"}
            yield {"type": "done", "text": "Campaign stopped: append target missing."}
            return

        can_append = bool(append_requested and requested_id)
        campaign_id = requested_id if can_append else self._build_campaign_id(req.brief)
        self.active_campaign_setter(campaign_id)
        workflow_ids = req.workflow_ids or ["01_flux2_text_to_image"]
        platform_skill = detect_platform_skill(
            req.brief,
            requested_mode=req.platform_mode or "auto",
            series_continuity=req.series_continuity,
        )
        platform_brief = enrich_brief_with_platform(req.brief, platform_skill)
        if can_append:
            existing = self.campaigns.get(campaign_id, {}) if isinstance(self.campaigns.get(campaign_id, {}), dict) else {}
            manifest = self._load_campaign_manifest(campaign_id)
            existing_workflows = existing.get("workflow_ids", []) if isinstance(existing.get("workflow_ids", []), list) else []
            if not existing_workflows and isinstance(manifest.get("workflow_ids"), list):
                existing_workflows = manifest.get("workflow_ids", [])
            merged_workflows = list(dict.fromkeys([*existing_workflows, *workflow_ids]))
            self.campaigns[campaign_id] = {
                **existing,
                "brief": req.brief or str(existing.get("brief", "") or manifest.get("brief", "") or ""),
                "started_at": str(existing.get("started_at", "") or manifest.get("started_at", "") or self.now_iso()),
                "updated_at": self.now_iso(),
                "workflow_ids": merged_workflows,
                "identity_pack": req.identity_pack or existing.get("identity_pack", {}) or manifest.get("identity_pack", {}) or {},
                "platform_skill": platform_skill if platform_skill.get("active") else existing.get("platform_skill", {}) or manifest.get("platform_skill", {}) or {},
            }
            workflow_ids = merged_workflows
        else:
            self.campaigns[campaign_id] = {
                "brief": req.brief,
                "started_at": self.now_iso(),
                "workflow_ids": workflow_ids,
                "identity_pack": req.identity_pack or {},
                "platform_skill": platform_skill if platform_skill.get("active") else {},
            }
        self._write_campaign_manifest(campaign_id, req.brief, workflow_ids, req.identity_pack, platform_skill)
        pipeline_t0 = time.perf_counter()

        def elapsed_ms() -> int:
            return int((time.perf_counter() - pipeline_t0) * 1000)

        yield {"type": "pipeline_timing", "stage": "backend_stream_open", "elapsed_ms": elapsed_ms()}
        yield {"type": "profile", "profile_color_key": "profile_director_kimi", "text": "Kimi / Director Planner online"}
        yield {"type": "profile", "profile_color_key": "profile_critic_kimi", "text": "Kimi / Coverage Critic online"}
        yield {"type": "profile", "profile_color_key": "profile_compiler_lmstudio", "text": "Hermes / Prompt Compiler online"}
        yield {"type": "profile", "profile_color_key": "profile_continuity_lmstudio", "text": "Hermes / Continuity Guard online"}
        yield {"type": "profile", "profile_color_key": "profile_remediation_lmstudio", "text": "Hermes / Remediation Reprompter online"}
        yield {"type": "profile", "profile_color_key": "profile_audit_kimi", "text": "Kimi / Audit Judge online"}
        if platform_skill.get("active"):
            yield {
                "type": "platform_skill",
                "campaign_id": campaign_id,
                "platform": platform_skill,
                "text": platform_skill.get("summary", "Platform skill active."),
            }

        # If appending to an existing campaign, continue shot numbering.
        shot_index_offset = 0
        if can_append:
            max_seq = 0
            for s in self.shots_store:
                if str(s.get("campaign_id") or "") != campaign_id:
                    continue
                sid = str(s.get("shot_id") or "")
                m = re.match(r"SHOT_(\d+)$", sid)
                if m:
                    try:
                        max_seq = max(max_seq, int(m.group(1)))
                    except Exception:
                        pass
                try:
                    seq = int(s.get("sequence") or 0)
                    if seq > 0:
                        max_seq = max(max_seq, seq)
                except Exception:
                    pass
            shot_index_offset = max_seq
        bible_text = self._resolve_bible_text(req.bible_path)

        target_shots = self.director.requested_shot_count(req.brief, req.length)
        intake_task = {
            "task": "campaign_intake",
            "campaign_id": campaign_id,
            "brief": platform_brief,
            "length": req.length or "unspecified",
            "target_shots": target_shots,
            "workflow_ids": workflow_ids,
            "identity_pack": req.identity_pack or {},
            "platform_skill": platform_skill,
            "world_bible_excerpt": bible_text[:4000] if bible_text else "none",
            "required_output_schema": {
                "director_brief": "string",
                "visual_strategy": "string",
                "continuity_priorities": ["string"],
                "render_risks": ["string"],
                "must_keep": ["string"],
            },
        }
        intake_t0 = time.perf_counter()
        yield {"type": "profile", "profile_color_key": "profile_compiler_lmstudio", "text": "Hermes / Campaign Intake starting."}
        hermes_intake = await self.profile_cli.run_json("director", intake_task)
        if not isinstance(hermes_intake, dict):
            detail = str(getattr(self.profile_cli, "last_error", "") or "unknown").strip()
            yield {
                "type": "error",
                "text": f"Campaign stopped: Hermes campaign intake failed before Kimi planning. detail={detail[:500]}",
            }
            yield {"type": "done", "text": "Campaign stopped: Hermes intake unavailable."}
            return
        self._record_agent_exchange(campaign_id, hermes_intake.get("__exchange"))
        self.campaigns[campaign_id]["hermes_intake"] = {
            k: v for k, v in hermes_intake.items() if not str(k).startswith("__")
        }
        yield {
            "type": "pipeline_timing",
            "stage": "hermes_campaign_intake",
            "elapsed_ms": elapsed_ms(),
            "duration_ms": int((time.perf_counter() - intake_t0) * 1000),
        }
        yield {"type": "profile", "profile_color_key": "profile_compiler_lmstudio", "text": "Hermes / Campaign Intake complete."}

        planning_brief = platform_brief
        intake_context = json.dumps(self.campaigns[campaign_id]["hermes_intake"], ensure_ascii=True)
        if intake_context and intake_context != "{}":
            planning_brief = f"{platform_brief}\n\nHermes campaign intake:\n{intake_context[:4000]}"

        yield {"type": "kimi", "text": "Generating shot list..."}
        use_fallback = os.getenv("FORGE_DEV_FALLBACK", "false").lower() == "true"

        kimi_plan_t0 = time.perf_counter()
        try:
            plan = await self.director.request_plan(
                planning_brief,
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
        self._record_agent_exchange(campaign_id, plan.get("__exchange"))
        yield {
            "type": "pipeline_timing",
            "stage": "kimi_director_plan",
            "elapsed_ms": elapsed_ms(),
            "duration_ms": int((time.perf_counter() - kimi_plan_t0) * 1000),
        }
        yield {"type": "kimi_raw", "campaign_id": campaign_id, "text": raw_content}

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
                    brief=planning_brief,
                    campaign_id=campaign_id,
                    existing_shots=kimi_shots,
                    target_shots=target_shots,
                    bible_text=bible_text,
                    length=req.length,
                )
                top_up_raw = top_up.get("__raw_content", "")
                self._record_agent_exchange(campaign_id, top_up.get("__exchange"))
                if top_up_raw:
                    raw_content = f"{raw_content}\n\n---TOP_UP---\n{top_up_raw}"
                    self.campaigns[campaign_id]["kimi_raw_response"] = raw_content
                    yield {"type": "kimi_raw", "campaign_id": campaign_id, "text": top_up_raw}
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
            review_t0 = time.perf_counter()
            review = await self.director.self_check_plan(planning_brief, campaign_id, kimi_shots)
            self.campaigns[campaign_id]["kimi_review"] = review
            self._record_agent_exchange(campaign_id, review.get("__exchange"))
            yield {
                "type": "pipeline_timing",
                "stage": "kimi_self_check",
                "elapsed_ms": elapsed_ms(),
                "duration_ms": int((time.perf_counter() - review_t0) * 1000),
            }
            yield {"type": "profile", "profile_color_key": "profile_critic_kimi", "text": "Kimi / Coverage Critic completed review."}
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

            needs_revision = False
            if isinstance(review, dict):
                status = str(review.get("status") or "").strip().lower()
                needs_revision = status in {"warn", "fail"} or bool(
                    review.get("coverage_gaps") or review.get("continuity_risks") or review.get("renderability_risks")
                )
            if platform_skill.get("active") and review_flags_low_watch_time(review):
                if apply_viral_hook_remediation_to_first_shot(kimi_shots):
                    self.campaigns[campaign_id]["viral_hook_remediation_applied"] = True
                    yield {
                        "type": "remediation",
                        "campaign_id": campaign_id,
                        "text": "TikTok hook remediation applied to the first shot for low watch-time risk.",
                    }
            if needs_revision:
                yield {"type": "kimi", "text": "Director revision pass running..."}
                try:
                    revision_t0 = time.perf_counter()
                    revised = await self.director.revise_plan(
                        brief=planning_brief,
                        campaign_id=campaign_id,
                        normalized_shots=kimi_shots,
                        review=review,
                        target_shots=target_shots,
                        bible_text=bible_text,
                        length=req.length,
                    )
                    yield {
                        "type": "pipeline_timing",
                        "stage": "kimi_director_revision",
                        "elapsed_ms": elapsed_ms(),
                        "duration_ms": int((time.perf_counter() - revision_t0) * 1000),
                    }
                    revised_raw = revised.get("__raw_content", "")
                    self._record_agent_exchange(campaign_id, revised.get("__exchange"))
                    if revised_raw:
                        self.campaigns[campaign_id]["kimi_revision_raw_response"] = revised_raw
                        yield {"type": "kimi_raw", "campaign_id": campaign_id, "text": revised_raw}
                    revised_shots = self.director.normalize_shots(revised, campaign_id)
                    if len(revised_shots) >= len(kimi_shots):
                        kimi_shots = revised_shots
                        self.campaigns[campaign_id]["kimi_revision_applied"] = True
                        yield {"type": "kimi", "text": f"Director revision applied: {len(kimi_shots)} shots"}
                    else:
                        self.campaigns[campaign_id]["kimi_revision_applied"] = False
                        yield {
                            "type": "warning",
                            "text": f"Director revision returned fewer shots ({len(revised_shots)}); keeping prior plan ({len(kimi_shots)}).",
                        }
                except Exception as e:
                    self.campaigns[campaign_id]["kimi_revision_applied"] = False
                    yield {"type": "warning", "text": f"Director revision unavailable: {self._exc_reason(e)}"}
        except Exception as e:
            if os.getenv("FORGE_KIMI_REQUIRE_SELF_CHECK", "true").lower() != "false":
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
        ).rstrip("/")
        if not host:
            yield {"type": "error", "text": "Campaign stopped: COMFYUI_PRIMARY is not configured."}
            yield {"type": "done", "text": "Campaign stopped before Spark dispatch."}
            return
        comfy = ComfyUIClient(host)
        rendered_count = 0
        source = "fallback" if use_fallback else "campaign"

        for i, shot in enumerate(kimi_shots, start=1):
            if self.is_cancelled():
                yield {"type": "error", "text": "Campaign cancelled by user."}
                break
            effective_shot = dict(shot)
            if shot_index_offset > 0:
                n = shot_index_offset + i
                effective_shot["shot_id"] = f"SHOT_{n:03d}"
                effective_shot["sequence"] = n
            for workflow_id in workflow_ids:
                if self.is_cancelled():
                    break

                record_id = f"{campaign_id}__{effective_shot['shot_id']}__{workflow_id}"
                yield {"type": "hermes", "shot_id": effective_shot["shot_id"], "text": f"Writing prompt for {effective_shot['shot_id']}..."}

                compiler_scope = role_skill_scope("prompt_compiler")
                artifact = compile_prompt_artifact(
                    raw_concept=platform_brief,
                    workflow_id=workflow_id,
                    kimi_plan=effective_shot,
                    character_names=effective_shot.get("characters", []),
                    shot_meta={
                        "campaign_id": campaign_id,
                        "shot_id": effective_shot["shot_id"],
                        "sequence": effective_shot["sequence"],
                        "identity_pack": req.identity_pack or {},
                        "platform_skill": platform_skill,
                    },
                    role_key="prompt_compiler",
                    allowed_skill_patterns=compiler_scope.get("patterns", []),
                )
                # Hermes Prompt Compiler is required in production; no hidden local fallback.
                refinement_task = {
                    "task": "refine_compiled_prompt",
                    "workflow_id": workflow_id,
                    "campaign_id": campaign_id,
                    "shot_id": effective_shot["shot_id"],
                    "visual_brief": effective_shot.get("visual_brief", ""),
                    "constraints": effective_shot.get("constraints", ""),
                    "compiled_prompt": artifact.get("compiled_prompt", ""),
                    "negative_prompt": artifact.get("negative_prompt", ""),
                    "platform_skill": platform_skill,
                }
                refined = await self.profile_cli.run_json("compiler", refinement_task)
                if not isinstance(refined, dict):
                    yield {"type": "error", "shot_id": effective_shot["shot_id"], "text": "Campaign stopped: Hermes / Prompt Compiler unavailable."}
                    yield {"type": "done", "text": "Campaign stopped before Spark dispatch."}
                    return
                self._record_agent_exchange(campaign_id, refined.get("__exchange"))
                refined_prompt = str(refined.get("compiled_prompt") or refined.get("prompt") or "").strip()
                if not refined_prompt:
                    yield {"type": "error", "shot_id": effective_shot["shot_id"], "text": "Campaign stopped: Hermes / Prompt Compiler returned no compiled_prompt."}
                    yield {"type": "done", "text": "Campaign stopped before Spark dispatch."}
                    return
                artifact["compiled_prompt"] = refined_prompt
                refined_negative = str(refined.get("negative_prompt") or "").strip()
                if refined_negative:
                    artifact["negative_prompt"] = refined_negative
                yield {
                    "type": "profile",
                    "profile_color_key": "profile_compiler_lmstudio",
                    "shot_id": effective_shot["shot_id"],
                    "text": f"Hermes / Prompt Compiler refined {effective_shot['shot_id']}.",
                }
                yield {
                    "type": "compiler",
                    "shot_id": effective_shot["shot_id"],
                    "workflow_id": workflow_id,
                    "profile_name": artifact.get("profile_name"),
                    "model_standard_name": artifact.get("model_standard_name"),
                    "model_standard_version": artifact.get("model_standard_version"),
                    "skills_used": artifact.get("skills_used", []),
                    "text": (
                        f"profile={artifact.get('profile_name')} "
                        f"standard={artifact.get('model_standard_name')}@{artifact.get('model_standard_version')} "
                        f"skills={','.join(artifact.get('skills_used', [])) or 'none'} "
                        f"scope={','.join(compiler_scope.get('patterns', [])[:4]) or 'global'}"
                    ),
                }
                compiled_text = str(artifact.get("compiled_prompt", "") or "").strip()
                negative_prompt = str(artifact.get("negative_prompt", "") or "").strip()
                identity_negative = str(artifact.get("identity_negative_prompt", "") or "").strip()
                if identity_negative:
                    negative_prompt = ", ".join([x for x in [negative_prompt, identity_negative] if x])
                if compiled_text:
                    yield {
                        "type": "hermes",
                        "shot_id": effective_shot["shot_id"],
                        "text": f"Compiled prompt ({workflow_id}): {compiled_text}",
                    }

                shot_record = {
                    "id": record_id,
                    "campaign_id": campaign_id,
                    "campaign_brief": req.brief,
                    "platform_skill": platform_skill if platform_skill.get("active") else {},
                    "platform_id": platform_skill.get("id", "") if platform_skill.get("active") else "",
                    "platform_constraints": platform_skill.get("constraints", {}) if platform_skill.get("active") else {},
                    "shot_id": effective_shot["shot_id"],
                    "sequence": effective_shot["sequence"],
                    "workflow_id": workflow_id,
                    "state": "planned",
                    "status": "planned",
                    "seed": random.randint(100000, 999999),
                    "prompt": artifact.get("compiled_prompt", ""),
                    "compiled_prompt": artifact.get("compiled_prompt", ""),
                    "negative_prompt": negative_prompt,
                    "workflow_profile": artifact.get("profile_name", ""),
                    "skills_used": artifact.get("skills_used", []),
                    "skills_scope_role": "prompt_compiler",
                    "skills_scope_patterns": compiler_scope.get("patterns", []),
                    "skills_scope_version": compiler_scope.get("map_version", "unknown"),
                    "compiler_version": artifact.get("compiler_version", ""),
                    "model_standard_name": artifact.get("model_standard_name", ""),
                    "model_standard_version": artifact.get("model_standard_version", ""),
                    "model_standard_source": artifact.get("model_standard_source", ""),
                    "model_standard_rules": artifact.get("model_standard_rules", []),
                    "sections": artifact.get("sections", {}),
                    "kimi_plan": effective_shot,
                    "raw_kimi_prompt": effective_shot.get("visual_brief", ""),
                    "kimi_rationale": effective_shot.get("rationale", ""),
                    "kimi_constraints": effective_shot.get("constraints", ""),
                    "kimi_raw_response": raw_content,
                    "kimi_review_score": review.get("score") if isinstance(review, dict) else None,
                    "identity_pack": req.identity_pack or {},
                    "identity_type": str((req.identity_pack or {}).get("type", "") or ""),
                    "identity_name": str((req.identity_pack or {}).get("name", "") or ""),
                    "identity_score": None,
                    "identity_fail_reasons": [],
                    "audit_status": "",
                    "source": source,
                    "profile_used": "prompt_compiler",
                    "profile_backend": "lmstudio",
                    "created_at": self.now_iso(),
                }
                if os.getenv("FORGE_AUTO_VIDEO_PROMPT", "true").lower() == "true":
                    video_prompt = await self._build_auto_video_prompt(shot_record)
                    if video_prompt:
                        shot_record["video_prompt"] = video_prompt
                        shot_record["video_prompt_source"] = "auto_compiler"
                    else:
                        shot_record["video_prompt"] = ""
                        shot_record["video_prompt_source"] = ""
                self.shots_store.append(shot_record)
                self.record_event("shot_planned", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source)

                wf = self.workflow_file_for_id(workflow_id)
                if not wf:
                    transition_shot(shot_record, "final_fail")
                    yield {"type": "error", "shot_id": effective_shot["shot_id"], "text": f"Workflow not found: {workflow_id}"}
                    self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": "workflow_missing"})
                    continue

                yield {"type": "spark", "shot_id": effective_shot["shot_id"], "text": f"Dispatching {effective_shot['shot_id']} to ComfyUI..."}
                transition_shot(shot_record, "queued")
                self.record_event("render_attempt", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source)
                try:
                    submit = await comfy.submit_prompt_for_shot(
                        shot_id=record_id,
                        prompt=artifact.get("compiled_prompt", ""),
                        workflow_path=str(wf),
                        seed=shot_record["seed"],
                        output_dir=str(self.media_images / campaign_id),
                        width=(platform_skill.get("constraints") or {}).get("width") if platform_skill.get("active") else None,
                        height=(platform_skill.get("constraints") or {}).get("height") if platform_skill.get("active") else None,
                    )
                except Exception as e:
                    transition_shot(shot_record, "final_fail")
                    msg = f"submit_exception:{e}"
                    yield {"type": "error", "shot_id": effective_shot["shot_id"], "text": f"ComfyUI submission failed for {effective_shot['shot_id']}: {msg}"}
                    self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": msg})
                    continue
                if submit.get("status") != "success":
                    transition_shot(shot_record, "final_fail")
                    msg = submit.get("error", "ComfyUI submission failed")
                    yield {"type": "error", "shot_id": effective_shot["shot_id"], "text": f"ComfyUI submission failed for {effective_shot['shot_id']}: {msg}"}
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
                    try:
                        self._persist_media_shot_metadata(shot_record)
                    except Exception as e:
                        self.record_event(
                            "render_metadata_persist_failed",
                            shot_id=record_id,
                            campaign_id=campaign_id,
                            workflow_id=workflow_id,
                            source=source,
                            success=False,
                            extra={"reason": str(e)},
                        )
                yield {
                    "type": "spark",
                    "campaign_id": campaign_id,
                    "id": record_id,
                    "shot_id": effective_shot["shot_id"],
                    "status": "rendered" if image_path else "queued",
                    "prompt_id": prompt_id,
                    "image_url": shot_record.get("image_url", ""),
                    "text": f"{'Rendered and stored' if image_path else 'Queued'} {effective_shot['shot_id']} ({workflow_id})",
                }
                self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=True, extra={"prompt_id": prompt_id})

                if image_path:
                    transition_shot(shot_record, "audit_started")
                    self.record_event("audit_started", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source)
                    try:
                        audit = await self.audit_render(image_path, shot_record["compiled_prompt"], campaign_id)
                    except Exception as e:
                        transition_shot(shot_record, "final_fail")
                        self.record_event("audit_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": f"audit_exception:{e}"})
                        yield {"type": "error", "shot_id": effective_shot["shot_id"], "text": f"Audit failed for {effective_shot['shot_id']}: {e}"}
                        continue
                    score = float(audit.get("score", 0) or 0)
                    passed = bool(audit.get("passed", False))
                    shot_record["audit_model"] = os.getenv("KIMI_VISUAL_MODEL", os.getenv("LMSTUDIO_VISION_MODEL", "qwen3.6-35b-a3b"))
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
                    expected_traits = ((shot_record.get("identity_pack") or {}).get("identity_tokens") or []) if isinstance(shot_record.get("identity_pack"), dict) else []
                    shot_record["identity_expected_traits"] = expected_traits
                    detected_notes = []
                    detected_notes.extend([str(x) for x in (shot_record.get("audit_decision_reasons") or [])[:4]])
                    detected_notes.extend([str(x) for x in (shot_record.get("audit_issues") or [])[:4]])
                    shot_record["identity_detected_notes"] = detected_notes[:6]
                    if shot_record.get("identity_type"):
                        shot_record["identity_status"] = "pass" if passed else "fail"
                        shot_record["identity_score"] = score
                        shot_record["identity_fail_reasons"] = [] if passed else detected_notes[:4]
                    transition_shot(shot_record, "audited_pass" if passed else "audited_fail")
                    try:
                        self._persist_media_shot_metadata(shot_record)
                    except Exception as e:
                        self.record_event(
                            "audit_metadata_persist_failed",
                            shot_id=record_id,
                            campaign_id=campaign_id,
                            workflow_id=workflow_id,
                            source=source,
                            success=False,
                            extra={"reason": str(e)},
                        )
                        yield {
                            "type": "error",
                            "shot_id": effective_shot["shot_id"],
                            "text": f"Audit metadata persist failed for {effective_shot['shot_id']}: {e}",
                        }
                    self.record_event(
                        "audit_result",
                        shot_id=record_id,
                        campaign_id=campaign_id,
                        workflow_id=workflow_id,
                        source=source,
                        success=passed,
                        extra={
                            "audit_score": score,
                            "audit_model_score": shot_record.get("audit_model_score"),
                            "audit_checks_score": shot_record.get("audit_checks_score"),
                            "audit_issues": shot_record.get("audit_issues") or [],
                            "audit_critical_failures": shot_record.get("audit_critical_failures") or [],
                            "audit_noncritical_issues": shot_record.get("audit_noncritical_issues") or [],
                            "audit_decision_reasons": shot_record.get("audit_decision_reasons") or [],
                        },
                    )
                    if passed:
                        yield {"type": "memory", "shot_id": effective_shot["shot_id"], "text": f"Audit pass ({score:.1f})"}
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
                            "shot_id": effective_shot["shot_id"],
                            "text": f"Audit fail for {effective_shot['shot_id']} ({score:.1f}): {reason_text}",
                        }
                        yield {"type": "memory", "shot_id": effective_shot["shot_id"], "text": f"Audit fail ({score:.1f})"}
                        auto_remediate = os.getenv("FORGE_AUTO_REMEDIATE_ON_FAIL", "true").lower() == "true"
                        if auto_remediate and self.remediate_failed:
                            yield {"type": "hermes", "shot_id": effective_shot["shot_id"], "text": f"Auto-remediation queued for {effective_shot['shot_id']}..."}
                            try:
                                rem_task = asyncio.create_task(self.remediate_failed([record_id]))
                                self._detached_tasks.add(rem_task)
                                rem_task.add_done_callback(self._detached_tasks.discard)
                                try:
                                    rem = await asyncio.shield(rem_task)
                                except asyncio.CancelledError:
                                    self.record_event(
                                        "remediation_detached",
                                        shot_id=record_id,
                                        campaign_id=campaign_id,
                                        workflow_id=workflow_id,
                                        source=source,
                                        success=True,
                                        extra={"reason": "stream_cancelled_task_continues"},
                                    )
                                    raise
                                rlist = rem.get("results", []) if isinstance(rem, dict) else []
                                if rlist:
                                    r0 = rlist[0] or {}
                                    if r0.get("status") == "ok":
                                        yield {
                                            "type": "memory",
                                            "shot_id": effective_shot["shot_id"],
                                            "text": f"Auto-remediation complete: retry={r0.get('retry_shot_id', 'n/a')} status={r0.get('retry_audit_status', 'n/a')}",
                                        }
                                    else:
                                        yield {
                                            "type": "error",
                                            "shot_id": effective_shot["shot_id"],
                                            "text": f"Auto-remediation failed for {effective_shot['shot_id']}: {r0.get('reason', r0.get('status', 'unknown'))}",
                                        }
                                else:
                                    yield {"type": "warning", "shot_id": effective_shot["shot_id"], "text": f"Auto-remediation returned no result for {effective_shot['shot_id']}"}
                            except Exception as e:
                                yield {"type": "error", "shot_id": effective_shot["shot_id"], "text": f"Auto-remediation exception for {effective_shot['shot_id']}: {self._exc_reason(e)}"}

        yield {"type": "done", "text": f"Campaign complete. {rendered_count} shots processed."}
