import sys
import os
from pathlib import Path

# Add project root to sys.path so we can import core modules
project_root = "/Users/zgbot/Desktop/forge_nps_v01/"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.routing.prompt_enhancer import PromptEnhancer

def test_prompt_enhancer():
    # Setup dummy lighting bank for testing purposes
    lighting_bank_path = "/tmp/test_lighting_bank.txt"
    with open(lighting_bank_path, "w") as f:
        f.write("golden hour, moonlight, cinematic lighting, noir shadow, volumetric lighting")

    enhancer = PromptEnhancer(lighting_bank_path)

    print("Running Test Case 1: Standard Flux Shot with Style...")
    shot_1 = {"description": "a cat", "target_kernel": "flux_2_dev"}
    style_1 = {
        "name": "Golden Hour",
        "parameters": {
            "lens": "85mm f/1.4",
            "lighting": "golden hour",
            "color_grade": "warm"
        }
    }
    result_1 = enhancer.enhance_shot_prompt(shot_1, style_1)
    
    print(f"Input Description: {shot_1['description']}")
    print(f"Enhanced Prompt: {result_1['enhanced_prompt']}")
    print(f"Negative Prompt: {result_1['negative_prompt']}")

    assert "enhanced_prompt" in result_1
    assert "negative_prompt" in result_1
    assert "85mm f/1.4" in result_1["enhanced_prompt"]
    assert "golden hour" in result_1["enhanced_prompt"]
    # Check for the 'A detailed shot of' logic from CinematicEngine for short descriptions
    assert "A detailed shot of a cat" in result_1["enhanced_prompt"]

    print("\nRunning Test Case 2: Noir Style (Check Negatives)...")
    shot_2 = {"description": "a detective in a trench coat", "target_kernel": "flux_2_dev"}
    style_2 = {
        "name": "Film Noir",
        "parameters": {
            "lighting": "noir shadow",
            "color_grade": "black and white"
        }
    }
    result_2 = enhancer.enhance_shot_prompt(shot_2, style_2)

    print(f"Enhanced Prompt: {result_2['enhanced_prompt']}")
    print(f"Negative Prompt: {result_2['negative_prompt']}")

    assert "noir shadow" in result_2["enhanced_prompt"]
    # Noir should trigger 'bright colors, saturated, colorful' negative
    assert "bright colors" in result_2["negative_prompt"]

    print("\nRunning Test Case 3: LTX Video Kernel (Check Parameter Mapping)...")
    shot_3 = {"description": "waves crashing on a beach", "target_kernel": "ltx_video"}
    style_3 = {
        "name": "Naturalist",
        "parameters": {}
    }
    result_3 = enhancer.enhance_shot_prompt(shot_3, style_3)
    print(f"Enhanced Prompt: {result_3['enhanced_prompt']}")
    # LTX should have defaulted to 'static shot' if not provided (based on our implementation)
    assert "static shot" in result_3["enhanced_prompt"]

    print("\nALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    try:
        test_prompt_enhancer()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
