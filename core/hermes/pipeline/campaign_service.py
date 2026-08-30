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
from core.dispatch.capability_router import CapabilityRouter
from core.prompts.prompt_compiler import compile_prompt_artifact
from core.prompts.prompt_standards import apply_model_prompt_standard, flux_dev_ignores_negative_prompts
from core.bridge.runtime_config import get_raw_config
from core.hermes.platform_skills import (
    apply_viral_hook_remediation_to_first_shot,
    detect_platform_skill,
    enrich_brief_with_platform,
    review_flags_low_watch_time,
)

from .director_service import DirectorService
from .profile_cli import HermesProfileCLI
from .role_skill_mapper import role_skill_scope
from .state_machine import transition_shot


@dataclass
class CampaignRequest:
    brief: str
    bible_path: str = ""
    length: str = ""
    target_shots: Optional[int] = None
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
        self.director = DirectorService()
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

    @staticmethod
    def _requires_full_body_prompt(prompt: str) -> bool:
        text = str(prompt or "").lower()
        return any(
            phrase in text
            for phrase in ("full-body", "full body", "full-length", "full length", "head-to-toe", "head to toe")
        )

    @classmethod
    def _enforce_full_body_generation_prompt(cls, prompt: str) -> str:
        base = str(prompt or "").strip()
        if not cls._requires_full_body_prompt(base):
            return base
        required = (
            "FULL-BODY FRAMING REQUIREMENT: compose as a pulled-back head-to-toe studio portrait. "
            "The full person must be visible from top of head to shoes, including both complete legs, ankles, shoes, and both feet. "
            "Leave visible studio floor below the shoes and clear padding above the head and below the feet; subject occupies about 70 percent of frame height. "
            "Do not crop at thighs, knees, shins, ankles, or feet. Avoid waist-up, knee-up, thigh-up, close portrait, and oversized subject framing."
        )
        if "FULL-BODY FRAMING REQUIREMENT:" in base:
            return base
        return f"{required} {base}".strip()

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

    def _write_queued_render_record(
        self,
        *,
        campaign_id: str,
        shot_record: Dict[str, Any],
        prompt_id: str,
        status: str = "queued",
    ) -> None:
        """Persist Comfy prompt IDs immediately so queued work survives restarts."""
        if not campaign_id or not prompt_id:
            return
        try:
            folder = self.media_images / campaign_id
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "_queued_renders.json"
            try:
                payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
                if not isinstance(payload, dict):
                    payload = {}
            except Exception:
                payload = {}
            record_id = str(shot_record.get("id") or shot_record.get("shot_id") or prompt_id)
            existing = payload.get(record_id)
            if not isinstance(existing, dict):
                existing = {}
            fields = [
                "id",
                "campaign_id",
                "shot_id",
                "sequence",
                "workflow_id",
                "state",
                "status",
                "seed",
                "prompt",
                "compiled_prompt",
                "negative_prompt",
                "raw_kimi_prompt",
                "visual_brief",
                "camera_direction",
                "lighting_direction",
                "video_prompt",
                "video_prompt_source",
                "platform_skill",
                "platform_id",
                "platform_constraints",
                "source",
            ]
            for key in fields:
                if key in shot_record:
                    existing[key] = shot_record.get(key)
            existing["id"] = record_id
            existing["campaign_id"] = campaign_id
            existing["prompt_id"] = prompt_id
            existing["status"] = status
            existing["state"] = "queued" if status == "queued" else status
            existing["updated_at"] = self.now_iso()
            payload[record_id] = existing
            tmp = folder / "._queued_renders.json.tmp"
            tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception:
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

    def _attach_rendered_image(self, shot_record: Dict[str, Any], image_path: str) -> None:
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
                shot_id=str(shot_record.get("id") or ""),
                campaign_id=str(shot_record.get("campaign_id") or ""),
                workflow_id=str(shot_record.get("workflow_id") or ""),
                source=str(shot_record.get("source") or ""),
                success=False,
                extra={"reason": str(e)},
            )

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

    @staticmethod
    def compile_concurrency(default: int = 3) -> int:
        """Bounded concurrency for Hermes prompt compile/refine (env: CINESMITH_COMPILE_CONCURRENCY)."""
        try:
            n = int(os.getenv("CINESMITH_COMPILE_CONCURRENCY", str(default)) or default)
        except Exception:
            n = default
        return max(1, min(n, 16))

    @staticmethod
    def format_shot_error(
        *,
        shot_id: str,
        stage: str,
        message: str,
        recoverable: bool = True,
        hint: str = "",
        workflow_id: str = "",
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        Structured per-shot error for campaign streaming UI.

        Compatible with existing clients: keeps type=error and text=... while
        adding shot_id, stage, message, recoverable, hint.
        """
        msg = str(message or "").strip() or "Shot failed"
        hint_text = str(hint or "").strip()
        text = msg if not hint_text or hint_text in msg else f"{msg} — {hint_text}"
        payload: Dict[str, Any] = {
            "type": "error",
            "shot_id": str(shot_id or ""),
            "stage": str(stage or "compile"),
            "message": msg,
            "recoverable": bool(recoverable),
            "hint": hint_text,
            "text": text,
        }
        if workflow_id:
            payload["workflow_id"] = str(workflow_id)
        for key, value in extra.items():
            if value is not None and key not in payload:
                payload[key] = value
        return payload

    async def _compile_one_unit(
        self,
        *,
        effective_shot: Dict[str, Any],
        workflow_id: str,
        campaign_id: str,
        platform_brief: str,
        platform_skill: Dict[str, Any],
        identity_pack: Optional[Dict[str, Any]],
        raw_content: str,
        review: Any,
        source: str,
    ) -> Dict[str, Any]:
        """
        Compile + Hermes-refine a single shot/workflow unit.

        Does not mutate shared campaign state (shots_store / exchange file);
        the caller applies successful results on the main stream coroutine.
        """
        events: List[Dict[str, Any]] = []
        shot_id = str(effective_shot.get("shot_id") or "")
        record_id = f"{campaign_id}__{shot_id}__{workflow_id}"
        events.append({
            "type": "hermes",
            "shot_id": shot_id,
            "text": f"Writing prompt for {shot_id}...",
        })

        compiler_scope = role_skill_scope("prompt_compiler")
        try:
            artifact = compile_prompt_artifact(
                raw_concept=platform_brief,
                workflow_id=workflow_id,
                kimi_plan=effective_shot,
                character_names=effective_shot.get("characters", []),
                shot_meta={
                    "campaign_id": campaign_id,
                    "shot_id": shot_id,
                    "sequence": effective_shot.get("sequence"),
                    "identity_pack": identity_pack or {},
                    "platform_skill": platform_skill,
                },
                role_key="prompt_compiler",
                allowed_skill_patterns=compiler_scope.get("patterns", []),
            )
        except Exception as e:
            err = self.format_shot_error(
                shot_id=shot_id,
                stage="compile",
                message=f"Prompt compile failed for {shot_id}: {self._exc_reason(e)}",
                recoverable=True,
                hint="Retry this shot after adjusting the brief, or re-run the campaign.",
                workflow_id=workflow_id,
            )
            events.append(err)
            return {
                "ok": False,
                "events": events,
                "error": err,
                "shot_id": shot_id,
                "workflow_id": workflow_id,
                "record_id": record_id,
            }

        suppress_negative_prompt = flux_dev_ignores_negative_prompts(
            workflow_id=workflow_id,
            model_family=str(artifact.get("model_family") or ""),
        )
        if suppress_negative_prompt:
            artifact["negative_prompt"] = ""
            artifact["identity_negative_prompt"] = ""

        refinement_task = {
            "task": "refine_compiled_prompt",
            "workflow_id": workflow_id,
            "campaign_id": campaign_id,
            "shot_id": shot_id,
            "visual_brief": effective_shot.get("visual_brief", ""),
            "constraints": effective_shot.get("constraints", ""),
            "compiled_prompt": artifact.get("compiled_prompt", ""),
            "negative_prompt": "" if suppress_negative_prompt else artifact.get("negative_prompt", ""),
            "platform_skill": platform_skill,
        }
        try:
            refined = await self.profile_cli.run_json("compiler", refinement_task)
        except Exception as e:
            err = self.format_shot_error(
                shot_id=shot_id,
                stage="refine",
                message=f"Hermes prompt refine failed for {shot_id}: {self._exc_reason(e)}",
                recoverable=True,
                hint="Check Settings → Hermes / LM Studio, then re-run failed shots.",
                workflow_id=workflow_id,
            )
            events.append(err)
            return {
                "ok": False,
                "events": events,
                "error": err,
                "shot_id": shot_id,
                "workflow_id": workflow_id,
                "record_id": record_id,
            }

        if not isinstance(refined, dict):
            err = self.format_shot_error(
                shot_id=shot_id,
                stage="refine",
                message=f"Hermes prompt compile unavailable for {shot_id}.",
                recoverable=True,
                hint="Check Settings → Hermes / LM Studio, then re-run failed shots.",
                workflow_id=workflow_id,
            )
            events.append(err)
            return {
                "ok": False,
                "events": events,
                "error": err,
                "shot_id": shot_id,
                "workflow_id": workflow_id,
                "record_id": record_id,
            }

        exchange = refined.get("__exchange")
        refined_prompt = str(refined.get("compiled_prompt") or refined.get("prompt") or "").strip()
        if not refined_prompt:
            err = self.format_shot_error(
                shot_id=shot_id,
                stage="refine",
                message=f"Hermes returned no compiled_prompt for {shot_id}.",
                recoverable=True,
                hint="Re-run the campaign or retry this shot after Hermes is responding with JSON prompts.",
                workflow_id=workflow_id,
            )
            events.append(err)
            return {
                "ok": False,
                "events": events,
                "error": err,
                "shot_id": shot_id,
                "workflow_id": workflow_id,
                "record_id": record_id,
                "exchange": exchange,
            }

        refined_prompt = self._enforce_full_body_generation_prompt(refined_prompt)
        refined_prompt, enforced_standard_skills = apply_model_prompt_standard(
            refined_prompt,
            workflow_id=workflow_id,
            model_family=str(artifact.get("model_family") or ""),
            render_type=str((artifact.get("sections") or {}).get("Render Type") or ""),
        )
        for standard_skill in enforced_standard_skills:
            if standard_skill and standard_skill not in artifact.get("skills_used", []):
                artifact.setdefault("skills_used", []).append(standard_skill)
        artifact["compiled_prompt"] = refined_prompt
        refined_negative = str(refined.get("negative_prompt") or "").strip()
        if suppress_negative_prompt:
            artifact["negative_prompt"] = ""
            artifact["identity_negative_prompt"] = ""
        elif refined_negative:
            artifact["negative_prompt"] = refined_negative

        events.append({
            "type": "profile",
            "profile_color_key": "profile_compiler_lmstudio",
            "shot_id": shot_id,
            "text": f"Hermes / Prompt Compiler refined {shot_id}.",
        })
        events.append({
            "type": "compiler",
            "shot_id": shot_id,
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
        })

        compiled_text = str(artifact.get("compiled_prompt", "") or "").strip()
        negative_prompt = str(artifact.get("negative_prompt", "") or "").strip()
        identity_negative = str(artifact.get("identity_negative_prompt", "") or "").strip()
        if suppress_negative_prompt:
            negative_prompt = ""
        elif identity_negative:
            negative_prompt = ", ".join([x for x in [negative_prompt, identity_negative] if x])
        if compiled_text:
            events.append({
                "type": "hermes",
                "shot_id": shot_id,
                "text": f"Compiled prompt ({workflow_id}): {compiled_text}",
            })

        shot_record: Dict[str, Any] = {
            "id": record_id,
            "campaign_id": campaign_id,
            "platform_skill": platform_skill if platform_skill.get("active") else {},
            "platform_id": platform_skill.get("id", "") if platform_skill.get("active") else "",
            "platform_constraints": platform_skill.get("constraints", {}) if platform_skill.get("active") else {},
            "shot_id": shot_id,
            "sequence": effective_shot.get("sequence"),
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
            "identity_pack": identity_pack or {},
            "identity_type": str((identity_pack or {}).get("type", "") or ""),
            "identity_name": str((identity_pack or {}).get("name", "") or ""),
            "identity_score": None,
            "identity_fail_reasons": [],
            "audit_status": "",
            "source": source,
            "profile_used": "prompt_compiler",
            "profile_backend": "lmstudio",
            "created_at": self.now_iso(),
        }
        # campaign_brief is set by caller with full req.brief to avoid capturing req here

        if os.getenv("CINESMITH_AUTO_VIDEO_PROMPT", "true").lower() == "true":
            try:
                video_prompt = await self._build_auto_video_prompt(shot_record)
            except Exception as e:
                events.append({
                    "type": "warning",
                    "shot_id": shot_id,
                    "text": f"Auto video prompt skipped for {shot_id}: {self._exc_reason(e)}",
                })
                video_prompt = ""
            if video_prompt:
                shot_record["video_prompt"] = video_prompt
                shot_record["video_prompt_source"] = "auto_compiler"
            else:
                shot_record["video_prompt"] = ""
                shot_record["video_prompt_source"] = ""

        return {
            "ok": True,
            "events": events,
            "shot_record": shot_record,
            "artifact": artifact,
            "exchange": exchange,
            "shot_id": shot_id,
            "workflow_id": workflow_id,
            "record_id": record_id,
            "prompt": str(artifact.get("compiled_prompt", "") or ""),
        }

    async def _iter_parallel_compile(
        self,
        jobs: List[Dict[str, Any]],
        *,
        results_out: List[Dict[str, Any]],
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run compile jobs with bounded concurrency; yield stream events as each finishes."""
        if not jobs:
            return
        concurrency = self.compile_concurrency()
        yield {
            "type": "hermes",
            "text": f"Compiling {len(jobs)} shot prompt(s) in parallel (concurrency={concurrency})...",
        }
        yield {
            "type": "pipeline_timing",
            "stage": "compile_parallel_start",
            "text": f"parallel_compile jobs={len(jobs)} concurrency={concurrency}",
            "job_count": len(jobs),
            "concurrency": concurrency,
        }

        sem = asyncio.Semaphore(concurrency)
        queue: asyncio.Queue = asyncio.Queue()

        async def _run(job: Dict[str, Any]) -> None:
            async with sem:
                if self.is_cancelled():
                    shot_id = str((job.get("effective_shot") or {}).get("shot_id") or "")
                    err = self.format_shot_error(
                        shot_id=shot_id,
                        stage="compile",
                        message=f"Compile cancelled for {shot_id or 'shot'}.",
                        recoverable=True,
                        hint="Re-run the campaign when ready.",
                        workflow_id=str(job.get("workflow_id") or ""),
                    )
                    await queue.put({
                        "ok": False,
                        "cancelled": True,
                        "events": [err],
                        "error": err,
                        "shot_id": shot_id,
                        "workflow_id": str(job.get("workflow_id") or ""),
                        "record_id": "",
                    })
                    return
                result = await self._compile_one_unit(
                    effective_shot=job["effective_shot"],
                    workflow_id=job["workflow_id"],
                    campaign_id=job["campaign_id"],
                    platform_brief=job["platform_brief"],
                    platform_skill=job["platform_skill"],
                    identity_pack=job.get("identity_pack"),
                    raw_content=job.get("raw_content") or "",
                    review=job.get("review"),
                    source=job.get("source") or "campaign",
                )
                await queue.put(result)

        tasks = [asyncio.create_task(_run(job)) for job in jobs]
        remaining = len(jobs)
        try:
            while remaining > 0:
                result = await queue.get()
                remaining -= 1
                for event in result.get("events") or []:
                    yield event
                results_out.append(result)
        finally:
            # Ensure workers are not left hanging if consumer stops early.
            for t in tasks:
                if not t.done():
                    t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        ok_count = sum(1 for r in results_out if r.get("ok"))
        fail_count = len(results_out) - ok_count
        yield {
            "type": "pipeline_timing",
            "stage": "compile_parallel_done",
            "text": f"parallel_compile done ok={ok_count} failed={fail_count}",
            "ok_count": ok_count,
            "failed_count": fail_count,
        }

    async def _audit_completed_shot(self, shot_record: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        record_id = str(shot_record.get("id") or "")
        campaign_id = str(shot_record.get("campaign_id") or "")
        workflow_id = str(shot_record.get("workflow_id") or "")
        source = str(shot_record.get("source") or "campaign")
        shot_id = str(shot_record.get("shot_id") or record_id)
        image_path = str(shot_record.get("image_path") or "")
        if not image_path:
            return

        transition_shot(shot_record, "audit_started")
        self.record_event("audit_started", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source)
        try:
            audit = await self.audit_render(image_path, shot_record["compiled_prompt"], campaign_id)
        except Exception as e:
            transition_shot(shot_record, "final_fail")
            self.record_event("audit_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": f"audit_exception:{e}"})
            yield {"type": "error", "shot_id": shot_id, "text": f"Audit failed for {shot_id}: {e}"}
            return

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
            yield {"type": "error", "shot_id": shot_id, "text": f"Audit metadata persist failed for {shot_id}: {e}"}

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
            yield {"type": "memory", "shot_id": shot_id, "text": f"Audit pass ({score:.1f})"}
            return

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
        yield {"type": "error", "shot_id": shot_id, "text": f"Audit fail for {shot_id} ({score:.1f}): {reason_text}"}
        yield {"type": "memory", "shot_id": shot_id, "text": f"Audit fail ({score:.1f})"}
        auto_remediate = os.getenv("CINESMITH_AUTO_REMEDIATE_ON_FAIL", "true").lower() == "true"
        if auto_remediate and self.remediate_failed:
            yield {"type": "hermes", "shot_id": shot_id, "text": f"Auto-remediation queued for {shot_id}..."}
            try:
                rem_task = asyncio.create_task(self.remediate_failed([record_id]))
                self._detached_tasks.add(rem_task)
                rem_task.add_done_callback(self._detached_tasks.discard)
                rem = await asyncio.shield(rem_task)
                rlist = rem.get("results", []) if isinstance(rem, dict) else []
                if rlist:
                    r0 = rlist[0] or {}
                    if r0.get("status") == "ok":
                        yield {"type": "memory", "shot_id": shot_id, "text": f"Auto-remediation complete: retry={r0.get('retry_shot_id', 'n/a')} status={r0.get('retry_audit_status', 'n/a')}"}
                    else:
                        yield {"type": "error", "shot_id": shot_id, "text": f"Auto-remediation failed for {shot_id}: {r0.get('reason', r0.get('status', 'unknown'))}"}
                else:
                    yield {"type": "warning", "shot_id": shot_id, "text": f"Auto-remediation returned no result for {shot_id}"}
            except Exception as e:
                yield {"type": "error", "shot_id": shot_id, "text": f"Auto-remediation exception for {shot_id}: {self._exc_reason(e)}"}

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

        director_backend = str(getattr(self.director, "backend", "") or "nvidia").strip().lower()
        director_provider = "LM Studio" if director_backend == "lmstudio" else "NVIDIA"
        director_profile_key = "profile_director_lmstudio" if director_backend == "lmstudio" else "profile_director_kimi"
        critic_profile_key = "profile_critic_lmstudio" if director_backend == "lmstudio" else "profile_critic_kimi"
        director_role = f"{director_provider} / Director Planner"
        critic_role = f"{director_provider} / Coverage Critic"

        yield {"type": "pipeline_timing", "stage": "backend_stream_open", "elapsed_ms": elapsed_ms()}
        yield {"type": "profile", "profile_color_key": director_profile_key, "text": f"{director_role} online"}
        yield {"type": "profile", "profile_color_key": critic_profile_key, "text": f"{critic_role} online"}
        yield {"type": "profile", "profile_color_key": "profile_compiler_lmstudio", "text": "Hermes / Prompt Compiler online"}
        yield {"type": "profile", "profile_color_key": "profile_continuity_lmstudio", "text": "Hermes / Continuity Guard online"}
        yield {"type": "profile", "profile_color_key": "profile_remediation_lmstudio", "text": "Hermes / Remediation Reprompter online"}
        yield {"type": "profile", "profile_color_key": "profile_audit_kimi", "text": "Vision / Audit Judge online"}
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

        target_shots = max(1, min(int(req.target_shots or self.director.requested_shot_count(req.brief, req.length)), 120))
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
                "text": f"Campaign stopped: Hermes campaign intake failed before {director_provider} planning. detail={detail[:500]}",
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

        yield {"type": "kimi", "profile_color_key": director_profile_key, "role_label": director_role, "text": "Generating shot list..."}
        use_fallback = os.getenv("CINESMITH_DEV_FALLBACK", "false").lower() == "true"

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
            yield {"type": "error", "text": f"{director_provider} shot generation failed: {reason}"}
            if not use_fallback:
                yield {"type": "done", "text": f"Campaign stopped: {director_provider} failure before Spark dispatch."}
                return
            plan = self.director.build_dev_fallback_plan(req.brief, campaign_id, target_shots=target_shots)
            yield {"type": "error", "text": "Falling back to local synthetic shot list (CINESMITH_DEV_FALLBACK=true)"}

        raw_content = plan.get("__raw_content", "")
        self.campaigns[campaign_id]["kimi_raw_response"] = raw_content
        self._record_agent_exchange(campaign_id, plan.get("__exchange"))
        yield {
            "type": "pipeline_timing",
            "stage": "kimi_director_plan",
            "elapsed_ms": elapsed_ms(),
            "duration_ms": int((time.perf_counter() - kimi_plan_t0) * 1000),
        }
        yield {"type": "kimi_raw", "campaign_id": campaign_id, "profile_color_key": director_profile_key, "role_label": director_role, "text": raw_content}

        try:
            kimi_shots = self.director.normalize_shots(plan, campaign_id)
        except Exception as e:
            yield {"type": "error", "text": f"{director_provider} plan parse failed: {e}"}
            yield {"type": "done", "text": f"Campaign stopped: invalid {director_provider} plan."}
            return

        if len(kimi_shots) < target_shots:
            missing = target_shots - len(kimi_shots)
            yield {"type": "kimi", "profile_color_key": director_profile_key, "role_label": director_role, "text": f"Director returned {len(kimi_shots)}/{target_shots} shots. Requesting {missing} additional shots..."}
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
                    yield {"type": "kimi_raw", "campaign_id": campaign_id, "profile_color_key": director_profile_key, "role_label": director_role, "text": top_up_raw}
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
                yield {"type": "error", "text": f"{director_provider} top-up failed: {e}"}

        if len(kimi_shots) < target_shots and not use_fallback:
            yield {
                "type": "error",
                "text": (
                    f"{director_provider} coverage incomplete: only {len(kimi_shots)} shots returned vs {target_shots} requested. "
                    "Campaign stopped before Spark."
                ),
            }
            yield {"type": "done", "text": f"Campaign stopped: incomplete {director_provider} shot plan."}
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
            yield {"type": "profile", "profile_color_key": critic_profile_key, "text": f"{critic_role} completed review."}
            yield {
                "type": "kimi_review",
                "campaign_id": campaign_id,
                "profile_color_key": critic_profile_key,
                "role_label": critic_role,
                "score": review.get("score"),
                "status": review.get("status"),
                "director_notes": review.get("director_notes", ""),
                "coverage_gaps": review.get("coverage_gaps", []),
            }
            min_score = int(os.getenv("CINESMITH_KIMI_MIN_DIRECTOR_SCORE", "45"))
            score = self.director.score_from_review(review)
            if score is not None and score < min_score and not use_fallback:
                yield {
                    "type": "error",
                    "text": f"{director_provider} director self-check score {score} below threshold {min_score}. Campaign stopped before Spark.",
                }
                yield {"type": "done", "text": f"Campaign stopped: {director_provider} self-check below threshold."}
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
                yield {"type": "kimi", "profile_color_key": director_profile_key, "role_label": director_role, "text": "Director revision pass running..."}
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
                        yield {"type": "kimi_raw", "campaign_id": campaign_id, "profile_color_key": director_profile_key, "role_label": director_role, "text": revised_raw}
                    revised_shots = self.director.normalize_shots(revised, campaign_id)
                    if len(revised_shots) >= len(kimi_shots):
                        kimi_shots = revised_shots
                        self.campaigns[campaign_id]["kimi_revision_applied"] = True
                        yield {"type": "kimi", "profile_color_key": director_profile_key, "role_label": director_role, "text": f"Director revision applied: {len(kimi_shots)} shots"}
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
            if os.getenv("CINESMITH_KIMI_REQUIRE_SELF_CHECK", "true").lower() != "false":
                yield {"type": "error", "text": f"{director_provider} self-check failed: {e}"}
                yield {"type": "done", "text": f"Campaign stopped: {director_provider} self-check unavailable."}
                return
            yield {"type": "warning", "text": f"{director_provider} self-check unavailable: {e}"}

        yield {"type": "kimi_plan", "campaign_id": campaign_id, "profile_color_key": director_profile_key, "role_label": director_role, "count": len(kimi_shots), "target_shots": target_shots, "shots": kimi_shots}
        yield {"type": "kimi", "profile_color_key": director_profile_key, "role_label": director_role, "text": f"Shot list ready: {len(kimi_shots)} shots (requested {target_shots})"}

        cfg = get_raw_config()
        try:
            host = await CapabilityRouter(cfg).host_for("stills")
        except Exception:
            host = ""
        if not host:
            host = (
                os.getenv("COMFYUI_STILLS_A", "")
                or os.getenv("COMFYUI_SECONDARY", "")
                or os.getenv("COMFYUI_PRIMARY", "")
                or str(cfg.get("COMFYUI_STILLS_A", "") or cfg.get("COMFYUI_SECONDARY", "") or cfg.get("COMFYUI_PRIMARY", ""))
            ).rstrip("/")
        if not host:
            yield {"type": "error", "text": "Campaign stopped: no stills host (set 3090 A/B or Spark in Connect)."}
            yield {"type": "done", "text": "Campaign stopped before Spark dispatch."}
            return
        comfy = ComfyUIClient(host)
        rendered_count = 0
        source = "fallback" if use_fallback else "campaign"
        pending_render_jobs: List[Dict[str, Any]] = []
        deferred_render_submissions: List[Dict[str, Any]] = []
        defer_render_submit = os.getenv("CINESMITH_DEFER_CAMPAIGN_RENDER_SUBMIT", "true").lower() != "false"

        # --- Parallel Hermes compile (bounded concurrency), then render queue ---
        compile_jobs: List[Dict[str, Any]] = []
        for i, shot in enumerate(kimi_shots, start=1):
            effective_shot = dict(shot)
            if shot_index_offset > 0:
                n = shot_index_offset + i
                effective_shot["shot_id"] = f"SHOT_{n:03d}"
                effective_shot["sequence"] = n
            for workflow_id in workflow_ids:
                compile_jobs.append({
                    "effective_shot": effective_shot,
                    "workflow_id": workflow_id,
                    "campaign_id": campaign_id,
                    "platform_brief": platform_brief,
                    "platform_skill": platform_skill,
                    "identity_pack": req.identity_pack or {},
                    "raw_content": raw_content,
                    "review": review,
                    "source": source,
                })

        compile_results: List[Dict[str, Any]] = []
        if self.is_cancelled():
            yield {"type": "error", "text": "Campaign cancelled by user."}
            yield {"type": "done", "text": "Campaign cancelled before compile."}
            return

        async for event in self._iter_parallel_compile(compile_jobs, results_out=compile_results):
            yield event
            if self.is_cancelled() and event.get("type") in ("error", "warning"):
                # Keep draining events so workers finish cleanly; stop after loop.
                pass

        if self.is_cancelled():
            yield {"type": "error", "text": "Campaign cancelled by user."}
            yield {"type": "done", "text": "Campaign cancelled during compile."}
            return

        compile_errors: List[Dict[str, Any]] = []
        successful_units: List[Dict[str, Any]] = []
        for result in compile_results:
            if result.get("ok"):
                successful_units.append(result)
            else:
                err = result.get("error")
                if isinstance(err, dict):
                    compile_errors.append(err)

        if compile_errors:
            yield {
                "type": "compile_errors",
                "errors": compile_errors,
                "failed_count": len(compile_errors),
                "ok_count": len(successful_units),
                "campaign_id": campaign_id,
                "text": (
                    f"{len(compile_errors)} shot compile(s) failed; "
                    f"{len(successful_units)} ready for Spark."
                ),
            }

        if not successful_units:
            yield self.format_shot_error(
                shot_id="",
                stage="compile",
                message="All shot compiles failed. Campaign stopped before Spark dispatch.",
                recoverable=True,
                hint="Fix Hermes / LM Studio in Settings, then re-run the campaign.",
            )
            yield {"type": "done", "text": "Campaign stopped: no prompts compiled."}
            return

        for result in successful_units:
            shot_record = dict(result.get("shot_record") or {})
            shot_record["campaign_brief"] = req.brief
            record_id = str(result.get("record_id") or shot_record.get("id") or "")
            workflow_id = str(result.get("workflow_id") or shot_record.get("workflow_id") or "")
            shot_id = str(result.get("shot_id") or shot_record.get("shot_id") or "")
            prompt_text = str(result.get("prompt") or shot_record.get("compiled_prompt") or "")
            exchange = result.get("exchange")
            if exchange:
                self._record_agent_exchange(campaign_id, exchange if isinstance(exchange, dict) else None)

            self.shots_store.append(shot_record)
            self.record_event(
                "shot_planned",
                shot_id=record_id,
                campaign_id=campaign_id,
                workflow_id=workflow_id,
                source=source,
            )

            wf = self.workflow_file_for_id(workflow_id)
            if not wf:
                transition_shot(shot_record, "final_fail")
                yield self.format_shot_error(
                    shot_id=shot_id,
                    stage="render",
                    message=f"Workflow not found: {workflow_id}",
                    recoverable=True,
                    hint="Select a valid image model (Flux2 / Klein) and re-run failed shots.",
                    workflow_id=workflow_id,
                )
                self.record_event(
                    "render_result",
                    shot_id=record_id,
                    campaign_id=campaign_id,
                    workflow_id=workflow_id,
                    source=source,
                    success=False,
                    extra={"reason": "workflow_missing"},
                )
                continue

            if defer_render_submit:
                deferred_render_submissions.append({
                    "record_id": record_id,
                    "shot_record": shot_record,
                    "shot_id": shot_id,
                    "workflow_id": workflow_id,
                    "workflow_path": str(wf),
                    "prompt": prompt_text,
                    "platform_skill": platform_skill,
                })
                yield {
                    "type": "spark",
                    "campaign_id": campaign_id,
                    "id": record_id,
                    "shot_id": shot_id,
                    "status": "compiled_pending_batch",
                    "image_url": "",
                    "text": f"Prepared {shot_id} ({workflow_id}) for batch ComfyUI queue",
                }
                continue

            # Immediate (non-deferred) render path — sequential ComfyUI submit
            yield {"type": "spark", "shot_id": shot_id, "text": f"Dispatching {shot_id} to ComfyUI..."}
            transition_shot(shot_record, "queued")
            self.record_event(
                "render_attempt",
                shot_id=record_id,
                campaign_id=campaign_id,
                workflow_id=workflow_id,
                source=source,
            )
            try:
                submit = await comfy.submit_prompt_for_shot(
                    shot_id=record_id,
                    prompt=prompt_text,
                    workflow_path=str(wf),
                    seed=shot_record["seed"],
                    output_dir=str(self.media_images / campaign_id),
                    width=(platform_skill.get("constraints") or {}).get("width") if platform_skill.get("active") else None,
                    height=(platform_skill.get("constraints") or {}).get("height") if platform_skill.get("active") else None,
                    wait_for_output=False,
                )
            except Exception as e:
                transition_shot(shot_record, "final_fail")
                msg = f"submit_exception:{e}"
                yield self.format_shot_error(
                    shot_id=shot_id,
                    stage="render",
                    message=f"ComfyUI submission failed for {shot_id}: {msg}",
                    recoverable=True,
                    hint="Check Spark / ComfyUI connectivity, then re-run failed shots.",
                    workflow_id=workflow_id,
                )
                self.record_event(
                    "render_result",
                    shot_id=record_id,
                    campaign_id=campaign_id,
                    workflow_id=workflow_id,
                    source=source,
                    success=False,
                    extra={"reason": msg},
                )
                continue
            if submit.get("status") != "success":
                transition_shot(shot_record, "final_fail")
                msg = submit.get("error", "ComfyUI submission failed")
                yield self.format_shot_error(
                    shot_id=shot_id,
                    stage="render",
                    message=f"ComfyUI submission failed for {shot_id}: {msg}",
                    recoverable=True,
                    hint="Check Spark / ComfyUI connectivity, then re-run failed shots.",
                    workflow_id=workflow_id,
                )
                self.record_event(
                    "render_result",
                    shot_id=record_id,
                    campaign_id=campaign_id,
                    workflow_id=workflow_id,
                    source=source,
                    success=False,
                    extra={"reason": msg},
                )
                continue

            if isinstance(submit.get("lora"), dict):
                shot_record["lora"] = submit["lora"]
                if submit["lora"].get("requested"):
                    lora_state = "applied" if submit["lora"].get("applied") else submit["lora"].get("reason", "not applied")
                    yield {
                        "type": "compiler",
                        "shot_id": shot_id,
                        "workflow_id": workflow_id,
                        "text": f"LoRA preset {submit['lora'].get('requested')}: {lora_state}",
                    }

            prompt_id = submit.get("prompt_id", "")
            saved = submit.get("saved_files", [])
            image_path = saved[0] if saved else ""
            shot_record["prompt_id"] = prompt_id
            if not image_path:
                self._write_queued_render_record(
                    campaign_id=campaign_id,
                    shot_record=shot_record,
                    prompt_id=str(prompt_id),
                    status="queued",
                )
                pending_render_jobs.append({
                    "record_id": record_id,
                    "shot_record": shot_record,
                    "shot_id": shot_id,
                    "workflow_id": workflow_id,
                    "prompt_id": prompt_id,
                    "output_dir": str(self.media_images / campaign_id),
                })
                yield {
                    "type": "spark",
                    "campaign_id": campaign_id,
                    "id": record_id,
                    "shot_id": shot_id,
                    "status": "queued",
                    "prompt_id": prompt_id,
                    "image_url": "",
                    "text": f"Queued {shot_id} ({workflow_id})",
                }
                self.record_event(
                    "render_queued",
                    shot_id=record_id,
                    campaign_id=campaign_id,
                    workflow_id=workflow_id,
                    source=source,
                    success=True,
                    extra={"prompt_id": prompt_id},
                )
                continue

            rendered_count += 1
            transition_shot(shot_record, "rendered")
            self._attach_rendered_image(shot_record, image_path)
            self._write_queued_render_record(
                campaign_id=campaign_id,
                shot_record=shot_record,
                prompt_id=str(prompt_id),
                status="rendered",
            )
            yield {
                "type": "spark",
                "campaign_id": campaign_id,
                "id": record_id,
                "shot_id": shot_id,
                "status": "rendered",
                "prompt_id": prompt_id,
                "image_url": shot_record.get("image_url", ""),
                "text": f"Rendered and stored {shot_id} ({workflow_id})",
            }
            self.record_event(
                "render_result",
                shot_id=record_id,
                campaign_id=campaign_id,
                workflow_id=workflow_id,
                source=source,
                success=True,
                extra={"prompt_id": prompt_id},
            )
            async for audit_event in self._audit_completed_shot(shot_record):
                yield audit_event

        if deferred_render_submissions:
            yield {"type": "spark", "text": f"Batch submitting {len(deferred_render_submissions)} compiled image render(s) to ComfyUI..."}
        for item in deferred_render_submissions:
            if self.is_cancelled():
                yield {"type": "error", "text": "Campaign cancelled before batch render submission finished."}
                break
            shot_record = item["shot_record"]
            record_id = str(item.get("record_id") or shot_record.get("id") or "")
            shot_id = str(item.get("shot_id") or shot_record.get("shot_id") or record_id)
            workflow_id = str(item.get("workflow_id") or shot_record.get("workflow_id") or "")
            platform_item = item.get("platform_skill") if isinstance(item.get("platform_skill"), dict) else {}

            yield {"type": "spark", "shot_id": shot_id, "text": f"Dispatching {shot_id} to ComfyUI batch..."}
            transition_shot(shot_record, "queued")
            self.record_event("render_attempt", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source)
            try:
                submit = await comfy.submit_prompt_for_shot(
                    shot_id=record_id,
                    prompt=str(item.get("prompt") or ""),
                    workflow_path=str(item.get("workflow_path") or ""),
                    seed=int(shot_record["seed"]),
                    output_dir=str(self.media_images / campaign_id),
                    width=(platform_item.get("constraints") or {}).get("width") if platform_item.get("active") else None,
                    height=(platform_item.get("constraints") or {}).get("height") if platform_item.get("active") else None,
                    wait_for_output=False,
                )
            except Exception as e:
                transition_shot(shot_record, "final_fail")
                msg = f"submit_exception:{e}"
                yield self.format_shot_error(
                    shot_id=shot_id,
                    stage="render",
                    message=f"ComfyUI submission failed for {shot_id}: {msg}",
                    recoverable=True,
                    hint="Check Spark / ComfyUI connectivity, then re-run failed shots.",
                    workflow_id=workflow_id,
                )
                self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": msg})
                continue
            if submit.get("status") != "success":
                transition_shot(shot_record, "final_fail")
                msg = submit.get("error", "ComfyUI submission failed")
                yield self.format_shot_error(
                    shot_id=shot_id,
                    stage="render",
                    message=f"ComfyUI submission failed for {shot_id}: {msg}",
                    recoverable=True,
                    hint="Check Spark / ComfyUI connectivity, then re-run failed shots.",
                    workflow_id=workflow_id,
                )
                self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": msg})
                continue

            if isinstance(submit.get("lora"), dict):
                shot_record["lora"] = submit["lora"]
                if submit["lora"].get("requested"):
                    lora_state = "applied" if submit["lora"].get("applied") else submit["lora"].get("reason", "not applied")
                    yield {
                        "type": "compiler",
                        "shot_id": shot_id,
                        "workflow_id": workflow_id,
                        "text": f"LoRA preset {submit['lora'].get('requested')}: {lora_state}",
                    }

            prompt_id = submit.get("prompt_id", "")
            saved = submit.get("saved_files", [])
            image_path = saved[0] if saved else ""
            shot_record["prompt_id"] = prompt_id
            if not image_path:
                self._write_queued_render_record(
                    campaign_id=campaign_id,
                    shot_record=shot_record,
                    prompt_id=str(prompt_id),
                    status="queued",
                )
                pending_render_jobs.append({
                    "record_id": record_id,
                    "shot_record": shot_record,
                    "shot_id": shot_id,
                    "workflow_id": workflow_id,
                    "prompt_id": prompt_id,
                    "output_dir": str(self.media_images / campaign_id),
                })
                yield {
                    "type": "spark",
                    "campaign_id": campaign_id,
                    "id": record_id,
                    "shot_id": shot_id,
                    "status": "queued",
                    "prompt_id": prompt_id,
                    "image_url": "",
                    "text": f"Queued {shot_id} ({workflow_id})",
                }
                self.record_event("render_queued", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=True, extra={"prompt_id": prompt_id})
                continue

            rendered_count += 1
            transition_shot(shot_record, "rendered")
            self._attach_rendered_image(shot_record, image_path)
            self._write_queued_render_record(
                campaign_id=campaign_id,
                shot_record=shot_record,
                prompt_id=str(prompt_id),
                status="rendered",
            )
            yield {
                "type": "spark",
                "campaign_id": campaign_id,
                "id": record_id,
                "shot_id": shot_id,
                "status": "rendered",
                "prompt_id": prompt_id,
                "image_url": shot_record.get("image_url", ""),
                "text": f"Rendered and stored {shot_id} ({workflow_id})",
            }
            self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=True, extra={"prompt_id": prompt_id})
            async for audit_event in self._audit_completed_shot(shot_record):
                yield audit_event

        if pending_render_jobs:
            yield {"type": "spark", "text": f"Polling {len(pending_render_jobs)} queued ComfyUI image render(s)..."}
        render_deadline = time.time() + max(21600, int(os.getenv("CINESMITH_RENDER_BATCH_WAIT_SEC", "21600") or "21600"))
        cancelled_while_polling = False
        while pending_render_jobs and time.time() < render_deadline:
            if self.is_cancelled():
                yield {"type": "error", "text": "Campaign cancelled while waiting for queued renders."}
                cancelled_while_polling = True
                break
            remaining: List[Dict[str, Any]] = []
            for pending in pending_render_jobs:
                shot_record = pending["shot_record"]
                prompt_id = str(pending.get("prompt_id") or "")
                workflow_id = str(pending.get("workflow_id") or shot_record.get("workflow_id") or "")
                record_id = str(pending.get("record_id") or shot_record.get("id") or "")
                shot_id = str(pending.get("shot_id") or shot_record.get("shot_id") or record_id)
                try:
                    saved = await comfy.download_outputs(prompt_id, str(pending.get("output_dir") or self.media_images / campaign_id))
                except Exception as e:
                    remaining.append(pending)
                    yield {"type": "warning", "shot_id": shot_id, "text": f"Render poll failed for {shot_id}: {self._exc_reason(e)}"}
                    continue
                if not saved:
                    remaining.append(pending)
                    continue
                image_path = saved[0]
                rendered_count += 1
                transition_shot(shot_record, "rendered")
                self._attach_rendered_image(shot_record, image_path)
                self._write_queued_render_record(
                    campaign_id=campaign_id,
                    shot_record=shot_record,
                    prompt_id=str(prompt_id),
                    status="rendered",
                )
                yield {
                    "type": "spark",
                    "campaign_id": campaign_id,
                    "id": record_id,
                    "shot_id": shot_id,
                    "status": "rendered",
                    "prompt_id": prompt_id,
                    "image_url": shot_record.get("image_url", ""),
                    "text": f"Rendered and stored {shot_id} ({workflow_id})",
                }
                self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=True, extra={"prompt_id": prompt_id})
                async for audit_event in self._audit_completed_shot(shot_record):
                    yield audit_event
            pending_render_jobs = remaining
            if pending_render_jobs:
                await asyncio.sleep(5)
        if pending_render_jobs:
            for pending in pending_render_jobs:
                shot_record = pending["shot_record"]
                record_id = str(pending.get("record_id") or shot_record.get("id") or "")
                workflow_id = str(pending.get("workflow_id") or shot_record.get("workflow_id") or "")
                shot_id = str(pending.get("shot_id") or shot_record.get("shot_id") or record_id)
                transition_shot(shot_record, "final_fail")
                reason = "render_cancelled" if cancelled_while_polling else "render_batch_timeout"
                text = (
                    f"Render cancelled before image output was available for {shot_id}."
                    if cancelled_while_polling
                    else f"Render timed out before image output was available for {shot_id}."
                )
                yield self.format_shot_error(
                    shot_id=shot_id,
                    stage="render",
                    message=text,
                    recoverable=True,
                    hint="Re-run the campaign or retry this shot once Spark is free.",
                    workflow_id=workflow_id,
                    reason=reason,
                )
                self.record_event("render_result", shot_id=record_id, campaign_id=campaign_id, workflow_id=workflow_id, source=source, success=False, extra={"reason": reason})

        done_bits = [f"Campaign complete. {rendered_count} shots processed."]
        if compile_errors:
            done_bits.append(f"{len(compile_errors)} compile failure(s) — see failed shots list to retry.")
        yield {"type": "done", "text": " ".join(done_bits), "compile_failed": len(compile_errors), "compile_ok": len(successful_units)}
