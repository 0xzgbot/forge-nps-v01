"""Launch finish: aspect, fade, title card, music bed. Local ffmpeg, no GPU."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

ASPECTS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "2.39": (1920, 804),
}

DEFAULT_COLOR_VF = "eq=contrast=1.04:saturation=1.06:gamma=0.98"
COLOR_PRESETS = {
    "mild": "eq=contrast=1.02:saturation=1.04",
    "warm": "eq=contrast=1.04:saturation=1.08:gamma_r=1.04:gamma_b=0.96",
    "cool": "eq=contrast=1.03:saturation=1.02:gamma_b=1.06:gamma_r=0.96",
    "contrast": "eq=contrast=1.12:saturation=1.06",
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


def probe_duration(src: Path) -> float:
    ffmpeg = _ffmpeg()
    if not ffmpeg or not Path(src).exists():
        return 0.0
    ffprobe = shutil.which("ffprobe") or ""
    if ffprobe:
        proc = subprocess.run(
            [
                ffprobe, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(src),
            ],
            capture_output=True,
            text=True,
        )
        try:
            return max(0.0, float((proc.stdout or "").strip()))
        except (TypeError, ValueError):
            return 0.0
    proc = subprocess.run(
        [ffmpeg, "-i", str(src)],
        capture_output=True,
        text=True,
    )
    text = (proc.stderr or "") + (proc.stdout or "")
    marker = "Duration: "
    if marker not in text:
        return 0.0
    stamp = text.split(marker, 1)[1].split(",", 1)[0].strip()
    parts = stamp.split(":")
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except (TypeError, ValueError):
        return 0.0
    return 0.0


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
    duration = probe_duration(src)
    vf = f"fade=t=in:st=0:d={d}"
    af = f"afade=t=in:st=0:d={d}"
    if duration > d * 2:
        out_at = max(0.0, duration - d)
        vf = f"{vf},fade=t=out:st={out_at:.3f}:d={d}"
        af = f"{af},afade=t=out:st={out_at:.3f}:d={d}"
    cmd = [
        ffmpeg, "-y", "-i", str(src), "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ac", "2",
        "-af", af,
        "-movflags", "+faststart", str(dest),
    ]
    result = _run(cmd)
    if result["ok"] and dest.exists():
        result["output"] = str(dest)
    return result


def crossfade_concat(clips: List[Path], dest: Path, *, fade_sec: float = 0.25) -> Dict[str, Any]:
    """Hard-cut fallback when probe/ffmpeg xfade fails. Local only."""
    ffmpeg = _ffmpeg()
    existing = [Path(c) for c in clips if Path(c).exists()]
    if not existing:
        return {"ok": False, "error": "no_clips"}
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if len(existing) == 1 or not ffmpeg or fade_sec <= 0.04:
        if len(existing) == 1:
            shutil.copy2(existing[0], dest)
            return {"ok": dest.exists(), "output": str(dest), "xfade": False}
        return {"ok": False, "error": "xfade_skipped"}
    durs = [probe_duration(p) for p in existing]
    if any(d <= fade_sec * 2 for d in durs):
        return {"ok": False, "error": "clips_too_short"}
    cmd: List[str] = [ffmpeg, "-y"]
    for path in existing:
        cmd.extend(["-i", str(path)])
    n = len(existing)
    filters: List[str] = []
    offset = durs[0] - fade_sec
    last = "[0:v]"
    last_a = "[0:a]"
    for i in range(1, n):
        vout = f"[v{i}]"
        aout = f"[a{i}]"
        vin = last if i == 1 else last
        ain = last_a if i == 1 else last_a
        filters.append(
            f"{vin}[{i}:v]xfade=transition=fade:duration={fade_sec}:offset={offset:.3f}{vout}"
        )
        filters.append(
            f"{ain}[{i}:a]acrossfade=d={fade_sec}{aout}"
        )
        last = vout
        last_a = aout
        if i + 1 < n:
            offset = offset + durs[i] - fade_sec
    graph = ";".join(filters)
    cmd.extend(
        [
            "-filter_complex", graph,
            "-map", last, "-map", last_a,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2",
            "-movflags", "+faststart", str(dest),
        ]
    )
    result = _run(cmd)
    if result.get("ok") and dest.exists():
        result["output"] = str(dest)
        result["xfade"] = True
    return result


def color_vf(preset: str = "") -> str:
    key = str(preset or "").strip().lower()
    return COLOR_PRESETS.get(key) or DEFAULT_COLOR_VF


def apply_color(src: Path, dest: Path, preset: str = "mild") -> Dict[str, Any]:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        shutil.copy2(src, dest)
        return {"ok": True, "output": str(dest), "skipped": True, "preset": preset}
    vf = color_vf(preset)
    cmd = [
        ffmpeg, "-y", "-i", str(src), "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-movflags", "+faststart", str(dest),
    ]
    result = _run(cmd)
    if not result["ok"]:
        fallback = "eq=contrast=1.04:saturation=1.04"
        cmd = [
            ffmpeg, "-y", "-i", str(src), "-vf", fallback,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2",
            "-movflags", "+faststart", str(dest),
        ]
        result = _run(cmd)
        result["fallback"] = "eq"
    if result["ok"] and dest.exists():
        result["output"] = str(dest)
        result["preset"] = preset or "mild"
    return result


def _subtitles_path(path: Path) -> str:
    raw = str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
    return raw


def burn_srt(src: Path, dest: Path, srt_path: Path) -> Dict[str, Any]:
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        shutil.copy2(src, dest)
        return {"ok": True, "output": str(dest), "skipped": True, "error": "ffmpeg_not_installed"}
    if not Path(srt_path).exists():
        shutil.copy2(src, dest)
        return {"ok": True, "output": str(dest), "skipped": True, "error": "srt_missing"}
    vf = f"subtitles='{_subtitles_path(Path(srt_path))}'"
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


def burn_end_card(src: Path, dest: Path, text: str, *, seconds: float = 2.4) -> Dict[str, Any]:
    ffmpeg = _ffmpeg()
    font = _font()
    title = (text or "").replace("\\", " ").replace("'", "’")[:80]
    if not ffmpeg:
        shutil.copy2(src, dest)
        return {"ok": True, "output": str(dest), "skipped": True, "error": "ffmpeg_not_installed"}
    if not title or not font:
        shutil.copy2(src, dest)
        return {"ok": True, "output": str(dest), "skipped": True}
    duration = probe_duration(src)
    start = max(0.0, duration - max(0.6, float(seconds))) if duration else 0.0
    end = duration if duration else max(0.6, float(seconds))
    escaped = title.replace(":", "\\:").replace("%", "\\%")
    vf = (
        f"drawtext=fontfile={font}:text='{escaped}':fontsize=36:fontcolor=white:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:enable='between(t,{start:.3f},{end:.3f})':"
        f"shadowcolor=black@0.7:shadowx=2:shadowy=2"
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


def apply_finish(
    cut: Path,
    dest: Path,
    *,
    aspect: str = "16:9",
    title: str = "",
    music: Optional[Path] = None,
    fade_sec: float = 0.3,
    color_preset: str = "",
    burn_captions: bool = False,
    srt: Optional[Path] = None,
    end_card: str = "",
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
    if color_preset:
        graded = work / "graded.mp4"
        r = apply_color(current, graded, preset=color_preset)
        steps["color"] = r
        if r.get("ok"):
            current = graded
    if burn_captions and srt and Path(srt).exists():
        captioned = work / "captioned.mp4"
        r = burn_srt(current, captioned, Path(srt))
        steps["captions"] = r
        if r.get("ok"):
            current = captioned
    if end_card:
        ended = work / "endcard.mp4"
        r = burn_end_card(current, ended, end_card)
        steps["end_card"] = r
        if r.get("ok"):
            current = ended
    if music and Path(music).exists():
        mixed = work / "mixed.mp4"
        r = mix_music(current, Path(music), mixed)
        steps["music"] = r
        if r.get("ok"):
            current = mixed
    shutil.copy2(current, dest)
    return {"ok": dest.exists(), "output": str(dest), "steps": steps, "aspect": aspect}
