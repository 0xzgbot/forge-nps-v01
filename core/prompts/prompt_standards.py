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


def flux_dev_ignores_negative_prompts(workflow_id: str = "", model_family: str = "") -> bool:
    wf = str(workflow_id or "").lower()
    family = str(model_family or "").lower()
    if "klein" in wf or "klein" in family:
        return False
    return family == "flux2-dev" or wf in {
        "01_flux2_text_to_image",
        "spark_image_flux2_text_to_image",
        "spark_image_flux2_text_to_image_turbo",
    }


def _has_any(text: str, patterns: List[str]) -> bool:
    low = text.lower()
    return any(p in low for p in patterns)


def _append_missing(parts: List[str], prompt: str, clause: str, triggers: List[str]) -> None:
    if not _has_any(prompt, triggers):
        parts.append(clause)


def _explicit_subject_locks(prompt: str) -> List[str]:
    low = str(prompt or "").lower()
    parts: List[str] = []
    female = re.search(r"\b(?:female|woman|women|actress|mother|girl)\b", low)
    male = re.search(r"\b(?:male|man|men|actor|father|boy)\b", low)
    if female and not male:
        _append_missing(
            parts,
            prompt,
            "subject lock: primary subjects must match the requested female/woman presentation exactly; do not swap to male, and do not neutralize the requested presentation",
            ["subject lock"],
        )
    elif male and not female:
        _append_missing(
            parts,
            prompt,
            "subject lock: primary subjects must match the requested male/man presentation exactly; do not swap to female, and do not neutralize the requested presentation",
            ["subject lock"],
        )

    if re.search(r"\b(?:early|mid|late)[ -]?(?:20s|30s|40s|50s|60s|70s)\b", low) or re.search(
        r"\b\d{2}\s*[- ]?year[- ]?old\b", low
    ):
        _append_missing(
            parts,
            prompt,
            "age lock: preserve the explicitly requested age or age band; do not drift younger, older, childlike, or elderly unless the prompt says so",
            ["age lock"],
        )
    if re.search(r"\b(?:child|children|kid|kids|teen|teenager|minor|student)\b", low):
        _append_missing(
            parts,
            prompt,
            "age safety lock: preserve the explicitly requested life stage and context; do not age the subject up or down, sexualize styling, or change the role into an adult fashion or glamour setup",
            ["age safety lock"],
        )
    return parts


def _role_fidelity_clauses(prompt: str) -> List[str]:
    low = str(prompt or "").lower()
    parts: List[str] = []
    fitness_role = re.search(
        r"\b(?:fitness instructors?|fitness trainers?|personal trainers?|athletic trainers?|trainers?|coaches|athletes?|hiit|pilates|yoga instructors?|strength coaches)\b",
        low,
    )
    if fitness_role:
        _append_missing(
            parts,
            prompt,
            "fitness role fidelity: subject must read as a working fitness professional with visibly conditioned athletic build, lean or muscular body composition, confident coaching posture, performance-ready activewear, and credible exercise stance",
            ["fitness role fidelity"],
        )
    if re.search(r"\b(?:doctor|doctors|nurse|nurses|surgeon|surgeons|clinician|clinicians|healthcare worker|medical professional)\b", low):
        _append_missing(
            parts,
            prompt,
            "medical role fidelity: subject must read as a credible healthcare professional with appropriate clinical attire, hygienic grooming, medically plausible environment, and no fashion, glamour, costume, or athleisure drift",
            ["medical role fidelity"],
        )
    if re.search(r"\b(?:chef|chefs|cook|cooks|barista|bartender)\b", low):
        _append_missing(
            parts,
            prompt,
            "service role fidelity: subject must read as a working professional in the requested role with correct tools, uniform or workwear, plausible workspace, and role-specific posture or hand activity",
            ["service role fidelity"],
        )
    if re.search(r"\b(?:executive|ceo|founder|board member|lawyer|attorney|banker|consultant|investor)\b", low):
        _append_missing(
            parts,
            prompt,
            "professional role fidelity: subject must read as the requested working professional with credible industry wardrobe, posture, environment, and tools; do not drift into generic model, influencer, stock-photo, costume, or fantasy styling",
            ["professional role fidelity"],
        )
    if re.search(r"\b(?:athlete|athletes|runner|runners|cyclist|swimmer|boxer|martial artist|dancer|gymnast)\b", low):
        _append_missing(
            parts,
            prompt,
            "athlete role fidelity: subject must read as the requested athletic discipline with sport-specific body mechanics, equipment, venue, wardrobe, and action posture; do not drift into generic athleisure posing",
            ["athlete role fidelity"],
        )
    return parts


def _product_fidelity_clauses(prompt: str) -> List[str]:
    low = str(prompt or "").lower()
    if not re.search(
        r"\b(?:product|packaging|logo|brand|bottle|can|box|device|gadget|watch|shoe|sneaker|bag|lamp|chair|cosmetic|skincare|perfume|mug)\b",
        low,
    ):
        return []
    parts: List[str] = []
    _append_missing(
        parts,
        prompt,
        "product fidelity: preserve the exact requested product category, silhouette, material, proportions, colorway, logo placement, and functional parts; do not invent extra handles, labels, buttons, limbs, faces, or unrelated accessories",
        ["product fidelity"],
    )
    if re.search(r"\b(?:logo|brand|packaging|label|typography|font)\b", low):
        _append_missing(
            parts,
            prompt,
            "brand/text fidelity: do not invent readable words, fake logos, misspelled labels, random UI text, or extra typography unless the exact text is supplied",
            ["brand/text fidelity"],
        )
    if re.search(r"\b(?:luxury|premium|high-end|jewelry|watch|perfume|leather|handbag|sports car)\b", low):
        _append_missing(
            parts,
            prompt,
            "luxury product fidelity: preserve premium material cues, precise craftsmanship, clean proportions, controlled reflections, and restrained styling; do not add cheap plastic, random ornament, incorrect materials, or clutter",
            ["luxury product fidelity"],
        )
    return parts


