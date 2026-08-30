from pathlib import Path

from core.bridge.llm_endpoint import LLMEndpoint, probe_llm_endpoint
from core.hermes.produce import desk as produce_desk
from core.hermes.produce import render as produce_render
from core.hermes.produce.service import ProduceService


def test_probe_llm_unconfigured():
    endpoint = LLMEndpoint(base_url="", model="", api_key="", source="unset", local=False)
    out = probe_llm_endpoint(endpoint)
    assert out["configured"] is False
    assert out["reachable"] is False


def test_probe_llm_unreachable(monkeypatch):
    endpoint = LLMEndpoint(
        base_url="http://127.0.0.1:9",
        model="local",
        api_key="",
        source="llm",
        local=True,
    )
    out = probe_llm_endpoint(endpoint, timeout=0.2)
    assert out["configured"] is True
    assert out["reachable"] is False


def test_review_and_duplicate_and_scorecard(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    produce_render.save_shots(
        job,
        [
            {"id": "SHOT_001", "purpose": "arrive", "visual": "rain on glass wet city", "duration_sec": 5},
            {"id": "SHOT_002", "purpose": "walk", "visual": "wet city street rain", "duration_sec": 5},
        ],
    )
    row = produce_desk.review_shot(job, "SHOT_001", "approved", note="lock the coat")
    assert row["decision"] == "approved"
    shot = produce_render.get_shot(job, "SHOT_001")
    assert shot["review_status"] == "approved"
    assert shot["status"] == "approved"
    copy = produce_desk.duplicate_shot(job, "SHOT_001")
    assert copy["id"] == "SHOT_003"
    assert "rain" in str(copy.get("visual") or "")
    card = produce_desk.scorecard(job)
    assert card["shot_count"] == 3
    assert "grade" in card


def test_peek_screenplay(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "script.md").write_text(
        "INT. PLATFORM — NIGHT\nRain. Empty.\n\nEXT. STREET — NIGHT\nHe walks.\n",
        encoding="utf-8",
    )
    peek = produce_desk.peek_script(job)
    assert peek["format"] == "screenplay"
    assert len(peek["scenes"]) == 2
    assert peek["scenes"][0]["id"].startswith("INT.")


def test_cut_versions(tmp_path: Path):
    job = tmp_path / "job"
    job.mkdir()
    (job / "cut.mp4").write_bytes(b"cut-one")
    rel = produce_desk.archive_cut(job)
    assert rel == "cuts/001.mp4"
    (job / "cut.mp4").write_bytes(b"cut-two")
    produce_desk.restore_cut(job, rel)
    assert (job / "cut.mp4").read_bytes() == b"cut-one"
    assert len(produce_desk.list_cuts(job)) >= 2


def test_snapshot_includes_desk_fields(tmp_path: Path):
    service = ProduceService(tmp_path)
    snap = service.start("Rain on glass. Quiet.", profile="producer")
    job = service.job_dir(snap["job_id"])
    (job / "script.md").write_text("INT. HALL — NIGHT\nA door.\n", encoding="utf-8")
    produce_render.save_shots(job, [{"id": "SHOT_001", "visual": "door", "purpose": "enter"}])
    out = service.snapshot(snap["job_id"])
    assert "scorecard" in out
    assert out["script"]["format"] == "screenplay"
    assert out["transition"] == "cut"
    assert out["cuts"] == []


def test_assemble_archives_previous_cut(tmp_path: Path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    clip = job / "a.mp4"
    clip.write_bytes(b"clip")
    produce_render.save_edit(job, [{"shot_id": "SHOT_001", "clip": "a.mp4"}])
    (job / "cut.mp4").write_bytes(b"old-cut")

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, capture_output, text):
        Path(cmd[-1]).write_bytes(b"muxed")
        return Result()

    monkeypatch.setattr("core.assembly.timeline_assembler.shutil.which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr("core.assembly.timeline_assembler.subprocess.run", fake_run)
    result = produce_render.assemble_cut(job)
    assert result["ok"] is True
    assert (job / "cuts" / "001.mp4").read_bytes() == b"old-cut"
    meta = produce_render.load_job_meta(job)
    assert meta.get("last_assemble", {}).get("ok") is True
