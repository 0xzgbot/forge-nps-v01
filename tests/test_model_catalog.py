from pathlib import Path

from core.dispatch.model_catalog import (
    board_workflow_id,
    catalog,
    family_has_mode,
    family_supports_scout,
    normalize_video_model,
    workflow_for_take,
)
from core.dispatch.workflows import capability_for_workflow, take_workflow_for_mode
from core.hermes.produce import elements as produce_elements
from core.hermes.produce import queue as produce_queue
from core.hermes.produce import render as produce_render
from core.dispatch.capability_router import CapabilityRouter


def test_catalog_defaults_and_open_weight_lanes():
    data = catalog()
    stills_ids = {row["id"] for row in data["stills"]}
    video_ids = {row["id"] for row in data["video"]}
    assert "flux2" in stills_ids
    assert "z_image" in stills_ids
    assert "ernie" in stills_ids
    assert "h3" in video_ids
    assert "ltx23" in video_ids
    assert "wan22" in video_ids
    assert data["defaults"]["stills_model"] == "flux2"
    assert data["defaults"]["video_model"] == "h3"
    h3 = next(row for row in data["video"] if row["id"] == "h3")
    assert h3["available"] is True
    assert h3["host"] == "spark"
    flux = next(row for row in data["stills"] if row["id"] == "flux2")
    assert flux["available"] is True
    assert flux["host"] == "3090s"


def test_h3_never_classified_as_stills():
    assert capability_for_workflow("21_minimax_h3_image_to_video") == "spark"
    assert capability_for_workflow("09_ltx23_text_to_video") == "spark"
    assert capability_for_workflow("15_wan2_2_i2v") == "spark"
    assert capability_for_workflow("01_flux2_text_to_image") == "stills"
    assert capability_for_workflow("07_z_image") == "stills"


def test_take_workflow_follows_family():
    assert "h3" in workflow_for_take("h3", "i2va")
    assert "ltx23" in workflow_for_take("ltx23", "i2va") or "ltx" in workflow_for_take("ltx23", "i2va")
    assert family_has_mode("h3", "t2va")
    assert family_supports_scout("h3")
    assert not family_supports_scout("wan22")
    assert workflow_for_take("wan22", "t2va")  # coerces to i2v graph
    assert take_workflow_for_mode("i2va") == workflow_for_take("h3", "i2va")


def test_board_workflow_for_stills_family():
    assert board_workflow_id("flux2").startswith("01_flux")
    assert "z_image" in board_workflow_id("z_image")


def test_unknown_family_falls_back_to_default():
    assert normalize_video_model("nope") == "h3"


def test_scout_on_i2v_only_family_queues_boards(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_job_meta(job, {"produce_mode": "scout", "video_model": "wan22"})
    produce_render.save_shots(job, [{"id": "SHOT_001", "visual": "rain"}])
    added = produce_queue.enqueue_plan(job, router=CapabilityRouter({"COMFYUI_STILLS_A": "http://a:8189"}))
    actions = [row["action"] for row in added]
    assert "render_board" in actions
    takes = [row for row in added if row["action"] == "render_take"]
    assert takes[0]["mode"] == "i2va"


def test_take_bin_and_export(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    clips = job / "clips"
    clips.mkdir()
    first = clips / "SHOT_001.mp4"
    first.write_bytes(b"take-one")
    produce_render.save_shots(job, [{"id": "SHOT_001", "clip": "clips/SHOT_001.mp4"}])
    archived = produce_render.archive_take(job, "SHOT_001", "clips/SHOT_001.mp4")
    assert archived.startswith("takes/")
    first.write_bytes(b"take-two")
    restored = produce_render.restore_take(job, "SHOT_001", archived)
    assert restored["ok"]
    assert (job / "clips" / "SHOT_001.mp4").read_bytes() == b"take-one"
    (job / "story.md").write_text("wet city\n", encoding="utf-8")
    pack = produce_render.export_package(job)
    assert pack["ok"]
    assert (job / "handoff.zip").exists()


def test_elements_attach(tmp_path: Path):
    lib_root = tmp_path / "repo"
    job = tmp_path / "job"
    job.mkdir()
    item = produce_elements.add_element("character", "face.png", b"png", label="Courier", root=lib_root)
    copied = produce_elements.attach_to_job(job, [item["id"]], root=lib_root)
    assert copied
    assert (job / copied[0]).exists()
