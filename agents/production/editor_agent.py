from typing import Dict, Any
import logging

logger = logging.getLogger("EditorAgent")

class EditorAgent:
    def __init__(self, kimi_bridge: Any):
        self.kimi_bridge = kimi_bridge
        self.persona = "Cinematic Post-Production Supervisor"

    async def refine_asset(self, shot_id: str, description: str) -> Dict[str, Any]:
        """
        Provides post-production instructions or automated refinement parameters.
        """
        logger.info(f"EditorAgent refining shot {shot_id}")

        system_prompt = (
            f"You are the {self.persona}. Your job is to review a visual description and "
            "provide technical post-production instructions to ensure it meets high cinematic standards. "
            "Focus on lighting, color grading (LUTs), motion strength (for video models like LTX 2.3), "
            "and camera movement parameters."
        )

        user_input = (
            f"SHOT ID: {shot_id}\n"
            f"VISUAL DESCRIPTION: {description}\n\n"
            "Provide the following in JSON format:\n"
            "{\n"
            '  "motion_strength": 0.0-1.0 (intensity of movement),\n'
            '  "color_grading_notes": "Specific instructions for colorists/LUTs",\n'
            '  "camera_movement": "Detailed camera instruction (e.g., slow dolly zoom, handheld)",\n'
            '  "lighting_adjustments": "Refinements to light/shadow intensity or direction"\n'
            "}"
        )

        try:
            response = await self.kimi_bridge.direct(
                system_prompt=system_prompt,
                user_input=user_input,
                schema=None
            )

            if isinstance(response, str):
                import json
                return json.loads(response)
            elif hasattr(response, "model_dump"):
                return response.model_dump()
            else:
                return response

        except Exception as e:
            logger.error(f"EditorAgent failed: {e}")
            return {
                "motion_strength": 0.5,
                "color_grading_notes": "Default cinematic grade",
                "camera_movement": "Static or minimal movement",
                "lighting_adjustments": "Standard lighting",
                "error": str(e)
            }
