"""Character continuity helpers — anchors, multi-upload, auto-sheet, package→identity attach."""

from .anchor_manager import CharacterAnchorManager
from .auto_sheet import (
    apply_photo_to_character,
    build_auto_sheet_prompt,
    build_auto_sheet_result,
    clamp_grid,
    draft_character_record,
    name_from_filename,
    spark_recovery_hint,
)
from .identity_attach import build_identity_pack_from_vault_package, infer_reference_type
from .reference_upload import merge_character_uploads, save_character_reference_bytes

__all__ = [
    "CharacterAnchorManager",
    "apply_photo_to_character",
    "build_auto_sheet_prompt",
    "build_auto_sheet_result",
    "build_identity_pack_from_vault_package",
    "clamp_grid",
    "draft_character_record",
    "infer_reference_type",
    "merge_character_uploads",
    "name_from_filename",
    "save_character_reference_bytes",
    "spark_recovery_hint",
]
