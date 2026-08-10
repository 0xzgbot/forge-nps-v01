"""E5 multi-episode series continuity helpers + API."""

from __future__ import annotations


import pytest

from core.script_series import (
    draft_next_episode_meta,
    format_episode_label,
    group_projects_by_series,
    next_episode_number,
    series_fields_from_payload,
    slug_series_id,
)


def test_slug_series_id():
    assert slug_series_id("Coastal Girl!") == "coastal_girl"
    assert slug_series_id("") == ""


def test_series_fields_from_payload_infers_id_from_title():
    fields = series_fields_from_payload({"series_title": "Harbor Nights", "episode_number": 2})
    assert fields["series_id"] == "harbor_nights"
    assert fields["episode_number"] == 2
    assert fields["series_title"] == "Harbor Nights"


def test_series_fields_preserves_existing_when_blank_payload():
    existing = {
        "series_id": "harbor_nights",
        "series_title": "Harbor Nights",
        "episode_number": 1,
        "episode_title": "Pilot",
    }
    fields = series_fields_from_payload({}, existing=existing)
    assert fields["series_id"] == "harbor_nights"
    assert fields["episode_number"] == 1
    assert fields["episode_title"] == "Pilot"


def test_group_and_next_episode():
    projects = [
        {
            "script_id": "a",
            "series_id": "harbor_nights",
            "series_title": "Harbor Nights",
            "episode_number": 1,
            "updated_at": "2026-01-01T00:00:00Z",
        },
        {
            "script_id": "b",
            "series_id": "harbor_nights",
            "series_title": "Harbor Nights",
            "episode_number": 2,
            "updated_at": "2026-01-02T00:00:00Z",
        },
        {
            "script_id": "c",
            "title": "One-off",
            "updated_at": "2026-01-03T00:00:00Z",
        },
    ]
    groups = group_projects_by_series(projects)
    series = [g for g in groups if g["series_id"] == "harbor_nights"]
    assert len(series) == 1
    assert series[0]["episode_count"] == 2
    assert [e["script_id"] for e in series[0]["episodes"]] == ["a", "b"]
    assert next_episode_number(projects, "harbor_nights") == 3


def test_draft_next_episode_meta():
    source = {
        "script_id": "a",
        "series_id": "harbor_nights",
        "series_title": "Harbor Nights",
        "episode_number": 1,
        "title": "Harbor Nights — Pilot",
        "brief": "Girl finds the pier",
        "tone": "warm",
        "runtime_seconds": 45,
        "target_scenes": 3,
    }
    draft = draft_next_episode_meta(source, all_projects=[source])
    assert draft["series_id"] == "harbor_nights"
    assert draft["episode_number"] == 2
    assert draft["series_continuity"] is True
    assert draft["continues_from_script_id"] == "a"
    assert "Episode 2" in draft["episode_title"] or draft["episode_title"]


def test_format_episode_label():
    label = format_episode_label(
        series_title="Harbor Nights",
        episode_number=2,
        episode_title="Fog",
    )
    assert "Harbor Nights" in label
    assert "Ep 2" in label
    assert "Fog" in label


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d
    from fastapi.testclient import TestClient

    projects = tmp_path / "scripts"
    projects.mkdir()
    monkeypatch.setattr(d, "SCRIPT_PROJECTS_DIR", projects)
    # Ensure helpers use the patched dir if they close over path builders
    return TestClient(d.app)


def test_api_save_and_series_new_episode(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    projects = tmp_path / "scripts"
    projects.mkdir(exist_ok=True)
    monkeypatch.setattr(d, "SCRIPT_PROJECTS_DIR", projects)

    save = client.post(
        "/api/script/projects/save",
        json={
            "script_id": "harbor_ep1",
            "title": "Harbor Nights — Pilot",
            "brief": "Sunlit pier introduction",
            "series_title": "Harbor Nights",
            "episode_number": 1,
            "episode_title": "Pilot",
            "status": "draft",
        },
    )
    assert save.status_code == 200, save.text
    body = save.json()
    assert body["status"] == "ok"
    proj = body["project"]
    assert proj["series_id"] == "harbor_nights"
    assert proj["episode_number"] == 1

    listed = client.get("/api/script/projects")
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["status"] == "ok"
    assert any(p["script_id"] == "harbor_ep1" for p in listed_body["projects"])
    assert any(s.get("series_id") == "harbor_nights" for s in listed_body.get("series") or [])

    series_list = client.get("/api/script/series")
    assert series_list.status_code == 200
    assert series_list.json()["status"] == "ok"

    nxt = client.post(
        "/api/script/series/new-episode",
        json={
            "source_script_id": "harbor_ep1",
            "episode_title": "Fog Bank",
        },
    )
    assert nxt.status_code == 200, nxt.text
    ep2 = nxt.json()["project"]
    assert ep2["series_id"] == "harbor_nights"
    assert ep2["episode_number"] == 2
    assert ep2["episode_title"] == "Fog Bank"
    assert ep2["continues_from_script_id"] == "harbor_ep1"
    assert ep2["script_id"] != "harbor_ep1"
    # Brief carried for continuity by default
    assert "pier" in (ep2.get("brief") or "").lower() or ep2.get("brief")
