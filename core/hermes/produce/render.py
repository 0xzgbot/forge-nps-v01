"""Real produce tools: board stills on 3090s, H3 takes on Spark, ffmpeg cut."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.assembly.timeline_assembler import TimelineAssembler
from core.character.identity_attach import resolve_anchor_paths
from core.dispatch.capability_router import CapabilityRouter
from core.dispatch.comfy_client import ComfyUIClient
from core.dispatch.workflows import (
    DEFAULT_BOARD_WORKFLOW_ID,
    take_workflow_for_mode,
    workflow_file_for_id,
)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".m4v"}


def parse_shots_payload(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = raw.get("shots") if isinstance(raw.get("shots"), list) else []
    else:
        rows = []
    shots: List[Dict[str, Any]] = []
    for idx, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        shot_id = str(item.get("id") or item.get("shot_id") or f"SHOT_{idx:03d}").strip()
        shot = dict(item)
        shot["id"] = shot_id
        shot.setdefault("status", "planned")
        shots.append(shot)
    return shots


def load_shots(job_dir: Path) -> List[Dict[str, Any]]:
    target = job_dir / "shots.json"
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    return parse_shots_payload(data)


def save_shots(job_dir: Path, shots: List[Dict[str, Any]]) -> None:
    (job_dir / "shots.json").write_text(
        json.dumps({"shots": shots}, indent=2),
        encoding="utf-8",
    )


def get_shot(job_dir: Path, shot_id: str) -> Optional[Dict[str, Any]]:
    wanted = str(shot_id or "").strip()
    for shot in load_shots(job_dir):
        if str(shot.get("id") or "") == wanted:
            return shot
    return None


def upsert_shot(job_dir: Path, shot_id: str, **updates: Any) -> Dict[str, Any]:
    shots = load_shots(job_dir)
    wanted = str(shot_id or "").strip()
    found = None
    for row in shots:
        if str(row.get("id") or "") == wanted:
            row.update(updates)
            found = row
            break
    if found is None:
        found = {"id": wanted, "status": "planned", **updates}
        shots.append(found)
    save_shots(job_dir, shots)
    return found


def identity_search_dirs(job_dir: Path) -> List[Path]:
    return [
        job_dir / "identity",
        job_dir / "refs",
        job_dir / "characters",
        job_dir,
    ]


def identity_paths_for_job(job_dir: Path, pack: Optional[Dict[str, Any]] = None) -> List[str]:
    pack = pack if isinstance(pack, dict) else {}
    meta_path = job_dir / "job.json"
    if not pack and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta, dict) and isinstance(meta.get("identity_pack"), dict):
                pack = meta["identity_pack"]
        except Exception:
            pack = {}
    paths = resolve_anchor_paths(pack, search_dirs=identity_search_dirs(job_dir))
    for folder in identity_search_dirs(job_dir):
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() in IMAGE_EXTS and path.is_file():
                key = str(path.resolve())
                if key not in paths:
                    paths.append(key)
    return paths


def _rel_or_name(job_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(job_dir.resolve()))
    except Exception:
        return path.name


def list_media(job_dir: Path) -> Dict[str, List[str]]:
    stills: List[str] = []
    clips: List[str] = []
    for folder in (job_dir, job_dir / "boards", job_dir / "clips"):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            rel = _rel_or_name(job_dir, path)
            if path.suffix.lower() in IMAGE_EXTS:
                stills.append(rel)
            elif path.suffix.lower() in VIDEO_EXTS:
                clips.append(rel)
    return {"stills": stills, "clips": clips}


def load_edit(job_dir: Path) -> List[Dict[str, Any]]:
    target = job_dir / "edit.json"
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict) and isinstance(data.get("shots"), list):
        return [row for row in data["shots"] if isinstance(row, dict)]
    return []


def save_edit(job_dir: Path, rows: List[Dict[str, Any]]) -> None:
    (job_dir / "edit.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")


def ensure_edit_from_clips(job_dir: Path) -> List[Dict[str, Any]]:
    existing = load_edit(job_dir)
    if existing:
        return existing
    shots = load_shots(job_dir)
    rows: List[Dict[str, Any]] = []
    for shot in shots:
        clip = str(shot.get("clip") or "").strip()
        if clip:
            rows.append({"shot_id": shot.get("id"), "clip": clip})
    if not rows:
        for name in list_media(job_dir)["clips"]:
            rows.append({"shot_id": Path(name).stem, "clip": name})
    if rows:
        save_edit(job_dir, rows)
    return rows


async def render_board(
    job_dir: Path,
    shot_id: str,
    *,
    workflow_id: str = DEFAULT_BOARD_WORKFLOW_ID,
    wait: bool = False,
) -> Dict[str, Any]:
    shot = get_shot(job_dir, shot_id) or upsert_shot(job_dir, shot_id)
    prompt = str(
        shot.get("visual")
        or shot.get("h3_prompt")
        or shot.get("prompt")
        or shot.get("purpose")
        or ""
    ).strip()
    if not prompt:
        return {"status": "error", "error": "shot_prompt_missing"}
    wf = workflow_file_for_id(workflow_id or DEFAULT_BOARD_WORKFLOW_ID)
    if not wf:
        return {"status": "error", "error": f"workflow_missing:{workflow_id}"}
    host = await CapabilityRouter().host_for("stills")
    if not host:
        return {"status": "error", "error": "stills_host_unavailable", "message": "Connect a 3090 or Spark for boards."}
    out_dir = job_dir / "boards"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = ComfyUIClient(host)
    submit = await client.submit_prompt_for_shot(
        shot_id=f"{shot_id}_board",
        prompt=prompt,
        workflow_path=str(wf),
        output_dir=str(out_dir),
        wait_for_output=wait,
        width=1344,
        height=768,
    )
    updates: Dict[str, Any] = {
        "status": "boarding" if submit.get("queued") else ("boarded" if submit.get("status") == "success" else "failed"),
        "board_prompt_id": submit.get("prompt_id"),
        "board_host": host,
        "board_workflow_id": workflow_id,
        "board_error": submit.get("error") or "",
    }
    saved = [Path(p) for p in (submit.get("saved_files") or [])]
    if saved:
        dest = out_dir / f"{shot_id}{saved[0].suffix}"
        shutil.copy2(saved[0], dest)
        updates["still"] = _rel_or_name(job_dir, dest)
        updates["status"] = "boarded"
    upsert_shot(job_dir, shot_id, **updates)
    return {"status": submit.get("status") or "error", "shot": get_shot(job_dir, shot_id), **submit, "host": host}


async def render_take(
    job_dir: Path,
    shot_id: str,
    *,
    mode: str = "i2va",
    wait: bool = False,
    identity_pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    shot = get_shot(job_dir, shot_id) or upsert_shot(job_dir, shot_id)
    mode_key = str(mode or shot.get("h3_mode") or "i2va").strip().lower()
    workflow_id = take_workflow_for_mode(mode_key)
    wf = workflow_file_for_id(workflow_id)
    if not wf:
        return {"status": "error", "error": f"workflow_missing:{workflow_id}"}
    prompt = str(shot.get("h3_prompt") or shot.get("visual") or shot.get("purpose") or "").strip()
    if not prompt:
        return {"status": "error", "error": "shot_prompt_missing"}
    duration = int(shot.get("duration_sec") or 5)
    still = shot.get("still") or ""
    still_path = (job_dir / still).resolve() if still else None
    if still_path and not still_path.exists():
        still_path = None
    needs_still = mode_key not in {"t2va", "t2v"}
    if needs_still and not still_path:
        return {"status": "error", "error": "board_required", "message": "Approve a 3090 still before an H3 take, or use scout (t2va)."}
    refs = identity_paths_for_job(job_dir, identity_pack)
    image_paths: List[str] = []
    if mode_key in {"r2va", "r2v"}:
        image_paths = list(refs)
        if still_path:
            image_paths.append(str(still_path))
        if not image_paths:
            return {"status": "error", "error": "identity_refs_missing"}
        workflow_id = take_workflow_for_mode("r2va")
        wf = workflow_file_for_id(workflow_id) or wf
    elif mode_key in {"fl2va", "fl2v", "first_last"}:
        end_still = shot.get("end_still") or ""
        end_path = (job_dir / end_still).resolve() if end_still else None
        if still_path:
            image_paths.append(str(still_path))
        if end_path and end_path.exists():
            image_paths.append(str(end_path))
        else:
            return {"status": "error", "error": "end_frame_required"}
    elif still_path:
        image_paths = [str(still_path)]

    host = await CapabilityRouter().host_for_workflow(workflow_id, require_h3="h3" in workflow_id)
    if not host:
        return {"status": "error", "error": "spark_unavailable", "message": "H3 runs on Spark only."}
    out_dir = job_dir / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = ComfyUIClient(host)
    submit = await client.submit_prompt_for_shot(
        shot_id=f"{shot_id}_take",
        prompt=prompt,
        workflow_path=str(wf),
        output_dir=str(out_dir),
        image_paths=image_paths or None,
        wait_for_output=wait,
        duration=duration,
        fps=24,
        width=1344,
        height=768,
    )
    updates: Dict[str, Any] = {
        "status": "shooting" if submit.get("queued") else ("shot" if submit.get("status") == "success" else "failed"),
        "h3_mode": mode_key,
        "take_prompt_id": submit.get("prompt_id"),
        "take_host": host,
        "take_workflow_id": workflow_id,
        "take_error": submit.get("error") or "",
        "identity_ref_count": len(refs),
    }
    saved = [Path(p) for p in (submit.get("saved_files") or []) if Path(p).suffix.lower() in VIDEO_EXTS]
    if not saved:
        saved = [Path(p) for p in (submit.get("saved_files") or [])]
    if saved:
        dest = out_dir / f"{shot_id}{saved[0].suffix}"
        shutil.copy2(saved[0], dest)
        updates["clip"] = _rel_or_name(job_dir, dest)
        updates["status"] = "shot"
    upsert_shot(job_dir, shot_id, **updates)
    return {"status": submit.get("status") or "error", "shot": get_shot(job_dir, shot_id), **submit, "host": host}


def assemble_cut(job_dir: Path, *, rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    edit_rows = rows if rows is not None else ensure_edit_from_clips(job_dir)
    if rows is not None:
        save_edit(job_dir, edit_rows)
    clips: List[Path] = []
    for item in edit_rows:
        rel = str(item.get("clip") or "").strip()
        if not rel:
            continue
        path = (job_dir / rel).resolve()
        if path.exists():
            clips.append(path)
    if not clips:
        return {"status": "error", "error": "no_clips"}
    assembler = TimelineAssembler()
    out = job_dir / "cut.mp4"
    result = assembler.export_cut(clips, out, keep_audio=True)
    if result.get("ok"):
        (job_dir / "STATUS.md").write_text("edit — cut.mp4 assembled.\n", encoding="utf-8")
    return result


def set_shot_status(job_dir: Path, shot_id: str, status: str) -> Dict[str, Any]:
    shot = upsert_shot(job_dir, shot_id, status=status)
    return {"status": "ok", "shot": shot}
