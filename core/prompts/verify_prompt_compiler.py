import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.prompts.prompt_compiler import compile_prompt_artifact


def main():
    concept = "A red Jeep powers through autumn aspens at golden hour with cinematic dust trails."
    kimi_plan = {
        "shot_id": "SHOT_001",
        "visual_brief": "Hero vehicle three-quarter front tracking shot with visible terrain detail.",
        "environment": "Colorado mountain pass with dense yellow aspens and winding gravel road.",
        "camera_direction": "low-angle tracking, 35mm lens, medium-wide composition",
        "lighting_direction": "warm late-afternoon directional sunlight with subtle haze",
        "rationale": "Establish premium adventure tone and immediate brand recognition.",
        "constraints": "vehicle anatomy must remain accurate, no text overlays",
        "characters": ["Driver"],
    }

    z = compile_prompt_artifact(
        raw_concept=concept,
        workflow_id="spark_image_z_image",
        kimi_plan=kimi_plan,
        character_names=["Driver"],
        shot_meta={"campaign_id": "verify"},
    )
    f = compile_prompt_artifact(
        raw_concept=concept,
        workflow_id="spark_image_flux2_text_to_image",
        kimi_plan=kimi_plan,
        character_names=["Driver"],
        shot_meta={"campaign_id": "verify"},
    )
    u = compile_prompt_artifact(
        raw_concept=concept,
        workflow_id="unknown_workflow",
        kimi_plan=kimi_plan,
        character_names=["Driver"],
        shot_meta={"campaign_id": "verify"},
    )

    print("Z_IMAGE_PROFILE:", z["profile_name"])
    print("FLUX_PROFILE:", f["profile_name"])
    print("UNKNOWN_PROFILE:", u["profile_name"])
    print("Z_IMAGE_STANDARD:", z.get("model_standard_name"), z.get("model_standard_version"))
    print("FLUX_STANDARD:", f.get("model_standard_name"), f.get("model_standard_version"))
    print("PROMPTS_DIFFER:", z["compiled_prompt"] != f["compiled_prompt"])
    print("UNKNOWN_WARNINGS:", ",".join(u.get("warnings", [])))
    print(json.dumps({"z": z, "flux": f, "unknown": u}, indent=2))


if __name__ == "__main__":
    main()
