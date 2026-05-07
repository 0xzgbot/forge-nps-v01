import json
import re
from pathlib import Path
import fnmatch
from typing import Any, Dict, List, Optional, Tuple

from core.skills.skill_loader import SkillLoader
from core.hermes.platform_skills import platform_prompt_clause


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_PROFILES_DIR = REPO_ROOT / "data" / "prompt_profiles"
DEFAULT_PROFILE = "default.json"
COMPILER_VERSION = "v1.0.0"
PROFILE_SCRIPT_SKILLS_DIR = REPO_ROOT / "hermes_home" / "profiles" / "script" / "skills"
PROFILE_PRODUCT_SKILLS_DIR = REPO_ROOT / "hermes_home" / "profiles" / "product" / "skills"

MODEL_STANDARD_PATHS = {
    "flux-ltx-prompt-engineering-standard": [
        PROFILE_SCRIPT_SKILLS_DIR / "flux-ltx-prompt-engineering-standard" / "SKILL.md",
        PROFILE_PRODUCT_SKILLS_DIR / "flux-ltx-prompt-engineering-standard" / "SKILL.md",
    ],
    "ltx23-prompting-workflow": [
        PROFILE_SCRIPT_SKILLS_DIR / "ltx23-prompting-workflow" / "SKILL.md",
    ],
    "ltx25-beat-based-scripting": [
        PROFILE_SCRIPT_SKILLS_DIR / "ltx25-beat-based-scripting" / "SKILL.md",
    ],
    "grok-video-prompting-standard": [
        PROFILE_SCRIPT_SKILLS_DIR / "grok-video-prompting-standard" / "SKILL.md",
    ],
    "seedance-2-prompt-standard": [
        PROFILE_SCRIPT_SKILLS_DIR / "seedance-2-prompt-standard" / "SKILL.md",
    ],
    "flux-dir-command-protocol": [
        PROFILE_SCRIPT_SKILLS_DIR / "flux-dir-command-protocol" / "SKILL.md",
        PROFILE_PRODUCT_SKILLS_DIR / "flux-dir-command-protocol" / "SKILL.md",
    ],
}


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_chars(character_names: Optional[List[str]], kimi_plan: Optional[Dict[str, Any]]) -> List[str]:
    names = []
    for item in (character_names or []):
        t = _safe_text(item)
        if t:
            names.append(t)
    if kimi_plan and isinstance(kimi_plan.get("characters"), list):
        for item in kimi_plan["characters"]:
            t = _safe_text(item)
            if t and t not in names:
                names.append(t)
    return names


def _load_profile(workflow_id: str) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    profile_path = PROMPT_PROFILES_DIR / f"{workflow_id}.json"
    selected = profile_path
    if not profile_path.exists():
        selected = PROMPT_PROFILES_DIR / DEFAULT_PROFILE
        warnings.append(f"profile_missing:{workflow_id}")

    if not selected.exists():
        return (
            {
                "profile_name": "Default Fallback",
                "model_family": "generic",
                "prompt_style": "cinematic still image",
                "camera_defaults": "35mm lens, medium-wide framing",
                "lighting_defaults": "soft key and practical fill",
                "quality_terms": "high detail, coherent composition",
                "negative_prompt": "blurry, low quality, deformed, watermark, text",
                "forbidden_terms": [],
                "max_prompt_chars": 1200,
            },
            warnings + ["profile_file_missing:default"],
        )

    try:
        return json.loads(selected.read_text(encoding="utf-8")), warnings
    except Exception:
        warnings.append(f"profile_parse_error:{selected.name}")
        return (
            {
                "profile_name": "Default Fallback",
                "model_family": "generic",
                "prompt_style": "cinematic still image",
                "camera_defaults": "35mm lens, medium-wide framing",
                "lighting_defaults": "soft key and practical fill",
                "quality_terms": "high detail, coherent composition",
                "negative_prompt": "blurry, low quality, deformed, watermark, text",
                "forbidden_terms": [],
                "max_prompt_chars": 1200,
            },
            warnings,
        )


