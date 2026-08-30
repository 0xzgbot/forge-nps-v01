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
    assert "queue_eta_sec" in out
    assert out["produce_mode"] in {"scout", "shoot"}


def test_snapshot_cut_marks_status_ready(tmp_path: Path):
    service = ProduceService(tmp_path)
    snap = service.start("a wet city walk", profile="producer")
    job = service.job_dir(snap["job_id"])
    (job / "cut.mp4").write_bytes(b"cut")
    out = service.snapshot(snap["job_id"])
    assert out["cut"] == "cut.mp4"
    assert out["stage"] == "done"
    assert out["status"] == "ready"


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


def test_patch_shot_and_identity_upload(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_shots(job, [{"id": "SHOT_001", "visual": "rain"}])
    produce_render.patch_shot(job, "SHOT_001", {"h3_prompt": "wet city walk", "duration_sec": 8})
    shot = produce_render.get_shot(job, "SHOT_001")
    assert shot["h3_prompt"] == "wet city walk"
    assert shot["duration_sec"] == 8
    saved = produce_render.save_upload(job, kind="identity", filename="face.png", data=b"png")
    assert saved["ok"]
    assert "face.png" in produce_render.list_identity(job)[0]


def test_color_pass_uses_eq_filter(tmp_path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    clip = job / "a.mp4"
    clip.write_bytes(b"clip")
    produce_render.save_edit(job, [{"shot_id": "SHOT_001", "clip": "a.mp4"}])
    cmds = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text):
        cmds.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"out")
        return Result()

    monkeypatch.setattr("core.assembly.timeline_assembler.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("core.assembly.timeline_assembler.subprocess.run", fake_run)
    result = produce_render.assemble_cut(job, color_pass=True)
    assert result["ok"] is True
    assert any("eq=" in " ".join(cmd) for cmd in cmds)


def test_assemble_cut_mutes_clip_with_an(tmp_path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    a = job / "a.mp4"
    b = job / "b.mp4"
    a.write_bytes(b"clip-a")
    b.write_bytes(b"clip-b")
    produce_render.save_edit(
        job,
        [
            {"shot_id": "SHOT_001", "clip": "a.mp4", "muted": True},
            {"shot_id": "SHOT_002", "clip": "b.mp4", "muted": False},
        ],
    )
    cmds = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text):
        cmds.append(list(cmd))
        Path(cmd[-1]).write_bytes(b"out")
        return Result()

    monkeypatch.setattr("core.assembly.timeline_assembler.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("core.assembly.timeline_assembler.subprocess.run", fake_run)
    result = produce_render.assemble_cut(job)
    assert result["ok"] is True
    assert any("-an" in cmd for cmd in cmds)
    final = cmds[-1]
    assert "-ac" in final and "2" in final


def test_list_media_dedupes_boards_and_skips_identity(tmp_path: Path):
    job = tmp_path / "job"
    (job / "boards").mkdir(parents=True)
    (job / "clips").mkdir()
    (job / "identity").mkdir()
    (job / "boards" / "SHOT_001.png").write_bytes(b"png")
    (job / "clips" / "SHOT_001.mp4").write_bytes(b"mp4")
    (job / "identity" / "face.png").write_bytes(b"face")
    media = produce_render.list_media(job)
    assert media["stills"] == ["boards/SHOT_001.png"]
    assert media["clips"] == ["clips/SHOT_001.mp4"]

