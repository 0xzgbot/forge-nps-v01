"""Hermes-led produce API — prompt in, job artifacts out."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.bridge.llm_endpoint import probe_llm_endpoint, resolve_llm_endpoint
from core.bridge.runtime_config import get_raw_config, set_config
from core.dispatch.capability_router import CapabilityRouter
from core.dispatch.model_catalog import catalog as model_catalog
from core.hermes.produce import elements as produce_elements
from core.hermes.produce import desk as produce_desk
from core.hermes.produce import job_ops as produce_ops
from core.hermes.produce import queue as produce_queue
from core.hermes.produce import render as produce_render
from core.hermes.produce.service import ProduceService
from dashboard.errors import CinesmithAPIError

router = APIRouter(tags=["produce"])
_service = ProduceService()


class ProduceStartRequest(BaseModel):
    prompt: str = ""
    profile: str = "producer"
    produce_mode: str = "shoot"
    stills_model: str = ""
    video_model: str = ""
    title: str = ""
    aspect: str = "16:9"


class ProduceShotRequest(BaseModel):
    shot_id: str = ""
    shot_ids: List[str] = []
    mode: str = ""
    workflow_id: str = ""
    wait: bool = False
    host: str = ""


class ProduceModeRequest(BaseModel):
    produce_mode: str = "shoot"


class ProduceQueueItemRequest(BaseModel):
    action: str
    shot_id: str = ""
    mode: str = ""
    workflow_id: str = ""
    host: str = ""
    start_sec: float = 0
    end_sec: float = 0


class ProduceRangeRequest(BaseModel):
    shot_id: str
    start_sec: float
    end_sec: float
    wait: bool = False


class ProduceShotPatch(BaseModel):
    visual: Optional[str] = None
    h3_prompt: Optional[str] = None
    purpose: Optional[str] = None
    duration_sec: Optional[int] = None
    camera: Optional[str] = None
    audio: Optional[str] = None
    h3_mode: Optional[str] = None
    still: Optional[str] = None
    end_still: Optional[str] = None
    voice_ref: Optional[str] = None
    guides: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = None
    seed: Optional[int] = None
    negative_prompt: Optional[str] = None
    review_status: Optional[str] = None
    review_note: Optional[str] = None


class ProduceOptionsRequest(BaseModel):
    produce_mode: str = ""
    color_pass: Optional[bool] = None
    stills_model: str = ""
    video_model: str = ""
    title: str = ""
    aspect: str = ""
    fade_sec: Optional[float] = None
    transition: str = ""


class ProduceQueueRunRequest(BaseModel):
    max_items: int = 8


class ProduceEditRequest(BaseModel):
    shots: List[Dict[str, Any]] = []


class ProduceAttachRequest(BaseModel):
    ids: List[str] = []


class ProduceRestoreTakeRequest(BaseModel):
    shot_id: str
    clip: str


class ProduceCommentRequest(BaseModel):
    text: str = ""
    shot_id: str = ""
    author: str = "you"


class ProduceShotAddRequest(BaseModel):
    purpose: str = ""
    visual: str = ""


class ProduceRenameRequest(BaseModel):
    title: str = ""


class ProduceReviewRequest(BaseModel):
    shot_id: str = ""
    decision: str = "approved"
    note: str = ""


class ProduceAbRequest(BaseModel):
    shot_id: str
    take_a: str
    take_b: str
    winner: str = ""
    note: str = ""


class ProduceGrabRequest(BaseModel):
    shot_id: str
    time_sec: float = 0
    as_last: bool = False


class ProduceRestoreCutRequest(BaseModel):
    file: str = ""


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
    probe = await asyncio.to_thread(probe_llm_endpoint, llm)
    hosts = await CapabilityRouter(cfg).connect_status()
    return {
        "status": "ok",
        "llm": {
            "ready": llm.ready,
            "configured": bool(probe.get("configured")),
            "reachable": bool(probe.get("reachable")),
            "model": llm.model,
            "base_url": llm.base_url,
            "source": llm.source,
            "error": probe.get("error") or "",
        },
        "spark": hosts.get("spark") or {},
        "stills_a": hosts.get("stills_a") or {},
        "stills_b": hosts.get("stills_b") or {},
        "hosts": hosts,
    }


@router.post("/api/produce/start")
async def produce_start(req: ProduceStartRequest):
    try:
        snap = _service.start(
            req.prompt,
            profile=req.profile,
            produce_mode=req.produce_mode,
            stills_model=req.stills_model,
            video_model=req.video_model,
            title=req.title,
            aspect=req.aspect,
        )
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    asyncio.create_task(_service._run_hermes(snap["job_id"], snap["prompt"]))
    return {"status": "ok", **snap}


@router.get("/api/produce/jobs")
async def produce_jobs():
    return {"status": "ok", "jobs": _service.list_jobs()}


@router.get("/api/produce/models")
async def produce_models():
    return {"status": "ok", **model_catalog()}


@router.get("/api/produce/samples")
async def produce_samples():
    return {
        "status": "ok",
        "samples": produce_ops.SAMPLE_BRIEFS,
        "presets": produce_ops.SOCIAL_PRESETS,
    }


@router.get("/api/produce/elements")
async def produce_elements_list():
    return {"status": "ok", "elements": produce_elements.load_elements()}


@router.post("/api/produce/elements")
async def produce_elements_add(
    file: UploadFile = File(...),
    kind: str = Form("character"),
    label: str = Form(""),
):
    data = await file.read()
    item = produce_elements.add_element(kind, file.filename or "upload.bin", data, label=label)
    return {"status": "ok", "element": item, "elements": produce_elements.load_elements()}


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


@router.post("/api/produce/{job_id}/shots")
async def produce_add_shot(job_id: str, req: ProduceShotAddRequest):
    path = _job_or_404(job_id)
    shot = produce_ops.add_shot(path, purpose=req.purpose, visual=req.visual)
    return {"status": "ok", "shot": shot, **_service.snapshot(job_id)}


@router.delete("/api/produce/{job_id}/shots/{shot_id}")
async def produce_delete_shot(job_id: str, shot_id: str):
    path = _job_or_404(job_id)
    produce_ops.delete_shot(path, shot_id)
    return {"status": "ok", **_service.snapshot(job_id)}


@router.get("/api/produce/{job_id}/comments")
async def produce_comments(job_id: str):
    path = _job_or_404(job_id)
    return {"status": "ok", "comments": produce_ops.load_comments(path)}


@router.post("/api/produce/{job_id}/comments")
async def produce_add_comment(job_id: str, req: ProduceCommentRequest):
    path = _job_or_404(job_id)
    try:
        row = produce_ops.add_comment(path, req.text, shot_id=req.shot_id, author=req.author)
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", "comment": row, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/duplicate")
async def produce_duplicate(job_id: str):
    import time
    import uuid

    src = _job_or_404(job_id)
    new_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    dest = _service.job_dir(new_id)
    produce_ops.duplicate_job(src, dest)
    return {"status": "ok", **_service.snapshot(new_id)}


@router.post("/api/produce/{job_id}/rename")
async def produce_rename(job_id: str, req: ProduceRenameRequest):
    path = _job_or_404(job_id)
    title = produce_ops.rename_job(path, req.title)
    return {"status": "ok", "title": title, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/captions")
async def produce_captions(job_id: str):
    path = _job_or_404(job_id)
    dest = produce_ops.write_captions(path)
    return {"status": "ok", "captions": dest.name, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/review")
async def produce_review(job_id: str, req: ProduceReviewRequest):
    path = _job_or_404(job_id)
    try:
        row = produce_desk.review_shot(path, req.shot_id or "", req.decision, note=req.note)
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", "review": row, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/ab")
async def produce_ab(job_id: str, req: ProduceAbRequest):
    path = _job_or_404(job_id)
    row = produce_desk.compare_takes(
        path, req.shot_id, req.take_a, req.take_b, winner=req.winner, note=req.note
    )
    return {"status": "ok", "ab": row, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/enhance")
async def produce_enhance(job_id: str, req: ProduceShotRequest):
    path = _job_or_404(job_id)
    try:
        shot = produce_desk.enhance_shot(path, req.shot_id)
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", "shot": shot, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/shots/{shot_id}/duplicate")
async def produce_duplicate_shot(job_id: str, shot_id: str):
    path = _job_or_404(job_id)
    try:
        shot = produce_desk.duplicate_shot(path, shot_id)
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", "shot": shot, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/grab-still")
async def produce_grab_still(job_id: str, req: ProduceGrabRequest):
    path = _job_or_404(job_id)
    result = produce_desk.grab_still(path, req.shot_id, time_sec=req.time_sec, as_last=req.as_last)
    if not result.get("ok"):
        raise CinesmithAPIError(result.get("error") or "grab_failed", status_code=400)
    return {"status": "ok", **result, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/cuts/restore")
async def produce_restore_cut(job_id: str, req: ProduceRestoreCutRequest):
    path = _job_or_404(job_id)
    result = produce_desk.restore_cut(path, req.file)
    if not result.get("ok"):
        raise CinesmithAPIError(result.get("error") or "restore_failed", status_code=400)
    return {"status": "ok", **result, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/render-board")
async def produce_render_board(job_id: str, req: ProduceShotRequest):
    path = _job_or_404(job_id)
    result = await produce_render.render_board(
        path,
        req.shot_id,
        workflow_id=req.workflow_id,
        wait=req.wait,
        host=req.host,
    )
    if result.get("status") == "error":
        raise CinesmithAPIError(result.get("error") or "render_board_failed", status_code=400)
    return {"status": "ok", **result, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/render-take")
async def produce_render_take(job_id: str, req: ProduceShotRequest):
    path = _job_or_404(job_id)
    result = await produce_render.render_take(
        path, req.shot_id, mode=req.mode, wait=req.wait, host=req.host
    )
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


@router.put("/api/produce/{job_id}/mode")
async def produce_set_mode(job_id: str, req: ProduceModeRequest):
    path = _job_or_404(job_id)
    produce_render.set_produce_mode(path, req.produce_mode)
    return {"status": "ok", **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/render-boards")
async def produce_render_boards(job_id: str, req: Optional[ProduceShotRequest] = None):
    path = _job_or_404(job_id)
    ids = (req.shot_ids if req and req.shot_ids else None) or None
    results = await produce_render.render_boards(
        path,
        ids,
        workflow_id=(req.workflow_id if req else "") or "",
        wait=bool(req.wait) if req else False,
    )
    return {"status": "ok", "results": results, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/queue")
async def produce_queue_add(job_id: str, req: ProduceQueueItemRequest):
    path = _job_or_404(job_id)
    try:
        item = produce_queue.enqueue(
            path,
            req.action,
            shot_id=req.shot_id,
            mode=req.mode,
            workflow_id=req.workflow_id,
            host=req.host,
            start_sec=req.start_sec,
            end_sec=req.end_sec,
        )
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", "item": item, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/queue/plan")
async def produce_queue_plan(job_id: str):
    path = _job_or_404(job_id)
    added = produce_queue.enqueue_plan(path)
    return {"status": "ok", "added": added, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/queue/run")
async def produce_queue_run(job_id: str, req: Optional[ProduceQueueRunRequest] = None):
    path = _job_or_404(job_id)
    results = await produce_queue.drain_pending(path, max_items=(req.max_items if req else 8))
    return {"status": "ok", "results": results, **_service.snapshot(job_id)}


@router.put("/api/produce/{job_id}/shots/{shot_id}")
async def produce_patch_shot(job_id: str, shot_id: str, req: ProduceShotPatch):
    path = _job_or_404(job_id)
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    produce_render.patch_shot(path, shot_id, fields)
    return {"status": "ok", **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/range-retake")
async def produce_range_retake(job_id: str, req: ProduceRangeRequest):
    path = _job_or_404(job_id)
    result = await produce_render.range_retake(
        path, req.shot_id, req.start_sec, req.end_sec, wait=req.wait
    )
    if result.get("status") == "error":
        raise CinesmithAPIError(result.get("error") or "range_retake_failed", status_code=400)
    return {"status": "ok", **result, **_service.snapshot(job_id)}


@router.put("/api/produce/{job_id}/options")
async def produce_options(job_id: str, req: ProduceOptionsRequest):
    path = _job_or_404(job_id)
    meta: Dict[str, Any] = {}
    if req.produce_mode:
        produce_render.set_produce_mode(path, req.produce_mode)
    if req.color_pass is not None:
        meta["color_pass"] = bool(req.color_pass)
    if req.stills_model or req.video_model:
        produce_render.set_model_options(path, stills=req.stills_model, video=req.video_model)
    if req.title:
        produce_ops.rename_job(path, req.title)
    if req.aspect:
        meta["aspect"] = str(req.aspect).strip()
    if req.fade_sec is not None:
        try:
            meta["fade_sec"] = max(0.0, min(3.0, float(req.fade_sec)))
        except (TypeError, ValueError):
            pass
    if req.transition:
        key = str(req.transition).strip().lower()
        meta["transition"] = "crossfade" if key in {"crossfade", "dissolve", "fade"} else "cut"
    if meta:
        produce_render.save_job_meta(path, meta)
    return {"status": "ok", **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/elements/attach")
async def produce_attach_elements(job_id: str, req: ProduceAttachRequest):
    path = _job_or_404(job_id)
    copied = produce_elements.attach_to_job(path, req.ids)
    if copied:
        produce_desk.refresh_identity_pack(path)
    return {"status": "ok", "copied": copied, **_service.snapshot(job_id)}


@router.post("/api/produce/{job_id}/takes/restore")
async def produce_restore_take(job_id: str, req: ProduceRestoreTakeRequest):
    path = _job_or_404(job_id)
    result = produce_render.restore_take(path, req.shot_id, req.clip)
    if not result.get("ok"):
        raise CinesmithAPIError(result.get("error") or "restore_failed", status_code=400)
    return {"status": "ok", **result, **_service.snapshot(job_id)}


@router.get("/api/produce/{job_id}/export")
async def produce_export(job_id: str):
    path = _job_or_404(job_id)
    produce_render.export_package(path)
    dest = path / "handoff.zip"
    if not dest.exists():
        raise CinesmithAPIError("export_failed", status_code=400)
    return FileResponse(str(dest), filename=f"{job_id}-handoff.zip")


@router.post("/api/produce/{job_id}/upload")
async def produce_upload(
    job_id: str,
    file: UploadFile = File(...),
    kind: str = Form("identity"),
    shot_id: str = Form(""),
):
    path = _job_or_404(job_id)
    data = await file.read()
    saved = produce_render.save_upload(path, kind=kind, filename=file.filename or "upload.bin", data=data)
    if shot_id and saved.get("path"):
        field = {"still": "still", "end_still": "end_still", "voice": "voice_ref"}.get(kind)
        if field:
            produce_render.patch_shot(path, shot_id, {field: saved["path"]})
        elif kind == "guide":
            shot = produce_render.get_shot(path, shot_id) or {}
            guides = list(shot.get("guides") or [])
            guides.append({"frame_idx": 48, "image": saved["path"]})
            produce_render.patch_shot(path, shot_id, {"guides": guides})
    if str(kind or "").strip().lower() in {"identity", "voice", "score"}:
        produce_desk.refresh_identity_pack(path)
    return {"status": "ok", **saved, **_service.snapshot(job_id)}


@router.get("/api/produce/{job_id}/file/{name:path}")
async def produce_file(job_id: str, name: str):
    path = _job_or_404(job_id)
    target = (path / name).resolve()
    if path.resolve() not in target.parents and target != path.resolve():
        raise CinesmithAPIError("file not found", status_code=404)
    if not target.exists() or not target.is_file():
        raise CinesmithAPIError("file not found", status_code=404)
    return FileResponse(str(target))