def _scene_fidelity_clauses(prompt: str) -> List[str]:
    low = str(prompt or "").lower()
    parts: List[str] = []
    if re.search(r"\b(?:restaurant|kitchen|cafe|meal|food|dish|dessert|cocktail|coffee|steak|salad|pasta|pizza|sushi|burger|bakery)\b", low):
        _append_missing(
            parts,
            prompt,
            "food fidelity: food must look edible, fresh, physically plausible, and specific to the requested dish; do not invent unrelated ingredients, plastic texture, malformed utensils, or impossible plating",
            ["food fidelity"],
        )
    if re.search(r"\b(?:new york|tokyo|paris|london|miami|los angeles|studio|hospital|gym|office|boardroom|classroom|school|track|stadium|arena|warehouse|beach|mountain|desert|forest|subway|airport|train station)\b", low):
        _append_missing(
            parts,
            prompt,
            "location fidelity: preserve the requested place or environment with concrete architecture, signage rules, lighting, weather, and scale cues; do not swap to a generic backdrop or unrelated location",
            ["location fidelity"],
        )
    return parts


def _composition_fidelity_clauses(prompt: str, render_type: str = "") -> List[str]:
    low = str(prompt or "").lower()
    kind = str(render_type or "").lower()
    parts: List[str] = []
    if re.search(r"\b(?:full[- ]?body|head[- ]?to[- ]?toe|feet visible|shoes visible|standing portrait|turnaround)\b", low):
        _append_missing(
            parts,
            prompt,
            "full-body framing lock: show the entire subject from head to toe with both feet or shoes visible, leave clear floor margin below the feet and headroom above the head, and do not crop through legs, ankles, feet, hands, or the top of the head",
            ["full-body framing lock"],
        )
    if kind == "storyboard":
        _append_missing(
            parts,
            prompt,
            "storyboard frame lock: render one sharp full-bleed production keyframe only, no contact sheet, no multi-panel grid, no page layout, no captions, no labels, no readable signage, no watermark, no border",
            ["storyboard frame lock"],
        )
    return parts


def _looks_like_realistic_human_prompt(prompt: str) -> bool:
    low = str(prompt or "").lower()
    human_terms = re.search(
        r"\b(?:human|person|people|portrait|headshot|selfie|face|skin|woman|women|man|men|male|female|girl|boy|adult|model|actor|actress|cast|doctor|nurse|chef|barista|athlete|trainer|coach|teacher|student|ceo|founder|lawyer|parent|mother|father)\b",
        low,
    )
    if not human_terms:
        return False
    if re.search(r"\b(?:photoreal|photo[- ]?real|realistic|realism|documentary|editorial|lifestyle|cinematic|street photo|fashion photo|portrait photo|natural light|studio portrait|headshot)\b", low):
        return True
    return bool(re.search(r"\b(?:portrait|headshot|selfie|model|actor|actress|face|skin|people|person|woman|man|female|male)\b", low))


def _flux_positive_specificity(prompt: str, render_type: str = "") -> List[str]:
    kind = str(render_type or "").lower()
    parts: List[str] = []
    if kind == "sheet":
        parts.append(
            "visible natural skin texture, skin imperfections, individual hair strands, fabric weave, seam stitching, shoe material grain, accurate hand anatomy"
        )
        parts.append(
            "controlled studio optics, 70mm portrait lens for face panels, 50mm full-body lens for turnaround panels, even softbox catchlights"
        )
        return parts
    parts.extend(_explicit_subject_locks(prompt))
    parts.extend(_role_fidelity_clauses(prompt))
    if re.search(r"\b(?:people|persons|characters|portraits|models|cast|crowd|group|20|twenty|10|ten|multiple)\b", prompt, re.IGNORECASE):
        _append_missing(
            parts,
            prompt,
            "batch intent lock: do not invent subject traits, age, body-type, wardrobe, role, or setting variation that the user did not request; preserve the explicit subject constraints across every image",
            ["batch intent lock", "do not invent subject traits", "preserve the explicit subject constraints"],
        )
    parts.extend(_product_fidelity_clauses(prompt))
    parts.extend(_scene_fidelity_clauses(prompt))
    parts.extend(_composition_fidelity_clauses(prompt, render_type))
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
    if _looks_like_realistic_human_prompt(prompt):
        _append_missing(
            parts,
            prompt,
            "realistic human skin detail: skin imperfections, visible pores, faint blemishes, subtle under-eye texture, tiny asymmetries, natural non-plastic facial planes",
            ["skin imperfections", "realistic human skin detail"],
        )
    _append_missing(
        parts,
        prompt,
        "anti-smoothness: visible pores, faint blemishes, subtle under-eye texture, tiny asymmetries, natural flyaway hairs, non-plastic facial planes",
        ["pore", "blemish", "under-eye", "asymmetr", "flyaway", "non-plastic", "natural skin"],
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
