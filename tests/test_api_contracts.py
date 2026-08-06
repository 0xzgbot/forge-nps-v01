"""Canonical API contract smoke (in-process TestClient)."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from dashboard.cinesmith_dashboard import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


CANONICAL_GET = [
    "/api/stats",
    "/api/config",
    "/api/config/effective",
    "/api/system/readiness",
    "/api/shots",
    "/api/memory/health",
    "/api/script/storyboard/image-models",
    "/api/product/create-hub",
    "/api/product/queue-summary",
    "/api/product/wizard-state",
    "/api/product/suggestions",
    "/api/product/ab-compare/recent",
]


@pytest.mark.parametrize("path", CANONICAL_GET)
def test_canonical_get_ok(client, path):
    resp = client.get(path)
    assert resp.status_code < 500, path
    # most return JSON objects
    if resp.headers.get("content-type", "").startswith("application/json"):
        data = resp.json()
        assert isinstance(data, (dict, list)), path


def test_legacy_routes_disabled(client):
    for path, body in [
        ("/api/shots/dispatch-all", {}),
        ("/api/render", {"prompt": "x"}),
        ("/api/inject-prompt", {"prompt": "x"}),
    ]:
        resp = client.post(path, json=body)
        assert resp.status_code == 410, path
        data = resp.json()
        assert data.get("status") == "legacy_disabled"


def test_structured_scorecard_error(client):
    resp = client.post("/api/product/scorecard", json={})
    assert resp.status_code == 400
    data = resp.json()
    assert data.get("status") == "error"
    assert "error" in data and data["error"].get("code")


def test_create_hub_modes(client):
    data = client.get("/api/product/create-hub").json()
    modes = {m["id"] for m in data.get("modes", [])}
    assert {"images", "story", "video"}.issubset(modes)
    assert data.get("product_model") == "hermes_agency"
    titles = " ".join(m.get("title", "") for m in data.get("modes", [])).lower()
    assert "script studio" not in titles
    assert "hermes" in " ".join(
        (m.get("title", "") + " " + m.get("subtitle", "")).lower() for m in data.get("modes", [])
    )
