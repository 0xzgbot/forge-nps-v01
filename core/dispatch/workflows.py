"""Workflow catalog and file resolver for Spark / 3090 Comfy graphs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / "workflows"

DEFAULT_BOARD_WORKFLOW_ID = "01_flux2_text_to_image"
DEFAULT_VIDEO_WORKFLOW_ID = "21_minimax_h3_image_to_video"
DEFAULT_TEXT_VIDEO_WORKFLOW_ID = "20_minimax_h3_text_to_video"
DEFAULT_FIRST_LAST_WORKFLOW_ID = "22_minimax_h3_first_last_frame_to_video"
DEFAULT_REF_VIDEO_WORKFLOW_ID = "23_minimax_h3_reference_to_video"
LTX_DRAFT_I2V_WORKFLOW_ID = "04_ltx2.3_image_to_video"
LTX_DRAFT_T2V_WORKFLOW_ID = "09_ltx23_text_to_video_draft_clean"

VIDEO_WORKFLOW_LABELS = {
    "21_minimax_h3_image_to_video": "MiniMax H3 Image-to-Video",
    "20_minimax_h3_text_to_video": "MiniMax H3 Text-to-Video",
    "22_minimax_h3_first_last_frame_to_video": "MiniMax H3 First/Last Frame",
    "23_minimax_h3_reference_to_video": "MiniMax H3 Reference-to-Video",
    "04_ltx2.3_image_to_video": "LTX 2.3 Image-to-Video (draft)",
    "05_ltx2.3_first_last_frame_to_video": "LTX 2.3 First/Last Frame (draft)",
    "09_ltx23_text_to_video_draft_clean": "LTX 2.3 Text-to-Video Draft",
    "02_ltx2.3_T2V_I2V_distilled": "LTX 2.3 Text-to-Video",
    "03_ltx2.3_T2V_two_stage": "LTX 2.3 Text-to-Video Two Stage",
}

VIDEO_WORKFLOW_FILE_ALIASES = {
    "04_ltx2.3_image_to_video": "11_ltx23_image_to_video",
    "04_ltx2.3_image_to_video_v1.1": "11_ltx23_image_to_video",
    "04_ltx2.3_image_to_video_fp8": "14_ltx23_i2v_nvfp4",
    "02_ltx2.3_T2V_I2V_distilled": "09_ltx23_text_to_video",
    "03_ltx2.3_T2V_two_stage": "10_ltx23_text_to_video_two_stage",
    "05_ltx2.3_first_last_frame_to_video": "12_ltx23_first_last_frame_to_video",
    "07_ltx2.3_id_lora": "13_ltx23_id_lora",
    "02_flux2_multi_reference_character_sheet": "04_flux2_multi_reference_character_sheet",
    "h3_t2v": "20_minimax_h3_text_to_video",
    "h3_i2v": "21_minimax_h3_image_to_video",
    "h3_fl2v": "22_minimax_h3_first_last_frame_to_video",
    "h3_r2v": "23_minimax_h3_reference_to_video",
}

H3_TAKE_MODES = {
    "t2va": DEFAULT_TEXT_VIDEO_WORKFLOW_ID,
    "t2v": DEFAULT_TEXT_VIDEO_WORKFLOW_ID,
    "i2va": DEFAULT_VIDEO_WORKFLOW_ID,
    "i2v": DEFAULT_VIDEO_WORKFLOW_ID,
    "fl2va": DEFAULT_FIRST_LAST_WORKFLOW_ID,
    "fl2v": DEFAULT_FIRST_LAST_WORKFLOW_ID,
    "first_last": DEFAULT_FIRST_LAST_WORKFLOW_ID,
    "r2va": DEFAULT_REF_VIDEO_WORKFLOW_ID,
    "r2v": DEFAULT_REF_VIDEO_WORKFLOW_ID,
}


def capability_for_workflow(workflow_id: str = "") -> str:
    """spark = video (H3 / LTX); stills = Flux / Z-Image / character sheets."""
    wid = str(workflow_id or "").strip().lower()
    if not wid:
        return "stills"
    still_markers = ("flux", "z_image", "z-image", "ernie", "klein", "character_sheet")
    if any(token in wid for token in still_markers) and "video" not in wid:
        return "stills"
    video_markers = ("h3", "minimax", "ltx", "wan", "video", "i2v", "t2v", "first_last", "fl2v", "r2v")
    if any(token in wid for token in video_markers):
        return "spark"
    return "stills"


def take_workflow_for_mode(mode: str = "") -> str:
    key = str(mode or "").strip().lower() or "i2va"
    return H3_TAKE_MODES.get(key, DEFAULT_VIDEO_WORKFLOW_ID)


def workflow_file_for_id(workflow_id: str) -> Optional[Path]:
    requested = (workflow_id or "").strip()
    if not requested:
        return None
    alias = VIDEO_WORKFLOW_FILE_ALIASES.get(requested, "")
    reverse_aliases = [
        source for source, target in VIDEO_WORKFLOW_FILE_ALIASES.items() if target == requested
    ]
    workflow_ids = [requested]
    if alias:
        workflow_ids.append(alias)
    workflow_ids.extend(reverse_aliases)
    seen: set[str] = set()
    candidates = [
        candidate
        for wid in workflow_ids
        if wid and not (wid in seen or seen.add(wid))
        for candidate in [
            WORKFLOWS_DIR / f"{wid}.json",
            WORKFLOWS_DIR / f"{wid}_api.json",
            WORKFLOWS_DIR / "_disabled_non_numbered" / f"{wid}.json",
            WORKFLOWS_DIR / "_disabled_non_numbered" / f"{wid}_api.json",
        ]
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def workflow_preflight(workflow_id: str = "") -> Dict[str, Any]:
    requested = (workflow_id or "").strip() or DEFAULT_VIDEO_WORKFLOW_ID
    path = workflow_file_for_id(requested)
    return {
        "requested": requested,
        "workflow_id": requested,
        "label": VIDEO_WORKFLOW_LABELS.get(requested, requested),
        "available": bool(path),
        "path": str(path) if path else "",
        "capability": capability_for_workflow(requested),
    }
