from pathlib import Path

import pytest

from core.dispatch.capability_router import CapabilityRouter
from core.dispatch.comfy_client import (
    ComfyUIClient,
    align_h3_length,
    first_output_filename,
)
from core.dispatch.workflows import (
    DEFAULT_VIDEO_WORKFLOW_ID,
    capability_for_workflow,
    take_workflow_for_mode,
    workflow_file_for_id,
)


def test_capability_for_workflow_splits_stills_and_spark():
    assert capability_for_workflow("01_flux2_text_to_image") == "stills"
    assert capability_for_workflow("21_minimax_h3_image_to_video") == "spark"
    assert capability_for_workflow("04_ltx2.3_image_to_video") == "spark"
    assert capability_for_workflow("23_minimax_h3_reference_to_video") == "spark"


def test_h3_workflow_files_exist():
    for workflow_id in (
        "20_minimax_h3_text_to_video",
        "21_minimax_h3_image_to_video",
        "22_minimax_h3_first_last_frame_to_video",
        "23_minimax_h3_reference_to_video",
        DEFAULT_VIDEO_WORKFLOW_ID,
    ):
        path = workflow_file_for_id(workflow_id)
        assert path is not None, workflow_id
        assert path.exists()


def test_take_modes_map_to_h3():
    assert "h3" in take_workflow_for_mode("i2va")
    assert "text" in take_workflow_for_mode("t2va")
    assert "first_last" in take_workflow_for_mode("fl2va")
    assert "reference" in take_workflow_for_mode("r2va")


def test_router_does_not_mix_spark_into_stills_list_when_secondary_set():
    router = CapabilityRouter(
        {
            "COMFYUI_PRIMARY": "http://spark:8188",
            "COMFYUI_SECONDARY": "http://gpu:8189",
            "COMFYUI_STILLS_B": "http://gpu:8190",
        }
    )
    assert router.spark_urls() == ["http://spark:8188"]
    assert router.stills_urls() == ["http://gpu:8189", "http://gpu:8190"]
    assert "http://gpu:8189" not in router.spark_urls()


def test_router_stills_fallback_to_spark_when_only_primary():
    router = CapabilityRouter({"COMFYUI_PRIMARY": "http://spark:8188"})
    assert router.stills_urls() == ["http://spark:8188"]


def test_align_h3_length_snaps_to_grid():
    assert align_h3_length(120) == 124
    assert align_h3_length(124) == 124


def test_first_output_filename_prefers_video():
    outputs = {
        "9": {"images": [{"filename": "preview.png"}]},
        "15": {"gifs": [{"filename": "take.mp4"}]},
    }
    assert first_output_filename(outputs) == "take.mp4"


@pytest.mark.asyncio
async def test_submit_injects_h3_prompt(tmp_path, monkeypatch):
    workflow = {
        "6": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {"prompt": "", "width": 16, "height": 16, "length": 5},
        },
        "15": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "x"}},
    }
    path = tmp_path / "h3.json"
    path.write_text(__import__("json").dumps(workflow), encoding="utf-8")
    captured = {}

    async def fake_object_info(self):
        return {}

    async def fake_submit_prompt(self, nodes):
        captured["nodes"] = nodes
        return {"ok": True, "prompt_id": "p1"}

    monkeypatch.setattr(ComfyUIClient, "_get_object_info", fake_object_info)
    monkeypatch.setattr(ComfyUIClient, "submit_prompt", fake_submit_prompt)
    result = await ComfyUIClient("http://spark:8188").submit_prompt_for_shot(
        prompt="wet city walk with stereo rain",
        workflow_path=str(path),
        wait_for_output=False,
        duration=5,
        fps=24,
    )
    assert result["status"] == "success"
    assert captured["nodes"]["6"]["inputs"]["prompt"] == "wet city walk with stereo rain"
    assert captured["nodes"]["6"]["inputs"]["length"] == 124
