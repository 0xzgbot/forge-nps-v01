from core.hermes.platform_skills import (
    apply_viral_hook_remediation_to_first_shot,
    detect_platform_skill,
    generate_hook_ideas,
    platform_prompt_clause,
    review_flags_low_watch_time,
)


def test_tiktok_detection_for_vertical_brief():
    platform = detect_platform_skill("Need happy TikTok travel videos with a girl next door character")

    assert platform["active"] is True
    assert platform["id"] == "tiktok_vertical"
    assert platform["constraints"]["width"] == 1080
    assert platform["constraints"]["height"] == 1920
    assert platform["series_continuity"] is True
    assert "girl_next_door_realism" in platform["skills"]


def test_tiktok_detection_respects_negation():
    platform = detect_platform_skill("Make a cinematic launch film, not TikTok style")

    assert platform["active"] is False
    assert platform["negated"] is True


def test_forced_tiktok_mode_activates_without_keyword():
    platform = detect_platform_skill("A soft travel scene", requested_mode="tiktok")

    assert platform["active"] is True
    assert "1080x1920" in platform_prompt_clause(platform)


def test_hook_generation_returns_audio_directions():
    platform = detect_platform_skill("TikTok video about sunlit travel")
    hooks = generate_hook_ideas("TikTok video about sunlit travel", platform)

    assert len(hooks) >= 3
    assert all(hook.get("hook") for hook in hooks)
    assert all(hook.get("audio") for hook in hooks)


def test_low_watch_time_review_remediates_first_shot():
    shots = [{"visual_brief": "Wide establishing shot of a beach.", "constraints": ""}]
    review = {"viral_risks": ["low watch-time risk in first 3 seconds"]}

    assert review_flags_low_watch_time(review) is True
    assert apply_viral_hook_remediation_to_first_shot(shots) is True
    assert "Opening hook revision" in shots[0]["visual_brief"]
    assert shots[0]["viral_hook_remediated"] is True
