"""Multi-file reference upload helpers for character banks and asset vault.

Filesystem-only helpers used by dashboard multi-upload endpoints.
"""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.character.identity_attach import infer_reference_type

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}
FONT_EXTS = {".ttf", ".otf", ".woff", ".woff2"}
DOC_EXTS = {".pdf"}
CHARACTER_REF_EXTS = IMAGE_EXTS | VIDEO_EXTS
ASSET_REF_EXTS = IMAGE_EXTS | FONT_EXTS | DOC_EXTS | {".bin"}


def _slug(value: str, *, fallback: str = "asset") -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower().strip()).strip("_")
    return (slug[:80] if slug else fallback) or fallback


def save_character_reference_bytes(
    *,
    char_id: str,
    filename: str,
    content: bytes,
    banks_dir: Path,
    reference_type: str = "auto",
    notes: str = "",
    stamp: Optional[int] = None,
) -> Dict[str, Any]:
    """Write one character reference under data/character_banks/references/{char_id}/."""
    cid = _slug(char_id, fallback="character")
    ext = Path(filename or "").suffix.lower() or ".jpg"
    if ext not in CHARACTER_REF_EXTS:
        raise ValueError(f"Unsupported character reference type: {ext or '(none)'}")
    inferred = (
        reference_type
        if reference_type and reference_type != "auto"
        else infer_reference_type(filename or "")
    )
    ref_dir = Path(banks_dir) / "references" / cid
    ref_dir.mkdir(parents=True, exist_ok=True)
    ts = int(stamp if stamp is not None else time.time())
    # uniqueness when batching many files in the same second
    ref_id = f"{inferred}_{ts}_{uuid.uuid4().hex[:6]}"
    dest = ref_dir / f"{ref_id}{ext}"
    dest.write_bytes(content)
    url = f"/api/characters/reference/{cid}/{dest.name}"
    return {
        "id": ref_id,
        "url": url,
        "type": inferred,
        "source": "upload",
        "notes": str(notes or ""),
        "filename": dest.name,
        "path": str(dest),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def save_asset_vault_reference_bytes(
    *,
    package_id: str,
    filename: str,
    content: bytes,
    media_root: Path,
    asset_type: str = "reference",
    name: str = "",
    prompt: str = "",
) -> Tuple[Dict[str, Any], Path]:
    """Write one Asset Vault reference under MEDIA_ROOT/asset_vault/{package_id}/."""
    pid = _slug(package_id, fallback="package")
    upload_name = _slug(Path(filename or "asset").stem, fallback="asset")
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ASSET_REF_EXTS:
        suffix = ".bin"
    out_dir = Path(media_root) / "asset_vault" / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{upload_name}_{uuid.uuid4().hex[:8]}{suffix}"
    out_path.write_bytes(content)
    ref = {
        "id": _slug(f"{asset_type}_{upload_name}_{uuid.uuid4().hex[:6]}", fallback="ref"),
        "type": str(asset_type or "reference").strip().lower() or "reference",
        "name": (name or Path(filename or "Asset").stem)[:90],
        "url": "",  # filled by caller once media URL helper is available
        "prompt": str(prompt or "")[:360],
        "notes": "",
        "path": str(out_path),
        "filename": out_path.name,
    }
    return ref, out_path


def merge_character_uploads(
    character: Dict[str, Any],
    uploads: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Append upload records onto a character profile dict (mutates a copy)."""
    out = dict(character or {})
    existing = [r for r in out.get("reference_uploads", []) if isinstance(r, dict)]
    for rec in uploads:
        if not isinstance(rec, dict):
            continue
        existing.append({
            "id": rec.get("id"),
            "url": rec.get("url"),
            "type": rec.get("type") or "reference",
            "source": rec.get("source") or "upload",
            "notes": rec.get("notes") or "",
            "created_at": rec.get("created_at") or "",
        })
        ext = Path(str(rec.get("filename") or rec.get("url") or "")).suffix.lower()
        if not out.get("anchor_url") and ext in IMAGE_EXTS and rec.get("url"):
            out["anchor_url"] = rec["url"]
    out["reference_uploads"] = existing
    return out


def list_batch_errors(errors: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [e for e in errors if isinstance(e, dict)]
