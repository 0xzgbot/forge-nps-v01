"""Hermes-led produce API — prompt in, job artifacts out."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.bridge.llm_endpoint import resolve_llm_endpoint
from core.bridge.runtime_config import get_raw_config, set_config
from core.dispatch.capability_router import CapabilityRouter
from core.hermes.produce import render as produce_render
from core.hermes.produce.service import ProduceService
from dashboard.errors import CinesmithAPIError

router = APIRouter(tags=["produce"])
_service = ProduceService()


class ProduceStartRequest(BaseModel):
    prompt: str = ""
    profile: str = "producer"


class ProduceShotRequest(BaseModel):
    shot_id: str
    mode: str = "i2va"
    workflow_id: str = ""
    wait: bool = False


class ProduceEditRequest(BaseModel):
    shots: List[Dict[str, Any]] = []


class ProduceConnectSave(BaseModel):
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""
    LLM_API_KEY: str = ""
    COMFYUI_PRIMARY: str = ""
    COMFYUI_STILLS_A: str = ""
    COMFYUI_STILLS_B: str = ""


def _job_or_404(job_id: str):
    path = _service.job_dir(job_id)
    if not path.exists():
        raise CinesmithAPIError("job not found", status_code=404)
    return path


@router.get("/api/connect/status")
async def connect_status():
    cfg = get_raw_config()
    llm = resolve_llm_endpoint(cfg)
    hosts = await CapabilityRouter(cfg).connect_status()
    return {
        "status": "ok",
        "llm": {
            "ready": llm.ready,
            "model": llm.model,
            "base_url": llm.base_url,
            "source": llm.source,
        },
        "spark": hosts.get("spark") or {},
        "stills_a": hosts.get("stills_a") or {},
        "stills_b": hosts.get("stills_b") or {},
        "hosts": hosts,
    }


@router.post("/api/produce/start")
async def produce_start(req: ProduceStartRequest):
    try:
        snap = _service.start(req.prompt, profile=req.profile)
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    asyncio.create_task(_service._run_hermes(snap["job_id"], snap["prompt"]))
    return {"status": "ok", **snap}


@router.get("/api/produce/jobs")
async def produce_jobs():
    return {"status": "ok", "jobs": _service.list_jobs()}


@router.get("/api/produce/{job_id}")
async def produce_job(job_id: str):
    try:
        return {"status": "ok", **_service.snapshot(job_id)}
    except FileNotFoundError as exc:
        raise CinesmithAPIError("job not found", status_code=404) from exc


@router.get("/api/produce/{job_id}/shots")
async def produce_shots(job_id: str):
    path = _job_or_404(job_id)
    return {"status": "ok", "shots": produce_render.load_shots(path), "edit": produce_render.load_edit(path)}


@router.post("/api/produce/{job_id}/render-board")
async def produce_render_board(job_id: str, req: ProduceShotRequest):
    path = _job_or_404(job_id)
    result = await produce_render.render_board(
        path,
        req.shot_id,
        workflow_id=req.workflow_id,
        wait=req.wait,
    )
    if result.get("status") == "error":
        raise CinesmithAPIError(result.get("error") or "render_board_failed", status_code=400)
    return {"status": "ok", **result, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/render-take")
async def produce_render_take(job_id: str, req: ProduceShotRequest):
    path = _job_or_404(job_id)
    result = await produce_render.render_take(path, req.shot_id, mode=req.mode, wait=req.wait)
    if result.get("status") == "error":
        raise CinesmithAPIError(result.get("error") or "render_take_failed", status_code=400)
    return {"status": "ok", **result, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/shots/{shot_id}/approve")
async def produce_approve(job_id: str, shot_id: str):
    path = _job_or_404(job_id)
    produce_render.set_shot_status(path, shot_id, "approved")
    return {"status": "ok", **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/shots/{shot_id}/retake")
async def produce_retake(job_id: str, shot_id: str):
    path = _job_or_404(job_id)
    produce_render.set_shot_status(path, shot_id, "retake")
    return {"status": "ok", **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/assemble")
async def produce_assemble(job_id: str, req: Optional[ProduceEditRequest] = None):
    path = _job_or_404(job_id)
    rows = req.shots if req and req.shots else None
    result = produce_render.assemble_cut(path, rows=rows)
    if not result.get("ok"):
        raise CinesmithAPIError(result.get("error") or "assemble_failed", status_code=400)
    return {"status": "ok", **result, **_service.snapshot(job_id)}


@router.put("/api/produce/{job_id}/edit")
async def produce_edit(job_id: str, req: ProduceEditRequest):
    path = _job_or_404(job_id)
    produce_render.save_edit(path, req.shots)
    return {"status": "ok", "edit": produce_render.load_edit(path), **_service.snapshot(job_id)}


@router.get("/api/produce/{job_id}/file/{name:path}")
async def produce_file(job_id: str, name: str):
    path = _job_or_404(job_id)
    target = (path / name).resolve()
    if path.resolve() not in target.parents and target != path.resolve():
        raise CinesmithAPIError("file not found", status_code=404)
    if not target.exists() or not target.is_file():
        raise CinesmithAPIError("file not found", status_code=404)
    return FileResponse(str(target))
