from typing import Dict, Any
import logging

logger = logging.getLogger("CopywriterAgent")

class CopywriterAgent:
    def __init__(self, kimi_bridge: Any):
        self.kimi_bridge = kimi_bridge
        self.persona = "Copywriting God"

    async def generate_copy(self, shot_id: str, description: str) -> Dict[str, Any]:
        """
        Generates high-engagement marketing copy for a specific shot.
        """
        logger.info(f"CopywriterAgent generating copy for shot {shot_id}")
        
        system_prompt = (
            f"You are the {self.persona}. Your task is to write elite-level, high-engagement "
            "marketing copy for a cinematic asset. You specialize in platform-specific hooks: "
            "X (short, punchy, viral) and Instagram (visual, evocative, storytelling). "
            "Use emojis sparingly but effectively. Focus on emotion and curiosity."
        )

        user_input = (
            f"SHOT ID: {shot_id}\n"
            f"VISUAL DESCRIPTION: {description}\n\n"
            "Please provide the following in JSON format:\n"
            "{\n"
            '  "x_post": "A punchy X post with a hook and hashtags",\n'
            '  "instagram_caption": "An evocative Instagram caption that tells a story",\n'
            '  "engagement_score": 0-100 (your estimation of viral potential)\n'
            "}"
        )

        try:
            # We use the bridge to call Kimi
            response = await self.kimi_bridge.direct(
                system_prompt=system_prompt,
                user_input=user_input,
                schema=None # In a real implementation, we'd pass a Pydantic model
            )

            # If response is not already a dict (depending on bridge implementation), try to parse it
            if isinstance(response, str):
                import json
                return json.loads(response)
            elif hasattr(response, "model_dump"):
                return response.model_dump()
            else:
                return response

        except Exception as e:
            logger.error(f"CopywriterAgent failed: {e}")
            return {
                "x_post": f"Check out this incredible shot! #cinematic #{shot_id}",
                "instagram_caption": "A moment frozen in time. ✨",
                "engagement_score": 0,
                "error": str(e)
            }
