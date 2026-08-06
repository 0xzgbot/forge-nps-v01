"""Export a Script Studio project as a portable story package ZIP."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.media_probe import probe_media, resolve_media_path
from core.script_projects import load_script_project, now_iso, safe_script_id


def _captions_from_project(project: Dict[str, Any]) -> str:
    lines: List[str] = []
    title = project.get("title") or project.get("script_id") or "Story"
    lines.append(f"# {title}")
    brief = str(project.get("brief") or "").strip()
    if brief:
        lines.append("")
        lines.append("## Brief")
        lines.append(brief)
    package = project.get("package") if isinstance(project.get("package"), dict) else {}
    logline = str(package.get("logline") or package.get("synopsis") or "").strip()
    if logline:
        lines.append("")
        lines.append("## Logline")
        lines.append(logline)

    video_shots = project.get("video_shots") if isinstance(project.get("video_shots"), list) else []
    if video_shots:
        lines.append("")
        lines.append("## Shots")
        for i, shot in enumerate(video_shots, 1):
            if not isinstance(shot, dict):
                continue
            sid = shot.get("shot_id") or shot.get("id") or f"shot_{i}"
            prompt = str(shot.get("video_prompt") or shot.get("prompt") or shot.get("caption") or "").strip()
            lines.append(f"{i}. [{sid}] {prompt[:300]}")
    return "\n".join(lines).strip() + "\n"


def _collect_frame_urls(project: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Return list of (label, url_or_path) for start frames."""
    out: List[Tuple[str, str]] = []
    panel_jobs = project.get("storyboard_panel_jobs") if isinstance(project.get("storyboard_panel_jobs"), dict) else {}
    for board_id, items in panel_jobs.items():
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or item.get("image_url") or item.get("path") or "").strip()
            if url:
                out.append((f"frame_b{board_id}_{idx+1:02d}", url))
    # also from video shots
    for i, shot in enumerate(project.get("video_shots") or []):
        if not isinstance(shot, dict):
            continue
        url = str(shot.get("image_url") or shot.get("start_frame_url") or shot.get("frame_url") or "").strip()
        if url:
            out.append((f"start_{(shot.get('shot_id') or i+1)}", url))
    return out


def _collect_video_urls(project: Dict[str, Any]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    for i, shot in enumerate(project.get("video_shots") or []):
        if not isinstance(shot, dict):
            continue
        url = str(shot.get("video_url") or shot.get("video_path") or shot.get("path") or "").strip()
        if url:
            label = str(shot.get("shot_id") or shot.get("id") or f"clip_{i+1}")
            out.append((label, url))
    return out


def build_story_package_zip(
    script_id: str,
    *,
    media_root: Path,
    repo_root: Path,
    dest_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Write a story package ZIP and return metadata."""
    project = load_script_project(script_id, root=repo_root)
    sid = safe_script_id(str(project.get("script_id") or script_id))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest_dir = dest_dir or (Path(media_root) / "exports" / "stories")
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"{sid}__story_package_{stamp}.zip"

    manifest: Dict[str, Any] = {
        "format": "cinesmith_story_package_v1",
        "exported_at": now_iso(),
        "script_id": sid,
        "title": project.get("title") or sid,
        "brief": project.get("brief") or "",
        "files": {"frames": [], "videos": [], "docs": []},
        "audio_honesty": [],
        "counts": {
            "coverage": len(project.get("coverage_shots") or []),
            "storyboard_panels": 0,
            "video_shots": len(project.get("video_shots") or []),
        },
    }
    boards = (project.get("storyboard_plan") or {}).get("boards") if isinstance(project.get("storyboard_plan"), dict) else []
    if isinstance(boards, list):
        manifest["counts"]["storyboard_panels"] = sum(
            len(b.get("panels") or []) for b in boards if isinstance(b, dict)
        )

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Docs
        zf.writestr("README.md", _captions_from_project(project))
        manifest["files"]["docs"].append("README.md")
        zf.writestr("captions.txt", _captions_from_project(project))
        manifest["files"]["docs"].append("captions.txt")
        zf.writestr("project.json", json.dumps({k: v for k, v in project.items() if not str(k).startswith("_")}, indent=2, ensure_ascii=True))
        manifest["files"]["docs"].append("project.json")
        if project.get("package"):
            zf.writestr("script_package.json", json.dumps(project["package"], indent=2, ensure_ascii=True))
            manifest["files"]["docs"].append("script_package.json")
        if project.get("storyboard_plan"):
            zf.writestr("storyboard_plan.json", json.dumps(project["storyboard_plan"], indent=2, ensure_ascii=True))
            manifest["files"]["docs"].append("storyboard_plan.json")
        if project.get("coverage_shots"):
            zf.writestr("coverage_shots.json", json.dumps(project["coverage_shots"], indent=2, ensure_ascii=True))
            manifest["files"]["docs"].append("coverage_shots.json")
        if project.get("video_shots"):
            zf.writestr("video_shots.json", json.dumps(project["video_shots"], indent=2, ensure_ascii=True))
            manifest["files"]["docs"].append("video_shots.json")

        # Frames
        seen_frames = set()
        for label, url in _collect_frame_urls(project):
            path = resolve_media_path(url, media_root=media_root, repo_root=repo_root)
            if not path or not path.exists():
                continue
            key = str(path)
            if key in seen_frames:
                continue
            seen_frames.add(key)
            arc = f"frames/{label}{path.suffix.lower() or '.png'}"
            zf.write(path, arcname=arc)
            manifest["files"]["frames"].append(arc)

        # Videos + audio honesty
        seen_vids = set()
        for label, url in _collect_video_urls(project):
            path = resolve_media_path(url, media_root=media_root, repo_root=repo_root)
            if not path or not path.exists():
                continue
            key = str(path)
            if key in seen_vids:
                continue
            seen_vids.add(key)
            safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)[:60]
            arc = f"videos/{safe_label}{path.suffix.lower() or '.mp4'}"
            zf.write(path, arcname=arc)
            manifest["files"]["videos"].append(arc)
            probe = probe_media(path)
            manifest["audio_honesty"].append(
                {
                    "file": arc,
                    "has_audio": bool(probe.get("has_audio")),
                    "has_video": bool(probe.get("has_video")),
                    "duration_sec": probe.get("duration_sec"),
                    "video_codec": probe.get("video_codec"),
                    "audio_codec": probe.get("audio_codec"),
                    "error": probe.get("error"),
                }
            )

        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=True))

    return {
        "status": "ok",
        "script_id": sid,
        "zip_path": str(zip_path),
        "download_url": f"/media-assets/exports/stories/{zip_path.name}",
        "manifest": manifest,
        "frame_count": len(manifest["files"]["frames"]),
        "video_count": len(manifest["files"]["videos"]),
        "has_silent_clips": any(
            item.get("has_video") and not item.get("has_audio") for item in manifest["audio_honesty"]
        ),
    }
