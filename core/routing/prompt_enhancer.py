from typing import Dict, Any
from core.prompts.cinematic_engine import CinematicEngine

class PromptEnhancer:
    """
    High-level Intent Router that orchestrates how shot descriptions are 
    transformed into technical model payloads using the CinematicEngine.
    """

    def __init__(self, lighting_bank_path: str):
        self.cinematic_engine = CinematicEngine(lighting_bank_path)

    def enhance_shot_prompt(self, shot: Dict[str, Any], style: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes target kernel and maps high-level styles to technical parameters.
        
        Args:
            shot: {'description': str, 'target_kernel': str}
            style: {'name': str, 'parameters': dict} (e.g., {'name': 'Noir', 'params': {...}})
            
        Returns:
            Enriched shot dictionary with 'enhanced_prompt' and 'negative_prompt'.
        """
        description = shot.get("description", "")
        target_kernel = shot.get("target_kernel", "flux_2_dev")
        
        # 1. Map style to technical parameters
        # We merge user-provided style params with kernel-specific defaults/constraints
        cinematic_params = self._map_style_to_params(style, target_kernel)

        # 2. Call CinematicEngine for the heavy lifting of string building
        enhanced_prompt = self.cinematic_engine.enhance(description, cinematic_params)

        # 3. Determine negative prompt based on kernel and style
        negative_prompt = self._generate_negative_prompt(target_kernel, style)

        # Create a copy to avoid mutating the input shot directly
        enriched_shot = shot.copy()
        enriched_shot["enhanced_prompt"] = enhanced_prompt
        enriched_shot["negative_prompt"] = negative_prompt

        return enriched_shot

    def _map_style_to_params(self, style: Dict[str, Any], target_kernel: str) -> Dict[str, Any]:
        """
        Logic to decide which cinematic parameters are valid and map styles.
        """
        # Default params
        params = {}

        # Extract base style name and any provided overrides
        style_name = style.get("name", "default")
        overrides = style.get("parameters", {})
        params.update(overrides)

        # Kernel-specific logic (e.g., LTX might need specific motion scales, Flux doesn't care as much about certain things)
        if target_kernel == "ltx_video":
            # Ensure we have some motion if it's a video kernel
            if "camera_motion" not in params:
                params["camera_motion"] = "static shot" # Default for LTX if unspecified
            # Example of kernel-specific constraint: 
            # LTX might be sensitive to certain lens types or we might want to enforce specific scales
        
        elif target_kernel == "flux_2_dev":
            # Flux handles descriptive text very well, so maybe less reliance on heavy technical jargon?
            # But for this exercise, we follow the style.
            pass

        return params

    def _generate_negative_prompt(self, target_kernel: str, style: Dict[str, Any]) -> str:
        """
        Generates appropriate negative prompts based on kernel capabilities.
        """
        negatives = []
        
        # Kernel specific negatives
        if target_kernel == "flux_2_dev":
            # Flux often doesn't need much negative prompting, but we can provide defaults
            negatives.append("deformed, blurry, low quality")
        elif target_kernel == "sdxl":
            negatives.append("ugly, tiling, poorly drawn hands, poorly drawn feet, poorly drawn face, out of frame, extra limbs, disfigured, deformed, body out of frame, blurry, bad anatomy, blurred, watermark, grainy, signature, cut off, draft")

        # Style specific negatives (e.g., Noir should NOT be colorful)
        style_name = style.get("name", "").lower()
        if "noir" in style_name:
            negatives.append("bright colors, saturated, colorful")
        elif "golden hour" in style_name or "sunset" in style_name:
            negatives.append("darkness, night, blue tones, cold lighting")

        return ", ".join(negatives) if negatives else ""

if __name__ == "__main__":
    # Quick smoke test
    import os
    # Create a dummy lighting bank for the test
    dummy_bank = "/tmp/test_lighting.txt"
    with open(dummy_bank, "w", encoding="utf-8") as f:
        f.write("golden hour, moonlight, cinematic lighting, studio lighting")

    enhancer = PromptEnhancer(dummy_bank)
    
    shot = {"description": "a futuristic car", "target_kernel": "flux_2_dev"}
    style = {
        "name": "Cyberpunk Noir", 
        "parameters": {
            "lens": "35mm anamorphic lens",
            "lighting": "moonlight",
            "color_grade": "neon blue and magenta"
        }
    }

    result = enhancer.enhance_shot_prompt(shot, style)
    print(f"ENHANCED PROMPT: {result['enhanced_prompt']}")
    print(f"NEGATIVE PROMPT: {result['negative_prompt']}")

    # Assertions
    assert "enhanced_prompt" in result
    assert "negative_prompt" in result
    assert "35mm anamorphic lens" in result["enhanced_prompt"]
    assert "moonlight" in result["enhanced_prompt"]
    print("Smoke test passed!")
