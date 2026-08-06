"""Media honesty helpers — duration, codec, and audio stream detection via ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse


def resolve_media_path(
    path_or_url: str,
    *,
    media_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Optional[Path]:
    """Map a dashboard media URL or absolute path to a local file if possible."""
    raw = (path_or_url or "").strip()
    if not raw:
        return None
    candidate = Path(unquote(raw))
    if candidate.exists() and candidate.is_file():
        return candidate.resolve()

    # Common dashboard prefixes: /media-assets/images/..., /media-assets/videos/...
    parsed = urlparse(raw)
    rel = unquote(parsed.path if parsed.scheme else raw)
    for prefix in ("/media-assets/", "media-assets/", "/media/", "media/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix) :]
            break
    rel = rel.lstrip("/")

    search_roots: List[Path] = []
    if media_root:
        search_roots.append(Path(media_root))
        search_roots.append(Path(media_root) / "images")
        search_roots.append(Path(media_root) / "videos")
    if repo_root:
        search_roots.append(Path(repo_root) / "media")
        search_roots.append(Path(repo_root) / "data" / "renders")

    for root in search_roots:
        p = (root / rel).resolve()
        try:
            if media_root and not str(p).startswith(str(Path(media_root).resolve())):
                # still allow repo-local media
                if not repo_root or not str(p).startswith(str(Path(repo_root).resolve())):
                    continue
        except Exception:
            continue
        if p.exists() and p.is_file():
            return p
        # try basename search one level
        base = Path(rel).name
        if base:
            for hit in root.rglob(base):
                if hit.is_file():
                    return hit.resolve()
    return None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def probe_media(path: Path, timeout: float = 8.0) -> Dict[str, Any]:
    """Return duration, codecs, and whether an audio stream exists."""
    result: Dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "ffprobe": ffprobe_available(),
        "has_video": False,
        "has_audio": False,
        "duration_sec": None,
        "video_codec": None,
        "audio_codec": None,
        "width": None,
        "height": None,
        "error": None,
    }
    if not path.exists():
        result["error"] = "file_not_found"
        return result
    if not ffprobe_available():
        result["error"] = "ffprobe_missing"
        # naive fallback for video extensions
        ext = path.suffix.lower()
        result["has_video"] = ext in {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
        return result

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        if proc.returncode != 0:
            result["error"] = (proc.stderr or "ffprobe_failed")[:240]
            return result
        data = json.loads(proc.stdout or "{}")
    except Exception as exc:
        result["error"] = str(exc)[:240]
        return result

    streams = data.get("streams") if isinstance(data, dict) else []
    fmt = data.get("format") if isinstance(data, dict) else {}
    try:
        if isinstance(fmt, dict) and fmt.get("duration") is not None:
            result["duration_sec"] = round(float(fmt["duration"]), 3)
    except Exception:
        pass

    for stream in streams or []:
        if not isinstance(stream, dict):
            continue
        ctype = str(stream.get("codec_type") or "")
        if ctype == "video":
            result["has_video"] = True
            result["video_codec"] = stream.get("codec_name")
            try:
                result["width"] = int(stream.get("width") or 0) or None
                result["height"] = int(stream.get("height") or 0) or None
            except Exception:
                pass
        elif ctype == "audio":
            result["has_audio"] = True
            result["audio_codec"] = stream.get("codec_name")

    return result


def probe_path_or_url(
    path_or_url: str,
    *,
    media_root: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    path = resolve_media_path(path_or_url, media_root=media_root, repo_root=repo_root)
    if not path:
        return {
            "path": path_or_url,
            "exists": False,
            "ffprobe": ffprobe_available(),
            "has_video": False,
            "has_audio": False,
            "duration_sec": None,
            "error": "unresolved_path",
        }
    return probe_media(path)
