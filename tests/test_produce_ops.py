from pathlib import Path

from core.hermes.produce import finish as produce_finish
from core.hermes.produce import job_ops as produce_ops
from core.hermes.produce import render as produce_render
from core.hermes.produce.service import ProduceService


def test_snapshot_includes_launch_fields(tmp_path: Path):
    service = ProduceService(tmp_path)
    snap = service.start("A courier misses the last train. Quiet.", profile="producer", aspect="9:16")
    assert snap["title"].startswith("A courier misses the last train")
    assert snap["aspect"] == "9:16"
    assert snap["next_action"]["id"] == "story"
    assert "continuity" in snap
    assert snap["fade_sec"] == 0


def test_comments_add_shot_delete_captions(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_shots(job, [])
    shot = produce_ops.add_shot(job, purpose="Arrive", visual="rain on glass")
    assert shot["id"] == "SHOT_001"
    produce_ops.add_comment(job, "lock the coat", shot_id="SHOT_001")
    notes = produce_ops.load_comments(job)
    assert notes[0]["text"] == "lock the coat"
    produce_render.upsert_shot(job, "SHOT_001", still="boards/a.png", duration_sec=4)
    score = produce_ops.continuity_score(job)
    assert score["boarded"] == 1
    assert score["grade"] in {"loose", "held", "locked"}
    srt = produce_ops.write_captions(job)
    body = srt.read_text(encoding="utf-8")
    assert "Arrive" in body
    assert "00:00:00,000" in body
    produce_ops.delete_shot(job, "SHOT_001")
    assert produce_render.load_shots(job) == []


def test_next_action_progresses(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_job_meta(job, {"produce_mode": "shoot"})
    produce_render.save_shots(job, [{"id": "SHOT_001", "visual": "rain", "duration_sec": 5}])
    assert produce_ops.next_action(job)["id"] == "boards"
    produce_render.upsert_shot(job, "SHOT_001", still="boards/a.png")
    assert produce_ops.next_action(job)["id"] == "takes"
    produce_render.upsert_shot(job, "SHOT_001", clip="clips/a.mp4")
    assert produce_ops.next_action(job)["id"] == "assemble"
    (job / "cut.mp4").write_bytes(b"cut")
    assert produce_ops.next_action(job)["id"] == "export"
    assert produce_ops.runtime_sec(job) == 5


def test_duplicate_and_music(tmp_path: Path):
    src = tmp_path / "a"
    dest = tmp_path / "b"
    src.mkdir()
    produce_render.save_job_meta(src, {"job_id": "a", "title": "Wet"})
    produce_render.save_shots(src, [{"id": "SHOT_001", "visual": "rain"}])
    ident = src / "identity"
    ident.mkdir()
    (ident / "music-bed.wav").write_bytes(b"wav")
    produce_ops.duplicate_job(src, dest)
    meta = produce_render.load_job_meta(dest)
    assert meta["job_id"] == "b"
    assert meta["cloned_from"] == "a"
    assert produce_ops.find_music(dest).name == "music-bed.wav"


def test_apply_finish_without_ffmpeg_still_writes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("core.hermes.produce.finish._ffmpeg", lambda: "")
    src = tmp_path / "in.mp4"
    src.write_bytes(b"cut")
    dest = tmp_path / "out.mp4"
    result = produce_finish.apply_finish(src, dest, aspect="9:16", title="Hello", fade_sec=0.3)
    assert result["ok"] is True
    assert dest.read_bytes() == b"cut"


def test_assemble_calls_finish_for_vertical(tmp_path: Path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    clip = job / "a.mp4"
    clip.write_bytes(b"clip")
    produce_render.save_edit(job, [{"shot_id": "SHOT_001", "clip": "a.mp4"}])
    produce_render.save_job_meta(job, {"aspect": "9:16", "title": "Wet city"})
    called = {}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text):
        Path(cmd[-1]).write_bytes(b"muxed")
        return Result()

    def fake_finish(cut, dest, **kwargs):
        dest.write_bytes(b"finished")
        called.update(kwargs)
        return {"ok": True, "output": str(dest), "steps": {"aspect": {"ok": True}}}

    monkeypatch.setattr("core.assembly.timeline_assembler.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("core.assembly.timeline_assembler.subprocess.run", fake_run)
    monkeypatch.setattr("core.hermes.produce.finish.apply_finish", fake_finish)
    result = produce_render.assemble_cut(job)
    assert result["ok"] is True
    assert called.get("aspect") == "9:16"
    assert called.get("title") == "Wet city"
    assert (job / "cut.mp4").read_bytes() == b"finished"
    assert (job / "cut.srt").exists()


def test_score_upload_renames_music(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    saved = produce_render.save_upload(job, kind="score", filename="theme.wav", data=b"wav")
    assert "music" in saved["path"].lower()
    assert produce_ops.find_music(job) is not None
