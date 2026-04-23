import logging
from enum import Enum
from typing import Dict, Any, Optional
from core.bridge.config_manager import ConfigManager

logger = logging.getLogger("KimiModelRouter")

class ModelTier(Enum):
    INSTRUCT = "kimi-instruct"      # Fast, cheap, creative (captions, simple editing)
    THINKING = "kimi-thinking"      # High reasoning (physics audits, complex continuity)
    VISUAL = "kimi-vl"              # Vision-Language (image/video auditing, visual inspection)

class KimiModelRouter:
    """
    Intelligent routing engine that maps task intent to the optimal Kimi model tier.
    Decisions are based on task complexity and required modality.
    """

    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        # Mapping of specific keywords or 'intents' to ModelTiers
        self._intent_map = {
            "caption": ModelTier.INSTRUCT,
            "hook": ModelTier.INSTRUCT,
            "describe": ModelTier.INSTRUCT,
            "audit": ModelTier.THINKING,
            "verify": ModelTier.THINKING,
            "consistency": ModelTier.THINKING,
            "remediate": ModelTier.THINKING,
            "inspect": ModelTier.VISUAL,
            "describe_visuals": ModelTier.VISUAL,
            "analyze_frame": ModelTier.VISUAL,
        }

    def route(self, task_description: str, has_visuals: bool = False) -> ModelTier:
        """
        Determines the target model tier based on task description and visual requirements.
        """
        desc_lower = task_description.lower()
        
        # 1. Priority Rule: If visuals are explicitly required for analysis, force VISUAL tier.
        if has_visuals and any(word in desc_lower for word in ["see", "look", "inspect", "visual", "analyze frame"]):
            logger.info(f"Routing to VISUAL tier due to visual requirement: {task_description}")
            return ModelTier.VISUAL

        # 2. Keyword-based intent matching
        for keyword, tier in self._intent_map.items():
            if keyword in desc_lower:
                logger.info(f"Routing to {tier.value} based on keyword '{keyword}': {task_description}")
                return tier

        # 3. Fallback Logic
        # If the description is long/complex, assume it needs reasoning (THINKING).
        if len(desc_lower.split()) > 50:
            logger.info("Routing to THINKING tier due to task complexity.")
            return ModelTier.THINKING

        # Default to standard INSTRUCT for everything else.
        logger.debug(f"Defaulting to INSTRUCT tier: {task_description}")
        return ModelTier.INSTRUCT

    def get_model_endpoint(self, tier: ModelTier) -> str:
        """
        Retrieves the actual API endpoint or model identifier from ConfigManager.
        """
        config_key = f"KIMI_{tier.name}_MODEL"
        endpoint = self.config.get(config_key)
        if not endpoint:
            logger.error(f"Configuration for {config_key} missing!")
            # Fallback to a generic instruct model if specifically configured tier is missing
            return self.config.get("KIMI_INSTRUCT_MODEL", "kimi-instruct")
        return endpoint
