from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ProfileDef:
    key: str
    name: str
    backend: str  # "lmstudio" | "kimi"
    stage: str
    color_key: str


PROFILE_REGISTRY: Dict[str, ProfileDef] = {
    "director_planner": ProfileDef(
        key="director_planner",
        name="Director Planner",
        backend="kimi",
        stage="plan",
        color_key="profile_director_kimi",
    ),
    "coverage_critic": ProfileDef(
        key="coverage_critic",
        name="Coverage Critic",
        backend="kimi",
        stage="review",
        color_key="profile_critic_kimi",
    ),
    "prompt_compiler": ProfileDef(
        key="prompt_compiler",
        name="Prompt Compiler",
        backend="lmstudio",
        stage="compile",
        color_key="profile_compiler_lmstudio",
    ),
    "continuity_guard": ProfileDef(
        key="continuity_guard",
        name="Continuity Guard",
        backend="lmstudio",
        stage="compile",
        color_key="profile_continuity_lmstudio",
    ),
    "remediation_reprompter": ProfileDef(
        key="remediation_reprompter",
        name="Remediation Reprompter",
        backend="lmstudio",
        stage="remediation",
        color_key="profile_remediation_lmstudio",
    ),
    "audit_judge": ProfileDef(
        key="audit_judge",
        name="Audit Judge",
        backend="kimi",
        stage="audit",
        color_key="profile_audit_kimi",
    ),
}


def profile_label(key: str) -> str:
    p = PROFILE_REGISTRY.get(key)
    if not p:
        return key
    if p.backend == "kimi":
        return f"{p.name} (kimi)"
    if p.backend == "lmstudio":
        return f"{p.name} (lmstudio)"
    return p.name


def profile_color_key(key: str) -> str:
    p = PROFILE_REGISTRY.get(key)
    return p.color_key if p else "profile_compiler_lmstudio"


def list_profiles() -> List[Dict[str, str]]:
    out = []
    for p in PROFILE_REGISTRY.values():
        out.append(
            {
                "key": p.key,
                "name": p.name,
                "backend": p.backend,
                "stage": p.stage,
                "label": profile_label(p.key),
                "color_key": p.color_key,
            }
        )
    return out


async def refine_compiled_prompt_with_lmstudio(
    *,
    hermes_bridge: Any,
    workflow_id: str,
    compiled_prompt: str,
    negative_prompt: str,
    visual_brief: str,
    constraints: str,
) -> Optional[Dict[str, str]]:
    """
    Optional high-level refiner profile executed on LM Studio via Hermes bridge.
    It keeps prompt intent but improves structure for the selected workflow.
    """
    if hermes_bridge is None or not getattr(hermes_bridge, "is_available", False):
        return None
    system = (
        "You are Prompt Compiler profile for cinematic generation. "
        "Return ONLY JSON with keys: compiled_prompt, negative_prompt, continuity_note. "
        "Keep subject identity intact. Do not invent unrelated concepts."
    )
    user = (
        f"workflow_id: {workflow_id}\n"
        f"visual_brief: {visual_brief}\n"
        f"constraints: {constraints}\n"
        f"compiled_prompt_current:\n{compiled_prompt}\n\n"
        f"negative_prompt_current:\n{negative_prompt}\n\n"
        "Rewrite for stronger model-specific clarity, camera intent, and continuity. "
        "Keep it concise and production ready."
    )
    try:
        import json

        raw = await hermes_bridge.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
        )
        data = json.loads((raw or "").strip())
        cp = str(data.get("compiled_prompt", "") or "").strip()
        np = str(data.get("negative_prompt", "") or "").strip()
        note = str(data.get("continuity_note", "") or "").strip()
        if not cp:
            return None
        return {
            "compiled_prompt": cp,
            "negative_prompt": np or negative_prompt,
            "continuity_note": note,
        }
    except Exception:
        return None
