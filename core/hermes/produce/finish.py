"""Launch finish: aspect, fade, title card, music bed. Local ffmpeg, no GPU."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

ASPECTS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "2.39": (1920, 804),
}

FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)


def _font() -> str:
    for path in FONTS:
        if Path(path).exists():
            return path
    return ""


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or ""


def _run(cmd: list[str]) -> Dict[str, Any]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "ok": proc.returncode == 0,
        "error": (proc.stderr or proc.stdout or "")[-600:],
    }


def scale_aspect(src: Path, dest: Path, aspect: str = "16:9") -> Dict[str, Any]:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg_not_installed"}
    w, h = ASPECTS.get(aspect, ASPECTS["16:9"])
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    )
    cmd = [
        ffmpeg, "-y", "-i", str(src),
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ac", "2",
        "-movflags", "+faststart", str(dest),
    ]
    result = _run(cmd)
    if result["ok"] and dest.exists():
        result["output"] = str(dest)
        result["width"] = w
        result["height"] = h
    return result


def burn_title(src: Path, dest: Path, title: str, *, seconds: float = 2.4) -> Dict[str, Any]:
    ffmpeg = _ffmpeg()
    font = _font()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg_not_installed"}
    text = (title or "").replace("\\", " ").replace("'", "’")[:80]
    if not text or not font:
        shutil.copy2(src, dest)
        return {"ok": True, "output": str(dest), "skipped": True}
    escaped = text.replace(":", "\\:").replace("%", "\\%")
    vf = (
        f"drawtext=fontfile={font}:text='{escaped}':fontsize=42:fontcolor=white:"
        f"x=(w-text_w)/2:y=h-120:enable='between(t,0.4,{seconds})':"
        f"shadowcolor=black@0.6:shadowx=2:shadowy=2"
    )
    cmd = [
        ffmpeg, "-y", "-i", str(src), "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart", str(dest),
    ]
    result = _run(cmd)
    if not result["ok"]:
        encode = [
            ffmpeg, "-y", "-i", str(src), "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2",
            "-movflags", "+faststart", str(dest),
        ]
        result = _run(encode)
    if result["ok"] and dest.exists():
        result["output"] = str(dest)
    return result


def mix_music(src: Path, music: Path, dest: Path, *, music_db: float = -18) -> Dict[str, Any]:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg_not_installed"}
    if not music.exists():
        return {"ok": False, "error": "music_missing"}
    # Assembled cuts are often muted (-an). Lay the bed under video duration.
    cmd = [
        ffmpeg, "-y", "-i", str(src), "-i", str(music),
        "-filter_complex",
        f"[1:a]volume={music_db}dB,aloop=loop=-1:size=2e9[bed]",
        "-map", "0:v", "-map", "[bed]",
        "-c:v", "copy", "-c:a", "aac", "-ac", "2",
        "-shortest",
        "-movflags", "+faststart", str(dest),
    ]
    result = _run(cmd)
    if not result["ok"]:
        cmd = [
            ffmpeg, "-y", "-i", str(src), "-i", str(music),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2",
            "-shortest",
            "-movflags", "+faststart", str(dest),
        ]
        result = _run(cmd)
    if result["ok"] and dest.exists():
        result["output"] = str(dest)
    return result


def fade_edges(src: Path, dest: Path, seconds: float = 0.35) -> Dict[str, Any]:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "ffmpeg_not_installed"}
    d = max(0.05, float(seconds))
    # Fade in only. Out-fade needs a probed duration; skip it rather than fade from t=0.
    vf = f"fade=t=in:st=0:d={d}"
    cmd = [
        ffmpeg, "-y", "-i", str(src), "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ac", "2",
        "-af", f"afade=t=in:st=0:d={d}",
        "-movflags", "+faststart", str(dest),
    ]
    result = _run(cmd)
    if result["ok"] and dest.exists():
        result["output"] = str(dest)
    return result


def apply_finish(
    cut: Path,
    dest: Path,
    *,
    aspect: str = "16:9",
    title: str = "",
    music: Optional[Path] = None,
    fade_sec: float = 0.3,
) -> Dict[str, Any]:
    """Post-process an assembled cut into a deliverable."""
    work = dest.parent / ".finish"
    work.mkdir(parents=True, exist_ok=True)
    current = Path(cut)
    steps: Dict[str, Any] = {}
    scaled = work / "scaled.mp4"
    r = scale_aspect(current, scaled, aspect=aspect)
    steps["aspect"] = r
    if r.get("ok"):
        current = scaled
    if fade_sec and fade_sec > 0.04:
        faded = work / "faded.mp4"
        r = fade_edges(current, faded, seconds=fade_sec)
        steps["fade"] = r
        if r.get("ok"):
            current = faded
    if title:
        titled = work / "titled.mp4"
        r = burn_title(current, titled, title)
        steps["title"] = r
        if r.get("ok"):
            current = titled
    if music and Path(music).exists():
        mixed = work / "mixed.mp4"
        r = mix_music(current, Path(music), mixed)
        steps["music"] = r
        if r.get("ok"):
            current = mixed
    shutil.copy2(current, dest)
    return {"ok": dest.exists(), "output": str(dest), "steps": steps, "aspect": aspect}
