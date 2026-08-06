"""Multi-episode series continuity helpers for Stories (E5).

Pure helpers — no FastAPI. Series identity lives on script project meta:
  series_id, series_title, episode_number, episode_title
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple


def slug_series_id(value: str = "", *, fallback: str = "") -> str:
    raw = re.sub(r"[^a-z0-9_\-]+", "_", str(value or "").strip().lower())
    raw = re.sub(r"_+", "_", raw).strip("_")
    if raw:
        return raw[:80]
    return (fallback or "")[:80]


def normalize_episode_number(value: Any, *, default: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, 9999))


def series_fields_from_payload(
    payload: Dict[str, Any],
    *,
    existing: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge series/episode fields from save payload + existing project meta."""
    existing = existing if isinstance(existing, dict) else {}

    series_title = str(
        payload.get("series_title")
        if payload.get("series_title") is not None
        else existing.get("series_title")
        or ""
    ).strip()
    series_id = str(
        payload.get("series_id")
        if payload.get("series_id") is not None
        else existing.get("series_id")
        or ""
    ).strip()
    series_id = slug_series_id(series_id or series_title)

    ep_raw = payload.get("episode_number")
    if ep_raw is None or str(ep_raw).strip() == "":
        ep_raw = existing.get("episode_number")
    # Only set episode_number when series is present or user sent a value.
    has_series = bool(series_id or series_title)
    episode_number: Optional[int]
    if has_series or (payload.get("episode_number") not in (None, "")):
        episode_number = normalize_episode_number(ep_raw, default=1 if has_series else 1)
    else:
        episode_number = None
        if existing.get("episode_number") not in (None, ""):
            try:
                episode_number = normalize_episode_number(existing.get("episode_number"))
            except Exception:
                episode_number = None

    episode_title = str(
        payload.get("episode_title")
        if payload.get("episode_title") is not None
        else existing.get("episode_title")
        or ""
    ).strip()

    out: Dict[str, Any] = {
        "series_id": series_id,
        "series_title": series_title or (series_id.replace("_", " ").title() if series_id else ""),
        "episode_title": episode_title,
    }
    if episode_number is not None and (has_series or episode_title or existing.get("episode_number")):
        out["episode_number"] = episode_number
    elif "episode_number" in existing and has_series:
        out["episode_number"] = normalize_episode_number(existing.get("episode_number"))
    else:
        out["episode_number"] = episode_number if has_series else int(existing.get("episode_number") or 0) or 0

    # Normalize: empty series clears episode bookkeeping for list filters.
    if not out["series_id"]:
        out["series_id"] = ""
        out["series_title"] = out["series_title"] if series_title else ""
        if not episode_title and not payload.get("episode_number"):
            out["episode_number"] = int(existing.get("episode_number") or 0) or 0
    return out


def format_episode_label(
    *,
    series_title: str = "",
    episode_number: Any = None,
    episode_title: str = "",
    project_title: str = "",
) -> str:
    parts: List[str] = []
    st = str(series_title or "").strip()
    if st:
        parts.append(st)
    try:
        ep = int(episode_number) if episode_number not in (None, "") else 0
    except (TypeError, ValueError):
        ep = 0
    if ep > 0:
        parts.append(f"Ep {ep}")
    et = str(episode_title or "").strip()
    if et:
        parts.append(et)
    elif project_title and project_title not in parts:
        if not st:
            parts.append(str(project_title))
    return " · ".join(parts) if parts else (project_title or "Untitled")


def group_projects_by_series(projects: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Return series groups for UI:
      [{series_id, series_title, episodes: [project_summary...], episode_count}]
    Unscoped projects (no series_id) get series_id "".
    Episodes sorted by episode_number then updated_at.
    """
    buckets: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for proj in projects:
        if not isinstance(proj, dict):
            continue
        sid = slug_series_id(str(proj.get("series_id") or ""))
        key = sid or "__standalone__"
        if key not in buckets:
            buckets[key] = {
                "series_id": sid,
                "series_title": str(proj.get("series_title") or "").strip()
                or (sid.replace("_", " ").title() if sid else "Standalone stories"),
                "episodes": [],
            }
            order.append(key)
        elif sid and not buckets[key].get("series_title"):
            buckets[key]["series_title"] = str(proj.get("series_title") or sid).strip()
        buckets[key]["episodes"].append(proj)

    groups: List[Dict[str, Any]] = []
    for key in order:
        g = buckets[key]
        eps = list(g["episodes"])

        def sort_key(p: Dict[str, Any]) -> Tuple[int, str]:
            try:
                n = int(p.get("episode_number") or 0)
            except (TypeError, ValueError):
                n = 0
            return (n, str(p.get("updated_at") or ""))

        eps.sort(key=sort_key)
        groups.append(
            {
                "series_id": g["series_id"],
                "series_title": g["series_title"],
                "episode_count": len(eps),
                "episodes": eps,
            }
        )
    # Series with ids first (by latest update), standalone last
    def group_sort(g: Dict[str, Any]) -> Tuple[int, str]:
        if not g.get("series_id"):
            return (1, "")
        latest = ""
        for e in g.get("episodes") or []:
            u = str(e.get("updated_at") or "")
            if u > latest:
                latest = u
        return (0, latest)

    groups.sort(key=group_sort, reverse=True)
    # reverse=True puts latest first but also flips standalone — re-order:
    series_groups = [g for g in groups if g.get("series_id")]
    standalone = [g for g in groups if not g.get("series_id")]
    series_groups.sort(
        key=lambda g: max((str(e.get("updated_at") or "") for e in g.get("episodes") or []), default=""),
        reverse=True,
    )
    return series_groups + standalone


def next_episode_number(projects: Sequence[Dict[str, Any]], series_id: str) -> int:
    sid = slug_series_id(series_id)
    if not sid:
        return 1
    max_ep = 0
    for p in projects:
        if not isinstance(p, dict):
            continue
        if slug_series_id(str(p.get("series_id") or "")) != sid:
            continue
        try:
            n = int(p.get("episode_number") or 0)
        except (TypeError, ValueError):
            n = 0
        if n > max_ep:
            max_ep = n
    return max_ep + 1


def draft_next_episode_meta(
    source: Dict[str, Any],
    *,
    all_projects: Sequence[Dict[str, Any]] = (),
    episode_title: str = "",
) -> Dict[str, Any]:
    """Build meta for a new episode carrying series continuity from source."""
    series_id = slug_series_id(str(source.get("series_id") or source.get("series_title") or ""))
    series_title = str(source.get("series_title") or "").strip() or series_id.replace("_", " ").title()
    if not series_id:
        # Promote single project into a series named after its title
        series_title = str(source.get("title") or "Series").strip() or "Series"
        series_id = slug_series_id(series_title, fallback="series")
    ep_n = next_episode_number(all_projects or [source], series_id)
    title_base = series_title or str(source.get("title") or "Story")
    ep_title = (episode_title or "").strip() or f"Episode {ep_n}"
    return {
        "series_id": series_id,
        "series_title": series_title,
        "episode_number": ep_n,
        "episode_title": ep_title,
        "title": f"{title_base} — {ep_title}",
        "tone": str(source.get("tone") or ""),
        "runtime_seconds": int(source.get("runtime_seconds") or 60),
        "target_scenes": int(source.get("target_scenes") or 4),
        "brief": str(source.get("brief") or ""),
        "status": "draft",
        # Continuity flags for Hermes / platform skills
        "series_continuity": True,
        "continues_from_script_id": str(source.get("script_id") or ""),
    }
