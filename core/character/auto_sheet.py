"""Auto character sheet from one photo — continuity pack helpers (F3).

Filesystem-safe pure helpers used by dashboard auto-sheet endpoints.
No Spark/network imports so offline unit tests stay hermetic.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}

# Standard Cinesmith sheet layout: 6 panels, wide 3×2
DEFAULT_SHEET_ROWS = 2
DEFAULT_SHEET_COLS = 3

SPARK_OFFLINE_RECOVERY_HINT = (
    "Master reference saved offline. Start Spark/ComfyUI (COMFYUI_PRIMARY), "
    "then re-run Sheet from photo or Generate Character Sheet on this character "
    "to build the multi-panel continuity pack."
)

SPARK_NOT_CONFIGURED_HINT = (
    "Master reference saved. Configure COMFYUI_PRIMARY / turn on Spark, "
    "then re-run Sheet from photo to generate the multi-panel continuity sheet."
)

NO_REFERENCE_HINT = (
    "Character has no usable face/body photo yet. Drop one photo, then Cinesmith "
    "can lock identity and generate a multi-panel character sheet when Spark is up."
)


def slug_character_id(value: str, *, fallback: str = "character") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower().strip()).strip("_")
    return (slug[:80] if slug else fallback) or fallback


def name_from_filename(filename: str, *, fallback: str = "New Character") -> str:
    """Derive a display name from an uploaded photo filename."""
    stem = Path(filename or "").stem
    clean = re.sub(r"[_\-.]+", " ", stem or "").strip()
    clean = re.sub(r"\s+", " ", clean)
    if not clean or clean.lower() in {"image", "photo", "img", "dsc", "untitled"}:
        return fallback
    # Drop trailing camera-style numbers like IMG_1234
    clean = re.sub(r"\b(img|dsc|photo|pic|image)\s*\d+\b", "", clean, flags=re.I).strip()
    clean = re.sub(r"\s+\d{3,}$", "", clean).strip()
    if not clean:
        return fallback
    return clean[:80].title()


def clamp_grid(rows: Any = None, cols: Any = None) -> Tuple[int, int]:
    """Clamp extract grid to safe bounds (1–4). Defaults match 3×2 sheet."""
    try:
        r = int(rows if rows is not None else DEFAULT_SHEET_ROWS)
    except (TypeError, ValueError):
        r = DEFAULT_SHEET_ROWS
    try:
        c = int(cols if cols is not None else DEFAULT_SHEET_COLS)
    except (TypeError, ValueError):
        c = DEFAULT_SHEET_COLS
    return max(1, min(r, 4)), max(1, min(c, 4))


def build_auto_sheet_prompt(
    *,
    name: str = "",
    role: str = "",
    user_prompt: str = "",
) -> str:
    """Default multi-panel continuity sheet direction (Hermes identity lock)."""
    identity = ", ".join(
        part for part in [
            str(name or "").strip() or "the character",
            str(role or "").strip(),
            str(user_prompt or "").strip(),
        ]
        if part
    )
    return (
        "professional multi-angle character continuity sheet for Hermes identity lock. "
        f"Character: {identity}. "
        "Match the supplied face/body reference photo exactly — same person, age, face, "
        "hair, body proportions, skin tone, and wardrobe cues. "
        "3840x2160 horizontal 16:9, six large panels in a wide 3-by-2 layout, clean studio background."
    )


def master_ref_from_upload(
    upload: Dict[str, Any],
    *,
    notes: str = "auto-sheet master photo",
    locked: bool = True,
) -> Dict[str, Any]:
    """Promote a reference upload record into a master_references entry."""
    url = str(upload.get("url") or "").strip()
    ref_type = str(upload.get("type") or "face_closeup").strip() or "face_closeup"
    if ref_type in {"reference", "auto"}:
        ref_type = "face_closeup"
    ref_id = str(upload.get("id") or f"master_{int(time.time())}")
    if not ref_id.startswith("master_"):
        ref_id = f"master_{ref_id}"
    return {
        "id": ref_id,
        "url": url,
        "type": ref_type,
        "source": "auto_sheet_photo",
        "locked": bool(locked),
        "score": int(upload.get("score") or 0),
        "prompt_id": str(upload.get("prompt_id") or ""),
        "notes": str(notes or upload.get("notes") or "auto-sheet master photo"),
        "created_at": str(
            upload.get("created_at")
            or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        ),
    }


def apply_photo_to_character(
    character: Dict[str, Any],
    upload: Dict[str, Any],
    *,
    notes: str = "auto-sheet master photo",
) -> Dict[str, Any]:
    """
    Merge one photo upload into character continuity pack:
    - append reference_uploads
    - promote to master_references (front, max 5)
    - set anchor_url when empty
    """
    out = dict(character or {})
    url = str(upload.get("url") or "").strip()
    if not url:
        return out

    # reference_uploads
    uploads = [r for r in (out.get("reference_uploads") or []) if isinstance(r, dict)]
    upload_rec = {
        "id": upload.get("id"),
        "url": url,
        "type": upload.get("type") or "face_closeup",
        "source": upload.get("source") or "auto_sheet_photo",
        "notes": notes or upload.get("notes") or "",
        "created_at": upload.get("created_at") or "",
    }
    if not any(r.get("url") == url for r in uploads):
        uploads.append(upload_rec)
    out["reference_uploads"] = uploads

    # master_references
    masters = [r for r in (out.get("master_references") or []) if isinstance(r, dict)]
    masters = [r for r in masters if r.get("url") != url]
    masters.insert(0, master_ref_from_upload(upload, notes=notes))
    out["master_references"] = masters[:5]

    # anchor when empty (image only)
    ext = Path(str(upload.get("filename") or upload.get("url") or "")).suffix.lower()
    if not out.get("anchor_url") and (not ext or ext in IMAGE_EXTS):
        out["anchor_url"] = url

    if out.get("status") in (None, "", "draft") and len(out.get("master_references") or []) >= 1:
        # Photo lock is a continuity step; keep draft until more refs unless already approved
        out.setdefault("status", "draft")

    return out


def spark_recovery_hint(*, configured: bool = True, has_reference: bool = True) -> str:
    if not has_reference:
        return NO_REFERENCE_HINT
    if not configured:
        return SPARK_NOT_CONFIGURED_HINT
    return SPARK_OFFLINE_RECOVERY_HINT


def build_auto_sheet_result(
    *,
    status: str,
    character_id: str,
    character: Optional[Dict[str, Any]] = None,
    master_reference: Optional[Dict[str, Any]] = None,
    spark_available: bool = False,
    spark_configured: bool = True,
    prompt_id: str = "",
    job_set_id: str = "",
    image_urls: Optional[Sequence[str]] = None,
    sheet_url: str = "",
    panels: Optional[Sequence[Dict[str, Any]]] = None,
    prompt: str = "",
    rows: int = DEFAULT_SHEET_ROWS,
    cols: int = DEFAULT_SHEET_COLS,
    message: str = "",
    recovery_hint: str = "",
    error: str = "",
    created: bool = False,
) -> Dict[str, Any]:
    """Unified API payload for auto-sheet endpoints."""
    images = [str(u) for u in (image_urls or []) if str(u or "").strip()]
    primary_sheet = str(sheet_url or (images[0] if images else "")).strip()
    pid = str(prompt_id or job_set_id or "").strip()
    jid = str(job_set_id or prompt_id or "").strip()

    clean_status = str(status or "error").strip().lower()
    if clean_status not in {"complete", "partial", "queued", "error"}:
        clean_status = "error"

    has_ref = bool(
        master_reference
        or (character and (
            character.get("anchor_url")
            or character.get("master_references")
            or character.get("reference_uploads")
        ))
    )
    hint = recovery_hint
    if clean_status == "partial" and not hint:
        hint = spark_recovery_hint(configured=spark_configured, has_reference=has_ref)

    if not message:
        if clean_status == "complete":
            message = "Character sheet generated and continuity pack updated."
        elif clean_status == "partial":
            message = "Photo locked as master reference. Sheet render skipped (Spark offline)."
        elif clean_status == "queued":
            message = "Character sheet submitted to Spark."
        else:
            message = error or "Auto sheet failed."

    return {
        "status": clean_status,
        "character_id": character_id,
        "character": character,
        "created": bool(created),
        "master_reference": master_reference,
        "spark_available": bool(spark_available),
        "spark_configured": bool(spark_configured),
        "prompt_id": pid,
        "job_set_id": jid,
        "image_urls": images,
        "sheet_url": primary_sheet,
        "panels": list(panels or []),
        "prompt": prompt,
        "rows": int(rows),
        "cols": int(cols),
        "message": message,
        "recovery_hint": hint,
        "error": error,
    }


def draft_character_record(
    *,
    char_id: str,
    name: str = "",
    role: str = "Character",
    description: str = "",
    accent: str = "cyan",
) -> Dict[str, Any]:
    """Minimal character dict for create-from-photo path (before dashboard normalize)."""
    cid = slug_character_id(char_id)
    display = (name or cid.replace("_", " ")).strip() or cid
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "id": cid,
        "name": display,
        "role": (role or "Character")[:60],
        "description": description or role or "",
        "bio": description or role or "",
        "accent": accent,
        "score": 0,
        "status": "draft",
        "anchor_url": "",
        "anchor_prompt": f"Portrait of {display}, {role or 'character'}",
        "dna": {},
        "master_references": [],
        "reference_uploads": [],
        "character_sheets": [],
        "sheet_panels": [],
        "created_at": now,
    }


def pick_sheet_url_from_render(render_result: Dict[str, Any]) -> str:
    """Extract primary sheet image URL from api_character_spark_render payload."""
    if not isinstance(render_result, dict):
        return ""
    images = render_result.get("image_urls") if isinstance(render_result.get("image_urls"), list) else []
    for url in images:
        clean = str(url or "").strip()
        if clean:
            return clean
    return str(render_result.get("anchor_url") or "").strip()


def list_sheet_urls(character: Dict[str, Any]) -> List[str]:
    """Collect known sheet image URLs from a character pack."""
    urls: List[str] = []
    seen: set[str] = set()

    def add(url: Any) -> None:
        clean = str(url or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            urls.append(clean)

    for sheet in character.get("character_sheets") or []:
        if isinstance(sheet, dict):
            add(sheet.get("url"))
        else:
            add(sheet)
    for asset in character.get("candidate_assets") or []:
        if isinstance(asset, dict) and str(asset.get("type") or "") == "sheet":
            add(asset.get("url"))
            for u in asset.get("all_urls") or []:
                add(u)
    for entry in character.get("render_history") or []:
        if isinstance(entry, dict) and str(entry.get("type") or "") == "sheet":
            for u in entry.get("image_urls") or []:
                add(u)
    return urls
