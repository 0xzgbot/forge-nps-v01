from core.prompts.prompt_compiler import compile_prompt_artifact
from core.prompts.prompt_standards import apply_model_prompt_standard


def test_flux_standard_removes_generic_quality_and_adds_specificity():
    prompt, skills = apply_model_prompt_standard(
        "A beautiful portrait, masterpiece, best quality. Negative prompt: blurry, bad anatomy.",
        workflow_id="01_flux2_text_to_image",
        model_family="flux2-dev",
    )
    low = prompt.lower()
    assert "masterpiece" not in low
    assert "best quality" not in low
    assert "negative prompt" not in low
    assert "material specificity" in low
    assert "optics:" in low
    assert "lighting source:" in low
    assert "flux-ltx-prompt-engineering-standard" in skills


def test_prompt_compiler_records_and_enforces_model_prompt_skills():
    artifact = compile_prompt_artifact(
        raw_concept="A fitness instructor smiles in a sunny travel plaza.",
        workflow_id="spark_image_flux2_text_to_image",
        kimi_plan={
            "shot_id": "SHOT_001",
            "sequence": 1,
            "visual_brief": "Natural lifestyle portrait of a fitness instructor holding a suitcase.",
            "environment": "Outdoor train station plaza in morning sun.",
            "camera_direction": "50mm eye-level portrait framing.",
            "lighting_direction": "warm window-reflected sunlight from camera left.",
            "characters": ["Nina"],
        },
    )
    prompt = artifact["compiled_prompt"].lower()
    assert "flux-ltx-prompt-engineering-standard" in artifact["skills_used"]
    assert "prompt standard enforcement" in prompt
    assert "material specificity" in prompt


def test_zimage_workflow_uses_zimage_skill_and_flux_foundation():
    artifact = compile_prompt_artifact(
        raw_concept="Hero product photo of a brushed aluminum travel mug.",
        workflow_id="spark_image_z_image_turbo",
        kimi_plan={
            "visual_brief": "Brushed aluminum travel mug on a wet stone cafe table.",
            "environment": "Cafe patio after rain.",
        },
    )
    assert "zimage-turbo-payload-generator" in artifact["skills_used"]
    assert "flux-ltx-prompt-engineering-standard" in artifact["skills_used"]
    assert artifact["model_standard_name"] == "zimage-turbo-payload-generator"
