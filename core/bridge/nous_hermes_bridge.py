"""
NousHermesBridge — wraps LMStudioClient to give Hermes-3 a structured API.
Hermes-3 is the local creative brain: writes prompts, diagnoses failures,
generates scripts and character DNA.
"""
import os
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is available on PYTHONPATH for direct script execution
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from core.bridge.lmstudio_client import LMStudioClient
    from core.bridge.runtime_config import get_raw_config
    from core.skills.skill_loader import SkillLoader
    from core.prompts.prompt_compiler import compile_prompt_artifact
except ImportError:
    from core.bridge.lmstudio_client import LMStudioClient
    from core.bridge.runtime_config import get_raw_config
    from core.skills.skill_loader import SkillLoader
    from core.prompts.prompt_compiler import compile_prompt_artifact

logger = logging.getLogger("NousHermesBridge")

HERMES_SYSTEM = (
    "You are Hermes, an AI creative director specialized in visual storytelling "
    "and cinematic image generation. You think in terms of composition, lighting, "
    "character presence, and visual continuity. Be specific, vivid, and concise."
)


class NousHermesBridge:
    def __init__(self):
        cfg = get_raw_config()
        self.model = (
            os.getenv("NOUS_HERMES_MODEL", "")
            or os.getenv("LMSTUDIO_CHAT_MODEL", "")
            or str(cfg.get("LMSTUDIO_CHAT_MODEL", ""))
            or "Hermes-3-Llama-3.2-3B"
        ).strip()
        self.client = LMStudioClient(timeout=float(os.getenv("CINESMITH_HERMES_CHAT_TIMEOUT_SEC", "240")))
        self.last_error: Optional[str] = None
        try:
            self.skills = SkillLoader()
            logger.info(f"[HERMES] Skills loaded: {self.skills.skill_names}")
        except Exception as e:
            logger.warning(f"[HERMES] SkillLoader unavailable: {e}")
            self.skills = None

    @property
    def is_available(self) -> bool:
        return self.client.is_available

    # ------------------------------------------------------------------
    # Core creative methods
    # ------------------------------------------------------------------

    async def generate_shot_prompt(
        self,
        concept: str,
        director_schema: Dict[str, Any] = None,
        memory_context: str = "",
        skills_context: str = "",
    ) -> Optional[str]:
        """Write a cinematic Stable Diffusion prompt for a shot brief.

        Args:
            concept: Shot description/brief.
            director_schema: Optional director guidance schema.
            memory_context: Optional episodic memory context.
            skills_context: Pre-computed skill injection block. If empty, auto-matched from skills.
        """
        # Auto-match skills if no pre-computed context provided
        if not skills_context and self.skills:
            try:
                skills_context = self.skills.get_skills_context(concept)
            except Exception as e:
                logger.debug(f"[HERMES] Skill matching failed: {e}")

        # Build system prompt with skill context prepended
        system = HERMES_SYSTEM
        if skills_context:
            system = f"{HERMES_SYSTEM}\n\nRelevant domain skills:\n{skills_context}"

        user = (
            f"Shot brief: {concept}\n"
            f"{f'Memory context: {memory_context}' if memory_context else ''}\n"
            f"{f'Director schema: {json.dumps(director_schema)}' if director_schema else ''}\n"
            "Write a vivid, specific Stable Diffusion prompt (2-4 sentences). "
            "Include: subject, action, lighting, mood, camera angle, style."
        )
        try:
            self.last_error = None
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.8,
                max_tokens=300,
            )
            content = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
            if not content:
                self.last_error = "Empty response content from Hermes model"
                return None
            return content
        except Exception as e:
            self.last_error = str(e)
            logger.warning(f"[HERMES] generate_shot_prompt failed: {e}")
            return None

    async def analyze_failure(
        self,
        visual_audit_result: Dict[str, Any],
        original_prompt: str,
        memory_context: str = "",
    ) -> Optional[Dict[str, str]]:
        """Diagnose a visual audit failure and return a corrected prompt."""
        user = (
            f"A rendered image failed visual QA.\n"
            f"Original prompt: {original_prompt}\n"
            f"Audit finding: {json.dumps(visual_audit_result)}\n"
            f"{f'Memory context: {memory_context}' if memory_context else ''}\n"
            "Respond in JSON with keys: root_cause (str), fix_prompt (str — the corrected full prompt)."
        )
        try:
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": HERMES_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.5,
                max_tokens=400,
                json_mode=True,
            )
            raw = resp["choices"][0]["message"]["content"]
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[HERMES] analyze_failure failed: {e}")
            return None

    async def generate_script(self, brief: str) -> Optional[Dict[str, Any]]:
        """
        Generate a structured shot list from a creative brief.
        Returns: {"title": str, "shots": [{"shot_id", "description", "characters", "intent"}]}
        """
        user = (
            f"Creative brief: {brief}\n\n"
            "Generate a production shot list. Return JSON with keys:\n"
            "  title (str): project title\n"
            "  shots (array): each item has shot_id (e.g. SHOT_001), description (str, "
            "  vivid visual description), characters (array of character names), "
            "  intent (one of: high_fidelity_image, fast_preview_image, video_generation)\n"
            "Generate 5-10 shots. Make descriptions cinematic and specific."
        )
        try:
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": HERMES_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.8,
                max_tokens=1200,
                json_mode=True,
            )
            raw = resp["choices"][0]["message"]["content"]
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[HERMES] generate_script failed: {e}")
            return None

    async def generate_character(self, description: str) -> Optional[Dict[str, Any]]:
        """
        Generate character DNA and a ComfyUI anchor prompt from a description.
        Returns structured character data.
        """
        user = (
            f"Character description: {description}\n\n"
            "Generate a complete character profile. Return JSON with keys:\n"
            "  name (str), role (str), hair (str), eyes (str), build (str),\n"
            "  clothing (str), signature (str — a signature item or detail),\n"
            "  palette (array of 3-5 hex color codes),\n"
            "  anchor_prompt (str — a detailed ComfyUI/Stable Diffusion prompt "
            "  to generate a reference portrait of this character, include all "
            "  physical details, lighting: softbox studio, neutral background)"
        )
        try:
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": HERMES_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.7,
                max_tokens=600,
                json_mode=True,
            )
            raw = resp["choices"][0]["message"]["content"]
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"[HERMES] generate_character failed: {e}")
            return None

    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2048,
        temperature: float = 0.8,
    ) -> str:
        """General chat — used by Hermes Live panel CLI."""
        # Prepend system message if not already present
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": HERMES_SYSTEM}] + messages
        messages = [dict(message) for message in messages]
        max_tokens = max(512, min(int(max_tokens or 2048), 16384))
        no_think_rule = (
            "/no_think\n"
            "Do not use hidden reasoning. Do not spend tokens thinking. "
            "Write the final assistant answer directly and completely."
        )
        messages[0]["content"] = no_think_rule + "\n" + str(messages[0].get("content") or "")
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                messages[i]["content"] = (
                    str(messages[i].get("content") or "")
                    + "\n\n/no_think\n"
                    + "Return visible final assistant content now. Do not put the answer only in reasoning_content."
                )
                break
        try:
            resp = await self.client.chat_async(
                messages=messages,
                model=self.model,
                temperature=max(0.1, min(float(temperature or 0.8), 1.5)),
                max_tokens=max_tokens,
            )
            content = self._chat_response_content(resp)
            if content is not None:
                return content

            # Some reasoning-heavy local models spend the whole budget in hidden
            # reasoning. Retry once with a larger budget and stricter final-only
            # instruction before surfacing the diagnostic to the UI.
            retry_messages = [dict(message) for message in messages]
            retry_messages[0]["content"] = (
                "/no_think\n"
                "You previously returned hidden reasoning only. This retry must emit visible final assistant content. "
                "Start with the requested answer immediately. No analysis, no preamble, no hidden reasoning.\n"
                + str(retry_messages[0].get("content") or "")
            )
            retry_max_tokens = min(16384, max(max_tokens * 2, 4096))
            resp = await self.client.chat_async(
                messages=retry_messages,
                model=self.model,
                temperature=max(0.1, min(float(temperature or 0.8), 1.5)),
                max_tokens=retry_max_tokens,
            )
            content = self._chat_response_content(resp)
            if content is not None:
                return content
            return self._chat_response_error(resp)
        except Exception as e:
            logger.warning(f"[HERMES] chat failed: {e}")
            return f"[Hermes offline] {e}"

    def _chat_response_content(self, resp: Dict[str, Any]) -> Optional[str]:
        if isinstance(resp, dict) and resp.get("error"):
            return f"[Hermes offline] {resp.get('error')}"
        choices = resp.get("choices") if isinstance(resp, dict) else None
        if not choices:
            return None
        choice = choices[0] if isinstance(choices[0], dict) else {}
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        content = (message.get("content") or "").strip()
        return content or None

    def _chat_response_error(self, resp: Dict[str, Any]) -> str:
        try:
            if isinstance(resp, dict) and resp.get("error"):
                return f"[Hermes offline] {resp.get('error')}"
            choices = resp.get("choices") if isinstance(resp, dict) else None
            if not choices:
                detail = json.dumps(resp, ensure_ascii=False)[:500] if isinstance(resp, dict) else str(resp)[:500]
                return f"[Hermes offline] invalid_chat_response: {detail}"
            choice = choices[0] if isinstance(choices[0], dict) else {}
            message = choice.get("message", {}) if isinstance(choice, dict) else {}
            content = (message.get("content") or "").strip()
            if not content:
                reasoning = (message.get("reasoning_content") or "").strip()
                finish_reason = choice.get("finish_reason") or "unknown"
                usage = resp.get("usage", {}) if isinstance(resp, dict) else {}
                reasoning_tokens = (
                    usage.get("completion_tokens_details", {}).get("reasoning_tokens")
                    if isinstance(usage, dict)
                    else None
                )
                if reasoning:
                    token_detail = f" reasoning_tokens={reasoning_tokens}" if reasoning_tokens is not None else ""
                    return (
                        "[Hermes offline] model_returned_reasoning_only "
                        f"finish_reason={finish_reason}{token_detail}; "
                        "LM Studio did not emit final assistant content after retry. "
                        "Use a non-reasoning chat model or increase the model context/output budget in LM Studio."
                    )
                return f"[Hermes offline] empty_chat_response finish_reason={finish_reason}"
        except Exception as e:
            detail = json.dumps(resp, ensure_ascii=False)[:500] if isinstance(resp, dict) else str(resp)[:500]
            return f"[Hermes offline] invalid_chat_response: {detail or e}"

    def compile_prompt(
        self,
        raw_concept: str,
        workflow_id: str,
        kimi_plan: Optional[Dict[str, Any]] = None,
        character_names: Optional[List[str]] = None,
        shot_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic prompt compiler entrypoint (no network call).
        """
        artifact = compile_prompt_artifact(
            raw_concept=raw_concept,
            workflow_id=workflow_id,
            kimi_plan=kimi_plan or {},
            character_names=character_names or [],
            shot_meta=shot_meta or {},
        )
        return artifact
