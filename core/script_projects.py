"""Script Studio project IO — shared by dashboard routes and export tools."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.cinesmith_env import repo_root


def script_projects_dir(root: Optional[Path] = None) -> Path:
    path = (root or repo_root()) / "data" / "scripts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_script_id(value: str = "", title: str = "") -> str:
    raw = (value or title or "script").strip().lower()
    raw = re.sub(r"[^a-z0-9_\-]+", "_", raw)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return (raw or "script")[:80]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json_file(path: Path, fallback: Any = None) -> Any:
    try:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def project_dir(script_id: str, root: Optional[Path] = None) -> Path:
    base = script_projects_dir(root)
    sid = safe_script_id(script_id)
    path = (base / sid).resolve()
    if not str(path).startswith(str(base.resolve())):
        raise ValueError("invalid script id")
    return path


def load_script_project(script_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    sid = safe_script_id(script_id)
    proj = project_dir(sid, root)
    meta = read_json_file(proj / "project.json", {})
    if not isinstance(meta, dict) or not meta:
        raise FileNotFoundError(f"script project not found: {sid}")
    package = read_json_file(proj / "script_package.json", None)
    coverage = read_json_file(proj / "coverage_shots.json", [])
    storyboard = read_json_file(proj / "storyboard_plan.json", None)
    panel_jobs = read_json_file(proj / "storyboard_panel_jobs.json", {})
    video_shots = read_json_file(proj / "video_shots.json", [])
    job = read_json_file(proj / "pipeline_job.json", None)
    return {
        **meta,
        "script_id": sid,
        "package": package if isinstance(package, dict) else None,
        "coverage_shots": coverage if isinstance(coverage, list) else [],
        "storyboard_plan": storyboard if isinstance(storyboard, dict) else None,
        "storyboard_panel_jobs": panel_jobs if isinstance(panel_jobs, dict) else {},
        "video_shots": video_shots if isinstance(video_shots, list) else [],
        "active_job": job if isinstance(job, dict) else None,
        "_project_path": str(proj),
    }


def list_script_projects(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    projects: List[Dict[str, Any]] = []
    for path in script_projects_dir(root).glob("*/project.json"):
        data = read_json_file(path, {})
        if isinstance(data, dict) and data.get("script_id"):
            projects.append(
                {
                    "script_id": data.get("script_id", ""),
                    "title": data.get("title", "") or "Untitled Script",
                    "brief": str(data.get("brief") or "")[:240],
                    "status": data.get("status", "draft"),
                    "updated_at": data.get("updated_at", ""),
                    "video_shot_count": int(data.get("video_shot_count") or 0),
                    "video_complete_count": int(data.get("video_complete_count") or 0),
                    "storyboard_count": int(data.get("storyboard_count") or 0),
                    "active_job_id": data.get("active_job_id", ""),
                }
            )
    projects.sort(key=lambda p: str(p.get("updated_at") or ""), reverse=True)
    return projects
