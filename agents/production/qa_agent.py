from typing import Dict, Any, List, Optional, Type
import logging
from pydantic import BaseModel

# Import the VL client and schema requirements
from core.bridge.kimi_vl_client import KimiVLClient

logger = logging.getLogger("QA_Agent")

class QAAuditSchema(BaseModel):
    pass_flag: bool
    quality_report: str
    error_category: str
    remediation_suggestion: str

class QAAgent:
    def __init__(self, kimi_bridge: Any):
        self.kimi_bridge = kimi_bridge
        # If the bridge is actually a KimiVLClient, we can use it for visual audits.
        # Otherwise, we default to standard KimiBridge capabilities.
        self.persona = "Master Quality Assurance Auditor"

    async def perform_textual_audit(self, shot_id: str, asset_description: str, original_prompt: str, lore_bible_content: str) -> Dict[str, Any]:
        """
        Performs narrative/descriptive audits using the standard KimiBridge.
        """
        system_prompt = (
            f"You are the {self.persona}. Your role is the final quality gate before assets reach production. "
            "You must perform a rigorous visual and narrative audit to ensure everything matches the brand, "
            "the original intent of the prompt, and the established lore."
        )

        user_input = (
            f"AUDIT REQUEST:\n"
            f"SHOT ID: {shot_id}\n\n"
            f"ORIGINAL PROMPT: {original_prompt}\n\n"
            f"GENERATED ASSET DESCRIPTION: {asset_description}\n\n"
            f"LORE BIBLE CONTEXT:\n{lore_bible_content}\n\n"
            "INSTRUCTIONS:\n"
            "1. Does the generated asset description match the original prompt's intent?\n"
            "2. Are there any lore contradictions (characters, locations, physics)?\n"
            "3. Is the visual quality described high enough for a premium production?\n\n"
            "OUTPUT FORMAT (JSON):\n"
            "{\n"
            '  "pass_flag": boolean,\n'
            '  "quality_report": "Detailed assessment of strengths and weaknesses",\n'
            '  "error_category": "None | Prompt Mismatch | Lore Contradiction | Visual Quality",\n'
            '  "remediation_suggestion": "If pass is false, how should the description be changed?"\n'
            "}"
        )

        try:
            response = await self.kimi_bridge.direct(
                system_prompt=system_prompt,
                user_input=user_input,
                schema=QAAuditSchema
            )
            return response
        except Exception as e:
            logger.error(f"QA_Agent textual audit failed for {shot_id}: {e}")
            return {"pass_flag": False, "quality_report": f"Audit error: {str(e)}", "error_category": "System Error", "remediation_suggestion": ""}

    async def perform_visual_audit(self, shot_id: str, image_path: str, original_prompt: str, lore_bible_content: str) -> Dict[str, Any]:
        """
        Performs actual visual audits by sending the asset image to Kimi-VL.
        Requires self.kimi_bridge to be an instance of KimiVLClient.
        """
        if not isinstance(self.kimi_bridge, KimiVLClient):
            raise TypeError("Visual audit requires KimiVLClient. Ensure kimi_bridge is initialized as KimiVLClient.")

        logger.info(f"QA_Agent performing VISUAL audit for shot {shot_id}")

        system_prompt = (
            f"You are the {self.persona}. You are performing a direct visual inspection of a production asset. "
            "Analyze the image provided against the original prompt and lore constraints."
        )

        user_input = (
            f"VISUAL AUDIT REQUEST:\n"
            f"SHOT ID: {shot_id}\n\n"
            f"ORIGINAL PROMPT: {original_prompt}\n\n"
            f"LORE BIBLE CONTEXT:\n{lore_bible_content}\n\n"
            "INSTRUCTIONS:\n"
            "1. Does the actual image match the intended visual elements of the prompt?\n"
            "2. Are there any lore contradictions (e.g., wrong colors, impossible physics, character mismatch)?\n"
            "3. Is the composition, lighting, and quality consistent with high-end cinematic standards?\n\n"
            "OUTPUT FORMAT (JSON):\n"
            "{\n"
            '  "pass_flag": boolean,\n'
            '  "quality_report": "Detailed visual assessment of strengths/weaknesses",\n'
            '  "error_category": "None | Prompt Mismatch | Lore Contradiction | Visual Quality",\n'
            '  "remediation_suggestion": "Specific instruction for the next generation cycle."\n'
            "}"
        )

        try:
            response = await self.kimi_bridge.analyze_visuals(
                image_path=image_path,
                system_prompt=system_prompt,
                user_prompt=user_input,
                schema=QAAuditSchema
            )
            return response
        except Exception as e:
            logger.error(f"QA_Agent visual audit failed for {shot_id}: {e}")
            return {"pass_flag": False, "quality_report": f"Visual Audit system error: {str(e)}", "error_category": "System Error", "remediation_suggestion": ""}

    async def perform_audit(self, shot_id: str, asset_description: str, original_prompt: str, lore_bible_content: str) -> Dict[str, Any]:
        """
        Legacy compatibility method. Routes to textual audit.
        """
        return await self.perform_textual_audit(shot_id, asset_description, original_prompt, lore_bible_content)
