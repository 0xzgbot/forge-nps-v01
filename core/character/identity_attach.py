"""Map Asset Vault packages → campaign identity packs (F4 one-click attach).

Pure helpers — no dashboard imports. Safe for offline unit tests.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_PRODUCT_TYPES = {
    "product",
    "brand",
    "logo",
    "font",
    "style",
    "prop",
    "location",
    "reference",
    "mixed",
    "image",
}

_DEFAULT_NEGATIVES = [
    "identity drift",
    "logo drift",
    "wrong product silhouette",
    "inconsistent palette",
    "unreadable invented text",
]


def _short(text: Any, limit: int = 120) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def _split_phrases(text: Any, *, limit: int = 12) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = re.split(r"[,;\n|/]+", raw)
    out: List[str] = []
    seen: set[str] = set()
    for part in parts:
        phrase = re.sub(r"\s+", " ", part).strip(" .")
        if len(phrase) < 3:
            continue
        key = phrase.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(_short(phrase, 90))
        if len(out) >= limit:
            break
    return out


def infer_identity_type(package: Dict[str, Any]) -> str:
    """Return 'character' or 'product' for CampaignIdentityPack.type."""
    asset_type = str(
        package.get("asset_type")
        or package.get("element_type")
        or package.get("kind")
        or ""
    ).strip().lower()
    character_ids = package.get("character_ids") if isinstance(package.get("character_ids"), list) else []
    character_refs = package.get("character_refs") if isinstance(package.get("character_refs"), list) else []
    has_chars = bool(character_ids or character_refs)
    if asset_type in {"character", "talent", "cast"} or (has_chars and asset_type not in _PRODUCT_TYPES):
        return "character"
    if asset_type in _PRODUCT_TYPES or package.get("brand_rules") or package.get("prop_notes"):
        return "product"
    if has_chars and not package.get("references"):
        return "character"
    return "product"


def collect_identity_tokens(package: Dict[str, Any], *, max_tokens: int = 24) -> List[str]:
    """Build continuity tokens Hermes can lock into a live image campaign."""
    tokens: List[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        phrase = _short(value, 90)
        if len(phrase) < 3:
            return
        key = phrase.lower()
        if key in seen:
            return
        seen.add(key)
        tokens.append(phrase)

    package_id = str(package.get("id") or "").strip()
    if package_id:
        add(f"asset_vault:{package_id}")

    name = str(package.get("name") or "").strip()
    if name:
        add(name)

    for tag in package.get("tags") if isinstance(package.get("tags"), list) else []:
        add(tag)

    for field in (
        "brand_rules",
        "style_rules",
        "logo_notes",
        "font_notes",
        "prop_notes",
        "location_notes",
        "description",
        "notes",
    ):
        for phrase in _split_phrases(package.get(field), limit=6):
            add(phrase)
            if len(tokens) >= max_tokens:
                return tokens[:max_tokens]

    for ref in package.get("references") if isinstance(package.get("references"), list) else []:
        if not isinstance(ref, dict):
            continue
        label = ref.get("name") or ref.get("type") or ""
        prompt = ref.get("prompt") or ref.get("notes") or ""
        if label:
            add(label)
        for phrase in _split_phrases(prompt, limit=3):
            add(phrase)
        if len(tokens) >= max_tokens:
            return tokens[:max_tokens]

    for ref in package.get("character_refs") if isinstance(package.get("character_refs"), list) else []:
        if not isinstance(ref, dict):
            continue
        cid = str(ref.get("id") or "").strip()
        role = str(ref.get("role") or "").strip()
        if cid:
            label = cid.replace("_", " ")
            add(f"character:{label}" + (f" ({role})" if role else ""))
        if len(tokens) >= max_tokens:
            return tokens[:max_tokens]

    for cid in package.get("character_ids") if isinstance(package.get("character_ids"), list) else []:
        add(f"character:{str(cid).replace('_', ' ')}")
        if len(tokens) >= max_tokens:
            break

    return tokens[:max_tokens]


def collect_negative_tokens(package: Dict[str, Any], *, max_tokens: int = 12) -> List[str]:
    """Negatives that protect package continuity."""
    tokens: List[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        phrase = _short(value, 80)
        key = phrase.lower()
        if len(phrase) < 3 or key in seen:
            return
        seen.add(key)
        tokens.append(phrase)

    for item in _DEFAULT_NEGATIVES:
        add(item)

    notes = str(package.get("notes") or "")
    for match in re.findall(r"(?:avoid|no|never|without)\s+([^.;\n]+)", notes, flags=re.I):
        add(match.strip())
        if len(tokens) >= max_tokens:
            break

    return tokens[:max_tokens]


def build_identity_pack_from_vault_package(
    package: Dict[str, Any],
    *,
    anchor_image_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    One-click map from Asset Vault package → CampaignIdentityPack fields.

    Returns a plain dict compatible with dashboard CampaignIdentityPack.
    """
    if not isinstance(package, dict):
        raise ValueError("package must be a dict")
    name = str(package.get("name") or package.get("id") or "Asset Vault package").strip()
    return {
        "type": infer_identity_type(package),
        "name": name,
        "anchor_image_ids": list(anchor_image_ids or []),
        "identity_tokens": collect_identity_tokens(package),
        "negative_tokens": collect_negative_tokens(package),
    }


def infer_reference_type(filename: str) -> str:
    """Infer character reference type from a filename (shared with multi-upload)."""
    lower = str(filename or "").lower()
    if any(token in lower for token in ("face", "head", "close", "portrait")):
        return "face_closeup"
    if any(token in lower for token in ("full", "body", "turnaround")):
        return "full_body"
    if any(token in lower for token in ("outfit", "wardrobe", "costume")):
        return "outfit"
    if any(token in lower for token in ("expression", "emotion")):
        return "expression_sheet"
    if any(token in lower for token in ("motion", "walk", "video")):
        return "motion_clip"
    if any(token in lower for token in ("pose", "openpose")):
        return "pose"
    if any(token in lower for token in ("profile", "side")):
        return "profile"
    return "reference"