def _strip_forbidden(text: str, forbidden_terms: List[str]) -> str:
    out = text
    for term in forbidden_terms:
        clean = _safe_text(term)
        if not clean:
            continue
        pattern = re.compile(re.escape(clean), re.IGNORECASE)
        out = pattern.sub("", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def _extract_skill_names(skills: List[Dict[str, Any]]) -> List[str]:
    names = []
    for s in skills:
        name = _safe_text(s.get("name"))
        if name:
            names.append(name)
    return names


def _filter_skills_by_patterns(skills: List[Dict[str, Any]], patterns: List[str]) -> List[Dict[str, Any]]:
    if not patterns:
        return skills
    out: List[Dict[str, Any]] = []
    for skill in skills:
        name = _safe_text(skill.get("name"))
        if not name:
            continue
        if any(fnmatch.fnmatch(name, p) for p in patterns):
            out.append(skill)
    return out


def _extract_frontmatter(markdown: str) -> Dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", markdown, re.DOTALL)
    if not m:
        return {}
    data: Dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = _safe_text(k).lower()
        val = _safe_text(v).strip("'\"")
        if key:
            data[key] = val
    return data


def _extract_bullets(markdown: str, max_items: int = 6) -> List[str]:
    items: List[str] = []
    for line in markdown.splitlines():
        t = line.strip()
        if t.startswith("- "):
            bullet = _safe_text(t[2:])
            if bullet:
                items.append(bullet)
        if len(items) >= max_items:
            break
    return items


def _choose_model_standard_name(workflow_id: str, model_family: str) -> str:
    wf = _safe_text(workflow_id).lower()
    family = _safe_text(model_family).lower()
    if "seedance" in wf:
        return "seedance-2-prompt-standard"
    if "grok" in wf:
        return "grok-video-prompting-standard"
    if "ltx25" in wf:
        return "ltx25-beat-based-scripting"
    if "ltx23" in wf or ("ltx" in wf and "25" not in wf):
        return "ltx23-prompting-workflow"
    if "ltx" in family:
        return "ltx23-prompting-workflow"
    if "flux" in wf or "z_image" in wf or "flux" in family or "sdxl" in family:
        return "flux-ltx-prompt-engineering-standard"
    return "flux-ltx-prompt-engineering-standard"


def _load_model_standard(workflow_id: str, model_family: str) -> Tuple[Dict[str, Any], List[str]]:
    warnings: List[str] = []
    standard_name = _choose_model_standard_name(workflow_id, model_family)
    candidates = MODEL_STANDARD_PATHS.get(standard_name, [])
    selected: Optional[Path] = None
    for p in candidates:
        if p.exists():
            selected = p
            break
    if selected is None:
        warnings.append(f"standard_missing:{standard_name}")
        return (
            {
                "name": standard_name,
                "version": "unknown",
                "description": "",
                "source": "",
                "rules": [],
            },
            warnings,
        )
    try:
        content = selected.read_text(encoding="utf-8")
        fm = _extract_frontmatter(content)
        return (
            {
                "name": _safe_text(fm.get("name")) or standard_name,
                "version": _safe_text(fm.get("version")) or "1.0",
                "description": _safe_text(fm.get("description")),
                "source": str(selected),
                "rules": _extract_bullets(content, max_items=8),
            },
            warnings,
        )
    except Exception:
        warnings.append(f"standard_parse_error:{standard_name}")
        return (
            {
                "name": standard_name,
                "version": "unknown",
                "description": "",
                "source": str(selected),
                "rules": [],
            },
            warnings,
        )


def _render_standard_clause(standard: Dict[str, Any]) -> str:
    name = _safe_text(standard.get("name"))
    directive_map = {
        "flux-ltx-prompt-engineering-standard": [
            "use physical material descriptors over abstract adjectives",
            "specify concrete camera and lens details",
            "specify physically plausible light behavior",
        ],
        "ltx23-prompting-workflow": [
            "compose as one cinematic paragraph with explicit motion",
            "prioritize camera movement and temporal evolution",
            "include a concise negative line for drift and artifacts",
        ],
        "ltx25-beat-based-scripting": [
            "express clip as time-stamped beats",
            "describe movement in subject, camera, and environment",
            "anchor each beat with explicit lighting and lens intent",
        ],
        "grok-video-prompting-standard": [
            "use director prose rather than weighted tag syntax",
            "describe motion and camera changes first",
            "use explicit consistency lock language on extensions",
        ],
        "seedance-2-prompt-standard": [
            "lead with subject plus primary action early",
            "prefer source-based lighting and physical texture cues",
            "avoid high-speed camera and subject movement at once",
        ],
        "flux-dir-command-protocol": [
            "use direct command-style cinematic intent statements",
            "bind shot intent to lens and lighting constraints",
            "enforce deterministic quality and continuity directives",
        ],
    }
    concise = directive_map.get(name) or ["apply model-specific camera, lighting, and temporal directives"]
    return f"standard {name}: " + "; ".join(concise)


def compile_prompt_artifact(
    raw_concept: str,
    workflow_id: str,
    kimi_plan: Optional[Dict[str, Any]] = None,
    character_names: Optional[List[str]] = None,
    shot_meta: Optional[Dict[str, Any]] = None,
    role_key: str = "prompt_compiler",
    allowed_skill_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Compile a workflow-aware prompt artifact from high-level concept + Kimi plan.
    No network calls.
    """
    shot_meta = shot_meta or {}
    identity_pack = shot_meta.get("identity_pack") or {}
    platform_skill = shot_meta.get("platform_skill") if isinstance(shot_meta.get("platform_skill"), dict) else {}
    plan = kimi_plan or {}
    profile, warnings = _load_profile(workflow_id)
    model_family = _safe_text(profile.get("model_family"))
    model_standard, standard_warnings = _load_model_standard(workflow_id, model_family)
    warnings.extend(standard_warnings)

    try:
        loader = SkillLoader()
        match_text = " ".join(
            [
                _safe_text(raw_concept),
                _safe_text(plan.get("visual_brief")),
                _safe_text(plan.get("narrative_intent")),
                _safe_text(plan.get("environment")),
                platform_prompt_clause(platform_skill),
                _safe_text(model_standard.get("name")),
            ]
        )
        matched_skills = loader.match(match_text, max_skills=12)
        matched_skills = _filter_skills_by_patterns(matched_skills, allowed_skill_patterns or [])
    except Exception:
        matched_skills = []
        warnings.append("skills_unavailable")

    skills_used = _extract_skill_names(matched_skills)
    for skill_name in (platform_skill.get("skills") or []) if isinstance(platform_skill, dict) else []:
        skill_name = _safe_text(skill_name)
        if skill_name and skill_name not in skills_used:
            skills_used.append(skill_name)
    skill_modifiers = []
    for s in matched_skills[:3]:
        kws = s.get("keywords", [])[:4]
        if kws:
            skill_modifiers.append(", ".join(kws))
    skill_line = "; ".join(skill_modifiers)

    chars = _normalize_chars(character_names, plan)
    char_line = ", ".join(chars) if chars else "no fixed character anchors"

    subject_action = _safe_text(plan.get("visual_brief")) or _safe_text(raw_concept)
    environment = _safe_text(plan.get("environment")) or _safe_text(shot_meta.get("environment")) or "cinematic location matching the brief"
    camera = _safe_text(plan.get("camera_direction")) or _safe_text(profile.get("camera_defaults"))
    lighting = _safe_text(plan.get("lighting_direction")) or _safe_text(profile.get("lighting_defaults"))
    style_quality = _safe_text(profile.get("prompt_style")) + ", " + _safe_text(profile.get("quality_terms"))
    rationale = _safe_text(plan.get("rationale"))
    constraints = _safe_text(plan.get("constraints"))
    suffix = f"model profile: {_safe_text(profile.get('profile_name'))}, family: {_safe_text(profile.get('model_family'))}"
    standard_clause = _render_standard_clause(model_standard)
    identity_type = _safe_text(identity_pack.get("type")).lower()
    identity_name = _safe_text(identity_pack.get("name"))
    identity_tokens = identity_pack.get("identity_tokens") if isinstance(identity_pack.get("identity_tokens"), list) else []
    negative_tokens = identity_pack.get("negative_tokens") if isinstance(identity_pack.get("negative_tokens"), list) else []
    anchors = identity_pack.get("anchor_image_ids") if isinstance(identity_pack.get("anchor_image_ids"), list) else []
    id_lines = []
    if identity_type in {"character", "product"}:
        if identity_name:
            id_lines.append(f"{identity_type} identity lock: {identity_name}")
        if identity_tokens:
            id_lines.append("identity traits: " + ", ".join([_safe_text(x) for x in identity_tokens if _safe_text(x)]))
        if anchors:
            id_lines.append(f"anchor refs: {len(anchors)}")
        if negative_tokens:
            id_lines.append("identity drift negatives: " + ", ".join([_safe_text(x) for x in negative_tokens if _safe_text(x)]))
        if identity_type == "character":
            id_lines.append("character continuity: preserve facial geometry, hairline, eye spacing, skin tone, and wardrobe signature across shots")
        if identity_type == "product":
            id_lines.append("product continuity: preserve exact geometry, proportions, logo placement, materials, and finish across shots")
    identity_clause = "; ".join([x for x in id_lines if x])
    platform_clause = platform_prompt_clause(platform_skill)

    sections = {
        "Subject/Action": subject_action,
        "Environment": environment,
        "Camera/Lens": camera,
        "Lighting": lighting,
        "Character Continuity": char_line,
        "Identity Continuity": identity_clause or "none",
        "Style/Quality": style_quality,
        "Model Standard": standard_clause,
        "Platform Skill": platform_clause or "none",
        "Skill Modifiers": skill_line or "none",
        "Model Profile Suffix": suffix,
    }

    parts = [
        sections["Subject/Action"],
        sections["Environment"],
        sections["Camera/Lens"],
        sections["Lighting"],
        sections["Character Continuity"],
        sections["Identity Continuity"],
        sections["Style/Quality"],
        sections["Model Standard"],
        sections["Platform Skill"],
    ]
    if skill_line:
        parts.append(f"skill cues: {skill_line}")
    if rationale:
        parts.append(f"intent: {rationale}")
    if constraints:
        parts.append(f"constraints: {constraints}")
    parts.append(sections["Model Profile Suffix"])

    compiled = ", ".join([p for p in parts if _safe_text(p)])
    compiled = _strip_forbidden(compiled, profile.get("forbidden_terms", []))
    max_chars = int(profile.get("max_prompt_chars", 1200) or 1200)
    if len(compiled) > max_chars:
        compiled = compiled[:max_chars].rstrip(", ")
        warnings.append("compiled_prompt_truncated")

    return {
        "raw_concept": _safe_text(raw_concept),
        "workflow_id": _safe_text(workflow_id),
        "role_key": _safe_text(role_key),
        "profile_name": _safe_text(profile.get("profile_name")),
        "skills_used": skills_used,
        "compiled_prompt": compiled,
        "negative_prompt": _safe_text(profile.get("negative_prompt")),
        "identity_negative_prompt": ", ".join([_safe_text(x) for x in negative_tokens if _safe_text(x)]),
        "compiler_version": COMPILER_VERSION,
        "model_standard_name": _safe_text(model_standard.get("name")),
        "model_standard_version": _safe_text(model_standard.get("version")),
        "model_standard_source": _safe_text(model_standard.get("source")),
        "model_standard_rules": model_standard.get("rules", []),
        "sections": sections,
        "warnings": warnings,
    }
