"""C7: parallel Hermes compile + structured per-shot errors."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, patch

import pytest

from core.hermes.pipeline.campaign_service import HermesCampaignService


def _make_service(
    *,
    shots_store: Optional[List[Dict[str, Any]]] = None,
    cancelled: bool = False,
) -> HermesCampaignService:
    return HermesCampaignService(
        repo_root=Path(__file__).resolve().parents[1],
        media_images=Path("/tmp/cinesmith_c7_media"),
        shots_store=shots_store if shots_store is not None else [],
        campaigns={},
        now_iso=lambda: "2026-07-09T00:00:00Z",
        record_event=lambda *a, **k: None,
        audit_render=AsyncMock(return_value={"passed": True, "score": 9.0}),
        workflow_file_for_id=lambda _wid: Path("/tmp/fake_workflow.json"),
        is_cancelled=lambda: cancelled,
        active_campaign_setter=lambda _cid: None,
    )


def test_format_shot_error_structure():
    err = HermesCampaignService.format_shot_error(
        shot_id="SHOT_002",
        stage="refine",
        message="Hermes returned no compiled_prompt for SHOT_002.",
        recoverable=True,
        hint="Check Settings → Hermes / LM Studio.",
        workflow_id="01_flux2_text_to_image",
    )
    assert err["type"] == "error"
    assert err["shot_id"] == "SHOT_002"
    assert err["stage"] == "refine"
    assert err["message"].startswith("Hermes returned")
    assert err["recoverable"] is True
    assert "LM Studio" in err["hint"]
    assert err["workflow_id"] == "01_flux2_text_to_image"
    # Backward-compatible text for existing stream consumers
    assert "SHOT_002" in err["text"] or "compiled_prompt" in err["text"]
    assert err["hint"] in err["text"] or err["message"] in err["text"]


def test_format_shot_error_does_not_duplicate_hint_in_text():
    msg = "fail — already hinted"
    err = HermesCampaignService.format_shot_error(
        shot_id="S1",
        stage="compile",
        message=msg,
        hint="already hinted",
    )
    assert err["text"] == msg


def test_compile_concurrency_bounds(monkeypatch):
    monkeypatch.delenv("CINESMITH_COMPILE_CONCURRENCY", raising=False)
    assert HermesCampaignService.compile_concurrency() == 3

    monkeypatch.setenv("CINESMITH_COMPILE_CONCURRENCY", "8")
    assert HermesCampaignService.compile_concurrency() == 8

    monkeypatch.setenv("CINESMITH_COMPILE_CONCURRENCY", "99")
    assert HermesCampaignService.compile_concurrency() == 16

    monkeypatch.setenv("CINESMITH_COMPILE_CONCURRENCY", "0")
    assert HermesCampaignService.compile_concurrency() == 1

    monkeypatch.setenv("CINESMITH_COMPILE_CONCURRENCY", "nope")
    assert HermesCampaignService.compile_concurrency() == 3


@pytest.mark.asyncio
async def test_parallel_compile_respects_concurrency_and_continues_on_failure(monkeypatch):
    monkeypatch.setenv("CINESMITH_COMPILE_CONCURRENCY", "2")
    monkeypatch.setenv("CINESMITH_AUTO_VIDEO_PROMPT", "false")

    svc = _make_service()
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def fake_run_json(profile: str, task: Dict[str, Any]):
        nonlocal active, max_active
        shot_id = str(task.get("shot_id") or "")
        async with lock:
            active += 1
            max_active = max(max_active, active)
        try:
            await asyncio.sleep(0.05)
            if shot_id == "SHOT_002":
                return None  # simulate Hermes unavailable for one shot
            return {
                "compiled_prompt": f"refined for {shot_id}",
                "negative_prompt": "blur",
            }
        finally:
            async with lock:
                active -= 1

    svc.profile_cli.run_json = fake_run_json  # type: ignore[method-assign]

    def fake_compile_prompt_artifact(**kwargs):
        shot_meta = kwargs.get("shot_meta") or {}
        sid = shot_meta.get("shot_id") or "SHOT"
        return {
            "compiled_prompt": f"local {sid}",
            "negative_prompt": "neg",
            "identity_negative_prompt": "",
            "profile_name": "test",
            "model_family": "flux",
            "model_standard_name": "std",
            "model_standard_version": "1",
            "skills_used": [],
            "compiler_version": "v1",
            "sections": {},
        }

    jobs = [
        {
            "effective_shot": {"shot_id": f"SHOT_{i:03d}", "sequence": i, "visual_brief": "v", "characters": []},
            "workflow_id": "01_flux2_text_to_image",
            "campaign_id": "camp_c7",
            "platform_brief": "brief",
            "platform_skill": {},
            "identity_pack": {},
            "raw_content": "{}",
            "review": {"score": 8},
            "source": "campaign",
        }
        for i in range(1, 5)
    ]
    results: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []

    with patch(
        "core.hermes.pipeline.campaign_service.compile_prompt_artifact",
        side_effect=fake_compile_prompt_artifact,
    ), patch(
        "core.hermes.pipeline.campaign_service.apply_model_prompt_standard",
        side_effect=lambda prompt, **k: (prompt, []),
    ), patch(
        "core.hermes.pipeline.campaign_service.flux_dev_ignores_negative_prompts",
        return_value=False,
    ):
        async for ev in svc._iter_parallel_compile(jobs, results_out=results):
            events.append(ev)

    assert max_active <= 2
    assert len(results) == 4
    ok = [r for r in results if r.get("ok")]
    bad = [r for r in results if not r.get("ok")]
    assert len(ok) == 3
    assert len(bad) == 1
    err = bad[0]["error"]
    assert err["shot_id"] == "SHOT_002"
    assert err["stage"] == "refine"
    assert err["recoverable"] is True
    assert err["hint"]
    assert any(e.get("type") == "error" and e.get("shot_id") == "SHOT_002" for e in events)
    assert any(e.get("type") == "pipeline_timing" and e.get("stage") == "compile_parallel_done" for e in events)


@pytest.mark.asyncio
async def test_compile_one_unit_empty_prompt_is_recoverable(monkeypatch):
    monkeypatch.setenv("CINESMITH_AUTO_VIDEO_PROMPT", "false")
    svc = _make_service()

    async def fake_run_json(profile: str, task: Dict[str, Any]):
        return {"compiled_prompt": "   ", "negative_prompt": ""}

    svc.profile_cli.run_json = fake_run_json  # type: ignore[method-assign]

    with patch(
        "core.hermes.pipeline.campaign_service.compile_prompt_artifact",
        return_value={
            "compiled_prompt": "base",
            "negative_prompt": "",
            "identity_negative_prompt": "",
            "profile_name": "t",
            "model_family": "flux",
            "skills_used": [],
            "sections": {},
        },
    ), patch(
        "core.hermes.pipeline.campaign_service.flux_dev_ignores_negative_prompts",
        return_value=False,
    ):
        result = await svc._compile_one_unit(
            effective_shot={"shot_id": "SHOT_009", "sequence": 9, "visual_brief": "x", "characters": []},
            workflow_id="wf",
            campaign_id="c",
            platform_brief="brief",
            platform_skill={},
            identity_pack={},
            raw_content="",
            review=None,
            source="campaign",
        )

    assert result["ok"] is False
    err = result["error"]
    assert err["shot_id"] == "SHOT_009"
    assert err["stage"] == "refine"
    assert err["recoverable"] is True
    assert "compiled_prompt" in err["message"]


@pytest.mark.asyncio
async def test_compile_one_unit_success_builds_shot_record(monkeypatch):
    monkeypatch.setenv("CINESMITH_AUTO_VIDEO_PROMPT", "false")
    svc = _make_service()

    async def fake_run_json(profile: str, task: Dict[str, Any]):
        return {
            "compiled_prompt": "beautiful cinematic frame",
            "negative_prompt": "blurry",
            "__exchange": {"role": "compiler", "ok": True},
        }

    svc.profile_cli.run_json = fake_run_json  # type: ignore[method-assign]

    with patch(
        "core.hermes.pipeline.campaign_service.compile_prompt_artifact",
        return_value={
            "compiled_prompt": "base prompt",
            "negative_prompt": "neg",
            "identity_negative_prompt": "",
            "profile_name": "Flux Profile",
            "model_family": "flux",
            "model_standard_name": "flux-std",
            "model_standard_version": "1.0",
            "skills_used": ["skill-a"],
            "compiler_version": "v1.0.0",
            "sections": {"Render Type": "still"},
        },
    ), patch(
        "core.hermes.pipeline.campaign_service.apply_model_prompt_standard",
        side_effect=lambda prompt, **k: (prompt + " [std]", ["std-skill"]),
    ), patch(
        "core.hermes.pipeline.campaign_service.flux_dev_ignores_negative_prompts",
        return_value=False,
    ):
        result = await svc._compile_one_unit(
            effective_shot={
                "shot_id": "SHOT_001",
                "sequence": 1,
                "visual_brief": "hero wide",
                "rationale": "open",
                "constraints": "no text",
                "characters": ["Elena"],
            },
            workflow_id="01_flux2_text_to_image",
            campaign_id="camp_ok",
            platform_brief="campaign brief",
            platform_skill={"active": False},
            identity_pack={"type": "character", "name": "Elena"},
            raw_content="{}",
            review={"score": 9},
            source="campaign",
        )

    assert result["ok"] is True
    rec = result["shot_record"]
    assert rec["shot_id"] == "SHOT_001"
    assert rec["compiled_prompt"].endswith("[std]")
    assert "std-skill" in rec["skills_used"]
    assert rec["negative_prompt"] == "blurry"
    assert any(e.get("type") == "compiler" for e in result["events"])
    assert result["exchange"]["role"] == "compiler"
