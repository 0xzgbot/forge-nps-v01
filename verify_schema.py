import json
import jsonschema
from jsonschema import validate

def test_validation():
    schema_path = '~/Desktop/forge_nps_v01/core/schemas/director_schema.json'
    
    with open(schema_path, 'r', encoding="utf-8") as f:
        schema = json.load(f)

    sample_data = {
        "production_metadata": {
            "project_title": "Cyberpunk Sunset",
            "overall_mood": "Melancholic but vibrant",
            "narrative_reasoning_trace": "Establishing a high-contrast environment to emphasize the neon lighting.",
            "consistency_anchors": [
                {
                    "anchor_id": "neon_flicker_01",
                    "constraint": "Neon signs must flicker at 2Hz rhythmically.",
                    "applies_to_shots": ["shot_001", "shot_002"]
                }
            ],
            "visual_style_guide": {
                "color_palette": ["#FF00FF", "#00FFFF", "#1A1A1A"],
                "lighting_profile": "High contrast, heavy bloom on neon sources",
                "texture_descriptors": ["wet asphalt", "scuffed chrome"]
            }
        },
        "shot_list": [
            {
                "shot_id": "shot_001",
                "sequence_order": 1,
                "reasoning_trace": "Wide angle to establish the scale of the cityscape.",
                "predicted_failure_modes": [
                    {
                        "failure_type": "Photometric",
                        "risk_level": "medium",
                        "mitigation": "Increase exposure compensation for shadows."
                    },
                    {
                        "failure_type": "Anatomical",
                        "risk_level": "low",
                        "mitigation": "N/A - no characters in shot."
                    }
                ],
                "visual_prompt": {
                    "subject": "Cyberpunk cityscape",
                    "action": "Distant flying vehicles moving through fog",
                    "environment": "Neon-lit street level looking up",
                    "camera": {
                        "movement": "pan",
                        "speed": "slow",
                        "altitude": "low",
                        "angle": "low angle"
                    },
                    "lens_specs": {
                        "focal_length": "24mm",
                        "depth_of_field": "deep"
                    }
                },
                "audio_directive": {
                    "music_style": "Synthwave",
                    "tempo": "80 BPM",
                    "sfx_elements": ["distant engine hum", "rain patter"],
                    "ambient_soundscape": "Rainy urban atmosphere"
                }
            }
        ]
    }

    try:
        validate(instance=sample_data, schema=schema)
        print("SUCCESS: Validation passed!")
    except jsonschema.exceptions.ValidationError as e:
        print(f"FAILURE: Validation failed: {e.message}")
        exit(1)
    except Exception as e:
        print(f"ERROR: An unexpected error occurred: {e}")
        exit(1)

if __name__ == "__main__":
    test_validation()
