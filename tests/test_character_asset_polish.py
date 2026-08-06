"""Offline unit + API tests for F2 multi-upload and F4 package→campaign identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.character.identity_attach import (
    build_identity_pack_from_vault_package,
    collect_identity_tokens,
    infer_identity_type,
    infer_reference_type,
)
from core.character.reference_upload import (
    merge_character_uploads,
    save_asset_vault_reference_bytes,
    save_character_reference_bytes,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_infer_reference_type_from_filename():
    assert infer_reference_type("hero_face_close.png") == "face_closeup"
    assert infer_reference_type("full_body_turn.png") == "full_body"
    assert infer_reference_type("wardrobe_outfit.jpg") == "outfit"
    assert infer_reference_type("walk_cycle.mp4") == "motion_clip"
    assert infer_reference_type("misc.png") == "reference"


def test_build_identity_pack_from_product_package():
    package = {
        "id": "demo_lamp",
        "name": "Sienna Desk Lamp",
        "asset_type": "product",
        "brand_rules": "Premium matte-black; clean silhouette",
        "style_rules": "teal shadows, amber highlights",
        "prop_notes": "brass dimmer knob",
        "tags": ["demo", "continuity"],
        "character_ids": ["avery_coleman"],
        "character_refs": [{"id": "avery_coleman", "role": "maker", "notes": ""}],
        "references": [
            {
                "id": "r1",
                "type": "product",
                "name": "Hero lamp",
                "prompt": "matte-black articulating desk lamp",
            }
        ],
    }
    pack = build_identity_pack_from_vault_package(package)
    assert pack["type"] == "product"
    assert pack["name"] == "Sienna Desk Lamp"
    assert "asset_vault:demo_lamp" in pack["identity_tokens"]
    assert any("lamp" in t.lower() or "matte" in t.lower() for t in pack["identity_tokens"])
    assert pack["negative_tokens"]
    assert "identity drift" in pack["negative_tokens"]


def test_infer_identity_type_character_package():
    pack = {
        "id": "cast_pack",
        "name": "Cast Continuity",
        "asset_type": "character",
        "character_ids": ["elara_vance"],
        "character_refs": [{"id": "elara_vance", "role": "lead"}],
    }
    assert infer_identity_type(pack) == "character"
    built = build_identity_pack_from_vault_package(pack)
    assert built["type"] == "character"
    assert any("elara" in t.lower() for t in collect_identity_tokens(pack))


def test_save_character_reference_bytes(tmp_path):
    banks = tmp_path / "character_banks"
    rec = save_character_reference_bytes(
        char_id="Elara Vance",
        filename="face_closeup.png",
        content=b"\x89PNG\r\n\x1a\n" + b"0" * 32,
        banks_dir=banks,
        reference_type="auto",
        notes="hero face",
    )
    assert rec["type"] == "face_closeup"
    assert rec["url"].startswith("/api/characters/reference/elara_vance/")
    dest = Path(rec["path"])
    assert dest.exists()
    assert dest.read_bytes().startswith(b"\x89PNG")


def test_save_character_reference_rejects_bad_ext(tmp_path):
    with pytest.raises(ValueError):
        save_character_reference_bytes(
            char_id="x",
            filename="notes.txt",
            content=b"hello",
            banks_dir=tmp_path,
        )


def test_merge_character_uploads_sets_anchor():
    char = {"id": "a", "name": "A", "reference_uploads": []}
    uploads = [
        {
            "id": "r1",
            "url": "/api/characters/reference/a/r1.png",
            "type": "face_closeup",
            "source": "upload",
            "notes": "",
            "filename": "r1.png",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]
    merged = merge_character_uploads(char, uploads)
    assert len(merged["reference_uploads"]) == 1
    assert merged["anchor_url"] == uploads[0]["url"]


def test_save_asset_vault_reference_bytes(tmp_path):
    media = tmp_path / "media"
    ref, path = save_asset_vault_reference_bytes(
        package_id="Demo Package!",
        filename="logo.png",
        content=b"PNGDATA",
        media_root=media,
        asset_type="logo",
        name="Brand Mark",
        prompt="flat logo",
    )
    assert path.exists()
    assert path.read_bytes() == b"PNGDATA"
    assert ref["type"] == "logo"
    assert ref["name"] == "Brand Mark"
    assert "demo_package" in str(path)


# ---------------------------------------------------------------------------
# In-process API (TestClient) — offline
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from dashboard.cinesmith_dashboard import app

    with TestClient(app) as c:
        yield c


def _pick_character_id(client) -> str:
    resp = client.get("/api/characters")
    assert resp.status_code == 200
    data = resp.json()
    chars = data if isinstance(data, list) else data.get("characters") or []
    assert chars, "expected at least one character bank entry for tests"
    first = chars[0]
    return first.get("id") or first.get("name")


def test_api_character_batch_upload(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    banks = tmp_path / "character_banks"
    banks.mkdir()
    monkeypatch.setattr(d, "CHARACTER_BANKS_DIR", banks)

    char_id = _pick_character_id(client)
    # ensure character exists in store after path patch — re-seed minimal char if needed
    cid = d._character_slug(char_id)
    if cid not in d._CHARACTERS_STORE:
        d._CHARACTERS_STORE[cid] = d._normalize_character(
            cid, {"id": cid, "name": cid, "role": "Test"}
        )

    files = [
        ("files", ("face_close.png", b"\x89PNG\r\n\x1a\n" + b"A" * 16, "image/png")),
        ("files", ("full_body.png", b"\x89PNG\r\n\x1a\n" + b"B" * 16, "image/png")),
    ]
    resp = client.post(
        f"/api/characters/{cid}/references/batch",
        files=files,
        data={"reference_type": "auto", "notes": "batch test"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["uploaded_count"] == 2
    assert len(payload["uploaded"]) == 2
    # files on disk
    ref_dir = banks / "references" / cid
    assert ref_dir.exists()
    assert len(list(ref_dir.glob("*"))) >= 2


def test_api_asset_batch_upload(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    media = tmp_path / "media"
    media.mkdir()
    vault = tmp_path / "asset_vault"
    vault.mkdir()
    packages_path = vault / "packages.json"
    packages_path.write_text(
        json.dumps(
            [
                {
                    "id": "test_polish_pkg",
                    "name": "Test Polish Package",
                    "asset_type": "product",
                    "references": [],
                    "character_ids": [],
                    "tags": ["test"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(d, "MEDIA_ROOT", media)
    monkeypatch.setattr(d, "ASSET_VAULT_DIR", vault)
    monkeypatch.setattr(d, "ASSET_VAULT_PACKAGES_PATH", packages_path)

    files = [
        ("files", ("product_a.png", b"PNG1", "image/png")),
        ("files", ("product_b.png", b"PNG2", "image/png")),
    ]
    resp = client.post(
        "/api/asset-vault/packages/test_polish_pkg/references/upload-batch",
        files=files,
        data={"asset_type": "product", "name": "Hero", "prompt": "lock silhouette"},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["uploaded_count"] == 2
    assert len(payload["package"]["references"]) >= 2
    out_dir = media / "asset_vault" / "test_polish_pkg"
    assert out_dir.exists()
    assert len(list(out_dir.glob("*"))) >= 2


def test_api_attach_package_identity(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    vault = tmp_path / "asset_vault"
    vault.mkdir()
    packages_path = vault / "packages.json"
    packages_path.write_text(
        json.dumps(
            [
                {
                    "id": "attach_demo_pkg",
                    "name": "Attach Demo Kit",
                    "asset_type": "product",
                    "brand_rules": "matte black product; brass accents",
                    "style_rules": "teal amber workshop",
                    "tags": ["attach-test"],
                    "references": [],
                    "character_ids": ["avery_coleman"],
                    "character_refs": [
                        {"id": "avery_coleman", "role": "maker", "notes": ""}
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(d, "ASSET_VAULT_DIR", vault)
    monkeypatch.setattr(d, "ASSET_VAULT_PACKAGES_PATH", packages_path)

    # Isolate campaign writes
    id_root = tmp_path / "identity_assets"
    id_root.mkdir()
    monkeypatch.setattr(d, "MEDIA_IDENTITY_ASSETS", id_root)

    campaign_id = "polish_attach_campaign"
    # Clear any prior state
    d._CAMPAIGNS.pop(campaign_id, None)

    resp = client.post(
        "/api/asset-vault/packages/attach_demo_pkg/attach-campaign-identity",
        json={"campaign_id": campaign_id, "copy_reference_assets": False},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["campaign_id"] == campaign_id
    identity = payload["identity_pack"]
    assert identity["type"] == "product"
    assert identity["name"] == "Attach Demo Kit"
    assert any("asset_vault:attach_demo_pkg" == t for t in identity["identity_tokens"])
    assert "identity drift" in identity["negative_tokens"]

    # Verify persisted via GET
    got = client.get(f"/api/campaigns/{campaign_id}/identity")
    assert got.status_code == 200
    body = got.json()
    assert body["identity_pack"]["name"] == "Attach Demo Kit"


def test_api_attach_requires_campaign_when_none(client, tmp_path, monkeypatch):
    from dashboard import cinesmith_dashboard as d

    vault = tmp_path / "asset_vault"
    vault.mkdir()
    packages_path = vault / "packages.json"
    packages_path.write_text(
        json.dumps(
            [
                {
                    "id": "no_campaign_pkg",
                    "name": "Orphan Package",
                    "asset_type": "product",
                    "references": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(d, "ASSET_VAULT_DIR", vault)
    monkeypatch.setattr(d, "ASSET_VAULT_PACKAGES_PATH", packages_path)
    monkeypatch.setattr(d, "_ACTIVE_CAMPAIGN", None)

    # Make campaigns list empty
    async def _empty_campaigns():
        return {"campaigns": [], "count": 0}

    monkeypatch.setattr(d, "api_get_campaigns", _empty_campaigns)

    resp = client.post(
        "/api/asset-vault/packages/no_campaign_pkg/attach-campaign-identity",
        json={"campaign_id": "", "copy_reference_assets": False},
    )
    assert resp.status_code == 400
