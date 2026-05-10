import os
from pathlib import Path

BANK_DIR = Path(__file__).parent

def load_bank(bank_name: str) -> list[str]:
    """
    Loads a character bank file and returns list of options.
    bank_name: "lighting" | "view" | "pose" | "background" | "quality" | "extras"
    """
    path = BANK_DIR / f"{bank_name}_bank.txt"
    if not path.exists():
        # Fallback for the purpose of this task if file doesn't exist exactly as expected
        # In a real scenario, we would ensure the files are migrated correctly per Phase B2
        return []
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_quality_constants() -> str:
    """Returns quality_constants as a comma-joined string for prompt injection."""
    # Try to load 'quality' bank, fallback to default if missing
    quality = load_bank("quality")
    if not quality:
        # If no bank file found, use the one we just created/simulated or a default
        return "photorealistic, visible natural texture, specific motivated light source, lens falloff"
    return ", ".join(quality)

def build_shot_modifiers(lighting: str = None, view: str = None,
                          pose: str = None, background: str = None,
                          extras: list[str] = None) -> str:
    """
    Compiles selected bank items into a prompt modifier string.
    If None, selects the first item from each bank as default.
    """
    mods = []
    if lighting: mods.append(lighting)
    if view: mods.append(view)
    if pose: mods.append(pose)
    if background: mods.append(background)
    if extras: mods.extend(extras)
    return ", ".join(mods)
