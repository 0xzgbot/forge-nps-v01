import json
from pathlib import Path

from core.character.identity_attach import resolve_anchor_paths
from core.hermes.produce import render as produce_render
from core.hermes.produce.service import ProduceService


def test_snapshot_includes_shots_and_boards(tmp_path: Path):
    service = ProduceService(tmp_path)
    snap = service.start("a wet city walk", profile="producer")
    job = service.job_dir(snap["job_id"])
    produce_render.save_shots(
        job,
        [{"id": "SHOT_001", "purpose": "arrive", "visual": "rain on glass", "duration_sec": 5}],
    )
    (job / "boards").mkdir()
    (job / "boards" / "SHOT_001.png").write_bytes(b"png")
    produce_render.upsert_shot(job, "SHOT_001", still="boards/SHOT_001.png", status="boarded")
    out = service.snapshot(snap["job_id"])
    assert out["shots"][0]["id"] == "SHOT_001"
    assert "boards/SHOT_001.png" in out["stills"]


def test_identity_anchor_paths(tmp_path: Path):
    img = tmp_path / "face.png"
    img.write_bytes(b"x")
    pack = {"anchor_image_ids": ["face.png"], "anchor_paths": [str(img)]}
    paths = resolve_anchor_paths(pack, search_dirs=[tmp_path])
    assert str(img.resolve()) in paths


def test_assemble_cut_without_ffmpeg_reports(tmp_path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    clip = job / "a.mp4"
    clip.write_bytes(b"not-a-real-mp4")
    produce_render.save_edit(job, [{"shot_id": "SHOT_001", "clip": "a.mp4"}])
    monkeypatch.setattr("core.assembly.timeline_assembler.shutil.which", lambda name: None)
    result = produce_render.assemble_cut(job)
    assert result["ok"] is False
    assert result["error"] == "ffmpeg_not_installed"


def test_assemble_cut_runs_ffmpeg(tmp_path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    clip = job / "a.mp4"
    clip.write_bytes(b"clip")
    produce_render.save_edit(job, [{"shot_id": "SHOT_001", "clip": "a.mp4"}])

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text):
        out = Path(cmd[-1])
        out.write_bytes(b"muxed")
        return Result()

    monkeypatch.setattr("core.assembly.timeline_assembler.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("core.assembly.timeline_assembler.subprocess.run", fake_run)
    result = produce_render.assemble_cut(job)
    assert result["ok"] is True
    assert (job / "cut.mp4").exists()
    assert "edit" in (job / "STATUS.md").read_text(encoding="utf-8")
