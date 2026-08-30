"""D3: First/last frame video mode — pair resolution + submit image_paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from core.hermes.pipeline.video_service import HermesVideoService


FIRST_LAST_WF = "05_ltx2.3_first_last_frame_to_video"
I2V_WF = "04_ltx2.3_image_to_video"


# ---------------------------------------------------------------------------
# Pure pair-resolution unit tests (no I/O)
# ---------------------------------------------------------------------------


def test_is_first_last_workflow_detects_aliases():
    assert HermesVideoService.is_first_last_workflow(FIRST_LAST_WF) is True
    assert HermesVideoService.is_first_last_workflow("12_ltx23_first_last_frame_to_video") is True
    assert HermesVideoService.is_first_last_workflow("05_ltx2.3_first-last_frame") is True
    assert HermesVideoService.is_first_last_workflow("22_minimax_h3_first_last_frame_to_video") is True
    assert HermesVideoService.is_first_last_workflow("h3_fl2va") is True
    assert HermesVideoService.is_first_last_workflow(I2V_WF) is False
    assert HermesVideoService.is_first_last_workflow("") is False


def test_resolve_frame_pairs_single_frame_i2v():
    pairs = HermesVideoService.resolve_frame_pairs(
        ["s1", "s2", "s3"],
        workflow_id=I2V_WF,
    )
    assert pairs == [
        {"start_shot_id": "s1", "end_shot_id": None},
        {"start_shot_id": "s2", "end_shot_id": None},
        {"start_shot_id": "s3", "end_shot_id": None},
    ]


def test_resolve_frame_pairs_explicit_end_shot_id():
    pairs = HermesVideoService.resolve_frame_pairs(
        ["start_a"],
        workflow_id=FIRST_LAST_WF,
        end_shot_id="end_b",
    )
    assert pairs == [{"start_shot_id": "start_a", "end_shot_id": "end_b"}]


def test_resolve_frame_pairs_explicit_end_skips_end_in_starts():
    pairs = HermesVideoService.resolve_frame_pairs(
        ["start_a", "end_b"],
        workflow_id=I2V_WF,
        end_shot_id="end_b",
    )
    assert pairs == [{"start_shot_id": "start_a", "end_shot_id": "end_b"}]


def test_resolve_frame_pairs_two_selected_first_last_auto_pair():
    """Documented: exactly 2 shot_ids + first_last → start=first, end=second."""
    pairs = HermesVideoService.resolve_frame_pairs(
        ["frame_start", "frame_end"],
        workflow_id=FIRST_LAST_WF,
    )
    assert pairs == [
        {"start_shot_id": "frame_start", "end_shot_id": "frame_end"},
    ]


def test_resolve_frame_pairs_first_last_without_end_emits_none():
    pairs = HermesVideoService.resolve_frame_pairs(
        ["only_one"],
        workflow_id=FIRST_LAST_WF,
    )
    assert pairs == [{"start_shot_id": "only_one", "end_shot_id": None}]


def test_resolve_frame_pairs_three_selected_first_last_no_auto_pair():
    """Only exactly-2 auto-pairs; 3+ without end_shot_id stays unpaired ends."""
    pairs = HermesVideoService.resolve_frame_pairs(
        ["a", "b", "c"],
        workflow_id=FIRST_LAST_WF,
    )
    assert pairs == [
        {"start_shot_id": "a", "end_shot_id": None},
        {"start_shot_id": "b", "end_shot_id": None},
        {"start_shot_id": "c", "end_shot_id": None},
    ]


def test_resolve_frame_pairs_strips_empty_ids():
    pairs = HermesVideoService.resolve_frame_pairs(
        ["", " s1 ", None],  # type: ignore[list-item]
        workflow_id=I2V_WF,
    )
    assert pairs == [{"start_shot_id": "s1", "end_shot_id": None}]


# ---------------------------------------------------------------------------
# process() integration with mocked Comfy submit
# ---------------------------------------------------------------------------


def _shot(shot_id: str, image_path: str) -> Dict[str, Any]:
    return {
        "id": shot_id,
        "shot_id": shot_id,
        "image_path": image_path,
        "audit_status": "pass",
        "audit_score": 1.0,
        "audit_confidence": 1.0,
        "video_prompt": f"motion for {shot_id}",
    }


def _service(
    tmp_path: Path,
    shots: Dict[str, Dict[str, Any]],
    submit: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> HermesVideoService:
    wf = tmp_path / "workflow.json"
    wf.write_text("{}", encoding="utf-8")

    class FakeClient:
        def __init__(self, host: str = ""):
            self.host = host

        async def check_health(self):
            return True, {}

        async def submit_prompt_for_shot(self, **kwargs):
            return await submit(**kwargs)

    monkeypatch.setattr(
        "core.hermes.pipeline.video_service.ComfyUIClient",
        FakeClient,
    )
    monkeypatch.setattr(
        "core.hermes.pipeline.video_service.get_raw_config",
        lambda: {"COMFYUI_PRIMARY": "http://localhost:8188"},
    )
    monkeypatch.setenv("COMFYUI_PRIMARY", "http://localhost:8188")

    media = tmp_path / "videos"
    media.mkdir(parents=True, exist_ok=True)

    return HermesVideoService(
        media_videos=media,
        active_campaign_getter=lambda: "test_campaign",
        find_shot=lambda sid: shots.get(str(sid)),
        resolve_image_path=lambda url: Path(url) if Path(url).exists() else None,
        workflow_file_for_id=lambda _wid: wf,
    )


@pytest.mark.asyncio
async def test_process_first_last_with_end_shot_id_passes_image_paths(tmp_path, monkeypatch):
    start_img = tmp_path / "start.png"
    end_img = tmp_path / "end.png"
    start_img.write_bytes(b"start")
    end_img.write_bytes(b"end")
    shots = {
        "S_START": _shot("S_START", str(start_img)),
        "S_END": _shot("S_END", str(end_img)),
    }
    submit = AsyncMock(
        return_value={"status": "success", "prompt_id": "pid-fl-1", "seed": 7, "queued": True}
    )
    service = _service(tmp_path, shots, submit, monkeypatch)

    result = await service.process(
        shot_ids=["S_START"],
        workflow_id=FIRST_LAST_WF,
        end_shot_id="S_END",
        duration=5,
        fps=24,
        require_audit_pass=False,
        min_audit_score=0,
        min_audit_confidence=0,
    )

    assert result["status"] == "ok"
    assert result["mode"] == "first_last"
    assert len(result["results"]) == 1
    assert result["results"][0]["status"] == "ok"
    assert result["results"][0]["end_shot_id"] == "S_END"
    submit.assert_awaited_once()
    kwargs = submit.await_args.kwargs
    assert kwargs["image_paths"] == [str(start_img), str(end_img)]
    assert kwargs["image_path"] == str(start_img)


@pytest.mark.asyncio
async def test_process_two_shot_ids_first_last_auto_pair(tmp_path, monkeypatch):
    start_img = tmp_path / "a.png"
    end_img = tmp_path / "b.png"
    start_img.write_bytes(b"a")
    end_img.write_bytes(b"b")
    shots = {
        "A": _shot("A", str(start_img)),
        "B": _shot("B", str(end_img)),
    }
    submit = AsyncMock(
        return_value={"status": "success", "prompt_id": "pid-auto", "seed": 1, "queued": True}
    )
    service = _service(tmp_path, shots, submit, monkeypatch)

    result = await service.process(
        shot_ids=["A", "B"],
        workflow_id=FIRST_LAST_WF,
        require_audit_pass=False,
        min_audit_score=0,
        min_audit_confidence=0,
    )

    assert result["status"] == "ok"
    assert len(result["results"]) == 1  # one pair, not two I2V jobs
    assert result["results"][0]["shot_id"] == "A"
    assert result["results"][0]["end_shot_id"] == "B"
    kwargs = submit.await_args.kwargs
    assert kwargs["image_paths"] == [str(start_img), str(end_img)]


@pytest.mark.asyncio
async def test_process_first_last_missing_end_blocks(tmp_path, monkeypatch):
    start_img = tmp_path / "only.png"
    start_img.write_bytes(b"only")
    shots = {"ONLY": _shot("ONLY", str(start_img))}
    submit = AsyncMock()
    service = _service(tmp_path, shots, submit, monkeypatch)

    result = await service.process(
        shot_ids=["ONLY"],
        workflow_id=FIRST_LAST_WF,
        require_audit_pass=False,
        min_audit_score=0,
        min_audit_confidence=0,
    )

    assert result["status"] == "ok"
    assert result["results"][0]["status"] == "blocked"
    assert result["results"][0]["error"] == "end_frame_required"
    submit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_single_frame_i2v_unchanged(tmp_path, monkeypatch):
    """Existing single-frame I2V must not send image_paths with an end frame."""
    img = tmp_path / "still.png"
    img.write_bytes(b"still")
    shots = {
        "S1": _shot("S1", str(img)),
        "S2": _shot("S2", str(img)),
    }
    submit = AsyncMock(
        return_value={"status": "success", "prompt_id": "pid-i2v", "seed": 3, "queued": True}
    )
    service = _service(tmp_path, shots, submit, monkeypatch)

    result = await service.process(
        shot_ids=["S1", "S2"],
        workflow_id=I2V_WF,
        require_audit_pass=False,
        min_audit_score=0,
        min_audit_confidence=0,
    )

    assert result["status"] == "ok"
    assert result.get("mode") == "start_frames"
    assert len(result["results"]) == 2
    assert submit.await_count == 2
    for call in submit.await_args_list:
        kwargs = call.kwargs
        assert "image_paths" not in kwargs or kwargs.get("image_paths") is None
        assert kwargs["image_path"] == str(img)


@pytest.mark.asyncio
async def test_local_spark_media_uploads_end_frame_in_image_paths(tmp_path, monkeypatch):
    from core.affiliate.local_spark_media import LocalSparkMediaAdapter

    start = tmp_path / "start.png"
    end = tmp_path / "end.png"
    start.write_bytes(b"start-bytes")
    end.write_bytes(b"end-bytes")
    workflow = tmp_path / "wf.json"
    workflow.write_text("{}", encoding="utf-8")

    captured: List[Dict[str, Any]] = []

    class FakeComfy:
        def __init__(self, base_url):
            self.base_url = base_url

        async def submit_prompt_for_shot(self, **kwargs):
            captured.append(kwargs)
            return {
                "status": "success",
                "prompt_id": "spark-fl",
                "seed": kwargs.get("seed") or 1,
                "queued": True,
            }

    monkeypatch.setattr("core.affiliate.local_spark_media.ComfyUIClient", FakeComfy)

    adapter = LocalSparkMediaAdapter(
        repo_root=tmp_path,
        media_root=tmp_path / "media",
        media_images=tmp_path / "media" / "images",
        comfy_url="http://localhost:8188",
        workflow_file_for_id=lambda workflow_id: workflow,
        resolve_image_path=lambda value: Path(value) if Path(value).exists() else None,
    )

    job = await adapter.generate_video(
        input_image_url=str(start),
        input_image_end_url=str(end),
        prompt="pan from start to end",
        enhance_prompt=False,
    )

    assert job["status"] == "queued"
    assert len(captured) == 1
    paths = captured[0].get("image_paths") or []
    assert len(paths) == 2
    assert Path(paths[0]).exists()
    assert Path(paths[1]).exists()
    assert Path(paths[0]).read_bytes() == b"start-bytes"
    assert Path(paths[1]).read_bytes() == b"end-bytes"
    assert job["input_params"].get("local_input_image_end")
