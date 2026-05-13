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


def test_fitness_prompts_lock_role_without_unrequested_variation_assumptions():
    prompt, _ = apply_model_prompt_standard(
        "20 images of female fitness instructors in a studio, full-body portraits.",
        workflow_id="01_flux2_text_to_image",
        model_family="flux2-dev",
    )
    low = prompt.lower()
    assert "fitness role fidelity" in low
    assert "visibly conditioned athletic build" in low
    assert "batch intent lock" in low
    assert "do not invent subject traits" in low
    assert "athletic casting variation" not in low
    assert "generic body-type diversification" not in low
    assert "each person has a distinct face shape, age bracket, hairstyle, body type" not in low
    assert "skin tone" not in low
    assert "demographic" not in low


def test_explicit_subject_age_and_role_locks_are_added():
    prompt, _ = apply_model_prompt_standard(
        "Portrait of a 27-year-old female doctor in a hospital exam room.",
        workflow_id="01_flux2_text_to_image",
        model_family="flux2-dev",
    )
    low = prompt.lower()
    assert "subject lock" in low
    assert "female/woman presentation" in low
    assert "age lock" in low
    assert "medical role fidelity" in low


def test_product_and_brand_prompts_block_invented_details():
    prompt, _ = apply_model_prompt_standard(
        "Hero product photo of a matte black desk lamp with logo on packaging.",
        workflow_id="01_flux2_text_to_image",
        model_family="flux2-dev",
    )
    low = prompt.lower()
    assert "product fidelity" in low
    assert "preserve the exact requested product category" in low
    assert "brand/text fidelity" in low
    assert "do not invent readable words" in low


def test_prompt_hole_audit_locks_professional_athlete_food_location_and_age_roles():
    cases = [
        (
            "Portrait of a CEO in a glass boardroom presenting a quarterly strategy.",
            ["professional role fidelity", "credible industry wardrobe", "location fidelity"],
            ["generic model", "fantasy styling"],
        ),
        (
            "Runner exploding out of starting blocks on an Olympic track.",
            ["athlete role fidelity", "sport-specific body mechanics"],
            ["generic athleisure posing"],
        ),
        (
            "Luxury watch product photo on black stone with brushed steel bracelet and logo packaging.",
            ["product fidelity", "brand/text fidelity", "luxury product fidelity"],
            ["incorrect materials"],
        ),
        (
            "Editorial food photo of sushi on a cedar counter in a Tokyo restaurant.",
            ["food fidelity", "requested dish", "location fidelity"],
            ["unrelated ingredients"],
        ),
        (
            "Documentary portrait of a 10-year-old student in a classroom science fair.",
            ["age safety lock", "location fidelity"],
            ["do not age"],
        ),
    ]
    for raw, expected, anti_drift in cases:
        prompt, _ = apply_model_prompt_standard(
            raw,
            workflow_id="01_flux2_text_to_image",
            model_family="flux2-dev",
        )
        low = prompt.lower()
        for phrase in expected:
            assert phrase in low
        for phrase in anti_drift:
            assert phrase in low
        assert "demographic" not in low
        assert "skin tone" not in low


def test_full_body_and_storyboard_prompts_block_cropping_and_contact_sheets():
    prompt, _ = apply_model_prompt_standard(
        "Full-body portrait of a fitness instructor standing on a gym floor.",
        workflow_id="01_flux2_text_to_image",
        model_family="flux2-dev",
        render_type="storyboard",
    )
    low = prompt.lower()
    assert "fitness role fidelity" in low
    assert "full-body framing lock" in low
    assert "both feet or shoes visible" in low
    assert "do not crop through legs" in low
    assert "storyboard frame lock" in low
    assert "no contact sheet" in low
    assert "no readable signage" in low


def test_prompt_locks_do_not_disappear_when_raw_prompt_contains_related_words():
    prompt, _ = apply_model_prompt_standard(
        "Storyboard start frame, full body visible head to toe, luxury brushed steel watch with controlled reflections, edible sushi in a Tokyo restaurant.",
        workflow_id="01_flux2_text_to_image",
        model_family="flux2-dev",
        render_type="storyboard",
    )
    low = prompt.lower()
    assert "full-body framing lock" in low
    assert "luxury product fidelity" in low
    assert "food fidelity" in low
    assert "location fidelity" in low
    assert "storyboard frame lock" in low


def test_compiler_truncation_preserves_prompt_standard_enforcement():
    long_brief = "20 images of female fitness instructors in a studio, full-body portraits. " + (
        "premium activewear campaign " * 120
    )
    artifact = compile_prompt_artifact(
        raw_concept=long_brief,
        workflow_id="spark_image_flux2_text_to_image_turbo",
        kimi_plan={
            "visual_brief": long_brief,
            "environment": "clean studio",
            "camera_direction": "vertical full-body framing",
            "lighting_direction": "large softbox",
        },
    )
    low = artifact["compiled_prompt"].lower()
    assert "compiled_prompt_truncated" in artifact["warnings"]
    assert "prompt standard enforcement" in low
    assert "fitness role fidelity" in low
    assert "batch intent lock" in low
    assert "athletic casting variation" not in low


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
