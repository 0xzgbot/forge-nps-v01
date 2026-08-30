"""Honest produce queue. Hermes writes items; a worker drains them.

GET snapshot never drains. Offline hosts stay pending (waiting_for_host),
never failed. This is not a stage machine — items are just file actions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.dispatch.capability_router import CapabilityRouter
from core.dispatch.workflows import capability_for_workflow, take_workflow_for_mode
from core.hermes.produce import render as produce_render

logger = logging.getLogger(__name__)

ACTIONS = ("render_board", "render_take", "assemble", "range_retake")
LIVE = {"pending", "waiting_for_host", "running"}
HOST_UNAVAILABLE = {"stills_host_unavailable", "spark_unavailable"}

QUEUE_FILE = "queue.json"


def _now() -> float:
    return time.time()


def _new_id(action: str, shot_id: str = "") -> str:
    tail = uuid.uuid4().hex[:8]
    shot = str(shot_id or "").strip() or "job"
    return f"q-{action}-{shot}-{tail}"


def load_queue(job_dir: Path) -> List[Dict[str, Any]]:
    target = Path(job_dir) / QUEUE_FILE
    if not target.exists():
        return []
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict) and isinstance(data.get("items"), list):
        raw = data["items"]
    else:
        return []
    items: List[Dict[str, Any]] = []
    for idx, row in enumerate(raw):
        if not isinstance(row, dict):
            continue
        items.append(_normalize(row, idx))
    return items


def save_queue(job_dir: Path, items: List[Dict[str, Any]]) -> None:
    Path(job_dir).mkdir(parents=True, exist_ok=True)
    payload = {"items": [_normalize(row, i) for i, row in enumerate(items) if isinstance(row, dict)]}
    (Path(job_dir) / QUEUE_FILE).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )


def _normalize(row: Dict[str, Any], idx: int = 0) -> Dict[str, Any]:
    action = str(row.get("action") or "").strip()
    shot_id = str(row.get("shot_id") or "").strip()
    status = str(row.get("status") or "pending").strip() or "pending"
    item = {
        "id": str(row.get("id") or "").strip() or _new_id(action or "item", shot_id or str(idx)),
        "action": action,
        "shot_id": shot_id,
        "mode": str(row.get("mode") or "").strip(),
        "workflow_id": str(row.get("workflow_id") or "").strip(),
        "status": status,
        "host": str(row.get("host") or "").strip(),
        "capability": str(row.get("capability") or "").strip() or _capability_for(action, row.get("workflow_id") or "", row.get("mode") or ""),
        "prompt_id": str(row.get("prompt_id") or "").strip(),
        "error": str(row.get("error") or ""),
        "created_at": row.get("created_at") or _now(),
        "updated_at": row.get("updated_at") or row.get("created_at") or _now(),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "start_sec": row.get("start_sec"),
        "end_sec": row.get("end_sec"),
    }
    return item


def _capability_for(action: str, workflow_id: str = "", mode: str = "") -> str:
    if action in {"assemble"}:
        return "local"
    if action == "render_board":
        return "stills"
    if workflow_id:
        return capability_for_workflow(workflow_id)
    if mode:
        return capability_for_workflow(take_workflow_for_mode(mode))
    return "spark"


def enqueue(
    job_dir: Path,
    action: str,
    *,
    shot_id: str = "",
    mode: str = "",
    workflow_id: str = "",
    host: str = "",
    capability: str = "",
    start_sec: Any = None,
    end_sec: Any = None,
) -> Dict[str, Any]:
    action = str(action or "").strip()
    if action not in ACTIONS:
        raise ValueError(f"unknown_queue_action:{action}")
    items = load_queue(job_dir)
    shot = str(shot_id or "").strip()
    for existing in items:
        if (
            existing.get("action") == action
            and str(existing.get("shot_id") or "") == shot
            and existing.get("status") in LIVE
        ):
            return existing
    item = _normalize(
        {
            "id": _new_id(action, shot),
            "action": action,
            "shot_id": shot,
            "mode": mode,
            "workflow_id": workflow_id,
            "status": "pending",
            "host": host,
            "capability": capability or _capability_for(action, workflow_id, mode),
            "start_sec": start_sec,
            "end_sec": end_sec,
            "created_at": _now(),
            "updated_at": _now(),
        }
    )
    items.append(item)
    save_queue(job_dir, items)
    return item


def enqueue_plan(job_dir: Path, *, router: Optional[CapabilityRouter] = None) -> List[Dict[str, Any]]:
    """Queue missing boards/takes from shots.json. Scout skips boards; takes are t2va."""
    job_dir = Path(job_dir)
    mode = produce_render.produce_mode(job_dir)
    shots = produce_render.load_shots(job_dir)
    hosts = (router or CapabilityRouter()).stills_hosts_configured()
    added: List[Dict[str, Any]] = []
    if mode == "shoot" or (mode == "scout" and not produce_render.family_supports_scout(produce_render.video_model(job_dir))):
        board_wf = produce_render.board_workflow_id(produce_render.stills_model(job_dir))
        for idx, shot in enumerate(shots):
            if shot.get("still"):
                continue
            host = hosts[idx % len(hosts)] if hosts else ""
            added.append(
                enqueue(
                    job_dir,
                    "render_board",
                    shot_id=str(shot.get("id") or ""),
                    host=host,
                    workflow_id=board_wf,
                )
            )
    for shot in shots:
        if shot.get("clip"):
            continue
        take_mode = produce_render.resolve_take_mode(job_dir, shot)
        added.append(
            enqueue(
                job_dir,
                "render_take",
                shot_id=str(shot.get("id") or ""),
                mode=take_mode,
                workflow_id=produce_render.workflow_for_take(produce_render.video_model(job_dir), take_mode),
            )
        )
    clips = produce_render.list_media(job_dir)["clips"]
    if clips and not (job_dir / "cut.mp4").exists():
        added.append(enqueue(job_dir, "assemble"))
    return added


def _update(job_dir: Path, item_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
    items = load_queue(job_dir)
    found = None
    for row in items:
        if row.get("id") == item_id:
            row.update(fields)
            row["updated_at"] = _now()
            found = row
            break
    if found is not None:
        save_queue(job_dir, items)
    return found


def retry_waiting(job_dir: Path) -> int:
    """Promote waiting_for_host → pending once per drain so we retry hosts."""
    items = load_queue(job_dir)
    n = 0
    for row in items:
        if row.get("status") == "waiting_for_host":
            row["status"] = "pending"
            row["updated_at"] = _now()
            n += 1
    if n:
        save_queue(job_dir, items)
    return n


def claim_next(job_dir: Path, *, action: str = "") -> Optional[Dict[str, Any]]:
    items = load_queue(job_dir)
    wanted = str(action or "").strip()
    for row in items:
        if row.get("status") != "pending":
            continue
        if wanted and row.get("action") != wanted:
            continue
        row["status"] = "running"
        row["started_at"] = _now()
        row["updated_at"] = _now()
        row["error"] = ""
        save_queue(job_dir, items)
        return row
    return None


def claim_many(job_dir: Path, *, action: str, limit: int) -> List[Dict[str, Any]]:
    claimed: List[Dict[str, Any]] = []
    for _ in range(max(0, int(limit))):
        item = claim_next(job_dir, action=action)
        if not item:
            break
        claimed.append(item)
    return claimed


def mark_waiting(job_dir: Path, item_id: str, *, host: str = "", error: str = "") -> Optional[Dict[str, Any]]:
    return _update(
        job_dir,
        item_id,
        status="waiting_for_host",
        host=host,
        error=error or "",
        started_at=None,
        finished_at=None,
    )


def mark_done(job_dir: Path, item_id: str, *, host: str = "", prompt_id: str = "") -> Optional[Dict[str, Any]]:
    return _update(
        job_dir,
        item_id,
        status="done",
        host=host,
        prompt_id=prompt_id,
        error="",
        finished_at=_now(),
    )


def mark_failed(job_dir: Path, item_id: str, *, error: str, host: str = "") -> Optional[Dict[str, Any]]:
    return _update(
        job_dir,
        item_id,
        status="failed",
        error=error,
        host=host,
        finished_at=_now(),
    )


async def _host_for_item(item: Dict[str, Any], router: CapabilityRouter) -> str:
    preferred = str(item.get("host") or "").strip()
    if preferred:
        probe = await router._probe(preferred)
        return preferred if probe.get("ok") else ""
    cap = str(item.get("capability") or "").strip()
    action = str(item.get("action") or "")
    if action == "assemble" or cap == "local":
        return "local"
    if action == "render_board" or cap == "stills":
        return await router.host_for("stills")
    workflow_id = str(item.get("workflow_id") or "")
    if workflow_id:
        return await router.host_for_workflow(workflow_id, require_h3="h3" in workflow_id)
    return await router.host_for("spark")


async def execute_item(
    job_dir: Path,
    item: Dict[str, Any],
    *,
    router: Optional[CapabilityRouter] = None,
) -> Dict[str, Any]:
    router = router or CapabilityRouter()
    action = str(item.get("action") or "")
    item_id = str(item.get("id") or "")
    if action == "assemble":
        result = produce_render.assemble_cut(job_dir)
        if result.get("ok"):
            mark_done(job_dir, item_id, host="local")
        else:
            mark_failed(job_dir, item_id, error=str(result.get("error") or "assemble_failed"), host="local")
        return {"item": load_item(job_dir, item_id), **result}

    host = await _host_for_item(item, router)
    if not host:
        waiting = mark_waiting(job_dir, item_id, host=str(item.get("host") or ""), error="")
        return {"status": "waiting_for_host", "item": waiting}

    if action == "render_board":
        result = await produce_render.render_board(
            job_dir,
            str(item.get("shot_id") or ""),
            workflow_id=str(item.get("workflow_id") or ""),
            wait=False,
            host=host,
        )
    elif action == "render_take":
        result = await produce_render.render_take(
            job_dir,
            str(item.get("shot_id") or ""),
            mode=str(item.get("mode") or ""),
            wait=False,
            host=host,
        )
    elif action == "range_retake":
        result = await produce_render.range_retake(
            job_dir,
            str(item.get("shot_id") or ""),
            float(item.get("start_sec") or 0),
            float(item.get("end_sec") or 0),
            wait=False,
        )
    else:
        mark_failed(job_dir, item_id, error=f"unknown_action:{action}")
        return {"status": "error", "error": f"unknown_action:{action}"}

    err = str(result.get("error") or "")
    used_host = str(result.get("host") or host)
    if result.get("waiting") or err in HOST_UNAVAILABLE:
        mark_waiting(job_dir, item_id, host=used_host, error="")
        return {"status": "waiting_for_host", "item": load_item(job_dir, item_id), **result}
    if result.get("status") == "error":
        mark_failed(job_dir, item_id, error=err or "render_failed", host=used_host)
        return {"status": "failed", "item": load_item(job_dir, item_id), **result}
    mark_done(job_dir, item_id, host=used_host, prompt_id=str(result.get("prompt_id") or ""))
    return {"status": "done", "item": load_item(job_dir, item_id), **result}


def load_item(job_dir: Path, item_id: str) -> Optional[Dict[str, Any]]:
    for row in load_queue(job_dir):
        if row.get("id") == item_id:
            return row
    return None


async def drain_pending(
    job_dir: Path,
    *,
    router: Optional[CapabilityRouter] = None,
    max_items: int = 8,
) -> List[Dict[str, Any]]:
    """Run queued work. Never called from GET snapshot.

    Boards fan out across configured 3090s. Takes/assemble run one at a time.
    Missing hosts leave items waiting_for_host.
    """
    router = router or CapabilityRouter()
    job_dir = Path(job_dir)
    retry_waiting(job_dir)
    results: List[Dict[str, Any]] = []
    remaining = max(1, int(max_items))

    board_limit = max(1, len(router.stills_hosts_configured()) or 1)
    boards = claim_many(job_dir, action="render_board", limit=min(board_limit, remaining))
    if boards:
        batch = await asyncio.gather(
            *[execute_item(job_dir, item, router=router) for item in boards],
            return_exceptions=True,
        )
        for item, outcome in zip(boards, batch):
            if isinstance(outcome, Exception):
                mark_failed(job_dir, str(item.get("id") or ""), error=str(outcome))
                results.append({"status": "failed", "error": str(outcome), "item": load_item(job_dir, str(item.get("id") or ""))})
            else:
                results.append(outcome)
        remaining -= len(boards)

    while remaining > 0:
        item = claim_next(job_dir)
        if not item:
            break
        try:
            results.append(await execute_item(job_dir, item, router=router))
        except Exception as exc:
            logger.exception("queue item failed")
            mark_failed(job_dir, str(item.get("id") or ""), error=str(exc))
            results.append({"status": "failed", "error": str(exc), "item": load_item(job_dir, str(item.get("id") or ""))})
        remaining -= 1
    return results


def queue_eta_sec(items: Optional[List[Dict[str, Any]]] = None) -> int:
    """Rough remaining work in seconds. Does not probe GPUs."""
    eta = 0
    for row in items or []:
        status = str(row.get("status") or "")
        if status not in LIVE:
            continue
        action = str(row.get("action") or "")
        if action == "render_board":
            eta += 25
        elif action in {"render_take", "range_retake"}:
            eta += 90
        else:
            eta += 8
    return eta
