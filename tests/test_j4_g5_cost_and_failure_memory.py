"""Offline unit tests for J4 failure auto-consolidate + G5 cost meter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.cost_meter import (
    CostMeter,
    estimate_cost_usd,
    get_rates,
    get_summary,
    record_image_call,
    reset_meter,
)
from core.hermes.memory.failure_auto_consolidate import (
    consolidate_failures,
    get_status,
    get_threshold,
    is_failure_event,
    note_failure,
    summaries_path,
)


@pytest.fixture()
def isolated_root(tmp_path, monkeypatch):
    """Repo-like tree: <tmp>/data/hermes_memory/..."""
    (tmp_path / "data" / "hermes_memory" / "episodic").mkdir(parents=True)
    (tmp_path / "data" / "hermes_memory" / "semantic").mkdir(parents=True)
    monkeypatch.delenv("CINESMITH_FAILURE_CONSOLIDATE_N", raising=False)
    monkeypatch.delenv("CINESMITH_AUTO_CONSOLIDATE_FAILURES", raising=False)
    monkeypatch.delenv("CINESMITH_COST_OPENAI_IMAGE_USD", raising=False)
    monkeypatch.delenv("CINESMITH_COST_GEMINI_IMAGE_USD", raising=False)
    return tmp_path


def _write_failure_events(root: Path, n: int, category: str = "anatomy") -> list[dict]:
    log = root / "data" / "hermes_memory" / "episodic" / "events.jsonl"
    events = []
    for i in range(n):
        ev = {
            "event_id": f"evt_test_{i}",
            "event_type": "final_outcome",
            "success": False,
            "error_category": category,
            "kernel_id": "flux2_dev",
            "concept": f"failed shot {i}",
            "reason": f"{category} failure {i}",
            "source": "campaign",
        }
        events.append(ev)
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev) + "\n")
    return events


# ── J4 ──────────────────────────────────────────────────────────────────────


def test_is_failure_event_detects_success_false():
    assert is_failure_event({"success": False, "event_type": "render_result"}) is True
    assert is_failure_event({"success": True, "event_type": "render_result"}) is False
    assert is_failure_event({"event_type": "render_failure"}) is True


def test_threshold_default_and_env(monkeypatch):
    monkeypatch.delenv("CINESMITH_FAILURE_CONSOLIDATE_N", raising=False)
    assert get_threshold() == 3
    monkeypatch.setenv("CINESMITH_FAILURE_CONSOLIDATE_N", "5")
    assert get_threshold() == 5
    assert get_threshold(2) == 2


def test_note_failure_counts_until_threshold(isolated_root, monkeypatch):
    monkeypatch.setenv("CINESMITH_FAILURE_CONSOLIDATE_N", "3")
    root = isolated_root
    r1 = note_failure(
        {"event_id": "e1", "success": False, "event_type": "final_outcome", "error_category": "timeout"},
        root=root,
        threshold=3,
    )
    assert r1["status"] == "counted"
    assert r1["failure_count_since_consolidate"] == 1
    assert r1["consolidated"] is False
    assert r1["remaining_until_consolidate"] == 2

    r2 = note_failure(
        {"event_id": "e2", "success": False, "event_type": "final_outcome", "error_category": "timeout"},
        root=root,
        threshold=3,
    )
    assert r2["failure_count_since_consolidate"] == 2
    assert r2["consolidated"] is False

    # seed episodic so consolidate has material
    _write_failure_events(root, 3, category="timeout")
    r3 = note_failure(
        {"event_id": "e3", "success": False, "event_type": "final_outcome", "error_category": "timeout"},
        root=root,
        threshold=3,
    )
    assert r3.get("consolidated") is True or r3.get("status") in {"consolidated", "noop"}
    # After threshold fire, counter resets
    st = get_status(root)
    assert st["threshold"] == 3
    assert st["failure_count_since_consolidate"] == 0


def test_consolidate_writes_durable_summary(isolated_root):
    root = isolated_root
    _write_failure_events(root, 4, category="anatomy")
    result = consolidate_failures(root=root, reason="test")
    assert result["status"] == "consolidated"
    assert result["failure_count"] >= 1
    summary = result["summary"]
    assert summary["summary_id"].startswith("fs_")
    assert "lessons" in summary and summary["lessons"]
    assert "Flux2" in " ".join(summary["lessons"]) or "anatomy" in summary["rule"].lower()

    path = summaries_path(root)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["summaries"]
    assert data["summaries"][-1]["summary_id"] == summary["summary_id"]

    # semantic insights store
    sem = root / "data" / "hermes_memory" / "semantic" / "insights.json"
    assert sem.exists()
    insights = json.loads(sem.read_text(encoding="utf-8"))
    assert isinstance(insights, list) and len(insights) >= 1
    assert insights[-1].get("applies_to", {}).get("kind") == "failure_auto_summary"


def test_non_failure_ignored(isolated_root):
    r = note_failure(
        {"event_id": "ok1", "success": True, "event_type": "final_outcome"},
        root=isolated_root,
        threshold=3,
    )
    assert r["status"] == "ignored"
    assert r["consolidated"] is False


def test_product_routes_include_cost_and_failure():
    from dashboard.routes.product import router

    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/api/product/cost-meter" in paths
    assert "/api/product/failure-auto-consolidate" in paths


# ── G5 ──────────────────────────────────────────────────────────────────────


def test_estimate_cost_defaults():
    openai = estimate_cost_usd("openai", "gpt-image-2", 1)
    gemini = estimate_cost_usd("gemini", "gemini-2.5-flash-image", 1)
    assert openai > 0
    assert gemini > 0
    assert estimate_cost_usd("openai", "gpt-image-2", 2) == pytest.approx(openai * 2)


def test_env_rate_override(monkeypatch, isolated_root):
    monkeypatch.setenv("CINESMITH_COST_OPENAI_IMAGE_USD", "0.10")
    rates = get_rates(isolated_root)
    assert rates["openai"]["default"] == 0.10
    assert estimate_cost_usd("openai", "unknown-model", 1, root=isolated_root) == 0.10


def test_record_and_summary(isolated_root):
    path = isolated_root / "data" / "cost_meter.json"
    reset_meter(root=isolated_root, path=path)
    s1 = record_image_call("openai", "gpt-image-2", success=True, root=isolated_root, path=path)
    assert s1["total_success"] == 1
    assert s1["estimated_spend_usd"] > 0
    s2 = record_image_call("gemini", "gemini-2.5-flash-image", success=True, root=isolated_root, path=path)
    assert s2["total_success"] == 2
    assert "openai" in s2["by_provider"]
    assert "gemini" in s2["by_provider"]
    # failed calls do not add spend by default
    s3 = record_image_call("openai", "gpt-image-2", success=False, root=isolated_root, path=path)
    assert s3["total_failed"] == 1
    assert s3["estimated_spend_usd"] == s2["estimated_spend_usd"]
    assert path.exists()


def test_cost_meter_class_reset(isolated_root):
    path = isolated_root / "data" / "cost_meter.json"
    meter = CostMeter(root=isolated_root, path=path)
    meter.record("openai", "gpt-image-2", success=True)
    assert meter.summary()["total_calls"] >= 1
    meter.reset()
    assert meter.summary()["total_calls"] == 0
    assert meter.summary()["estimated_spend_usd"] == 0.0


def test_get_summary_shape(isolated_root):
    path = isolated_root / "data" / "cost_meter.json"
    reset_meter(root=isolated_root, path=path)
    summary = get_summary(root=isolated_root, path=path)
    assert summary["status"] == "ok"
    assert "estimated_spend_display" in summary
    assert "rates_usd" in summary
    assert "by_provider" in summary
