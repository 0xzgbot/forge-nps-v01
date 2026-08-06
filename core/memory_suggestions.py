"""Memory-driven prompt / story suggestions from episodic events + recent projects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.cinesmith_env import repo_root
from core.script_projects import list_script_projects


def _read_events(limit: int = 80) -> List[Dict[str, Any]]:
    path = repo_root() / "data" / "hermes_memory" / "episodic" / "events.jsonl"
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def build_suggestions(
    *,
    brief: str = "",
    mode: str = "auto",
    limit: int = 6,
) -> Dict[str, Any]:
    """Return actionable suggestions for images, story, or video workflows."""
    brief_l = (brief or "").lower()
    events = _read_events()
    projects = list_script_projects()

    suggestions: List[Dict[str, Any]] = []

    # From recent failures / remediations + J4 durable failure summaries
    fail_n = 0
    remed_n = 0
    for ev in events:
        et = str(ev.get("type") or ev.get("event_type") or "").lower()
        msg = str(ev.get("message") or ev.get("text") or "")
        if "fail" in et or "error" in et or "fail" in msg.lower():
            fail_n += 1
        if "remed" in et or "retry" in et:
            remed_n += 1
    try:
        from core.hermes.memory.failure_auto_consolidate import get_status as _fail_status, latest_hermes_hint

        fail_status = _fail_status()
        hint = latest_hermes_hint()
        if hint:
            suggestions.append(
                {
                    "id": "mem_failure_summary",
                    "kind": "quality",
                    "title": "Learned from recent failures",
                    "body": hint,
                    "action": "images",
                }
            )
        elif int(fail_status.get("failure_count_since_consolidate") or 0) >= 1:
            remaining = fail_status.get("remaining_until_consolidate")
            suggestions.append(
                {
                    "id": "mem_failure_building",
                    "kind": "quality",
                    "title": "Failures tracking toward memory",
                    "body": (
                        f"{fail_status.get('failure_count_since_consolidate')} failure(s) logged; "
                        f"auto-summary after {fail_status.get('threshold')} "
                        f"({remaining} remaining)."
                    ),
                    "action": "settings",
                }
            )
    except Exception:
        pass
    if fail_n >= 2 and "mem_failure_summary" not in {s["id"] for s in suggestions}:
        suggestions.append(
            {
                "id": "mem_remediation",
                "kind": "quality",
                "title": "Hermes saw recent failures",
                "body": f"Memory shows ~{fail_n} failure signals. Prefer Flux2.Dev (not Turbo) and Series Continuity so Hermes can hold people/product locks.",
                "action": "images",
            }
        )
    if remed_n:
        suggestions.append(
            {
                "id": "mem_retry_lineage",
                "kind": "quality",
                "title": "Remediate, don’t restart",
                "body": "Hermes already improved weak frames via retries. Audit fails and remediate low scores instead of regenerating the whole campaign.",
                "action": "images",
            }
        )

    # From recent story projects
    if projects:
        latest = projects[0]
        suggestions.append(
            {
                "id": "mem_resume_story",
                "kind": "story",
                "title": f"Resume story: {latest.get('title') or latest.get('script_id')}",
                "body": f"Last story project has {latest.get('video_complete_count') or 0}/"
                        f"{latest.get('video_shot_count') or 0} clips done. Open Stories to continue or export.",
                "action": "script",
                "script_id": latest.get("script_id"),
            }
        )

    # Brief-aware tips
    if any(k in brief_l for k in ("tiktok", "vertical", "9:16", "reel", "short")):
        suggestions.append(
            {
                "id": "tip_tiktok",
                "kind": "platform",
                "title": "Vertical short detected",
                "body": "Force TikTok 9:16 platform skill, target 8–12 stills or a Story starter, keep caption-safe bottom third, hook in first frame.",
                "action": "images",
            }
        )
    if any(k in brief_l for k in ("character", "person", "girl", "man", "woman", "actor")):
        suggestions.append(
            {
                "id": "tip_character",
                "kind": "continuity",
                "title": "Lock character identity",
                "body": "Create/select a Character first, send to Cinesmith, then generate. For multi-shot stories, attach references in Asset Vault.",
                "action": "characters",
            }
        )
    if any(k in brief_l for k in ("product", "earbuds", "bottle", "packaging", "brand")):
        suggestions.append(
            {
                "id": "tip_product",
                "kind": "continuity",
                "title": "Package product references",
                "body": "Use Assets → New Package with hero product photos before Script Studio or campaign stills.",
                "action": "assets",
            }
        )
    if any(k in brief_l for k in ("story", "film", "scene", "episode", "script", "narrative")):
        suggestions.append(
            {
                "id": "tip_story",
                "kind": "workflow",
                "title": "Multi-beat story",
                "body": "Open Stories, load a story brief, and produce with Hermes — narrative package, frames, and clips as agency work, then export the package.",
                "action": "script",
            }
        )

    # Always-useful defaults if sparse
    defaults = [
        {
            "id": "tip_preset",
            "kind": "workflow",
            "title": "Brief like an EP",
            "body": "On Agency, write outcome + count + format, then run a live image campaign. Hermes plans and renders in real time.",
            "action": "create",
        },
        {
            "id": "tip_export",
            "kind": "delivery",
            "title": "Export deliverables",
            "body": "When story clips finish, export a ZIP (manifest, captions, frames, videos, audio honesty) for edit handoff.",
            "action": "script",
        },
        {
            "id": "tip_readiness",
            "kind": "ops",
            "title": "Stack before spend",
            "body": "Hermes isolated + Spark online in the sidebar before large campaigns. Fix Settings if chips are red/amber.",
            "action": "settings",
        },
    ]
    for d in defaults:
        if len(suggestions) >= limit:
            break
        if d["id"] not in {s["id"] for s in suggestions}:
            suggestions.append(d)

    # mode filter
    if mode in {"images", "script", "video"}:
        filtered = [s for s in suggestions if s.get("action") in {mode, "create", "settings", "quality", "continuity", "platform", "workflow", "delivery", "ops", "characters", "assets"}]
        if filtered:
            suggestions = filtered

    return {
        "status": "ok",
        "count": len(suggestions[:limit]),
        "suggestions": suggestions[:limit],
        "memory_events_scanned": len(events),
        "recent_projects": len(projects),
    }
