import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from core.bridge.runtime_config import get_raw_config
from core.dispatch.comfy_client import ComfyUIClient


class HermesVideoService:
    def __init__(
        self,
        *,
        media_videos: Path,
        active_campaign_getter: Callable[[], str],
        find_shot: Callable[[str], Optional[Dict[str, Any]]],
        resolve_image_path: Callable[[str], Optional[Path]],
        workflow_file_for_id: Callable[[str], Optional[Path]],
    ) -> None:
        self.media_videos = media_videos
        self.active_campaign_getter = active_campaign_getter
        self.find_shot = find_shot
        self.resolve_image_path = resolve_image_path
        self.workflow_file_for_id = workflow_file_for_id

    async def process(
        self,
        *,
        shot_ids: List[str],
        workflow_id: str,
        duration: int = 4,
        fps: int = 24,
        prompt: str = "",
        min_audit_score: float = 0.85,
        min_audit_confidence: float = 0.70,
        require_audit_pass: bool = True,
        allow_failed_override: bool = False,
    ) -> Dict[str, Any]:
        if not shot_ids:
            return {"status": "error", "error": "shot_ids_required"}
        if not workflow_id:
            return {"status": "error", "error": "workflow_id_required"}

        wf = self.workflow_file_for_id(workflow_id)
        if not wf:
            return {"status": "error", "error": f"workflow_missing:{workflow_id}"}

        cfg = get_raw_config()
        host = (
            os.getenv("COMFYUI_PRIMARY", "")
            or str(cfg.get("COMFYUI_PRIMARY", ""))
            or "http://localhost:8188"
        ).rstrip("/")
        client = ComfyUIClient(host)
        campaign_id = (self.active_campaign_getter() or "video_batch").strip() or "video_batch"
        output_dir = self.media_videos / campaign_id
        output_dir.mkdir(parents=True, exist_ok=True)

        results: List[Dict[str, Any]] = []
        for sid in shot_ids:
            shot = self.find_shot(str(sid))
            if not shot:
                results.append({"shot_id": sid, "status": "error", "error": "shot_not_found"})
                continue

            verdict = self._evaluate_video_eligibility(
                shot,
                min_audit_score=min_audit_score,
                min_audit_confidence=min_audit_confidence,
                require_audit_pass=require_audit_pass,
                allow_failed_override=allow_failed_override,
            )
            if not verdict["eligible"]:
                results.append(
                    {
                        "shot_id": sid,
                        "status": "blocked",
                        "error": "blocked_for_video",
                        "reasons": verdict["reasons"],
                        "workflow_id": workflow_id,
                    }
                )
                continue

            image_path = ""
            if shot.get("image_path"):
                image_path = str(shot.get("image_path"))
            elif shot.get("image_url"):
                p = self.resolve_image_path(str(shot.get("image_url") or ""))
                if p:
                    image_path = str(p)
            if not image_path:
                results.append({"shot_id": sid, "status": "error", "error": "image_missing"})
                continue

            prompt_text = (prompt or "").strip() or str(
                shot.get("compiled_prompt") or shot.get("prompt") or shot.get("campaign_brief") or ""
            )
            if duration:
                prompt_text = f"{prompt_text}\n\nvideo_duration_seconds={int(duration)}"
            if fps:
                prompt_text = f"{prompt_text}\nvideo_fps={int(fps)}"

            submit = await client.submit_prompt_for_shot(
                shot_id=f"{sid}__video",
                prompt=prompt_text,
                workflow_path=str(wf),
                output_dir=str(output_dir),
                image_path=image_path,
                wait_for_output=False,
            )
            if submit.get("status") != "success":
                results.append(
                    {
                        "shot_id": sid,
                        "status": "error",
                        "error": submit.get("error", "submit_failed"),
                        "workflow_id": workflow_id,
                    }
                )
                continue
            results.append(
                {
                    "shot_id": sid,
                    "status": "ok",
                    "workflow_id": workflow_id,
                    "prompt_id": submit.get("prompt_id"),
                    "seed": submit.get("seed"),
                    "queued": True,
                }
            )

        return {
            "status": "ok",
            "workflow_id": workflow_id,
            "requested": len(shot_ids),
            "results": results,
            "output_dir": str(output_dir),
        }

    @staticmethod
    def _evaluate_video_eligibility(
        shot: Dict[str, Any],
        *,
        min_audit_score: float,
        min_audit_confidence: float,
        require_audit_pass: bool,
        allow_failed_override: bool,
    ) -> Dict[str, Any]:
        reasons: List[str] = []
        audit_status = str(shot.get("audit_status", "") or "").strip().lower()
        score = float(shot.get("audit_score", 0) or 0)
        confidence = float(shot.get("audit_confidence", 0) or 0)
        issues = [str(x) for x in (shot.get("audit_issues") or [])]
        critical = [str(x) for x in (shot.get("audit_critical_failures") or [])]
        merged = " ".join([*issues, *critical]).lower()
        hard_fail_terms = (
            "extra fingers", "extra limbs", "deformed", "dog head", "broken face",
            "identity mismatch", "wrong identity", "reflection contradiction", "mirror contradiction",
        )
        has_hard_fail = any(t in merged for t in hard_fail_terms)
        if has_hard_fail:
            reasons.append("hard_fail_visual")
        if require_audit_pass and not audit_status:
            reasons.append("audit_missing")
        if require_audit_pass and audit_status != "pass":
            reasons.append("audit_not_passed")
        if score < min_audit_score:
            reasons.append("score_below_threshold")
        if confidence < min_audit_confidence:
            reasons.append("confidence_below_threshold")
        has_soft_failures = len(reasons) > 0 and not has_hard_fail
        eligible = (len(reasons) == 0) or (bool(allow_failed_override) and has_soft_failures)
        return {"eligible": eligible, "reasons": reasons, "has_hard_fail": has_hard_fail}
