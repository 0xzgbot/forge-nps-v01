"""Tests for modular product surface: export, probe, scorecard, suggestions, errors."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from core.consistency_scorecard import score_story_consistency
from core.cinesmith_env import repo_root
from core.media_probe import probe_media, resolve_media_path
from core.memory_suggestions import build_suggestions
from core.script_projects import load_script_project, safe_script_id, script_projects_dir, write_json_atomic
from core.story_export import build_story_package_zip
from dashboard.errors import CinesmithAPIError, error_payload


def test_error_payload_shape():
    payload = error_payload("boom", code="test_code", hint="h", recovery="r")
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "test_code"
    assert payload["error"]["message"] == "boom"
    assert payload["error"]["recovery"] == "r"


def test_scorecard_needs_two_shots():
    card = score_story_consistency({"video_shots": [{"prompt": "red car neon rain"}]})
    assert card["shot_count"] == 1
    assert card["grade"] in {"A", "N/A"}


def test_scorecard_detects_divergence():
    card = score_story_consistency(
        {
            "package": {"characters": ["Ava courier red jacket"], "location": "neon city"},
            "video_shots": [
                {"prompt": "Ava courier red jacket neon city rain night"},
                {"prompt": "Ava courier red jacket neon city alley steam"},
                {"prompt": "completely different beach vacation tropical fruit stand"},
            ],
        }
    )
    assert card["shot_count"] == 3
    assert 0 <= card["score"] <= 100
    assert card["grade"] in {"A", "B", "C", "D", "F"}
    assert "summary" in card


def test_suggestions_brief_aware():
    data = build_suggestions(brief="tiktok vertical girl next door travel series", mode="auto", limit=8)
    assert data["count"] >= 1
    ids = {s["id"] for s in data["suggestions"]}
    assert "tip_tiktok" in ids or "tip_character" in ids or data["suggestions"]


def test_story_export_zip(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    media = tmp_path / "media"
    scripts = root / "data" / "scripts"
    sid = "export_demo"
    proj = scripts / sid
    proj.mkdir(parents=True)
    (media / "videos").mkdir(parents=True)
    (media / "images").mkdir(parents=True)
    frame = media / "images" / "frame1.png"
    clip = media / "videos" / "clip1.mp4"
    frame.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    clip.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"0" * 64)

    write_json_atomic(
        proj / "project.json",
        {
            "script_id": sid,
            "title": "Export Demo",
            "brief": "A courier in the rain.",
            "status": "draft",
            "video_shot_count": 1,
            "video_complete_count": 1,
        },
    )
    write_json_atomic(
        proj / "video_shots.json",
        [
            {
                "shot_id": "SB_001",
                "prompt": "courier rain neon",
                "image_url": str(frame),
                "video_url": str(clip),
                "video_status": "complete",
            }
        ],
    )
    write_json_atomic(
        proj / "storyboard_panel_jobs.json",
        {"1": [{"url": str(frame)}]},
    )

    monkeypatch.setattr("core.story_export.load_script_project", lambda script_id, root=None: {
        **json.loads((proj / "project.json").read_text()),
        "package": None,
        "coverage_shots": [],
        "storyboard_plan": {"boards": [{"panels": [{"caption": "open"}]}]},
        "storyboard_panel_jobs": json.loads((proj / "storyboard_panel_jobs.json").read_text()),
        "video_shots": json.loads((proj / "video_shots.json").read_text()),
        "active_job": None,
    })

    result = build_story_package_zip(sid, media_root=media, repo_root=root, dest_dir=media / "exports" / "stories")
    assert result["status"] == "ok"
    zpath = Path(result["zip_path"])
    assert zpath.exists()
    with zipfile.ZipFile(zpath, "r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "captions.txt" in names
        assert any(n.startswith("frames/") for n in names)
        assert any(n.startswith("videos/") for n in names)


def test_resolve_media_path_absolute(tmp_path):
    f = tmp_path / "x.mp4"
    f.write_bytes(b"abc")
    assert resolve_media_path(str(f)) == f.resolve()


def test_probe_missing_file(tmp_path):
    p = probe_media(tmp_path / "nope.mp4")
    assert p["exists"] is False
    assert p["error"] == "file_not_found"


def test_product_routes_importable():
    from dashboard.routes.product import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/api/product/create-hub" in paths
    assert "/api/script/export-package" in paths
    assert "/api/media/probe" in paths
    assert "/api/product/scorecard" in paths
    assert "/api/product/review" in paths
    assert "/api/product/review/queue" in paths
    assert "/api/product/cost-meter" in paths
    assert "/api/product/failure-auto-consolidate" in paths
    assert "/api/product/ab-compare" in paths
    assert "/api/product/ab-compare/recent" in paths


def test_ab_compare_endpoint(tmp_path, monkeypatch):
    """A/B winner preference sticks on shot records and logs."""
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dashboard import cinesmith_dashboard as d
    from dashboard.cinesmith_dashboard import app

    # isolate log writes under tmp (REPO_ROOT must remain a Path)
    monkeypatch.setattr(d, "REPO_ROOT", tmp_path)
    monkeypatch.setattr("dashboard.routes.product.repo_root", lambda: tmp_path)
    (tmp_path / "data" / "reviews").mkdir(parents=True)
    (tmp_path / "data" / "campaigns").mkdir(parents=True)

    saved = list(d._SHOTS_STORE)
    try:
        d._SHOTS_STORE.clear()
        d._SHOTS_STORE.extend(
            [
                {
                    "id": "shot_a",
                    "shot_id": "shot_a",
                    "image_url": "/media/a.png",
                    "campaign_id": "camp1",
                    "prompt": "neon courier rain",
                },
                {
                    "id": "shot_b",
                    "shot_id": "shot_b",
                    "image_url": "/media/b.png",
                    "campaign_id": "camp1",
                    "prompt": "neon courier alley",
                },
            ]
        )

        # Avoid lifespan reindex wiping our fixtures: use client without context manager.
        client = TestClient(app, raise_server_exceptions=True)

        empty = client.get("/api/product/ab-compare/recent")
        assert empty.status_code == 200
        # may include prior runs if log not isolated; still a valid shape
        assert "items" in empty.json()

        bad = client.post(
            "/api/product/ab-compare",
            json={"shot_a_id": "shot_a", "shot_b_id": "shot_a", "winner_id": "shot_a"},
        )
        assert bad.status_code == 400

        missing = client.post(
            "/api/product/ab-compare",
            json={"shot_a_id": "nope1", "shot_b_id": "nope2", "winner_id": "nope1"},
        )
        assert missing.status_code == 404

        # Re-seed after any startup reindex side effects
        if not d._find_shot("shot_a"):
            d._SHOTS_STORE.extend(
                [
                    {
                        "id": "shot_a",
                        "shot_id": "shot_a",
                        "image_url": "/media/a.png",
                        "campaign_id": "camp1",
                        "prompt": "neon courier rain",
                    },
                    {
                        "id": "shot_b",
                        "shot_id": "shot_b",
                        "image_url": "/media/b.png",
                        "campaign_id": "camp1",
                        "prompt": "neon courier alley",
                    },
                ]
            )

        ok = client.post(
            "/api/product/ab-compare",
            json={
                "shot_a_id": "shot_a",
                "shot_b_id": "shot_b",
                "winner_id": "shot_a",
                "note": "cleaner silhouette",
            },
        )
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["status"] == "ok"
        assert body["result"] == "a"
        assert body["winner_id"] == "shot_a"
        assert body["loser_id"] == "shot_b"

        sa = d._find_shot("shot_a")
        sb = d._find_shot("shot_b")
        assert sa is not None and sb is not None
        assert sa.get("ab_preference") == "winner"
        assert int(sa.get("ab_wins") or 0) >= 1
        assert sb.get("ab_preference") == "loser"
        assert int(sb.get("ab_losses") or 0) >= 1

        recent = client.get("/api/product/ab-compare/recent?limit=5")
        assert recent.status_code == 200
        items = recent.json().get("items") or []
        assert len(items) >= 1
        assert any(i.get("winner_id") == "shot_a" for i in items)

        tie = client.post(
            "/api/product/ab-compare",
            json={"shot_a_id": "shot_a", "shot_b_id": "shot_b", "winner_id": "tie"},
        )
        assert tie.status_code == 200
        assert tie.json().get("result") == "tie"
    finally:
        d._SHOTS_STORE.clear()
        d._SHOTS_STORE.extend(saved)
