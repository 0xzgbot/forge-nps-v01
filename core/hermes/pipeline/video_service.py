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
