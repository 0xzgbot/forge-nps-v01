"""Bot routines = Hermes cron jobs namespaced `[bot:<name>]`."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def jobs_path(profile_dir: Path) -> Path:
    return profile_dir / "cron" / "jobs.json"


def list_routines(profile_dir: Path, name: str) -> List[Dict[str, Any]]:
    path = jobs_path(profile_dir)
    jobs = _load_jobs(path)
    prefix = f"[bot:{name}]"
    out = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        label = str(job.get("name") or "")
        if label.startswith(prefix) or not label:
            out.append(_public(job, name))
        elif job.get("cinesmith_bot") == name:
            out.append(_public(job, name))
    return out


def create_routine(
    profile_dir: Path,
    name: str,
    *,
    title: str,
    prompt: str,
    schedule: str,
) -> Dict[str, Any]:
    title_clean = (title or "").strip() or "routine"
    prompt_clean = (prompt or "").strip()
    if not prompt_clean:
        raise ValueError("routine prompt required")
    sched = (schedule or "").strip() or "every 1d"
    path = jobs_path(profile_dir)
    jobs = _load_jobs(path)
    job_id = uuid.uuid4().hex[:12]
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    job = {
        "id": job_id,
        "name": f"[bot:{name}] {title_clean}",
        "prompt": prompt_clean,
        "skills": [],
        "skill": None,
        "model": None,
        "provider": None,
        "schedule": {"kind": "display", "display": sched, "raw": sched},
        "schedule_display": sched,
        "repeat": {"times": None, "completed": 0},
        "enabled": True,
        "state": "scheduled",
        "created_at": now,
        "deliver": "bot-chat",
        "cinesmith_bot": name,
    }
    jobs.append(job)
    _save_jobs(path, jobs)
    return _public(job, name)


def delete_routine(profile_dir: Path, name: str, job_id: str) -> None:
    path = jobs_path(profile_dir)
    jobs = _load_jobs(path)
    kept = [j for j in jobs if not (isinstance(j, dict) and j.get("id") == job_id)]
    if len(kept) == len(jobs):
        raise FileNotFoundError(job_id)
    _save_jobs(path, kept)


def _public(job: Dict[str, Any], name: str) -> Dict[str, Any]:
    label = str(job.get("name") or "")
    prefix = f"[bot:{name}] "
    title = label[len(prefix) :] if label.startswith(prefix) else label
    return {
        "id": job.get("id"),
        "title": title,
        "name": label,
        "prompt": job.get("prompt") or "",
        "schedule": job.get("schedule_display") or "",
        "enabled": bool(job.get("enabled", True)),
        "state": job.get("state") or "",
        "last_run_at": job.get("last_run_at"),
    }


def _load_jobs(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [j for j in data if isinstance(j, dict)]
    if isinstance(data, dict):
        jobs = data.get("jobs", [])
        if isinstance(jobs, list):
            return [j for j in jobs if isinstance(j, dict)]
        if isinstance(jobs, dict):
            return [{**v, "id": v.get("id") or k} for k, v in jobs.items() if isinstance(v, dict)]
    return []


def _save_jobs(path: Path, jobs: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any]
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = None
        if isinstance(existing, dict):
            payload = dict(existing)
            payload["jobs"] = jobs
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return
    path.write_text(json.dumps({"jobs": jobs}, indent=2), encoding="utf-8")
