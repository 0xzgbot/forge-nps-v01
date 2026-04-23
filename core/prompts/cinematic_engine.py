import json
from pathlib import Path
from typing import Dict, Any, Optional

class CinematicEngine:
    """
    Enhances base prompts with cinematic layers: LENS, LIGHTING, CAMERA_MOTION, and COLOR_GRADE.
    """

    def __init__(self, lighting_bank_path: str):
        self.lighting_bank_path = Path(lighting_bank_path)
        # Since the existing bank is a comma-separated list in a txt file, 
        # we'll handle it as a simple set/list or parse it.
        self.lighting_descriptors = self._load_lighting_bank()

    def _load_lighting_bank(self) -> list[str]:
        try:
            if self.lighting_bank_path.exists():
                with open(self.lighting_bank_path, 'r') as f:
                    content = f.read().strip()
                    # Split by comma and strip whitespace
                    return [item.strip() for item in content.split(',') if item.strip()]
            else:
                print(f"Warning: Lighting bank not found at {self.lighting_bank_path}")
                return []
        except Exception as e:
            print(f"Error loading lighting bank: {e}")
            return []

    def enhance(self, base_prompt: str, cinematic_params: Dict[str, Any]) -> str:
        enhanced_layers = []

        # 1. LENS Layer
        if "lens" in cinematic_params:
            lens = cinematic_params["lens"]
            enhanced_layers.append(f"{lens}")

        # 2. LIGHTING Layer
        if "lighting" in cinematic_params:
            lighting_key = cinematic_params["lighting"]
            # Check if it's in our bank, otherwise use as raw descriptor
            if lighting_key in self.lighting_descriptors:
                enhanced_layers.append(f"{lighting_key}")
            else:
                enhanced_layers.append(f"{lighting_key}")

        # 3. CAMERA_MOTION Layer (FLUX_DIR_COMMAND protocol style)
        if "camera_motion" in cinematic_params:
            motion = cinematic_params["camera_motion"]
            enhanced_layers.append(f"{motion}")

        # 4. COLOR_GRADE Layer
        if "color_grade" in cinematic_params:
            grade = cinematic_params["color_grade"]
            enhanced_layers.append(f"{grade} color grading")

        if not enhanced_layers:
            return base_prompt

        layers_str = ", ".join(enhanced_layers)
        # Combine base prompt with layers
        # We add "A detailed shot of" if the base is very short to make it more cinematic as per requirement example
        if len(base_prompt.split()) < 4:
            return f"A detailed shot of {base_prompt}, {layers_str}"
        
        return f"{base_prompt}, {layers_str}"

if __name__ == "__main__":
    # Simple self-test
    engine = CinematicEngine("~/Desktop/forge_nps_v01/data/character_banks/lighting_bank.txt")
    test_params = {
        "lens": "85mm lens, f/1.4",
        "lighting": "golden hour",
        "camera_motion": "low angle shot",
        "color_grade": "teal and orange"
    }
    result = engine.enhance("a cat", test_params)
    print(f"Result: {result}")
