from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


@dataclass(frozen=True)
class LoraPreset:
    key: str
    label: str
    purpose: str
    model_family: str
    candidates: tuple[str, ...]
    default_strength: float
    source_url: str
    trigger_words: tuple[str, ...] = ()


LORA_PRESETS: Dict[str, LoraPreset] = {
    "flux2_turbo": LoraPreset(
        key="flux2_turbo",
        label="FLUX2 Turbo",
        purpose="Speed-focused FLUX2 generation; not a realism or storyboard LoRA.",
        model_family="flux2",
        candidates=("Flux_2-Turbo-LoRA_comfyui.safetensors", "Flux2TurboComfyv2.safetensors"),
        default_strength=1.0,
        source_url="https://huggingface.co/ByteZSzn/Flux.2-Turbo-ComfyUI",
    ),
    "flux2_multi_angle": LoraPreset(
        key="flux2_multi_angle",
        label="FLUX2 Multi-Angle",
        purpose="Camera-angle control for character sheets, turnaround sheets, and storyboard-like panel consistency.",
        model_family="flux2",
        candidates=("flux-multi-angles-v2-72poses-comfy.safetensors",),
        default_strength=0.65,
        source_url="https://huggingface.co/lovis93/Flux-2-Multi-Angles-LoRA-v2",
    ),
    "ltx23_distilled": LoraPreset(
        key="ltx23_distilled",
        label="LTX 2.3 Distilled",
        purpose="Speed/efficiency LoRA for LTX 2.3 video workflows.",
        model_family="ltx2.3",
        candidates=("ltx-2.3-22b-distilled-lora-384-1.1.safetensors", "ltx-2.3-22b-distilled-lora-384.safetensors"),
        default_strength=1.0,
        source_url="https://huggingface.co/Lightricks/LTX-2.3",
    ),
    "ltx23_id_talkvid": LoraPreset(
        key="ltx23_id_talkvid",
        label="LTX 2.3 ID TalkVid",
        purpose="Identity retention for talking-head or character-driven LTX 2.3 video.",
        model_family="ltx2.3",
        candidates=("ltx-2.3-id-lora-talkvid-3k.safetensors", "lora_weights.safetensors"),
        default_strength=0.8,
        source_url="https://huggingface.co/AviadDahan/LTX-2.3-ID-LoRA-TalkVid-3K",
    ),
}


WORKFLOW_LORA_DEFAULTS = {
    "02_flux2_multi_reference_character_sheet": "flux2_multi_angle",
    "04_flux2_multi_reference_character_sheet": "flux2_multi_angle",
    "07_ltx2.3_id_lora": "ltx23_id_talkvid",
}


def infer_lora_profile(workflow_path: str | Path | None, prompt: str = "") -> str:
    name = Path(str(workflow_path or "")).stem
    if name in WORKFLOW_LORA_DEFAULTS:
        return WORKFLOW_LORA_DEFAULTS[name]
    text = f"{name} {prompt or ''}".lower()
    if (
        "storyboard" in text
        or "turnaround" in text
        or "multi-angle" in text
        or "multi angle" in text
        or "multi_reference_character_sheet" in text
        or "character_sheet" in text
    ):
        return "flux2_multi_angle"
    return ""


def lora_preset_payload() -> list[dict[str, Any]]:
    return [
        {
            "key": preset.key,
            "label": preset.label,
            "purpose": preset.purpose,
            "model_family": preset.model_family,
            "candidates": list(preset.candidates),
            "default_strength": preset.default_strength,
            "source_url": preset.source_url,
            "trigger_words": list(preset.trigger_words),
        }
        for preset in LORA_PRESETS.values()
    ]


def available_lora_names(object_info: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for class_type, spec in (object_info or {}).items():
        if "lora" not in str(class_type).lower():
            continue
        inputs = spec.get("input", {}) if isinstance(spec, dict) else {}
        for section in ("required", "optional"):
            fields = inputs.get(section, {}) if isinstance(inputs, dict) else {}
            for key, meta in (fields or {}).items():
                if "lora" not in str(key).lower():
                    continue
                names.update(_choices_from_meta(meta))
    return {name for name in names if name}


def _choices_from_meta(meta: Any) -> Iterable[str]:
    if isinstance(meta, list):
        if meta and isinstance(meta[0], list):
            for item in meta[0]:
                if isinstance(item, str):
                    yield item
        if len(meta) > 1 and isinstance(meta[1], dict):
            options = meta[1].get("options")
            if isinstance(options, list):
                for option in options:
                    if isinstance(option, str):
                        yield option
                    elif isinstance(option, dict) and isinstance(option.get("key"), str):
                        yield option["key"]
