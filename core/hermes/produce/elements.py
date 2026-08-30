"""Persistent character / location / voice elements for Produce."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from core.cinesmith_env import repo_root

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def elements_dir(root: Path | None = None) -> Path:
    path = (root or repo_root()) / "data" / "elements"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(root: Path | None = None) -> Path:
    return elements_dir(root) / "elements.json"


def load_elements(root: Path | None = None) -> List[Dict[str, Any]]:
    target = _index_path(root)
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = data.get("elements") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def save_elements(rows: List[Dict[str, Any]], root: Path | None = None) -> None:
    _index_path(root).write_text(json.dumps({"elements": rows}, indent=2), encoding="utf-8")


def add_element(kind: str, filename: str, data: bytes, *, label: str = "", root: Path | None = None) -> Dict[str, Any]:
    kind = str(kind or "character").strip().lower()
    if kind not in {"character", "location", "voice"}:
        kind = "character"
    safe = Path(str(filename or "upload.bin").replace("..", "")).name
    dest_dir = elements_dir(root) / kind
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe
    dest.write_bytes(data)
    rel = f"{kind}/{safe}"
    rows = load_elements(root)
    item = {
        "id": f"{kind}-{safe}",
        "kind": kind,
        "file": rel,
        "label": (label or Path(safe).stem).strip(),
    }
    rows = [row for row in rows if row.get("id") != item["id"]]
    rows.append(item)
    save_elements(rows, root)
    return item


def attach_to_job(job_dir: Path, element_ids: List[str], *, root: Path | None = None) -> List[str]:
    wanted = {str(x) for x in (element_ids or []) if str(x).strip()}
    copied: List[str] = []
    ident = Path(job_dir) / "identity"
    ident.mkdir(parents=True, exist_ok=True)
    for row in load_elements(root):
        if row.get("id") not in wanted:
            continue
        src = elements_dir(root) / str(row.get("file") or "")
        if not src.exists():
            continue
        dest = ident / src.name
        shutil.copy2(src, dest)
        copied.append(f"identity/{dest.name}")
    return copied
