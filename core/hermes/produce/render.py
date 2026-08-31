"""Real produce tools: board stills on 3090s, H3 takes on Spark, ffmpeg cut."""

from __future__ import annotations

import asyncio
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.assembly.timeline_assembler import TimelineAssembler
from core.character.identity_attach import resolve_anchor_paths
from core.dispatch.capability_router import CapabilityRouter
from core.dispatch.comfy_client import ComfyUIClient
from core.dispatch.model_catalog import (
    DEFAULT_STILLS_MODEL,
    DEFAULT_VIDEO_MODEL,
    board_workflow_id,
    family_has_mode,
    family_supports_scout,
    normalize_stills_model,
    normalize_video_model,
    workflow_for_take,
)
from core.dispatch.workflows import (
    DEFAULT_BOARD_WORKFLOW_ID,
    take_workflow_for_mode,
    workflow_file_for_id,
)

_JOB_LOCKS: Dict[str, asyncio.Lock] = {}

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


def _job_lock(job_dir: Path) -> asyncio.Lock:
    key = str(Path(job_dir).resolve())
    lock = _JOB_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _JOB_LOCKS[key] = lock
    return lock


def load_job_meta(job_dir: Path) -> Dict[str, Any]:
    target = Path(job_dir) / "job.json"
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def save_job_meta(job_dir: Path, meta: Dict[str, Any]) -> None:
    current = load_job_meta(job_dir)
    current.update(meta)
    (Path(job_dir) / "job.json").write_text(json.dumps(current, indent=2), encoding="utf-8")


def produce_mode(job_dir: Path) -> str:
    mode = str(load_job_meta(job_dir).get("produce_mode") or "shoot").strip().lower()
    return "scout" if mode == "scout" else "shoot"


def set_produce_mode(job_dir: Path, mode: str) -> str:
    value = "scout" if str(mode or "").strip().lower() == "scout" else "shoot"
    save_job_meta(job_dir, {"produce_mode": value})
    return value


def stills_model(job_dir: Path) -> str:
    return normalize_stills_model(str(load_job_meta(job_dir).get("stills_model") or DEFAULT_STILLS_MODEL))


def video_model(job_dir: Path) -> str:
    return normalize_video_model(str(load_job_meta(job_dir).get("video_model") or DEFAULT_VIDEO_MODEL))


def set_model_options(job_dir: Path, *, stills: str = "", video: str = "") -> Dict[str, str]:
    meta: Dict[str, str] = {}
    if stills:
        meta["stills_model"] = normalize_stills_model(stills)
    if video:
        meta["video_model"] = normalize_video_model(video)
    if meta:
        save_job_meta(job_dir, meta)
    return {"stills_model": stills_model(job_dir), "video_model": video_model(job_dir)}


def coerce_take_mode(job_dir: Path, mode: str) -> str:
    family = video_model(job_dir)
    key = str(mode or "i2va").strip().lower()
    if family_has_mode(family, key):
        return key
    for fallback in ("i2va", "t2va", "fl2va", "r2va"):
        if family_has_mode(family, fallback):
            return fallback
    return key


