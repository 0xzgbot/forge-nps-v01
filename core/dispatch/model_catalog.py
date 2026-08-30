"""Produce model families: Spark video vs 3090 stills, plus dropped open-weight graphs.

Defaults stay MiniMax H3 (Spark) and Flux 2 (3090s). Any Comfy API graph dropped in
workflows/ that is not already in a family shows up as a custom option.
Video families never route to a 3090. Stills never use an H3 graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from core.dispatch.workflows import (
    DEFAULT_BOARD_WORKFLOW_ID,
    DEFAULT_FIRST_LAST_WORKFLOW_ID,
    DEFAULT_REF_VIDEO_WORKFLOW_ID,
    DEFAULT_TEXT_VIDEO_WORKFLOW_ID,
    DEFAULT_VIDEO_WORKFLOW_ID,
    VIDEO_WORKFLOW_FILE_ALIASES,
    WORKFLOWS_DIR,
    capability_for_workflow,
    workflow_file_for_id,
)

DEFAULT_STILLS_MODEL = "flux2"
DEFAULT_VIDEO_MODEL = "h3"

SKIP_CUSTOM_MARKERS = ("acestep", "audio", "tts", "music", "sufi")

STILLS_FAMILIES: List[Dict[str, Any]] = [
    {
        "id": "flux2",
        "label": "Flux 2",
        "host": "3090s",
        "note": "Default boards. Fits a 24GB 3090.",
        "workflows": {"t2i": "01_flux2_text_to_image", "i2i": "03_flux2_image_to_image"},
    },
    {
        "id": "flux2_turbo",
        "label": "Flux 2 Turbo",
        "host": "3090s",
        "note": "Faster Flux boards.",
        "workflows": {"t2i": "02_flux2_text_to_image_turbo"},
    },
    {
        "id": "flux2_klein",
        "label": "Flux Klein 9B",
        "host": "3090s",
        "note": "Smaller Flux for tight VRAM.",
        "workflows": {"t2i": "05_flux2_klein_9b_text_to_image"},
    },
    {
        "id": "z_image",
        "label": "Z-Image",
        "host": "3090s",
        "note": "Install the Z-Image weights on the 3090s.",
        "workflows": {"t2i": "07_z_image"},
    },
    {
        "id": "z_image_turbo",
        "label": "Z-Image Turbo",
        "host": "3090s",
        "note": "Faster Z-Image.",
        "workflows": {"t2i": "06_z_image_turbo"},
    },
    {
        "id": "ernie",
        "label": "ERNIE Image",
        "host": "3090s",
        "note": "Open-weight stills alternative.",
        "workflows": {"t2i": "17_image_ernie_image"},
    },
    {
        "id": "ernie_turbo",
        "label": "ERNIE Image Turbo",
        "host": "3090s",
        "note": "Faster ERNIE stills.",
        "workflows": {"t2i": "16_image_ernie_image_turbo"},
    },
    {
        "id": "flux2_sheet",
        "label": "Flux character sheet",
        "host": "3090s",
        "note": "Multi-ref sheet when you need turnarounds.",
        "workflows": {"t2i": "04_flux2_multi_reference_character_sheet"},
    },
]

VIDEO_FAMILIES: List[Dict[str, Any]] = [
    {
        "id": "h3",
        "label": "MiniMax H3",
        "host": "spark",
        "note": "Default takes. Native stereo. Spark only — never a 3090.",
        "modes": {
            "t2va": DEFAULT_TEXT_VIDEO_WORKFLOW_ID,
            "i2va": DEFAULT_VIDEO_WORKFLOW_ID,
            "fl2va": DEFAULT_FIRST_LAST_WORKFLOW_ID,
            "r2va": DEFAULT_REF_VIDEO_WORKFLOW_ID,
        },
    },
    {
        "id": "ltx23",
        "label": "LTX 2.3",
        "host": "spark",
        "note": "Open-weight Spark video. Drop LTX weights on Spark.",
        "modes": {
            "t2va": "09_ltx23_text_to_video",
            "i2va": "11_ltx23_image_to_video",
            "fl2va": "12_ltx23_first_last_frame_to_video",
            "r2va": "13_ltx23_id_lora",
        },
    },
    {
        "id": "ltx23_fp8",
        "label": "LTX 2.3 NVFP4",
        "host": "spark",
        "note": "Quantized LTX I2V if you installed the FP8/NVFP4 graph.",
        "modes": {"i2va": "14_ltx23_i2v_nvfp4"},
    },
    {
        "id": "wan22",
        "label": "Wan 2.2",
        "host": "spark",
        "note": "I2V only. Scout will board first, then take.",
        "modes": {"i2va": "15_wan2_2_i2v"},
    },
]


def _known_workflow_ids() -> set[str]:
    ids: set[str] = {
        "08_flux2_klein_9b_text_to_image",
    }
    for fam in STILLS_FAMILIES:
        ids.update(str(v) for v in (fam.get("workflows") or {}).values())
    for fam in VIDEO_FAMILIES:
        ids.update(str(v) for v in (fam.get("modes") or {}).values())
    ids.update(VIDEO_WORKFLOW_FILE_ALIASES.keys())
    ids.update(VIDEO_WORKFLOW_FILE_ALIASES.values())
    return ids


def _skip_custom(stem: str) -> bool:
    low = stem.lower()
    if any(token in low for token in SKIP_CUSTOM_MARKERS):
        return True
    if stem in _known_workflow_ids():
        return True
    return False


def _custom_families() -> List[Dict[str, Any]]:
    if not WORKFLOWS_DIR.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(WORKFLOWS_DIR.glob("*.json")):
        stem = path.stem
        if stem.endswith("_api"):
            stem = stem[: -len("_api")]
        if _skip_custom(stem):
            continue
        cap = capability_for_workflow(stem)
        if cap == "spark":
            rows.append(
                {
                    "id": f"custom_{stem}",
                    "label": stem.replace("_", " "),
                    "host": "spark",
                    "note": "Open-weight graph you dropped in workflows/.",
                    "custom": True,
                    "modes": {"t2va": stem, "i2va": stem, "fl2va": stem, "r2va": stem},
                    "capability": "spark",
                }
            )
        else:
            rows.append(
                {
                    "id": f"custom_{stem}",
                    "label": stem.replace("_", " "),
                    "host": "3090s",
                    "note": "Open-weight stills graph you dropped in workflows/.",
                    "custom": True,
                    "workflows": {"t2i": stem},
                    "capability": "stills",
                }
            )
    return rows


def _enrich(fam: Dict[str, Any], *, kind: str) -> Dict[str, Any]:
    row = dict(fam)
    row["kind"] = kind
    row["capability"] = "spark" if kind == "video" else "stills"
    ids: List[str] = []
    if kind == "video":
        ids = [str(v) for v in (row.get("modes") or {}).values() if v]
        row["mode_list"] = sorted({k for k in (row.get("modes") or {}) if k})
        row["supports_scout"] = "t2va" in (row.get("modes") or {})
    else:
        ids = [str(v) for v in (row.get("workflows") or {}).values() if v]
        row["supports_scout"] = False
        row["mode_list"] = []
    available = False
    missing: List[str] = []
    for wid in ids:
        if workflow_file_for_id(wid):
            available = True
        else:
            missing.append(wid)
    row["available"] = available
    row["missing_workflows"] = missing
    row["workflow_ids"] = ids
    return row


def list_stills_models() -> List[Dict[str, Any]]:
    rows = [_enrich(fam, kind="stills") for fam in STILLS_FAMILIES]
    rows.extend(_enrich(fam, kind="stills") for fam in _custom_families() if fam.get("capability") == "stills")
    return rows


def list_video_models() -> List[Dict[str, Any]]:
    rows = [_enrich(fam, kind="video") for fam in VIDEO_FAMILIES]
    rows.extend(_enrich(fam, kind="video") for fam in _custom_families() if fam.get("capability") == "spark")
    return rows


def catalog() -> Dict[str, Any]:
    return {
        "stills": list_stills_models(),
        "video": list_video_models(),
        "defaults": {"stills_model": DEFAULT_STILLS_MODEL, "video_model": DEFAULT_VIDEO_MODEL},
        "hint": "Drop a Comfy API graph in workflows/ to add an open-weight option. Video stays on Spark. Boards stay on the 3090s.",
    }


def get_family(model_id: str, *, kind: str) -> Optional[Dict[str, Any]]:
    wanted = str(model_id or "").strip()
    pool = list_video_models() if kind == "video" else list_stills_models()
    for row in pool:
        if row.get("id") == wanted:
            return row
    default_id = DEFAULT_VIDEO_MODEL if kind == "video" else DEFAULT_STILLS_MODEL
    for row in pool:
        if row.get("id") == default_id:
            return row
    return pool[0] if pool else None


def normalize_stills_model(model_id: str = "") -> str:
    fam = get_family(model_id, kind="stills")
    return str((fam or {}).get("id") or DEFAULT_STILLS_MODEL)


def normalize_video_model(model_id: str = "") -> str:
    fam = get_family(model_id, kind="video")
    return str((fam or {}).get("id") or DEFAULT_VIDEO_MODEL)


def board_workflow_id(model_id: str = "") -> str:
    fam = get_family(model_id, kind="stills") or {}
    workflows = fam.get("workflows") or {}
    return str(workflows.get("t2i") or workflows.get("i2i") or DEFAULT_BOARD_WORKFLOW_ID)


def workflow_for_take(model_id: str = "", mode: str = "") -> str:
    fam = get_family(model_id, kind="video") or {}
    modes = fam.get("modes") or {}
    key = str(mode or "i2va").strip().lower()
    aliases = {"t2v": "t2va", "i2v": "i2va", "fl2v": "fl2va", "first_last": "fl2va", "r2v": "r2va"}
    key = aliases.get(key, key)
    if key in modes:
        return str(modes[key])
    for fallback in ("i2va", "t2va", "fl2va", "r2va"):
        if fallback in modes:
            return str(modes[fallback])
    return DEFAULT_VIDEO_WORKFLOW_ID


def family_has_mode(model_id: str, mode: str) -> bool:
    fam = get_family(model_id, kind="video") or {}
    key = str(mode or "").strip().lower()
    aliases = {"t2v": "t2va", "i2v": "i2va", "fl2v": "fl2va", "first_last": "fl2va", "r2v": "r2va"}
    key = aliases.get(key, key)
    return key in (fam.get("modes") or {})


def family_supports_scout(model_id: str) -> bool:
    fam = get_family(model_id, kind="video") or {}
    return bool(fam.get("supports_scout"))
