from core.hermes.pipeline.director_service import KimiDirectorService


def test_requested_shot_count_reads_explicit_image_count():
    assert KimiDirectorService.requested_shot_count("make 20 images of a character arc") == 20
    assert KimiDirectorService.requested_shot_count("Images: 12 for the product launch") == 12
    assert KimiDirectorService.requested_shot_count("Need eight stills for the campaign") == 8


def test_requested_shot_count_uses_length_field_and_bounds_values():
    assert KimiDirectorService.requested_shot_count("pixar-style bedtime story", "30 shots") == 30
    assert KimiDirectorService.requested_shot_count("generate 999 images") == 120
    assert KimiDirectorService.requested_shot_count("single hero prompt") == 5


def test_fallback_people_plan_assigns_distinct_cast():
    service = KimiDirectorService()
    plan = service.build_dev_fallback_plan("make 20 portraits of everyday people", "test_campaign", target_shots=20)
    shots = plan["shots"]
    assert len(shots) == 20
    assert shots[0]["characters"]
    assert "Mara Ellis" in shots[0]["visual_brief"]
    assert "Dante Brooks" in shots[1]["visual_brief"]
    assert "preserve distinct cast identity" in shots[0]["constraints"]
