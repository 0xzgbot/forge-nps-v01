"""
NousHermesBridge — wraps LMStudioClient to give Hermes-3 a structured API.
Hermes-3 is the local creative brain: writes prompts, diagnoses failures,
generates scripts and character DNA.
"""
import os
import json
import logging
from typing import Any, Dict, List, Optional

# We must use absolute imports or ensure project root is in PYTHONPATH
try:
    from core.bridge.lmstudio_client import LMStudioClient
except ImportError:
    import sys
    sys.path.append("/Users/zgbot/Desktop/forge_nps_v01")
    from core.bridge.lmstudio_client import LMStudioClient

logger = logging.getLogger("NousHermesBridge")

HERMES_SYSTEM = (
    "You are Hermes, an AI creative director specialized in visual storytelling "
    "and cinematic image generation. You think in terms of composition, lighting, "
    "character presence, and visual continuity. Be specific, vivid, and concise."
)


class NousHermesBridge:
    def __init__(self):
        self.model = os.getenv("NOUS_HERMES_MODEL", "Hermes-3-Llama-3.2-3B")
        self.client = LMStudioClient()

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
    ) -> Optional[str]:
        """Write a cinematic Stable Diffusion prompt for a shot brief."""
        user = (
            f"Shot brief: {concept}\n"
            f"{f'Memory context: {memory_context}' if memory_context else ''}\n"
            "Write a vivid, specific Stable Diffusion prompt (2-4 sentences). "
            "Include: subject, action, lighting, mood, camera angle, style."
        )
        try:
            resp = await self.client.chat_async(
                messages=[
                    {"role": "system", "content": HERMES_SYSTEM},
                    {"role": "user", "content": user},
                ],
                model=self.model,
                temperature=0.8,
                max_tokens=300,
            )
            return resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
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
            return resp["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"[HERMES] chat failed: {e}")
            return f"[Hermes offline] {e}"
