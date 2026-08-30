import json
from pathlib import Path

import pytest

from core.dispatch.capability_router import CapabilityRouter
from core.dispatch.comfy_client import apply_h3_guides
from core.hermes.produce import queue as produce_queue
from core.hermes.produce import render as produce_render
from core.hermes.produce.service import ProduceService


def test_snapshot_includes_queue_without_draining(tmp_path: Path):
    service = ProduceService(tmp_path)
    snap = service.start("a wet city walk", profile="producer", produce_mode="scout")
    assert snap["produce_mode"] == "scout"
    job = service.job_dir(snap["job_id"])
    produce_queue.enqueue(job, "render_take", shot_id="SHOT_001", mode="t2va")
    out = service.snapshot(snap["job_id"])
    assert out["queue"][0]["status"] == "pending"
    assert out["queue"][0]["action"] == "render_take"
    # GET snapshot must not claim or fail the item
    again = produce_queue.load_queue(job)
    assert again[0]["status"] == "pending"


def test_enqueue_plan_scout_is_t2va_only(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_job_meta(job, {"produce_mode": "scout"})
    produce_render.save_shots(
        job,
        [
            {"id": "SHOT_001", "visual": "rain on glass", "end_still": "boards/end.png"},
            {"id": "SHOT_002", "visual": "hallway"},
        ],
    )
    added = produce_queue.enqueue_plan(job, router=CapabilityRouter({"COMFYUI_STILLS_A": "http://a:8189"}))
    actions = [row["action"] for row in added]
    assert "render_board" not in actions
    assert all(row["mode"] == "t2va" for row in added if row["action"] == "render_take")


def test_enqueue_plan_shoot_assigns_both_3090s(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_job_meta(job, {"produce_mode": "shoot"})
    produce_render.save_shots(
        job,
        [
            {"id": "SHOT_001", "visual": "rain", "end_still": "boards/end.png"},
            {"id": "SHOT_002", "visual": "hallway"},
        ],
    )
    router = CapabilityRouter(
        {
            "COMFYUI_PRIMARY": "http://spark:8188",
            "COMFYUI_STILLS_A": "http://a:8189",
            "COMFYUI_STILLS_B": "http://b:8189",
        }
    )
    added = produce_queue.enqueue_plan(job, router=router)
    boards = [row for row in added if row["action"] == "render_board"]
    takes = [row for row in added if row["action"] == "render_take"]
    assert {row["host"] for row in boards} == {"http://a:8189", "http://b:8189"}
    assert takes[0]["mode"] == "fl2va"
    assert takes[1]["mode"] == "i2va"


def test_resolve_take_mode_scout_and_fl2v(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_job_meta(job, {"produce_mode": "scout"})
    shot = {"id": "SHOT_001", "end_still": "boards/end.png", "h3_mode": "i2va"}
    assert produce_render.resolve_take_mode(job, shot, requested="i2va") == "t2va"
    produce_render.set_produce_mode(job, "shoot")
    assert produce_render.resolve_take_mode(job, shot) == "fl2va"
    assert produce_render.resolve_take_mode(job, {"id": "SHOT_002"}) == "i2va"


def test_hermes_can_write_queue_json(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "queue.json").write_text(
        json.dumps(
            [
                {"action": "render_board", "shot_id": "SHOT_001", "status": "pending"},
                {"action": "assemble"},
            ]
        ),
        encoding="utf-8",
    )
    items = produce_queue.load_queue(job)
    assert items[0]["action"] == "render_board"
    assert items[0]["id"]
    assert items[1]["action"] == "assemble"
    assert items[1]["status"] == "pending"


@pytest.mark.asyncio
async def test_drain_waits_when_host_offline(tmp_path: Path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_shots(job, [{"id": "SHOT_001", "visual": "rain"}])
    produce_queue.enqueue(job, "render_board", shot_id="SHOT_001", host="http://gpu:8189")

    async def down(self, url):
        return {"url": url, "ok": False, "error": "down", "queue_depth": None, "gpu": "", "nodes": []}

    monkeypatch.setattr("core.dispatch.capability_router.CapabilityRouter._probe", down)
    router = CapabilityRouter({"COMFYUI_STILLS_A": "http://gpu:8189"})
    results = await produce_queue.drain_pending(job, router=router)
    assert results
    items = produce_queue.load_queue(job)
    assert items[0]["status"] == "waiting_for_host"
    assert items[0]["status"] != "failed"


def test_apply_h3_guides_skipped_when_empty():
    nodes = {
        "6": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"prompt": "", "vae": ["3", 0]}},
        "10": {"class_type": "BasicGuider", "inputs": {"conditioning": ["6", 0]}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"latent_image": ["6", 1]}},
        "20": {"class_type": "LoadImage", "inputs": {"image": "first.png"}},
    }
    apply_h3_guides(nodes, [])
    assert not any(n.get("class_type") == "MiniMaxH3AddGuide" for n in nodes.values())
    assert sum(1 for n in nodes.values() if n.get("class_type") == "LoadImage") == 1


def test_apply_h3_guides_injects_mid_clip():
    nodes = {
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "video.safetensors"}},
        "6": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {"prompt": "x", "vae": ["3", 0]}},
        "10": {"class_type": "BasicGuider", "inputs": {"model": ["5", 0], "conditioning": ["6", 0]}},
        "11": {"class_type": "SamplerCustomAdvanced", "inputs": {"latent_image": ["6", 1]}},
        "20": {"class_type": "LoadImage", "inputs": {"image": "first.png"}},
    }
    apply_h3_guides(nodes, [{"frame_idx": 48, "image": "mid.png"}])
    guides = [n for n in nodes.values() if n.get("class_type") == "MiniMaxH3AddGuide"]
    assert len(guides) == 1
    assert guides[0]["inputs"]["frame_idx"] == 48
    assert nodes["10"]["inputs"]["conditioning"][0] != "6"
    assert nodes["11"]["inputs"]["latent_image"][0] != "6"
    assert any(
        n.get("class_type") == "LoadImage" and n.get("inputs", {}).get("image") == "mid.png"
        for n in nodes.values()
    )


def test_stills_hosts_configured_does_not_include_spark():
    router = CapabilityRouter(
        {
            "COMFYUI_PRIMARY": "http://spark:8188",
            "COMFYUI_STILLS_A": "http://a:8189",
            "COMFYUI_STILLS_B": "http://b:8189",
        }
    )
    assert router.stills_hosts_configured() == ["http://a:8189", "http://b:8189"]
    assert "http://spark:8188" not in router.stills_hosts_configured()
