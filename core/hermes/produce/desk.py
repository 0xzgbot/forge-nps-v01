"""Local Produce desk ops: review, A/B takes, cut versions, script peek, enhance."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.assembly.timeline_assembler import TimelineAssembler
from core.consistency_scorecard import score_campaign_shots
from core.cinesmith_env import repo_root
from core.hermes.produce import job_ops as produce_ops
from core.hermes.produce import render as produce_render
from core.routing.prompt_enhancer import PromptEnhancer
from core.script.script_parser import ScriptParser

HEADING_RE = re.compile(r"^(INT\.|EXT\.|INT/EXT\.|I/E\.)[^\n]+", re.MULTILINE | re.IGNORECASE)


def review_path(job_dir: Path) -> Path:
    return Path(job_dir) / "review_log.jsonl"


def load_reviews(job_dir: Path) -> List[Dict[str, Any]]:
    target = review_path(job_dir)
    if not target.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def review_shot(job_dir: Path, shot_id: str, decision: str, *, note: str = "") -> Dict[str, Any]:
    wanted = str(shot_id or "").strip()
    choice = str(decision or "").strip().lower()
    aliases = {
        "approve": "approved",
        "approved": "approved",
        "needs_changes": "needs_changes",
        "needs-changes": "needs_changes",
        "changes": "needs_changes",
        "reject": "rejected",
        "rejected": "rejected",
        "retake": "rejected",
    }
    choice = aliases.get(choice, "")
    if not wanted or choice not in {"approved", "needs_changes", "rejected"}:
        raise ValueError("decision must be approved, needs_changes, or rejected")
    status = {"approved": "approved", "needs_changes": "needs_changes", "rejected": "retake"}[choice]
    produce_render.upsert_shot(
        job_dir,
        wanted,
        status=status,
        review_status=choice,
        review_note=str(note or "").strip(),
    )
    row = {
        "shot_id": wanted,
        "decision": choice,
        "note": str(note or "").strip(),
        "created_at": time.time(),
    }
    with review_path(job_dir).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    if note:
        try:
            produce_ops.add_comment(job_dir, note, shot_id=wanted, author="review")
        except ValueError:
            pass
    return row


def ab_path(job_dir: Path) -> Path:
    return Path(job_dir) / "ab_log.jsonl"


def compare_takes(
    job_dir: Path,
    shot_id: str,
    take_a: str,
    take_b: str,
    *,
    winner: str = "",
    note: str = "",
) -> Dict[str, Any]:
    row = {
        "shot_id": str(shot_id or "").strip(),
        "a": str(take_a or "").strip(),
        "b": str(take_b or "").strip(),
        "winner": str(winner or "").strip(),
        "note": str(note or "").strip(),
        "created_at": time.time(),
    }
    with ab_path(job_dir).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    if row["winner"]:
        produce_render.restore_take(job_dir, row["shot_id"], row["winner"])
    return row


def list_cuts(job_dir: Path) -> List[Dict[str, Any]]:
    root = Path(job_dir) / "cuts"
    if not root.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(root.glob("*.mp4")):
        rows.append(
            {
                "file": "cuts/" + path.name,
                "name": path.name,
                "bytes": path.stat().st_size,
                "mtime": path.stat().st_mtime,
            }
        )
    return rows


def archive_cut(job_dir: Path) -> str:
    src = Path(job_dir) / "cut.mp4"
    if not src.exists() or not src.is_file() or src.stat().st_size < 1:
        return ""
    dest_dir = Path(job_dir) / "cuts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(dest_dir.glob("*.mp4"))) + 1
    dest = dest_dir / f"{n:03d}.mp4"
    shutil.copy2(src, dest)
    return "cuts/" + dest.name


def restore_cut(job_dir: Path, rel: str) -> Dict[str, Any]:
    src = (Path(job_dir) / str(rel or "")).resolve()
    root = (Path(job_dir) / "cuts").resolve()
    if root not in src.parents or not src.exists():
        return {"ok": False, "error": "cut_missing"}
    current = Path(job_dir) / "cut.mp4"
    if current.exists():
        archive_cut(job_dir)
    shutil.copy2(src, current)
    return {"ok": True, "cut": "cut.mp4", "from": str(rel)}


def peek_script(job_dir: Path) -> Dict[str, Any]:
    path = Path(job_dir) / "script.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if "# SCRIPT:" in text or "## SCENE" in text:
        parsed = ScriptParser().parse(str(path))
        scenes = []
        for scene in parsed.get("scenes") or []:
            scenes.append(
                {
                    "id": scene.get("id") or "",
                    "action": (scene.get("action") or "")[:240],
                    "visual": (scene.get("visual_notes") or "")[:240],
                    "audio": scene.get("audio_cues") or [],
                }
            )
        return {
            "title": parsed.get("title") or "",
            "format": "script",
            "scenes": scenes[:24],
            "characters": parsed.get("character_registry") or [],
            "locations": parsed.get("location_registry") or [],
        }
    scenes = []
    for match in HEADING_RE.finditer(text):
        start = match.end()
        nxt = HEADING_RE.search(text, start)
        body = text[start : nxt.start() if nxt else start + 240].strip()
        scenes.append({"id": match.group(0).strip(), "action": body[:240], "visual": "", "audio": []})
    return {
        "title": "",
        "format": "screenplay" if scenes else "freeform",
        "scenes": scenes[:24],
        "characters": [],
        "locations": [],
    }


def scorecard(job_dir: Path) -> Dict[str, Any]:
    adapted: List[Dict[str, Any]] = []
    for shot in produce_render.load_shots(job_dir):
        adapted.append(
            {
                "prompt": shot.get("h3_prompt") or shot.get("visual") or "",
                "description": shot.get("purpose") or "",
                "location": shot.get("camera") or "",
                "character": " ".join(
                    str(x) for x in (shot.get("guides") or []) if isinstance(x, str)
                ),
            }
        )
    card = score_campaign_shots(adapted)
    card["locks"] = produce_ops.continuity_score(job_dir)
    return card


def enhance_shot(job_dir: Path, shot_id: str) -> Dict[str, Any]:
    shot = produce_render.get_shot(job_dir, shot_id)
    if not shot:
        raise ValueError("shot not found")
    bank = repo_root() / "data" / "character_banks" / "lighting_bank.txt"
    enhancer = PromptEnhancer(str(bank))
    body = str(shot.get("visual") or shot.get("h3_prompt") or shot.get("purpose") or "").strip()
    if not body:
        raise ValueError("shot_prompt_missing")
    enriched = enhancer.enhance_shot_prompt(
        {"description": body, "target_kernel": "flux_2_dev"},
        {"name": "cinematic"},
    )
    enhanced = str(enriched.get("enhanced_prompt") or body).strip()
    negative = str(enriched.get("negative_prompt") or "").strip()
    produce_render.patch_shot(
        job_dir,
        shot_id,
        {"h3_prompt": enhanced, "negative_prompt": negative},
    )
    return produce_render.get_shot(job_dir, shot_id) or {}


def duplicate_shot(job_dir: Path, shot_id: str) -> Dict[str, Any]:
    src = produce_render.get_shot(job_dir, shot_id)
    if not src:
        raise ValueError("shot not found")
    copy = produce_ops.add_shot(
        job_dir,
        purpose=str(src.get("purpose") or src.get("id") or "Shot") + " copy",
        visual=str(src.get("visual") or src.get("h3_prompt") or ""),
    )
    produce_render.patch_shot(
        job_dir,
        copy["id"],
        {
            "h3_prompt": src.get("h3_prompt"),
            "camera": src.get("camera"),
            "duration_sec": src.get("duration_sec") or 5,
            "h3_mode": src.get("h3_mode"),
            "still": src.get("still"),
            "end_still": src.get("end_still"),
        },
    )
    return produce_render.get_shot(job_dir, copy["id"]) or copy


def grab_still(job_dir: Path, shot_id: str, *, time_sec: float = 0.0, as_last: bool = False) -> Dict[str, Any]:
    shot = produce_render.get_shot(job_dir, shot_id) or {}
    rel = str(shot.get("clip") or "").strip()
    clip = Path(job_dir) / rel
    if not rel or not clip.exists():
        return {"ok": False, "error": "clip_required"}
    dest_dir = Path(job_dir) / "boards"
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = "out" if as_last else "in"
    dest = dest_dir / f"{shot_id}_{suffix}.png"
    result = TimelineAssembler().extract_frame(clip, max(0.0, float(time_sec)), dest)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or "extract_failed"}
    field = "end_still" if as_last else "still"
    produce_render.patch_shot(job_dir, shot_id, {field: produce_render._rel_or_name(job_dir, dest)})
    return {"ok": True, field: produce_render._rel_or_name(job_dir, dest)}


def last_assemble(job_dir: Path) -> Dict[str, Any]:
    meta = produce_render.load_job_meta(job_dir)
    row = meta.get("last_assemble")
    return row if isinstance(row, dict) else {}
