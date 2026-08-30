"""Hermes-led produce API — prompt in, job artifacts out."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.bridge.llm_endpoint import resolve_llm_endpoint
from core.bridge.runtime_config import get_raw_config
from core.hermes.produce.service import ProduceService
from dashboard.errors import CinesmithAPIError

router = APIRouter(tags=["produce"])
_service = ProduceService()


class ProduceStartRequest(BaseModel):
    prompt: str = ""
    profile: str = "producer"


@router.get("/api/connect/status")
async def connect_status():
    cfg = get_raw_config()
    llm = resolve_llm_endpoint(cfg)
    spark = str(cfg.get("COMFYUI_PRIMARY", "") or "").strip()
    return {
        "status": "ok",
        "llm": {
            "ready": llm.ready,
            "model": llm.model,
            "base_url": llm.base_url,
            "source": llm.source,
        },
        "spark": {"url": spark, "configured": bool(spark)},
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


@router.get("/api/produce/{job_id}/file/{name}")
async def produce_file(job_id: str, name: str):
    path = _service.job_dir(job_id) / name
    if not path.exists() or not path.is_file():
        raise CinesmithAPIError("file not found", status_code=404)
    return FileResponse(str(path))
