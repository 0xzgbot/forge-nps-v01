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
        self.client = LMStudioClient()
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

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        """General chat — used by Hermes Live panel CLI."""
        # Prepend system message if not already present
        if not messages or messages[0].get("role") != "system":
            messages = [{"role": "system", "content": HERMES_SYSTEM}] + messages
        try:
            resp = await self.client.chat_async(
                messages=messages,
                model=self.model,
                temperature=0.8,
                max_tokens=500,
            )
            if isinstance(resp, dict) and resp.get("error"):
                return f"[Hermes offline] {resp.get('error')}"
            choices = resp.get("choices") if isinstance(resp, dict) else None
            if not choices:
                detail = json.dumps(resp, ensure_ascii=False)[:500] if isinstance(resp, dict) else str(resp)[:500]
                return f"[Hermes offline] invalid_chat_response: {detail}"
            content = (choices[0].get("message", {}).get("content") or "").strip()
            if not content:
                return "[Hermes offline] empty_chat_response"
            return content
        except Exception as e:
            logger.warning(f"[HERMES] chat failed: {e}")
            return f"[Hermes offline] {e}"

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
