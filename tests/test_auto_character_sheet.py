"""Offline unit + API tests for F3 auto character sheet from one photo."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.character.auto_sheet import (
    SPARK_OFFLINE_RECOVERY_HINT,
    apply_photo_to_character,
    build_auto_sheet_prompt,
    build_auto_sheet_result,
    clamp_grid,
    draft_character_record,
    master_ref_from_upload,
    name_from_filename,
    pick_sheet_url_from_render,
    spark_recovery_hint,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_name_from_filename():
    assert name_from_filename("sienna_vale_headshot.png") == "Sienna Vale Headshot"
    assert name_from_filename("IMG_1234.jpg") == "New Character"
    assert name_from_filename("", fallback="Hero") == "Hero"


def test_clamp_grid_defaults_and_bounds():
    assert clamp_grid() == (2, 3)
    assert clamp_grid(0, 0) == (1, 1)
    assert clamp_grid(99, 99) == (4, 4)
    assert clamp_grid("2", "3") == (2, 3)
    assert clamp_grid("x", None) == (2, 3)


def test_build_auto_sheet_prompt_includes_identity():
    prompt = build_auto_sheet_prompt(name="Avery", role="pilot", user_prompt="scar on left brow")
    assert "Avery" in prompt
    assert "pilot" in prompt
    assert "scar on left brow" in prompt
    assert "continuity" in prompt.lower() or "character" in prompt.lower()


def test_apply_photo_sets_master_and_anchor():
    char = {"id": "avery", "name": "Avery", "reference_uploads": [], "master_references": []}
    upload = {
        "id": "face_1",
        "url": "/api/characters/reference/avery/face_1.png",
        "type": "face_closeup",
        "source": "upload",
        "filename": "face_1.png",
        "created_at": "2026-01-01T00:00:00Z",
    }
    out = apply_photo_to_character(char, upload)
    assert out["anchor_url"] == upload["url"]
    assert len(out["master_references"]) == 1
    assert out["master_references"][0]["source"] == "auto_sheet_photo"
    assert out["master_references"][0]["locked"] is True
    assert len(out["reference_uploads"]) == 1


def test_apply_photo_preserves_existing_anchor():
    char = {
        "id": "a",
        "anchor_url": "/existing.png",
        "master_references": [],
        "reference_uploads": [],
    }
    upload = {
        "id": "r2",
        "url": "/new.png",
        "type": "full_body",
        "filename": "body.png",
    }
    out = apply_photo_to_character(char, upload)
    assert out["anchor_url"] == "/existing.png"
    assert out["master_references"][0]["url"] == "/new.png"


def test_master_ref_from_upload():
    rec = master_ref_from_upload(
        {"id": "x", "url": "/u.png", "type": "reference"},
        notes="lock",
    )
    assert rec["type"] == "face_closeup"
    assert rec["id"].startswith("master_")
    assert rec["locked"] is True
    assert rec["notes"] == "lock"


def test_build_auto_sheet_result_partial_has_recovery_hint():
    payload = build_auto_sheet_result(
        status="partial",
        character_id="demo",
        character={"id": "demo", "anchor_url": "/a.png"},
        master_reference={"url": "/a.png"},
        spark_available=False,
        spark_configured=True,
    )
    assert payload["status"] == "partial"
    assert payload["recovery_hint"]
    assert "Spark" in payload["recovery_hint"] or "offline" in payload["recovery_hint"].lower()
    assert payload["character_id"] == "demo"
    assert "prompt_id" in payload
    assert "job_set_id" in payload
    assert "image_urls" in payload
    assert "panels" in payload


def test_spark_recovery_hint_variants():
    assert "photo" in spark_recovery_hint(has_reference=False).lower()
    assert "COMFYUI" in spark_recovery_hint(configured=False) or "Spark" in spark_recovery_hint(
        configured=False
    )
    assert SPARK_OFFLINE_RECOVERY_HINT == spark_recovery_hint(configured=True, has_reference=True)


def test_pick_sheet_url_from_render():
    assert pick_sheet_url_from_render({"image_urls": ["https://x/a.png", "https://x/b.png"]}) == "https://x/a.png"
    assert pick_sheet_url_from_render({}) == ""


def test_draft_character_record():
    rec = draft_character_record(char_id="Sienna Vale!", name="Sienna Vale", role="lead")
    assert rec["id"] == "sienna_vale"
    assert rec["name"] == "Sienna Vale"
    assert rec["role"] == "lead"
    assert rec["master_references"] == []


# ---------------------------------------------------------------------------
# In-process API (TestClient) — offline, Spark mocked down
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from dashboard.cinesmith_dashboard import app

    with TestClient(app) as c:
        yield c


def test_api_auto_sheet_spark_down_still_stores_master(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    banks = tmp_path / "character_banks"
    banks.mkdir()
    monkeypatch.setattr(d, "CHARACTER_BANKS_DIR", banks)

    cid = "auto_sheet_offline_hero"
    d._CHARACTERS_STORE[cid] = d._normalize_character(
        cid, {"id": cid, "name": "Offline Hero", "role": "Test"}
    )

    async def _spark_down():
        return {
            "configured": True,
            "available": False,
            "host": "http://127.0.0.1:8188",
            "error": "connection refused",
        }

    # Patch probe used inside the router module closure — re-import path
    # The handler closes over local _probe_spark; monkeypatch ComfyUIClient instead.
    class _FakeClient:
        def __init__(self, host):
            self.host = host

        async def check_health(self):
            return False, {"error": "connection refused"}

    monkeypatch.setattr(d, "_character_host_from_config", lambda: "http://127.0.0.1:8188")
    monkeypatch.setattr(
        "core.dispatch.comfy_client.ComfyUIClient",
        _FakeClient,
    )

    files = {
        "file": ("hero_face.png", b"\x89PNG\r\n\x1a\n" + b"PHOTO" * 8, "image/png"),
    }
    resp = client.post(
        f"/api/characters/{cid}/auto-sheet",
        files=files,
        data={
            "prompt": "soft studio key light",
            "rows": "2",
            "cols": "3",
            "extract_panels": "false",
        },
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "partial"
    assert payload["character_id"] == cid
    assert payload["spark_available"] is False
    assert payload["master_reference"]
    assert payload["master_reference"]["url"]
    assert payload["recovery_hint"]
    assert "Spark" in payload["recovery_hint"] or "offline" in payload["recovery_hint"].lower()
    assert payload["character"]["anchor_url"]
    assert len(payload["character"].get("master_references") or []) >= 1
    # File landed on disk under banks
    ref_dir = banks / "references" / cid
    assert ref_dir.exists()
    assert any(ref_dir.iterdir())


def test_api_auto_sheet_from_photo_creates_character(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    banks = tmp_path / "character_banks"
    banks.mkdir()
    monkeypatch.setattr(d, "CHARACTER_BANKS_DIR", banks)
    monkeypatch.setattr(d, "_character_host_from_config", lambda: "")

    class _FakeClient:
        def __init__(self, host):
            self.host = host

        async def check_health(self):
            return False, {"error": "offline"}

    monkeypatch.setattr("core.dispatch.comfy_client.ComfyUIClient", _FakeClient)

    files = {
        "file": ("mara_chen_portrait.jpg", b"\xff\xd8\xff" + b"JPEGDATA" * 4, "image/jpeg"),
    }
    resp = client.post(
        "/api/characters/auto-sheet-from-photo",
        files=files,
        data={"role": "courier", "extract_panels": "false"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "partial"
    assert payload["created"] is True
    assert payload["character_id"]
    assert payload["character"]
    assert payload["character"]["anchor_url"]
    assert payload["master_reference"]["url"] == payload["character"]["anchor_url"]
    # Stored in memory
    cid = payload["character_id"]
    assert cid in d._CHARACTERS_STORE
    assert d._CHARACTERS_STORE[cid].get("anchor_url")


def test_api_auto_sheet_create_if_missing(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    banks = tmp_path / "character_banks"
    banks.mkdir()
    monkeypatch.setattr(d, "CHARACTER_BANKS_DIR", banks)
    monkeypatch.setattr(d, "_character_host_from_config", lambda: "")

    class _FakeClient:
        def __init__(self, host):
            self.host = host

        async def check_health(self):
            return False, {"error": "offline"}

    monkeypatch.setattr("core.dispatch.comfy_client.ComfyUIClient", _FakeClient)

    files = {
        "file": ("face.png", b"\x89PNG\r\n\x1a\n" + b"Z" * 16, "image/png"),
    }
    resp = client.post(
        "/api/characters/brand_new_auto_char/auto-sheet",
        files=files,
        data={"create_if_missing": "Brand New Auto Char", "extract_panels": "0"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "partial"
    assert payload["created"] is True
    assert payload["character_id"] == "brand_new_auto_char"


def test_api_auto_sheet_missing_char_without_create(client):
    from dashboard import cinesmith_dashboard as d

    # Ensure true miss — store may retain leftovers from earlier local runs.
    cid = "definitely_missing_char_xyz"
    d._CHARACTERS_STORE.pop(cid, None)
    resp = client.post(
        f"/api/characters/{cid}/auto-sheet",
        data={"prompt": "x"},
    )
    assert resp.status_code == 404
    assert cid not in d._CHARACTERS_STORE


def test_api_auto_sheet_spark_up_submits_sheet(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    banks = tmp_path / "character_banks"
    banks.mkdir()
    monkeypatch.setattr(d, "CHARACTER_BANKS_DIR", banks)
    monkeypatch.setattr(d, "_character_host_from_config", lambda: "http://127.0.0.1:8188")

    class _HealthyClient:
        def __init__(self, host):
            self.host = host

        async def check_health(self):
            return True, {"status": "ok"}

    monkeypatch.setattr("core.dispatch.comfy_client.ComfyUIClient", _HealthyClient)

    cid = "auto_sheet_spark_ok"
    d._CHARACTERS_STORE[cid] = d._normalize_character(
        cid, {"id": cid, "name": "Spark Ok", "role": "lead"}
    )

    async def _fake_render(req):
        assert req.render_type == "sheet"
        assert req.character_id == cid
        char = d._normalize_character(cid, d._CHARACTERS_STORE[cid])
        char.setdefault("candidate_assets", []).append(
            {
                "type": "sheet",
                "url": "/media/characters/spark_ok/sheet.png",
                "prompt_id": "pid-sheet-1",
            }
        )
        d._CHARACTERS_STORE[cid] = char
        return {
            "status": "complete",
            "character": char,
            "render_type": "sheet",
            "prompt_id": "pid-sheet-1",
            "image_urls": ["/media/characters/spark_ok/sheet.png"],
            "anchor_url": char.get("anchor_url") or "",
        }

    monkeypatch.setattr(d, "api_character_spark_render", AsyncMock(side_effect=_fake_render))

    # Skip real panel extract (needs image file)
    async def _no_panels(*_a, **_k):
        return {"status": "ok", "panels": [], "character": d._CHARACTERS_STORE[cid]}

    monkeypatch.setattr(d, "api_extract_character_sheet_panels", AsyncMock(side_effect=_no_panels))

    files = {
        "file": ("face.png", b"\x89PNG\r\n\x1a\n" + b"OK" * 16, "image/png"),
    }
    resp = client.post(
        f"/api/characters/{cid}/auto-sheet",
        files=files,
        data={"extract_panels": "true", "rows": "2", "cols": "3"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "complete"
    assert payload["spark_available"] is True
    assert payload["prompt_id"] == "pid-sheet-1"
    assert payload["job_set_id"] == "pid-sheet-1"
    assert payload["sheet_url"] == "/media/characters/spark_ok/sheet.png"
    assert payload["image_urls"]
    assert payload["master_reference"]
    assert payload["character"]["anchor_url"]
