from pathlib import Path

from dashboard import cinesmith_dashboard as dashboard


def test_rebuild_script_video_shots_from_storyboard_frames_uses_unique_sequences():
    dashboard._SHOTS_STORE[:] = []
    storyboard = {
        "title": "Test Storyboard",
        "panel_count": 4,
        "boards": [
            {
                "index": 1,
                "board_id": "STORYBOARD_01",
                "panels": [
                    {"panel_id": "PANEL_001", "caption": "first"},
                    {"panel_id": "PANEL_002", "caption": "second"},
                ],
            },
            {
                "index": 2,
                "board_id": "STORYBOARD_02",
                "panels": [
                    {"panel_id": "PANEL_003", "caption": "third"},
                    {"panel_id": "PANEL_004", "caption": "fourth"},
                ],
            },
        ],
    }
    panel_jobs = {
        "1": [{"url": "/media-assets/images/one.png"}, {"url": "/media-assets/images/two.png"}],
        "2": [{"url": "/media-assets/images/three.png"}, {"url": "/media-assets/images/four.png"}],
    }

    shots = dashboard._rebuild_script_video_shots_from_storyboard_frames("script_test", storyboard, panel_jobs)

    assert [shot["shot_id"] for shot in shots] == ["SB_001", "SB_002", "SB_003", "SB_004"]
    assert [shot["sequence"] for shot in shots] == [1, 2, 3, 4]
    assert len({shot["id"] for shot in shots}) == 4


def test_repair_script_video_urls_maps_legacy_duplicate_board_outputs(tmp_path, monkeypatch):
    dashboard._SHOTS_STORE[:] = []
    monkeypatch.setattr(dashboard, "MEDIA_VIDEOS", tmp_path)
    campaign_dir = tmp_path / "script_script_test"
    campaign_dir.mkdir(parents=True)
    for base in ("SB_001", "SB_002"):
        for version in ("00001", "00002"):
            (campaign_dir / f"script_script_test__{base}__video_{version}_.mp4").write_bytes(b"video")

    video_shots = [
        {"id": "script_script_test__SB_001", "shot_id": "SB_001", "sequence": 1},
        {"id": "script_script_test__SB_002", "shot_id": "SB_002", "sequence": 2},
        {"id": "script_script_test__SB_003", "shot_id": "SB_003", "sequence": 3},
        {"id": "script_script_test__SB_004", "shot_id": "SB_004", "sequence": 4},
    ]
    job = {
        "video_jobs": [
            {"shot_id": "script_script_test__SB_001", "status": "complete", "prompt_id": "p1"},
            {"shot_id": "script_script_test__SB_002", "status": "complete", "prompt_id": "p2"},
            {"shot_id": "script_script_test__SB_001", "status": "complete", "prompt_id": "p3"},
            {"shot_id": "script_script_test__SB_002", "status": "complete", "prompt_id": "p4"},
        ]
    }

    changed = dashboard._repair_script_video_urls_from_existing_outputs("script_test", video_shots, job)

    assert changed is True
    assert [Path(shot["video_path"]).name for shot in video_shots] == [
        "script_script_test__SB_001__video_00001_.mp4",
        "script_script_test__SB_002__video_00001_.mp4",
        "script_script_test__SB_001__video_00002_.mp4",
        "script_script_test__SB_002__video_00002_.mp4",
    ]
    assert [shot["video_prompt_id"] for shot in video_shots] == ["p1", "p2", "p3", "p4"]


def test_script_package_fingerprint_invalidates_changed_brief():
    req = dashboard.ScriptPipelineStartRequest(
        title="Test",
        brief="first idea",
        runtime_seconds=60,
        target_scenes=4,
        hook_first_dialogue=True,
    )
    package = dashboard._annotate_script_package({"title": "Test"}, req)

    assert dashboard._script_package_matches_request(package, req) is True

    changed = dashboard.ScriptPipelineStartRequest(
        title="Test",
        brief="second idea",
        runtime_seconds=60,
        target_scenes=4,
        hook_first_dialogue=True,
    )
    assert dashboard._script_package_matches_request(package, changed) is False


def test_load_script_project_rebuilds_video_shots_from_completed_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard, "SCRIPT_PROJECTS_DIR", tmp_path)
    dashboard._SHOTS_STORE[:] = []
    root = tmp_path / "script_done"
    root.mkdir(parents=True)
    dashboard._write_json_atomic(root / "project.json", {
        "script_id": "script_done",
        "title": "Script Done",
        "brief": "brief",
        "status": "frames_ready",
        "has_package": True,
    })
    dashboard._write_json_atomic(root / "storyboard_plan.json", {
        "title": "Script Done",
        "panel_count": 2,
        "boards": [{
            "index": 1,
            "board_id": "STORYBOARD_01",
            "panels": [
                {"panel_id": "PANEL_001", "caption": "first", "dialogue": "Hero: Start now."},
                {"panel_id": "PANEL_002", "caption": "second", "audio_prompt": "soft hit"},
            ],
        }],
    })
    dashboard._write_json_atomic(root / "storyboard_panel_jobs.json", {
        "1": [
            {"url": "/media-assets/images/one.png"},
            {"url": "/media-assets/images/two.png"},
        ],
    })
    dashboard._write_json_atomic(root / "video_shots.json", [])

    project = dashboard._load_script_project("script_done")

    assert len(project["video_shots"]) == 2
    assert project["video_shots"][0]["image_url"] == "/media-assets/images/one.png"
    assert "Exact dialogue" in project["video_shots"][0]["video_prompt"]
