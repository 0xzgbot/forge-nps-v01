import base64
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx


@dataclass
class StoryboardImageResult:
    provider: str
    model: str
    path: Path
    mime_type: str
    metadata: Dict[str, Any]


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return slug[:48] or "storyboard_image"


def _extension_for_mime(mime_type: str) -> str:
    mime = (mime_type or "").lower()
    if "jpeg" in mime or "jpg" in mime:
        return ".jpg"
    if "webp" in mime:
        return ".webp"
    return ".png"


def _write_image(output_dir: Path, stem: str, image_b64: str, mime_type: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = _extension_for_mime(mime_type)
    path = output_dir / f"{_safe_slug(stem)}_{uuid.uuid4().hex[:10]}{suffix}"
    path.write_bytes(base64.b64decode(image_b64))
    return path


def _record_cloud_image_cost(
    provider: str,
    model: str,
    *,
    success: bool,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Best-effort spend meter (G5). Never raises into the image path."""
    try:
        from core.cost_meter import record_image_call

        record_image_call(provider, model, success=success, units=1, meta=meta or {})
    except Exception:
        pass


class StoryboardImageProvider:
    """Text-to-image adapters used only by the Script/Storyboard workflow."""

    def __init__(
        self,
        *,
        openai_api_key: str = "",
        openai_model: str = "gpt-image-2",
        gemini_api_key: str = "",
        gemini_model: str = "gemini-2.5-flash-image",
    ) -> None:
        self.openai_api_key = (openai_api_key or "").strip()
        self.openai_model = (openai_model or "gpt-image-2").strip()
        self.gemini_api_key = (gemini_api_key or "").strip()
        self.gemini_model = (gemini_model or "gemini-2.5-flash-image").strip()

    async def generate(
        self,
        *,
        provider: str,
        prompt: str,
        output_dir: Path,
        title: str = "storyboard",
        model: str = "",
        size: str = "auto",
    ) -> StoryboardImageResult:
        provider_key = (provider or "").strip().lower()
        if provider_key == "openai":
            return await self._generate_openai(prompt=prompt, output_dir=output_dir, title=title, model=model, size=size)
        if provider_key in {"gemini", "nano_banana", "nanobanana"}:
            return await self._generate_gemini(prompt=prompt, output_dir=output_dir, title=title, model=model)
        raise ValueError(f"unsupported_storyboard_image_provider:{provider}")

    async def _generate_openai(
        self,
        *,
        prompt: str,
        output_dir: Path,
        title: str,
        model: str = "",
        size: str = "auto",
    ) -> StoryboardImageResult:
        api_key = self.openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        selected_model = (model or self.openai_model or "gpt-image-2").strip()
        payload: Dict[str, Any] = {
            "model": selected_model,
            "prompt": prompt,
            "n": 1,
        }
        if size:
            payload["size"] = size
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post("https://api.openai.com/v1/images/generations", headers=headers, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"openai_image_http_{response.status_code}:{response.text[:500]}")
            data = response.json()
            items = data.get("data") if isinstance(data, dict) else None
            first = items[0] if isinstance(items, list) and items else {}
            image_b64 = str(first.get("b64_json") or "")
            mime_type = "image/png"
            if not image_b64 and first.get("url"):
                async with httpx.AsyncClient(timeout=180.0) as client:
                    image_response = await client.get(str(first["url"]))
                if image_response.status_code >= 400:
                    raise RuntimeError(f"openai_image_download_http_{image_response.status_code}")
                image_b64 = base64.b64encode(image_response.content).decode("utf-8")
                mime_type = image_response.headers.get("content-type", "image/png").split(";", 1)[0]
            if not image_b64:
                raise RuntimeError("openai_image_response_missing_image")
            path = _write_image(output_dir, f"{title}_openai", image_b64, mime_type)
            _record_cloud_image_cost("openai", selected_model, success=True, meta={"title": title, "size": size})
            return StoryboardImageResult(
                provider="openai",
                model=selected_model,
                path=path,
                mime_type=mime_type,
                metadata={"usage": data.get("usage") if isinstance(data, dict) else None},
            )
        except Exception as exc:
            _record_cloud_image_cost(
                "openai",
                selected_model,
                success=False,
                meta={"error": str(exc)[:200]},
            )
            raise

    async def _generate_gemini(
        self,
        *,
        prompt: str,
        output_dir: Path,
        title: str,
        model: str = "",
    ) -> StoryboardImageResult:
        api_key = self.gemini_api_key
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        selected_model = (model or self.gemini_model or "gemini-2.5-flash-image").strip()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                raise RuntimeError(f"gemini_image_http_{response.status_code}:{response.text[:500]}")
            data = response.json()
            for candidate in data.get("candidates", []) if isinstance(data, dict) else []:
                content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
                for part in content.get("parts", []) if isinstance(content, dict) else []:
                    inline = part.get("inlineData") or part.get("inline_data") if isinstance(part, dict) else None
                    if not isinstance(inline, dict):
                        continue
                    image_b64 = str(inline.get("data") or "")
                    if not image_b64:
                        continue
                    mime_type = str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
                    path = _write_image(output_dir, f"{title}_gemini", image_b64, mime_type)
                    _record_cloud_image_cost("gemini", selected_model, success=True, meta={"title": title})
                    return StoryboardImageResult(
                        provider="gemini",
                        model=selected_model,
                        path=path,
                        mime_type=mime_type,
                        metadata={"text": self._extract_gemini_text(data)},
                    )
            raise RuntimeError("gemini_image_response_missing_image")
        except Exception as exc:
            _record_cloud_image_cost(
                "gemini",
                selected_model,
                success=False,
                meta={"error": str(exc)[:200]},
            )
            raise

    @staticmethod
    def _extract_gemini_text(data: Dict[str, Any]) -> str:
        chunks = []
        for candidate in data.get("candidates", []) if isinstance(data, dict) else []:
            content = candidate.get("content", {}) if isinstance(candidate, dict) else {}
            for part in content.get("parts", []) if isinstance(content, dict) else []:
                if isinstance(part, dict) and part.get("text"):
                    chunks.append(str(part["text"]))
        return "\n".join(chunks).strip()