def resolve_take_mode(job_dir: Path, shot: Optional[Dict[str, Any]] = None, requested: str = "") -> str:
    """Scout is t2va when the video family has T2V. Shoot prefers FL2VA when an end still exists."""
    if produce_mode(job_dir) == "scout" and family_supports_scout(video_model(job_dir)):
        return coerce_take_mode(job_dir, "t2va")
    aliases = {
        "t2v": "t2va",
        "t2va": "t2va",
        "i2v": "i2va",
        "i2va": "i2va",
        "fl2v": "fl2va",
        "fl2va": "fl2va",
        "first_last": "fl2va",
        "r2v": "r2va",
        "r2va": "r2va",
    }
    req = str(requested or "").strip().lower()
    if req in aliases:
        return coerce_take_mode(job_dir, aliases[req])
    stored = str((shot or {}).get("h3_mode") or "").strip().lower()
    stored = aliases.get(stored, "")
    if stored in {"t2va", "r2va"}:
        return coerce_take_mode(job_dir, stored)
    if (shot or {}).get("end_still"):
        return coerce_take_mode(job_dir, "fl2va")
    if stored:
        return coerce_take_mode(job_dir, stored)
    return coerce_take_mode(job_dir, "i2va")


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
    seen_stills: set[str] = set()
    seen_clips: set[str] = set()
    if not job_dir.exists():
        return {"stills": stills, "clips": clips}
    for path in sorted(job_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = _rel_or_name(job_dir, path)
        if rel.startswith("identity/") or "/identity/" in rel.replace("\\", "/"):
            continue
        if rel.startswith("takes/") or "/takes/" in rel.replace("\\", "/"):
            continue
        if path.suffix.lower() in IMAGE_EXTS:
            if rel in seen_stills:
                continue
            seen_stills.add(rel)
            stills.append(rel)
        elif path.suffix.lower() in VIDEO_EXTS:
            if rel in seen_clips:
                continue
            seen_clips.add(rel)
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
            rows.append({
                "shot_id": shot.get("id"),
                "clip": clip,
                "muted": bool(shot.get("muted")),
                "trim_in": shot.get("trim_in") or 0,
                "trim_out": shot.get("trim_out") or 0,
            })
    if not rows:
        for name in list_media(job_dir)["clips"]:
            rows.append({"shot_id": Path(name).stem, "clip": name, "muted": False})
    if rows:
        save_edit(job_dir, rows)
    return rows


def _shot_prompt(shot: Dict[str, Any]) -> str:
    return str(
        shot.get("visual")
        or shot.get("h3_prompt")
        or shot.get("prompt")
        or shot.get("purpose")
        or ""
    ).strip()


def _guide_specs(job_dir: Path, shot: Dict[str, Any]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    raw = shot.get("guides") if isinstance(shot.get("guides"), list) else []
    for row in raw:
        if not isinstance(row, dict):
            continue
        image = str(row.get("image") or row.get("path") or row.get("image_path") or "").strip()
        if not image:
            continue
        path = Path(image)
        if not path.is_absolute():
            path = (Path(job_dir) / image).resolve()
        if not path.exists():
            continue
        try:
            frame_idx = int(row.get("frame_idx") if row.get("frame_idx") is not None else row.get("frame") or 0)
        except (TypeError, ValueError):
            frame_idx = 0
        specs.append({"frame_idx": max(0, frame_idx), "image_path": str(path)})
    return specs


def _voice_path(job_dir: Path, shot: Optional[Dict[str, Any]] = None) -> str:
    audio_exts = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
    rel = str((shot or {}).get("voice_ref") or "").strip()
    if rel:
        path = Path(rel)
        if not path.is_absolute():
            path = (Path(job_dir) / rel).resolve()
        if path.exists() and path.suffix.lower() in audio_exts:
            return str(path)
    identity = Path(job_dir) / "identity"
    if identity.exists():
        for path in sorted(identity.iterdir()):
            if path.suffix.lower() in audio_exts and path.is_file():
                return str(path.resolve())
    return ""


SHOT_PATCH_FIELDS = {
    "visual",
    "h3_prompt",
    "purpose",
    "duration_sec",
    "camera",
    "audio",
    "h3_mode",
    "still",
    "end_still",
    "voice_ref",
    "guides",
    "status",
    "seed",
    "negative_prompt",
    "review_status",
    "review_note",
    "imported_from",
}


def patch_shot(job_dir: Path, shot_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    updates = {k: v for k, v in fields.items() if k in SHOT_PATCH_FIELDS}
    if "duration_sec" in updates:
        try:
            updates["duration_sec"] = max(2, min(15, int(updates["duration_sec"])))
        except (TypeError, ValueError):
            updates.pop("duration_sec", None)
    return upsert_shot(job_dir, shot_id, **updates)


def list_identity(job_dir: Path) -> List[str]:
    names: List[str] = []
    for folder in identity_search_dirs(job_dir):
        if not folder.exists():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS | {".wav", ".mp3", ".flac", ".ogg", ".m4a"}:
                rel = _rel_or_name(job_dir, path)
                if rel not in names:
                    names.append(rel)
    return names


def save_upload(job_dir: Path, *, kind: str, filename: str, data: bytes) -> Dict[str, Any]:
    kind = str(kind or "identity").strip().lower()
    safe = Path(str(filename or "upload.bin").replace("..", "")).name
    if kind == "score":
        kind = "identity"
        if "music" not in safe.lower() and "bed" not in safe.lower() and "score" not in safe.lower():
            safe = "music-" + safe
    folders = {
        "identity": job_dir / "identity",
        "still": job_dir / "boards",
        "end_still": job_dir / "boards",
        "guide": job_dir / "boards",
        "voice": job_dir / "identity",
    }
    dest_dir = folders.get(kind, job_dir / "identity")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    dest.write_bytes(data)
    rel = _rel_or_name(job_dir, dest)
    return {"ok": True, "path": rel, "kind": kind}


def maybe_stitch_range(job_dir: Path, shot_id: str) -> Dict[str, Any]:
    shot = get_shot(job_dir, shot_id) or {}
    if not shot.get("stitch_pending"):
        return {"ok": False, "error": "not_pending"}
    orig_rel = str(shot.get("orig_clip") or "").strip()
    clip_rel = str(shot.get("clip") or "").strip()
    orig = (job_dir / orig_rel).resolve() if orig_rel else None
    middle = (job_dir / clip_rel).resolve() if clip_rel else None
    if not orig or not orig.exists() or not middle or not middle.exists():
        return {"ok": False, "error": "clips_missing"}
    if orig == middle:
        return {"ok": False, "error": "take_not_ready"}
    try:
        start = float(shot.get("range_start") or 0)
        end = float(shot.get("range_end") or 0)
    except (TypeError, ValueError):
        return {"ok": False, "error": "bad_range"}
    dest = job_dir / "clips" / f"{shot_id}_stitched.mp4"
    result = TimelineAssembler().stitch_range(orig, middle, start, end, dest)
    if result.get("ok"):
        rel = _rel_or_name(job_dir, dest)
        upsert_shot(job_dir, shot_id, clip=rel, stitch_pending=False, stitched=True)
        result["clip"] = rel
    return result


async def range_retake(
    job_dir: Path,
    shot_id: str,
    start_sec: float,
    end_sec: float,
    *,
    wait: bool = False,
) -> Dict[str, Any]:
    shot = get_shot(job_dir, shot_id)
    if not shot:
        return {"status": "error", "error": "shot_missing"}
    clip_rel = str(shot.get("clip") or "").strip()
    clip = (job_dir / clip_rel).resolve() if clip_rel else None
    if not clip or not clip.exists():
        return {"status": "error", "error": "clip_required"}
    start = max(0.0, float(start_sec))
    end = float(end_sec)
    if end <= start + 0.2:
        return {"status": "error", "error": "range_too_short"}
    assembler = TimelineAssembler()
    orig = job_dir / "clips" / f"{shot_id}_orig{clip.suffix}"
    if not orig.exists():
        shutil.copy2(clip, orig)
    in_path = job_dir / "boards" / f"{shot_id}_in.png"
    out_path = job_dir / "boards" / f"{shot_id}_out.png"
    first = assembler.extract_frame(clip, start, in_path)
    last = assembler.extract_frame(clip, end, out_path)
    if not first.get("ok") or not last.get("ok"):
        return {"status": "error", "error": first.get("error") or last.get("error") or "extract_failed"}
    duration = max(2, min(15, int(round(end - start))))
    upsert_shot(
        job_dir,
        shot_id,
        still=_rel_or_name(job_dir, in_path),
        end_still=_rel_or_name(job_dir, out_path),
        orig_clip=_rel_or_name(job_dir, orig),
        range_start=start,
        range_end=end,
        stitch_pending=True,
        duration_sec=duration,
        status="retake",
    )
    result = await render_take(job_dir, shot_id, mode="fl2va", wait=wait)
    return result


async def render_board(
    job_dir: Path,
    shot_id: str,
    *,
    workflow_id: str = "",
    wait: bool = False,
    host: str = "",
) -> Dict[str, Any]:
    shot = get_shot(job_dir, shot_id) or upsert_shot(job_dir, shot_id)
    prompt = _shot_prompt(shot)
    if not prompt:
        return {"status": "error", "error": "shot_prompt_missing"}
    camera = str(shot.get("camera") or "").strip()
    if camera:
        prompt = prompt + "\nCamera: " + camera
    chosen_wf = str(workflow_id or "").strip() or board_workflow_id(stills_model(job_dir))
    wf = workflow_file_for_id(chosen_wf or DEFAULT_BOARD_WORKFLOW_ID)
    if not wf:
        return {"status": "error", "error": f"workflow_missing:{chosen_wf}"}
    router = CapabilityRouter()
    chosen = str(host or "").strip()
    if chosen:
        probe = await router._probe(chosen)
        if not probe.get("ok"):
            return {
                "status": "error",
                "error": "stills_host_unavailable",
                "waiting": True,
                "host": chosen,
                "message": "3090 is offline. Queue item stays waiting.",
            }
    else:
        chosen = await router.host_for("stills")
    if not chosen:
        return {
            "status": "error",
            "error": "stills_host_unavailable",
            "waiting": True,
            "message": "Connect a 3090 or Spark for boards.",
        }
    out_dir = job_dir / "boards"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = ComfyUIClient(chosen)
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
        "board_host": chosen,
        "board_workflow_id": chosen_wf,
        "board_error": submit.get("error") or "",
    }
    saved = [Path(p) for p in (submit.get("saved_files") or [])]
    if saved:
        dest = out_dir / f"{shot_id}{saved[0].suffix}"
        shutil.copy2(saved[0], dest)
        updates["still"] = _rel_or_name(job_dir, dest)
        updates["status"] = "boarded"
    async with _job_lock(job_dir):
        upsert_shot(job_dir, shot_id, **updates)
    return {"status": submit.get("status") or "error", "shot": get_shot(job_dir, shot_id), **submit, "host": chosen}


async def render_boards(
    job_dir: Path,
    shot_ids: Optional[List[str]] = None,
    *,
    workflow_id: str = "",
    wait: bool = False,
) -> List[Dict[str, Any]]:
    """Paint boards in parallel across 3090 A/B."""
    if shot_ids:
        ids = [str(s).strip() for s in shot_ids if str(s).strip()]
    else:
        ids = [str(s.get("id") or "") for s in load_shots(job_dir) if s.get("id")]
    hosts = await CapabilityRouter().stills_hosts_for_batch()
    tasks = []
    for idx, shot_id in enumerate(ids):
        host = hosts[idx % len(hosts)] if hosts else ""
        tasks.append(render_board(job_dir, shot_id, workflow_id=workflow_id, wait=wait, host=host))
    if not tasks:
        return []
    return list(await asyncio.gather(*tasks))


async def render_take(
    job_dir: Path,
    shot_id: str,
    *,
    mode: str = "",
    wait: bool = False,
    identity_pack: Optional[Dict[str, Any]] = None,
    host: str = "",
) -> Dict[str, Any]:
    shot = get_shot(job_dir, shot_id) or upsert_shot(job_dir, shot_id)
    mode_key = resolve_take_mode(job_dir, shot, requested=mode)
    family = video_model(job_dir)
    workflow_id = workflow_for_take(family, mode_key)
    wf = workflow_file_for_id(workflow_id)
    if not wf:
        return {"status": "error", "error": f"workflow_missing:{workflow_id}"}
    prompt = str(shot.get("h3_prompt") or shot.get("visual") or shot.get("purpose") or "").strip()
    if not prompt:
        return {"status": "error", "error": "shot_prompt_missing"}
    camera = str(shot.get("camera") or "").strip()
    if camera:
        prompt = prompt + "\nCamera: " + camera
    guides = _guide_specs(job_dir, shot)
    duration = int(shot.get("duration_sec") or 5)
    still = shot.get("still") or ""
    still_path = (job_dir / still).resolve() if still else None
    if still_path and not still_path.exists():
        still_path = None
    needs_still = mode_key not in {"t2va", "t2v"}
    if needs_still and not still_path:
        return {"status": "error", "error": "board_required", "message": "Approve a 3090 still before a take, or pick a T2V family (H3 / LTX) for Scout."}
    refs = identity_paths_for_job(job_dir, identity_pack)
    image_paths: List[str] = []
    if mode_key in {"r2va", "r2v"}:
        image_paths = list(refs)
        if still_path:
            image_paths.append(str(still_path))
        if not image_paths:
            return {"status": "error", "error": "identity_refs_missing"}
        workflow_id = workflow_for_take(family, "r2va")
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

    voice_path = _voice_path(job_dir, shot)

    router = CapabilityRouter()
    chosen = str(host or "").strip()
    if chosen:
        probe = await router._probe(chosen)
        if not probe.get("ok"):
            return {
                "status": "error",
                "error": "spark_unavailable",
                "waiting": True,
                "host": chosen,
                "message": "Spark is offline. Queue item stays waiting.",
            }
    else:
        chosen = await router.host_for_workflow(workflow_id, require_h3="h3" in workflow_id or "minimax" in workflow_id)
    if not chosen:
        return {"status": "error", "error": "spark_unavailable", "waiting": True, "message": "Video runs on Spark only."}
    out_dir = job_dir / "clips"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = ComfyUIClient(chosen)
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
        guides=guides or None,
        audio_path=voice_path,
    )
    updates: Dict[str, Any] = {
        "status": "shooting" if submit.get("queued") else ("shot" if submit.get("status") == "success" else "failed"),
        "h3_mode": mode_key,
        "take_prompt_id": submit.get("prompt_id"),
        "take_host": chosen,
        "take_workflow_id": workflow_id,
        "take_error": submit.get("error") or "",
        "identity_ref_count": len(refs),
        "guide_count": len(guides),
        "voice_ref": _rel_or_name(job_dir, Path(voice_path)) if voice_path else "",
    }
    saved = [Path(p) for p in (submit.get("saved_files") or []) if Path(p).suffix.lower() in VIDEO_EXTS]
    if not saved:
        saved = [Path(p) for p in (submit.get("saved_files") or [])]
    if saved:
        dest = out_dir / f"{shot_id}{saved[0].suffix}"
        existing = get_shot(job_dir, shot_id) or {}
        old_clip = str(existing.get("clip") or "").strip()
        if old_clip:
            archive_take(job_dir, shot_id, old_clip)
        shutil.copy2(saved[0], dest)
        updates["clip"] = _rel_or_name(job_dir, dest)
        updates["status"] = "shot"
    async with _job_lock(job_dir):
        upsert_shot(job_dir, shot_id, **updates)
    if updates.get("clip"):
        maybe_stitch_range(job_dir, shot_id)
    return {"status": submit.get("status") or "error", "shot": get_shot(job_dir, shot_id), **submit, "host": chosen}


def assemble_cut(
    job_dir: Path,
    *,
    rows: Optional[List[Dict[str, Any]]] = None,
    color_pass: Optional[bool] = None,
) -> Dict[str, Any]:
    edit_rows = rows if rows is not None else ensure_edit_from_clips(job_dir)
    if rows is not None:
        save_edit(job_dir, edit_rows)
    assembler = TimelineAssembler()
    work = job_dir / ".trim"
    clips: List[Path] = []
    muted_paths: List[Path] = []
    for item in edit_rows:
        rel = str(item.get("clip") or "").strip()
        if not rel:
            continue
        path = (job_dir / rel).resolve()
        if not path.exists():
            continue
        try:
            trim_in = float(item.get("trim_in") or 0)
        except (TypeError, ValueError):
            trim_in = 0.0
        try:
            trim_out = float(item.get("trim_out") or 0)
        except (TypeError, ValueError):
            trim_out = 0.0
        use = path
        if trim_in > 0.04 or trim_out > trim_in + 0.04:
            dest = work / f"{path.stem}_{int(trim_in * 10)}_{int(trim_out * 10)}{path.suffix}"
            sliced = assembler.slice_clip(path, trim_in, trim_out if trim_out > 0 else None, dest)
            if sliced.get("ok"):
                use = Path(sliced["output"])
        clips.append(use)
        if item.get("muted"):
            muted_paths.append(use)
    if not clips:
        return {"ok": False, "status": "error", "error": "no_clips"}
    from core.hermes.produce import desk as produce_desk
    from core.hermes.produce import finish as produce_finish
    from core.hermes.produce import job_ops as produce_ops

    out = job_dir / "cut.mp4"
    if out.exists():
        produce_desk.archive_cut(job_dir)
    meta = load_job_meta(job_dir)
    transition = str(meta.get("transition") or "cut").strip().lower()
    result: Dict[str, Any]
    if transition in {"crossfade", "dissolve", "fade"} and len(clips) > 1:
        faded = job_dir / ".trim" / "xfade.mp4"
        faded.parent.mkdir(parents=True, exist_ok=True)
        xf = produce_finish.crossfade_concat(clips, faded, fade_sec=0.25)
        if xf.get("ok") and faded.exists():
            shutil.copy2(faded, out)
            result = {"ok": True, "output": str(out), "transition": "crossfade"}
        else:
            result = assembler.export_cut(clips, out, keep_audio=True, muted_paths=muted_paths)
            result["transition_fallback"] = xf.get("error") or "xfade_failed"
    else:
        result = assembler.export_cut(clips, out, keep_audio=True, muted_paths=muted_paths)
    preset = str(meta.get("color_preset") or "").strip().lower()
    if preset in {"off", "none", "false"}:
        preset = ""
    want_color = bool(meta.get("color_pass")) if color_pass is None else bool(color_pass)
    if preset in produce_finish.COLOR_PRESETS:
        want_color = True
    if result.get("ok") and want_color:
        graded = job_dir / "cut.grade.mp4"
        grade = assembler.color_pass(out, graded, preset=preset)
        if grade.get("ok"):
            shutil.copy2(graded, out)
            result["color_pass"] = True
            result["color_preset"] = preset or "mild"
        else:
            result["color_pass_error"] = grade.get("error")
    if result.get("ok"):
        produce_ops.write_captions(job_dir)
        aspect = str(meta.get("aspect") or "16:9")
        title = str(meta.get("title") or "")
        try:
            fade_sec = float(meta.get("fade_sec") or 0)
        except (TypeError, ValueError):
            fade_sec = 0.0
        music = produce_ops.find_music(job_dir)
        burn = bool(meta.get("burn_captions"))
        end_card = str(meta.get("end_card") or "").strip()
        srt = job_dir / "cut.srt"
        if aspect != "16:9" or title or music or fade_sec > 0.04 or burn or end_card:
            finished = job_dir / "cut_finish.mp4"
            fin = produce_finish.apply_finish(
                out,
                finished,
                aspect=aspect,
                title=title,
                music=music,
                fade_sec=fade_sec,
                color_preset="",
                burn_captions=burn,
                srt=srt if burn else None,
                end_card=end_card,
            )
            if fin.get("ok") and finished.exists():
                shutil.copy2(finished, out)
                result["finish"] = {k: v for k, v in fin.items() if k != "steps"}
                result["finish"]["steps_ok"] = {
                    name: bool(step.get("ok")) for name, step in (fin.get("steps") or {}).items()
                }
        produce_desk.write_audio_manifest(job_dir)
        last = {
            "ok": True,
            "transition": transition,
            "color_pass": bool(result.get("color_pass")),
            "color_preset": result.get("color_preset") or preset,
            "color_pass_error": result.get("color_pass_error") or "",
            "burn_captions": burn,
            "end_card": end_card,
            "finish": result.get("finish") or {},
        }
        save_job_meta(job_dir, {"last_assemble": last, "status": "ready", "stage": "edit"})
        (job_dir / "STATUS.md").write_text("edit — cut.mp4 assembled.\n", encoding="utf-8")
        try:
            from core.hermes.produce import queue as produce_queue
            for item in produce_queue.load_queue(job_dir):
                if item.get("action") == "assemble" and item.get("status") in {"pending", "waiting_for_host", "running"}:
                    produce_queue.mark_done(job_dir, str(item.get("id") or ""), host="local")
        except Exception:
            pass
    return result


def set_shot_status(job_dir: Path, shot_id: str, status: str) -> Dict[str, Any]:
    shot = upsert_shot(job_dir, shot_id, status=status)
    return {"status": "ok", "shot": shot}


def archive_take(job_dir: Path, shot_id: str, clip_rel: str) -> str:
    src = Path(job_dir) / str(clip_rel or "")
    if not src.exists() or not src.is_file():
        return ""
    dest_dir = Path(job_dir) / "takes" / str(shot_id or "shot")
    dest_dir.mkdir(parents=True, exist_ok=True)
    n = len([p for p in dest_dir.iterdir() if p.is_file()]) + 1
    dest = dest_dir / f"{n:03d}{src.suffix}"
    shutil.copy2(src, dest)
    return _rel_or_name(job_dir, dest)


def list_takes(job_dir: Path) -> List[Dict[str, str]]:
    root = Path(job_dir) / "takes"
    if not root.exists():
        return []
    rows: List[Dict[str, str]] = []
    for shot_dir in sorted(root.iterdir()):
        if not shot_dir.is_dir():
            continue
        for path in sorted(shot_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
                rows.append({"shot_id": shot_dir.name, "clip": _rel_or_name(job_dir, path)})
    return rows


def restore_take(job_dir: Path, shot_id: str, clip_rel: str) -> Dict[str, Any]:
    src = Path(job_dir) / str(clip_rel or "")
    if not src.exists():
        return {"ok": False, "error": "take_missing"}
    current = get_shot(job_dir, shot_id) or {}
    old = str(current.get("clip") or "").strip()
    if old and (Path(job_dir) / old).resolve() != src.resolve() and (Path(job_dir) / old).exists():
        archive_take(job_dir, shot_id, old)
    dest = Path(job_dir) / "clips" / f"{shot_id}{src.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    rel = _rel_or_name(job_dir, dest)
    upsert_shot(job_dir, shot_id, clip=rel, status="shot")
    edit = load_edit(job_dir)
    found = False
    for row in edit:
        if str(row.get("shot_id") or "") == shot_id:
            row["clip"] = rel
            found = True
    if not found:
        edit.append({"shot_id": shot_id, "clip": rel, "muted": False})
    save_edit(job_dir, edit)
    return {"ok": True, "clip": rel, "shot": get_shot(job_dir, shot_id)}


def export_package(job_dir: Path) -> Dict[str, Any]:
    job_dir = Path(job_dir)
    dest = job_dir / "handoff.zip"
    names = [
        "prompt.md", "story.md", "script.md", "storyboard.md", "shots.json",
        "edit.json", "STATUS.md", "job.json", "queue.json", "cut.mp4",
        "cut.srt", "comments.json", "cut_finish.mp4",
        "review_log.jsonl", "ab_log.jsonl", "handoffs.json", "audio_manifest.json",
    ]
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            path = job_dir / name
            if path.exists():
                zf.write(path, name)
        for folder in ("boards", "clips", "identity", "takes", "cuts"):
            root = job_dir / folder
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file():
                    zf.write(path, str(path.relative_to(job_dir)))
    return {"ok": True, "file": "handoff.zip", "bytes": dest.stat().st_size}
