"""Job-level ops for a launchable Produce desk: shots, comments, continuity, duplicate."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.hermes.produce import render as produce_render

SAMPLE_BRIEFS = [
    {
        "id": "wet-city",
        "title": "Wet city",
        "prompt": "A courier misses the last train and walks home through a wet city. Two minutes. Quiet. No dialogue.",
    },
    {
        "id": "neon-kitchen",
        "title": "Neon kitchen",
        "prompt": "A late-night cook plates one perfect dish under neon. Steam. Close-ups. No dialogue. Forty seconds.",
    },
    {
        "id": "last-light",
        "title": "Last light",
        "prompt": "Two strangers share a bus stop at dusk. One offers an umbrella. One minute. Almost no words.",
    },
    {
        "id": "product-spin",
        "title": "Product",
        "prompt": "A matte-black bottle turns in soft window light. Hero beauty. Ten seconds. No people.",
    },
    {
        "id": "vertical-hook",
        "title": "Vertical hook",
        "prompt": "A runner hits a flooded underpass. Slow motion splash. Vertical 9:16. Eight seconds. Hard cut to title.",
    },
]


def comments_path(job_dir: Path) -> Path:
    return Path(job_dir) / "comments.json"


def load_comments(job_dir: Path) -> List[Dict[str, Any]]:
    target = comments_path(job_dir)
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data if isinstance(data, list) else data.get("comments")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def add_comment(job_dir: Path, text: str, *, shot_id: str = "", author: str = "you") -> Dict[str, Any]:
    body = str(text or "").strip()
    if not body:
        raise ValueError("comment required")
    row = {
        "id": uuid.uuid4().hex[:10],
        "shot_id": str(shot_id or "").strip(),
        "author": str(author or "you").strip() or "you",
        "text": body,
        "created_at": time.time(),
    }
    rows = load_comments(job_dir)
    rows.append(row)
    comments_path(job_dir).write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return row


def continuity_score(job_dir: Path) -> Dict[str, Any]:
    """Honest heuristic — not a vision model. Counts locks, not beauty."""
    job_dir = Path(job_dir)
    shots = produce_render.load_shots(job_dir)
    identity = produce_render.list_identity(job_dir)
    stills = [s for s in shots if s.get("still")]
    clips = [s for s in shots if s.get("clip")]
    end_stills = [s for s in shots if s.get("end_still")]
    n = max(1, len(shots))
    score = 0.0
    notes: List[str] = []
    if identity:
        score += 35
        notes.append(f"{len(identity)} identity lock(s)")
    else:
        notes.append("No face/location lock")
    score += 25 * (len(stills) / n)
    score += 25 * (len(clips) / n)
    if end_stills:
        score += 10
        notes.append(f"{len(end_stills)} last-frame lock(s)")
    if produce_render.video_model(job_dir) == "h3" and identity:
        score += 5
        notes.append("H3 + identity → R2VA path")
    score = max(0, min(100, round(score)))
    grade = "locked" if score >= 80 else ("held" if score >= 50 else "loose")
    return {
        "score": score,
        "grade": grade,
        "shots": len(shots),
        "boarded": len(stills),
        "shot": len(clips),
        "identity": len(identity),
        "notes": notes,
    }


def add_shot(job_dir: Path, *, purpose: str = "", visual: str = "") -> Dict[str, Any]:
    shots = produce_render.load_shots(job_dir)
    n = len(shots) + 1
    shot_id = f"SHOT_{n:03d}"
    while any(str(s.get("id")) == shot_id for s in shots):
        n += 1
        shot_id = f"SHOT_{n:03d}"
    shot = {
        "id": shot_id,
        "purpose": purpose or f"Shot {n}",
        "visual": visual or purpose,
        "status": "planned",
        "duration_sec": 5,
    }
    shots.append(shot)
    produce_render.save_shots(job_dir, shots)
    return shot


def delete_shot(job_dir: Path, shot_id: str) -> Dict[str, Any]:
    wanted = str(shot_id or "").strip()
    shots = [s for s in produce_render.load_shots(job_dir) if str(s.get("id")) != wanted]
    produce_render.save_shots(job_dir, shots)
    edit = [row for row in produce_render.load_edit(job_dir) if str(row.get("shot_id")) != wanted]
    produce_render.save_edit(job_dir, edit)
    return {"ok": True, "shot_id": wanted, "remaining": len(shots)}


def duplicate_job(src: Path, dest: Path) -> Path:
    if dest.exists():
        raise ValueError("job exists")
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".trim", ".finish", "*.concat.txt"))
    meta = produce_render.load_job_meta(dest)
    meta["job_id"] = dest.name
    meta["cloned_from"] = src.name
    meta["created_at"] = time.time()
    meta["status"] = "running"
    produce_render.save_job_meta(dest, meta)
    status = dest / "STATUS.md"
    status.write_text("story — duplicated. Review boards before you spend Spark.\n", encoding="utf-8")
    return dest


def rename_job(job_dir: Path, title: str) -> str:
    value = str(title or "").strip()[:120]
    produce_render.save_job_meta(job_dir, {"title": value})
    return value


def find_music(job_dir: Path) -> Optional[Path]:
    identity = Path(job_dir) / "identity"
    if not identity.exists():
        return None
    for path in sorted(identity.iterdir()):
        if path.suffix.lower() in {".wav", ".mp3", ".m4a", ".flac", ".ogg"} and "voice" not in path.stem.lower():
            if "music" in path.stem.lower() or "bed" in path.stem.lower() or "score" in path.stem.lower():
                return path
    return None


SOCIAL_PRESETS = [
    {"id": "youtube", "aspect": "16:9", "label": "YouTube 16:9"},
    {"id": "reels", "aspect": "9:16", "label": "Reels / TikTok 9:16"},
    {"id": "square", "aspect": "1:1", "label": "Feed 1:1"},
    {"id": "scope", "aspect": "2.39", "label": "Scope 2.39"},
]


def runtime_sec(job_dir: Path) -> float:
    total = 0.0
    for shot in produce_render.load_shots(job_dir):
        try:
            total += float(shot.get("duration_sec") or 5)
        except (TypeError, ValueError):
            total += 5.0
    return round(total, 2)


def next_action(job_dir: Path) -> Dict[str, Any]:
    """Honest producer coach. File presence only — not a vision model."""
    job_dir = Path(job_dir)
    shots = produce_render.load_shots(job_dir)
    boarded = [s for s in shots if s.get("still")]
    shot = [s for s in shots if s.get("clip")]
    cut = (job_dir / "cut.mp4").exists()
    mode = produce_render.produce_mode(job_dir)
    if not shots:
        return {"id": "story", "label": "Hermes is writing the shot list.", "cta": ""}
    missing_boards = max(0, len(shots) - len(boarded))
    if mode == "shoot" and missing_boards:
        return {
            "id": "boards",
            "label": f"Board {missing_boards} shot(s) on the 3090s.",
            "cta": "Queue boards",
        }
    missing_takes = max(0, len(shots) - len(shot))
    if missing_takes:
        return {
            "id": "takes",
            "label": f"Shoot {missing_takes} take(s) on Spark.",
            "cta": "Queue takes",
        }
    if not cut:
        return {"id": "assemble", "label": "Clips are in. Assemble the cut.", "cta": "Assemble"}
    return {
        "id": "export",
        "label": "Cut is ready. Pick an aspect and download, or hand off a zip.",
        "cta": "Export",
    }


def _srt_ts(sec: float) -> str:
    ms = max(0, int(round(float(sec) * 1000)))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def write_captions(job_dir: Path) -> Path:
    """Burn-in-ready SRT from shot purpose/visual. Local, no GPU."""
    job_dir = Path(job_dir)
    t = 0.0
    blocks: List[str] = []
    n = 0
    for shot in produce_render.load_shots(job_dir):
        try:
            dur = float(shot.get("duration_sec") or 5)
        except (TypeError, ValueError):
            dur = 5.0
        text = str(shot.get("purpose") or shot.get("visual") or shot.get("id") or "").strip()[:180]
        if text:
            n += 1
            blocks.append(f"{n}\n{_srt_ts(t)} --> {_srt_ts(t + dur)}\n{text}\n")
        t += dur
    dest = job_dir / "cut.srt"
    dest.write_text("\n".join(blocks).strip() + ("\n" if blocks else ""), encoding="utf-8")
    return dest
