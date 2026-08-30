"""Hermes Bot Mode surfaces: roster, chat, hide, routines, group room."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from core.hermes.bots.routines import create_routine, delete_routine
from core.hermes.bots.runtime import BotRuntime
from core.hermes.bots.store import BotStore
from dashboard.errors import CinesmithAPIError

router = APIRouter(tags=["bots"])
_store = BotStore()
_runtime = BotRuntime(store=_store)


class ChatRequest(BaseModel):
    message: str = ""
    job_id: str = ""


class HideRequest(BaseModel):
    hidden: bool = True


class SoulRequest(BaseModel):
    soul: str = ""


class CreateBotRequest(BaseModel):
    name: str = ""
    title: str = ""
    description: str = ""
    soul: str = ""
    clone_from: str = ""


class RoutineRequest(BaseModel):
    title: str = ""
    prompt: str = ""
    schedule: str = "every 1d"


class GroupRequest(BaseModel):
    message: str = ""
    members: Optional[List[str]] = None
    job_id: str = ""


@router.get("/api/bots")
async def list_bots(hidden: bool = False):
    _store.ensure_crew()
    roster = _store.list_roster(include_hidden=hidden)
    running = _runtime.running()
    busy = {str(r.get("name")) for r in running}
    for row in roster:
        row["busy"] = row["name"] in busy
        row["active"] = row["active"] or row["busy"]
    return {
        "status": "ok",
        "bots": roster,
        "running": running,
        "active": _runtime.active_names(),
    }


@router.get("/api/crew/group")
async def crew_group():
    return {"status": "ok", "group": "crew", "messages": _runtime.read_group("crew")}


@router.post("/api/crew/group")
async def crew_group_send(req: GroupRequest):
    try:
        result = await _runtime.group_round(req.message, members=req.members, job_id=req.job_id)
    except (ValueError, RuntimeError) as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", **result}


@router.get("/api/bots/{name}")
async def get_bot(name: str):
    try:
        row = _store.get(name)
    except FileNotFoundError as exc:
        raise CinesmithAPIError("bot not found", status_code=404) from exc
    row["busy"] = any(r.get("name") == name for r in _runtime.running())
    return {"status": "ok", **row}


@router.post("/api/bots")
async def create_bot(req: CreateBotRequest):
    try:
        row = _store.create_bot(
            req.name,
            title=req.title,
            description=req.description,
            soul=req.soul,
            clone_from=req.clone_from,
        )
    except FileExistsError as exc:
        raise CinesmithAPIError("bot already exists", status_code=409) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", **row}


@router.delete("/api/bots/{name}")
async def delete_bot(name: str):
    try:
        _store.delete_bot(name)
    except FileNotFoundError as exc:
        raise CinesmithAPIError("bot not found", status_code=404) from exc
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok"}


@router.post("/api/bots/{name}/hide")
async def hide_bot(name: str, req: HideRequest):
    try:
        row = _store.set_hidden(name, req.hidden)
    except FileNotFoundError as exc:
        raise CinesmithAPIError("bot not found", status_code=404) from exc
    return {"status": "ok", **row}


@router.put("/api/bots/{name}/soul")
async def write_soul(name: str, req: SoulRequest):
    try:
        _store.write_soul(name, req.soul)
    except FileNotFoundError as exc:
        raise CinesmithAPIError("bot not found", status_code=404) from exc
    return {"status": "ok", "soul": _store.read_soul(name)}


@router.post("/api/bots/{name}/chat")
async def chat_bot(name: str, req: ChatRequest):
    try:
        result = await _runtime.mention_or_send(name, req.message, job_id=req.job_id)
    except FileNotFoundError as exc:
        raise CinesmithAPIError("bot not found", status_code=404) from exc
    except (ValueError, RuntimeError) as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", **result}


@router.get("/api/bots/{name}/routines")
async def list_bot_routines(name: str):
    if not _store.profile_dir(name).is_dir():
        raise CinesmithAPIError("bot not found", status_code=404)
    return {"status": "ok", "routines": _store.list_routines(name)}


@router.post("/api/bots/{name}/routines")
async def create_bot_routine(name: str, req: RoutineRequest):
    if not _store.profile_dir(name).is_dir():
        raise CinesmithAPIError("bot not found", status_code=404)
    try:
        row = create_routine(
            _store.profile_dir(name),
            name,
            title=req.title,
            prompt=req.prompt,
            schedule=req.schedule,
        )
    except ValueError as exc:
        raise CinesmithAPIError(str(exc), status_code=400) from exc
    return {"status": "ok", **row}


@router.delete("/api/bots/{name}/routines/{job_id}")
async def delete_bot_routine(name: str, job_id: str):
    try:
        delete_routine(_store.profile_dir(name), name, job_id)
    except FileNotFoundError as exc:
        raise CinesmithAPIError("routine not found", status_code=404) from exc
    return {"status": "ok"}


