import re
from typing import List, Tuple


GENERIC_QUALITY_PATTERNS = [
    r"\bmasterpiece\b",
    r"\bbest quality\b",
    r"\bultra[- ]?high[- ]?resolution\b",
    r"\bhigh quality\b",
    r"\b8k\b",
    r"\b4k quality\b",
    r"\bhyper[- ]?realistic\b",
    r"\bperfect skin\b",
    r"\bsmooth skin\b",
    r"\bflawless skin\b",
]

FLUX_UNSUPPORTED_NEGATIVE_RE = re.compile(
    r"(?:^|[\n.])\s*(?:negative prompt|negative)\s*:\s*.+?(?=(?:\n[A-Z0-9_][^:\n]{0,80}:)|\Z)",
    re.IGNORECASE | re.DOTALL,
)


def clean_generic_quality_terms(prompt: str) -> str:
    """Remove generic quality tokens that often create polished AI sameness."""
    out = str(prompt or "")
    for pattern in GENERIC_QUALITY_PATTERNS:
        out = re.sub(pattern, "", out, flags=re.IGNORECASE)
    out = re.sub(r"(,\s*){2,}", ", ", out)
    out = re.sub(r",\s*,", ", ", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" ,")


def prompt_standard_name_for_workflow(workflow_id: str = "", model_family: str = "") -> str:
    wf = str(workflow_id or "").lower()
    family = str(model_family or "").lower()
    if "seedance" in wf or "seedance" in family:
        return "seedance-2-prompt-standard"
    if "grok" in wf or "grok" in family:
        return "grok-video-prompting-standard"
    if "ltx25" in wf or "ltx-2.5" in family or "ltx2.5" in family:
        return "ltx25-beat-based-scripting"
    if "ltx23" in wf or "ltx2.3" in wf or ("ltx" in wf and "25" not in wf) or "ltx" in family:
        return "ltx23-prompting-workflow"
    if "z_image" in wf or "z-image" in family:
        return "zimage-turbo-payload-generator"
    return "flux-ltx-prompt-engineering-standard"


def prompt_standard_skills_for_workflow(workflow_id: str = "", model_family: str = "") -> List[str]:
    primary = prompt_standard_name_for_workflow(workflow_id, model_family)
    skills = [primary]
    if primary == "zimage-turbo-payload-generator":
        skills.append("flux-ltx-prompt-engineering-standard")
    return skills


def _has_any(text: str, patterns: List[str]) -> bool:
    low = text.lower()
    return any(p in low for p in patterns)


def _append_missing(parts: List[str], prompt: str, clause: str, triggers: List[str]) -> None:
    if not _has_any(prompt, triggers):
        parts.append(clause)


def _flux_positive_specificity(prompt: str, render_type: str = "") -> List[str]:
    kind = str(render_type or "").lower()
    parts: List[str] = []
    if kind == "sheet":
        parts.append(
            "visible natural skin texture, individual hair strands, fabric weave, seam stitching, shoe material grain, accurate hand anatomy"
        )
        parts.append(
            "controlled studio optics, 70mm portrait lens for face panels, 50mm full-body lens for turnaround panels, even softbox catchlights"
        )
        return parts
    _append_missing(
        parts,
        prompt,
        "material specificity: visible skin pores, fine flyaway hairs, fabric weave, scuffed surfaces, dust and fingerprints where physically plausible",
        ["skin pore", "fabric weave", "scuffed", "fingerprint", "grain", "micro-scar", "weathered"],
    )
    _append_missing(
        parts,
        prompt,
        "optics: photographed with a specific lens and aperture, natural lens falloff, realistic depth of field, slight sensor noise",
        ["mm lens", "anamorphic", "aperture", "f/", "depth of field", "sensor noise", "film stock", "kodak"],
    )
    _append_missing(
        parts,
        prompt,
        "lighting source: motivated real light source with direction, color temperature, catchlights, practical reflections, grounded shadows",
        ["softbox", "window light", "tungsten", "sunlight", "rim light", "practical", "color temperature", "catchlight"],
    )
    _append_missing(
        parts,
        prompt,
        "anti-smoothness: visible pores, faint blemishes, subtle under-eye texture, tiny asymmetries, natural flyaway hairs, non-plastic facial planes",
        ["pore", "blemish", "under-eye", "asymmetr", "flyaway", "non-plastic", "natural skin"],
    )
    if re.search(r"\b(?:people|persons|characters|portraits|models|cast|crowd|group|20|twenty|10|ten|multiple)\b", prompt, re.IGNORECASE):
        _append_missing(
            parts,
            prompt,
            "casting variation: each person has a distinct face shape, age bracket, hairstyle, body type, skin tone, wardrobe silhouette, posture, and expression; no duplicated template faces",
            ["distinct face", "different face", "varied age", "body type", "skin tone", "wardrobe silhouette", "no duplicate"],
        )
    return parts


def _ltx_temporal_specificity(prompt: str) -> List[str]:
    parts: List[str] = []
    _append_missing(
        parts,
        prompt,
        "temporal beats: first seconds establish posture and gaze, middle seconds introduce subject/environment motion, final seconds settle into a held end frame",
        ["0-", "1-", "2-", "seconds", "time range", "beat"],
    )
    _append_missing(
        parts,
        prompt,
        "motion physics: micro-expressions, breathing, hair or clothing movement, environmental particles, stable identity across frames",
        ["micro-expression", "breathing", "hair", "particles", "drifting", "flicker", "rain", "dust"],
    )
    _append_missing(
        parts,
        prompt,
        "camera behavior: one controlled move only, with lens intent and no abrupt reframing",
        ["dolly", "push-in", "tracking", "pan", "tilt", "locked-off", "handheld"],
    )
    return parts


def apply_model_prompt_standard(
    prompt: str,
    *,
    workflow_id: str = "",
    model_family: str = "",
    render_type: str = "",
) -> Tuple[str, List[str]]:
    """
    Make model-prompting skills operational instead of passive metadata.
    Returns (standardized_prompt, standard_skill_names).
    """
    standard = prompt_standard_name_for_workflow(workflow_id, model_family)
    skills = prompt_standard_skills_for_workflow(workflow_id, model_family)
    clean = clean_generic_quality_terms(prompt)

    if standard in {"flux-ltx-prompt-engineering-standard", "zimage-turbo-payload-generator"}:
        # FLUX-style image models respond better to positive specificity than embedded negative blocks.
        clean = FLUX_UNSUPPORTED_NEGATIVE_RE.sub("", clean).strip(" ,\n")
        additions = _flux_positive_specificity(clean, render_type)
    elif standard in {"ltx23-prompting-workflow", "ltx25-beat-based-scripting", "grok-video-prompting-standard", "seedance-2-prompt-standard"}:
        additions = _ltx_temporal_specificity(clean)
    else:
        additions = []

    if additions:
        clean = clean.rstrip(" .,\n") + ". Prompt standard enforcement: " + "; ".join(additions).rstrip(" .") + "."
    return re.sub(r"\s{2,}", " ", clean).strip(), skills
