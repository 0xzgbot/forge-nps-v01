"""Local Higgsfield-like adapter backed by Forge/ComfyUI.

This is an interoperability shim, not a Higgsfield API client. It mirrors the
publicly documented shape of Higgsfield-style creative MCP tools: submit async
job sets, poll status, browse style/motion presets, and keep character
reference records. Actual rendering is delegated to local ComfyUI workflows.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from core.dispatch.comfy_client import ComfyUIClient


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str, fallback: str = "asset") -> str:
    text = "".join(ch if ch.isalnum() else "_" for ch in (value or "").lower())
    text = "_".join(part for part in text.split("_") if part)
    return (text[:64] or fallback).strip("_")


def _parse_size(value: str, default: tuple[int, int] = (1696, 960)) -> tuple[int, int]:
    try:
        width_s, height_s = str(value or "").lower().split("x", 1)
        width = max(64, min(4096, int(width_s)))
        height = max(64, min(4096, int(height_s)))
        return width, height
    except Exception:
        return default


class LocalHiggsfieldAdapter:
    """Higgsfield-shaped local creative adapter.

    The adapter stores job-set manifests under the configured media root so
    dashboard calls and agent calls can poll the same results across restarts.
    """

    STYLE_PRESETS: List[Dict[str, Any]] = [
        {
            "id": "forge-commercial-product",
            "name": "Commercial Product Hero",
            "description": "Clean ecommerce product lighting, sharp packaging, controlled reflections.",
        },
        {
            "id": "forge-ugc-natural",
            "name": "UGC Natural",
            "description": "Handheld creator-style realism with practical light and casual framing.",
        },
        {
            "id": "forge-cinematic-premium",
            "name": "Cinematic Premium",
            "description": "High-end ad cinematography, shaped light, shallow depth, dramatic contrast.",
        },
        {
            "id": "forge-social-scrollstop",
            "name": "Social Scroll Stopper",
            "description": "Bold composition, immediate focal point, high readability for short-form feeds.",
        },
    ]

    MOTION_PRESETS: List[Dict[str, Any]] = [
        {
            "id": "subtle_push_in",
            "name": "Subtle Push In",
            "description": "Slow dolly toward subject, stable product/character identity.",
            "start_end_frame": False,
        },
        {
            "id": "handheld_ugc",
            "name": "Handheld UGC",
            "description": "Light phone-camera motion, natural creator cadence.",
            "start_end_frame": False,
        },
        {
            "id": "product_orbit",
            "name": "Product Orbit",
            "description": "Controlled parallax around a hero object with dimensional reveal.",
            "start_end_frame": False,
        },
        {
            "id": "before_after_transition",
            "name": "Before/After Transition",
            "description": "Start-to-end frame morph for transformation or comparison ads.",
            "start_end_frame": True,
        },
    ]

    def __init__(
        self,
        *,
        repo_root: Path,
        media_root: Path,
        media_images: Path,
        comfy_url: str,
        workflow_file_for_id: Callable[[str], Optional[Path]],
        resolve_image_path: Optional[Callable[[str], Optional[Path]]] = None,
    ) -> None:
        self.repo_root = repo_root
        self.media_root = media_root
        self.media_images = media_images
        self.comfy_url = (comfy_url or "http://localhost:8188").rstrip("/")
        self.workflow_file_for_id = workflow_file_for_id
        self.resolve_image_path = resolve_image_path
        self.root = media_root / "local_higgsfield"
        self.jobs_dir = self.root / "jobs"
        self.results_dir = self.root / "results"
        self.characters_dir = self.root / "characters"
        for folder in (self.jobs_dir, self.results_dir, self.characters_dir):
            folder.mkdir(parents=True, exist_ok=True)

    def list_styles(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.STYLE_PRESETS]

    def list_motions(self) -> List[Dict[str, Any]]:
        return [dict(item) for item in self.MOTION_PRESETS]

    def _job_path(self, job_set_id: str) -> Path:
        return self.jobs_dir / f"{job_set_id}.json"

    def _read_job(self, job_set_id: str) -> Dict[str, Any]:
        path = self._job_path(job_set_id)
        if not path.exists():
            raise KeyError(f"job_set_not_found:{job_set_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise KeyError(f"job_set_invalid:{job_set_id}")
        return data

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".{path.name}.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _media_url(self, path: Path) -> str:
        try:
            rel = path.resolve().relative_to(self.media_root.resolve())
            return f"/media-assets/{rel.as_posix()}"
        except Exception:
            return str(path)

    async def _copy_or_download_reference(self, source: str, target_dir: Path) -> Optional[Path]:
        text = str(source or "").strip()
        if not text:
            return None

        resolved = self.resolve_image_path(text) if self.resolve_image_path else None
        if resolved and resolved.exists():
            dest = target_dir / resolved.name
            if not dest.exists() or dest.stat().st_size != resolved.stat().st_size:
                shutil.copy2(resolved, dest)
            return dest

        parsed = urlparse(text)
        if parsed.scheme in {"http", "https"}:
            suffix = Path(parsed.path).suffix or ".png"
            digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
            dest = target_dir / f"remote_{digest}{suffix}"
            if dest.exists():
                return dest
            async with httpx.AsyncClient() as client:
                resp = await client.get(text, timeout=60.0)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            return dest

        p = Path(text)
        if not p.is_absolute():
            p = (self.repo_root / text).resolve()
        if p.exists():
            dest = target_dir / p.name
            if not dest.exists() or dest.stat().st_size != p.stat().st_size:
                shutil.copy2(p, dest)
            return dest
        return None

    def _style_prompt(self, style_id: Optional[str], strength: float = 1.0) -> str:
        if not style_id:
            return ""
        style = next((item for item in self.STYLE_PRESETS if item["id"] == style_id), None)
        if not style:
            return ""
        return f"{style['name']} style at {strength:.2f} strength: {style['description']}"

    def _motion_prompt(self, motions: Optional[List[Dict[str, Any]]]) -> str:
        if not motions:
            return ""
        chunks: List[str] = []
        for motion in motions:
            motion_id = str((motion or {}).get("id") or "")
            strength = float((motion or {}).get("strength") or 1.0)
            preset = next((item for item in self.MOTION_PRESETS if item["id"] == motion_id), None)
            if preset:
                chunks.append(f"{preset['name']} motion at {strength:.2f} strength: {preset['description']}")
        return " ".join(chunks)

    def _make_job_set(
        self,
        *,
        job_set_id: str,
        job_type: str,
        prompt_id: Optional[str],
        status: str,
        input_params: Dict[str, Any],
        local_output_dir: Path,
        error: str = "",
    ) -> Dict[str, Any]:
        job_id = prompt_id or job_set_id
        return {
            "id": job_set_id,
            "type": job_type,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "status": status,
            "local_backend": "forge_comfyui",
            "comfy_url": self.comfy_url,
            "local_output_dir": str(local_output_dir),
            "jobs": [
                {
                    "id": job_id,
                    "prompt_id": prompt_id,
                    "job_set_type": job_type,
                    "status": status,
                    "results": {},
                    "error": error,
                }
            ],
            "input_params": input_params,
        }

    async def generate_image_soul(
        self,
        *,
        prompt: str,
        width_and_height: str = "1696x960",
        enhance_prompt: bool = False,
        quality: str = "720p",
        batch_size: int = 1,
        style_id: Optional[str] = None,
        style_strength: float = 1.0,
        seed: Optional[int] = None,
        custom_reference_id: Optional[str] = None,
        custom_reference_strength: float = 1.0,
        image_reference_url: Optional[str] = None,
        wait_for_output: bool = False,
    ) -> Dict[str, Any]:
        job_set_id = str(uuid.uuid4())
        width, height = _parse_size(width_and_height)
        output_dir = self.results_dir / job_set_id
        output_dir.mkdir(parents=True, exist_ok=True)

        prompt_parts = [prompt.strip()]
        style_text = self._style_prompt(style_id, style_strength)
        if style_text:
            prompt_parts.append(style_text)
        if custom_reference_id:
            prompt_parts.append(
                f"Preserve the local character reference {custom_reference_id} "
                f"at {custom_reference_strength:.2f} strength."
            )
        if enhance_prompt:
            prompt_parts.append("Ad-ready, coherent product/subject identity, polished composition.")
        final_prompt = " ".join(part for part in prompt_parts if part)

        workflow = self.workflow_file_for_id("01_flux2_text_to_image") or self.workflow_file_for_id("08_flux2_klein_9b_text_to_image")
        if not workflow:
            job = self._make_job_set(
                job_set_id=job_set_id,
                job_type="text2image_soul_local",
                prompt_id=None,
                status="failed",
                input_params={"prompt": prompt, "width_and_height": width_and_height},
                local_output_dir=output_dir,
                error="text_to_image_workflow_missing",
            )
            self._write_json(self._job_path(job_set_id), job)
            return job

        comfy = ComfyUIClient(self.comfy_url)
        submit = await comfy.submit_prompt_for_shot(
            shot_id=f"local_higgsfield_{job_set_id[:8]}",
            prompt=final_prompt,
            workflow_path=str(workflow),
            seed=seed,
            output_dir=str(output_dir),
            image_path=None,
            wait_for_output=wait_for_output,
            width=width,
            height=height,
        )
        status = "queued" if submit.get("queued") else ("completed" if submit.get("status") == "success" else "failed")
        job = self._make_job_set(
            job_set_id=job_set_id,
            job_type="text2image_soul_local",
            prompt_id=submit.get("prompt_id"),
            status=status,
            input_params={
                "prompt": prompt,
                "final_prompt": final_prompt,
                "width_and_height": width_and_height,
                "quality": quality,
                "batch_size": batch_size,
                "style_id": style_id,
                "style_strength": style_strength,
                "seed": submit.get("seed", seed),
                "custom_reference_id": custom_reference_id,
                "image_reference_url": image_reference_url,
                "local_equivalence_note": "Local adapter maps Soul-style request to Forge Flux/ComfyUI workflow.",
            },
            local_output_dir=output_dir,
            error=str(submit.get("error") or ""),
        )
        if submit.get("saved_files"):
            self._attach_results(job, [Path(p) for p in submit.get("saved_files", [])])
        self._write_json(self._job_path(job_set_id), job)
        return job

    async def generate_video_dop(
        self,
        *,
        input_image_url: str,
        prompt: str,
        model: str = "dop-turbo",
        seed: Optional[int] = None,
        motions: Optional[List[Dict[str, Any]]] = None,
        input_image_end_url: Optional[str] = None,
        enhance_prompt: bool = True,
        wait_for_output: bool = False,
    ) -> Dict[str, Any]:
        job_set_id = str(uuid.uuid4())
        output_dir = self.results_dir / job_set_id
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = await self._copy_or_download_reference(input_image_url, output_dir)
        if not image_path:
            job = self._make_job_set(
                job_set_id=job_set_id,
                job_type="image2video_dop_local",
                prompt_id=None,
                status="failed",
                input_params={"input_image_url": input_image_url, "prompt": prompt},
                local_output_dir=output_dir,
                error="input_image_not_resolved",
            )
            self._write_json(self._job_path(job_set_id), job)
            return job

        motion_text = self._motion_prompt(motions)
        prompt_parts = [prompt.strip(), motion_text]
        if enhance_prompt:
            prompt_parts.append("Preserve subject identity and product geometry across temporal motion.")
        final_prompt = " ".join(part for part in prompt_parts if part)

        workflow = self.workflow_file_for_id("04_ltx2.3_image_to_video")
        if input_image_end_url:
            workflow = self.workflow_file_for_id("05_ltx2.3_first_last_frame_to_video") or workflow
        if not workflow:
            job = self._make_job_set(
                job_set_id=job_set_id,
                job_type="image2video_dop_local",
                prompt_id=None,
                status="failed",
                input_params={"input_image_url": input_image_url, "prompt": prompt},
                local_output_dir=output_dir,
                error="image_to_video_workflow_missing",
            )
            self._write_json(self._job_path(job_set_id), job)
            return job

        comfy = ComfyUIClient(self.comfy_url)
        submit = await comfy.submit_prompt_for_shot(
            shot_id=f"local_higgsfield_{job_set_id[:8]}",
            prompt=final_prompt,
            workflow_path=str(workflow),
            seed=seed,
            output_dir=str(output_dir),
            image_path=str(image_path),
            wait_for_output=wait_for_output,
        )
        status = "queued" if submit.get("queued") else ("completed" if submit.get("status") == "success" else "failed")
        job = self._make_job_set(
            job_set_id=job_set_id,
            job_type="image2video_dop_local",
            prompt_id=submit.get("prompt_id"),
            status=status,
            input_params={
                "input_image_url": input_image_url,
                "local_input_image": str(image_path),
                "prompt": prompt,
                "final_prompt": final_prompt,
                "model": model,
                "motions": motions or [],
                "input_image_end_url": input_image_end_url,
                "seed": submit.get("seed", seed),
                "local_equivalence_note": "Local adapter maps DoP-style request to Forge LTX/ComfyUI workflow.",
            },
            local_output_dir=output_dir,
            error=str(submit.get("error") or ""),
        )
        if submit.get("saved_files"):
            self._attach_results(job, [Path(p) for p in submit.get("saved_files", [])])
        self._write_json(self._job_path(job_set_id), job)
        return job

    async def create_character(self, *, name: str, image_urls: List[str]) -> Dict[str, Any]:
        reference_id = str(uuid.uuid4())
        folder = self.characters_dir / reference_id
        folder.mkdir(parents=True, exist_ok=True)
        local_images = []
        for source in image_urls:
            copied = await self._copy_or_download_reference(source, folder)
            if copied:
                local_images.append(str(copied))
        character = {
            "id": reference_id,
            "name": name[:100],
            "status": "completed" if local_images else "failed",
            "created_at": _now_iso(),
            "input_images": image_urls,
            "local_images": local_images,
            "thumbnail_url": self._media_url(Path(local_images[0])) if local_images else "",
            "local_equivalence_note": (
                "Local character references are stored as reusable identity assets. "
                "They are not Higgsfield Soul training jobs."
            ),
        }
        self._write_json(folder / "character.json", character)
        return character

    def get_character(self, reference_id: str) -> Dict[str, Any]:
        path = self.characters_dir / reference_id / "character.json"
        if not path.exists():
            raise KeyError(f"character_not_found:{reference_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise KeyError(f"character_invalid:{reference_id}")
        return data

    def list_characters(self) -> Dict[str, Any]:
        items = []
        for path in sorted(self.characters_dir.glob("*/character.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    items.append(data)
            except Exception:
                continue
        return {"total": len(items), "items": items}

    def delete_character(self, reference_id: str) -> Dict[str, Any]:
        folder = self.characters_dir / reference_id
        if not folder.exists():
            raise KeyError(f"character_not_found:{reference_id}")
        shutil.rmtree(folder)
        return {"status": "success", "message": "Character reference deleted"}

    def _attach_results(self, job: Dict[str, Any], paths: List[Path]) -> None:
        results = []
        for path in paths:
            if not path.exists():
                continue
            mime_type = "video/mp4" if path.suffix.lower() in {".mp4", ".mov", ".webm"} else "image_url"
            results.append(
                {
                    "type": "video_url" if mime_type == "video/mp4" else "image_url",
                    "url": self._media_url(path),
                    "local_path": str(path),
                }
            )
        if not results:
            return
        raw = results[0]
        job["status"] = "completed"
        job["updated_at"] = _now_iso()
        for item in job.get("jobs", []):
            item["status"] = "completed"
            item["results"] = {"raw": raw, "min": raw, "all": results}

    async def get_job_status(self, job_set_id: str) -> Dict[str, Any]:
        job = self._read_job(job_set_id)
        prompt_id = str((job.get("jobs") or [{}])[0].get("prompt_id") or "")
        if not prompt_id or job.get("status") in {"completed", "failed", "nsfw"}:
            return job

        async with httpx.AsyncClient() as client:
            history_resp = await client.get(f"{self.comfy_url}/history/{prompt_id}", timeout=10.0)
            if history_resp.status_code == 200:
                history = history_resp.json()
                if prompt_id in history:
                    outputs = history[prompt_id].get("outputs", {})
                    found_paths = await self._download_history_outputs(prompt_id, outputs, Path(job["local_output_dir"]))
                    if found_paths:
                        self._attach_results(job, found_paths)
                    else:
                        job["status"] = "completed"
                        job["updated_at"] = _now_iso()
                        for item in job.get("jobs", []):
                            item["status"] = "completed"
                    self._write_json(self._job_path(job_set_id), job)
                    return job

            queue_resp = await client.get(f"{self.comfy_url}/queue", timeout=10.0)
            if queue_resp.status_code == 200:
                queue_text = json.dumps(queue_resp.json())
                status = "in_progress" if prompt_id in queue_text else "queued"
                job["status"] = status
                job["updated_at"] = _now_iso()
                for item in job.get("jobs", []):
                    item["status"] = status
                self._write_json(self._job_path(job_set_id), job)
        return job

    async def _download_history_outputs(self, prompt_id: str, outputs: Dict[str, Any], output_dir: Path) -> List[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        saved: List[Path] = []
        async with httpx.AsyncClient() as client:
            for node_output in outputs.values():
                if not isinstance(node_output, dict):
                    continue
                for key in ("images", "gifs", "videos", "animated", "files"):
                    for media in node_output.get(key) or []:
                        filename = media.get("filename")
                        if not filename:
                            continue
                        params = {
                            "filename": filename,
                            "type": media.get("type", "output"),
                            "subfolder": media.get("subfolder", ""),
                        }
                        resp = await client.get(f"{self.comfy_url}/view", params=params, timeout=60.0)
                        if resp.status_code == 200:
                            target = output_dir / Path(filename).name
                            target.write_bytes(resp.content)
                            saved.append(target)
        return saved
