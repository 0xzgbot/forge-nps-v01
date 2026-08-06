"""
Prompt Builder API for Cinesmith Dashboard.

Serves variation bank items and generates recipes from user selections.
"""

import json
import random
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Any, Optional

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
BANKS_DIR = REPO_ROOT / "data" / "character_banks"
PRODUCT_BANKS_DIR = REPO_ROOT / "data" / "product_banks"
CREATIVE_BRIEF_PATH = REPO_ROOT / "data" / "lore_bible" / "creative_brief.md"

QUALITY_CONSTANTS = "natural skin or material texture, slight real-world imperfection, sharp focal priority, specific lens behavior, motivated light source"


def load_banks(mode: str = "character") -> Dict[str, List[str]]:
    """Load all bank files for the given mode."""
    target_dir = BANKS_DIR if mode == "character" else PRODUCT_BANKS_DIR
    banks = {}
    if not target_dir.exists():
        return banks
    for bank_file in sorted(target_dir.glob("*_bank.txt")):
        name = bank_file.stem.replace("_bank", "")
        lines = [line.strip() for line in bank_file.read_text().split("\n") if line.strip()]
        banks[name] = lines
    return banks


def save_banks(mode: str = "character", banks: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
    """Persist editable variation bank files."""
    target_dir = BANKS_DIR if mode == "character" else PRODUCT_BANKS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    saved: Dict[str, int] = {}
    for raw_name, raw_value in (banks or {}).items():
        name = re.sub(r"[^a-z0-9_]+", "_", str(raw_name).strip().lower()).strip("_")
        if not name:
            continue
        if name.endswith("_bank"):
            name = name[:-5]
        path = target_dir / f"{name}_bank.txt"
        if isinstance(raw_value, list):
            lines = [str(item).strip() for item in raw_value]
        else:
            lines = [line.strip() for line in str(raw_value or "").splitlines()]
        cleaned = [line for line in lines if line]
        path.write_text("\n".join(cleaned) + ("\n" if cleaned else ""), encoding="utf-8")
        saved[name] = len(cleaned)
    return saved


def get_character_descriptor(name: Optional[str] = None) -> str:
    """Extract character descriptor from creative brief or CCE."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from core.consistency.character_consistency_engine import CharacterConsistencyEngine
        cce = CharacterConsistencyEngine(str(CREATIVE_BRIEF_PATH))
        detected = cce.detect_characters(name) if name else cce.detect_characters()
        if detected:
            return cce.get_anchor_prompt(detected[0])
    except Exception:
        pass
    return "photorealistic portrait with visible natural skin texture, slight facial asymmetry, individual hair strands, realistic wardrobe fabric weave"


def build_recipe(
    selections: Dict[str, str],
    character_name: Optional[str] = None,
    mode: str = "character",
    index: int = 0,
) -> Dict[str, Any]:
    """
    Build a complete recipe from user bank selections.
    selections: {"pose": "standing neutral", "view": "front view", ...}
    """
    if mode == "character":
        descriptor = get_character_descriptor(character_name)
        pose = selections.get("pose", "")
        view = selections.get("view", "")
        lighting = selections.get("lighting", "")
        background = selections.get("background", "")
        extras = selections.get("extras", "")
        crop = selections.get("crop", "")

        prompt_parts = [
            crop,
            f"{pose}, {view}" if pose and view else (pose or view),
            descriptor,
            f"in {background}" if background else "",
            lighting,
            extras,
            QUALITY_CONSTANTS,
        ]
        prompt = ", ".join(p for p in prompt_parts if p)
        filename_base = f"CUSTOM_{index:03d}_{pose.replace(' ', '_')}_{lighting.replace(' ', '_')}"

        seed = (hash(character_name or descriptor) + index * 7919 + hash(json.dumps(selections, sort_keys=True))) % (2**32)

        return {
            "index": index,
            "mode": mode,
            "character": character_name,
            "seed": seed,
            "selections": selections,
            "prompt": prompt,
            "filename": filename_base,
            "descriptor": descriptor,
        }
    else:
        # Product mode
        descriptor = selections.get("product_description", "high-end professional product")
        angle = selections.get("angle", "")
        material = selections.get("material", "")
        context = selections.get("context", "")
        lighting = selections.get("lighting", "")

        prompt_parts = [
            descriptor,
            f"made of {material}" if material else "",
            angle,
            context,
            lighting,
            QUALITY_CONSTANTS,
        ]
        prompt = ", ".join(p for p in prompt_parts if p)
        filename_base = f"PROD_{index:03d}"
        seed = (hash(descriptor) + index * 7919) % (2**32)

        return {
            "index": index,
            "mode": mode,
            "seed": seed,
            "selections": selections,
            "prompt": prompt,
            "filename": filename_base,
            "descriptor": descriptor,
        }


def generate_random_recipe(
    mode: str = "character",
    character_name: Optional[str] = None,
    index: int = 0,
) -> Dict[str, Any]:
    """Generate a random recipe by sampling from banks."""
    banks = load_banks(mode)
    selections = {}
    for bank_name, options in banks.items():
        if options:
            selections[bank_name] = random.choice(options)
    return build_recipe(selections, character_name, mode, index)


def build_batch(count: int = 6, mode: str = "character", character_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Build a batch of random recipes."""
    return [generate_random_recipe(mode, character_name, i) for i in range(count)]
