"""Product-surface routes: export, media honesty, scorecard, wizard, create hub, suggestions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from core.consistency_scorecard import score_campaign_shots, score_story_consistency
from core.cinesmith_env import default_media_root, hermes_isolation_status, repo_root
from core.media_probe import probe_path_or_url
from core.memory_suggestions import build_suggestions
from core.script_projects import list_script_projects, load_script_project
from core.story_export import build_story_package_zip
from dashboard.errors import CinesmithAPIError

router = APIRouter()


class ProbeRequest(BaseModel):
    path: str = ""
    url: str = ""


class ScorecardRequest(BaseModel):
    script_id: str = ""
    shots: List[Dict[str, Any]] = Field(default_factory=list)


class SuggestionsRequest(BaseModel):
    brief: str = ""
    mode: str = "auto"
    limit: int = 6


class WizardSaveRequest(BaseModel):
    completed: bool = False
    step: str = ""
    notes: str = ""


def _media_root() -> Path:
    return Path(os.getenv("CINESMITH_MEDIA_ROOT") or default_media_root())


@router.get("/api/product/create-hub")
async def api_create_hub():
    """Unified Create hub payload: modes, presets, readiness snapshot, recent work."""
    isolation = hermes_isolation_status()
    projects = list_script_projects()[:5]
    return {
        "status": "ok",
        "product_model": "hermes_agency",
        "modes": [
            {
                "id": "images",
                "title": "Live image campaign",
                "subtitle": "Hermes plans, compiles, renders, and audits stills in real time",
                "page": "dashboard-view",
                "cta": "Run with Hermes",
            },
            {
                "id": "story",
                "title": "Story production",
                "subtitle": "Multi-beat narrative Hermes structures into frames and clips",
                "page": "script-view",
                "cta": "Open Stories",
            },
            {
                "id": "video",
                "title": "Stills → motion",
                "subtitle": "Direct control when you already have start frames",
                "page": "spark-view",
                "cta": "Open Videos",
            },
            {
                "id": "character",
                "title": "Character continuity",
                "subtitle": "Identity locks Hermes reuses across campaigns and stories",
                "page": "identity-view",
                "cta": "Open Characters",
            },
        ],
        "isolation_ok": bool(isolation.get("isolation_ok")),
        "hermes_home": isolation.get("hermes_home"),
        "recent_stories": projects,
        "tips": [
            "Brief Hermes like an executive producer — outcome, tone, count, format.",
            "Images = live agency campaign. Stories = multi-beat production Hermes orchestrates.",
            "Export a story package when clips finish. Sidebar chips should show Spark online first.",
            "Characters: one photo → Sheet from photo locks identity offline; multi-panel sheet when Spark is up.",
            "Videos: First → Last needs two stills (start, then end) for LTX pair motion.",
            "Stories: set Series + Episode for multi-episode continuity, then New episode in series.",
        ],
        "sample_briefs": [
            {
                "id": "neon-courier",
                "label": "Neon courier",
                "text": (
                    "8 cinematic stills of a courier on a rain-soaked rooftop at night, "
                    "neon cyan and magenta rim light, anamorphic bokeh, grounded wardrobe, no text no logos"
                ),
            },
            {
                "id": "travel-hook",
                "label": "Travel series",
                "text": (
                    "TikTok vertical 9:16 series — girl-next-door traveler finds a hidden coastal village "
                    "at golden hour, hook-first framing, caption-safe bottom third, soft pastel light, 3 beats"
                ),
            },
            {
                "id": "product-hero",
                "label": "Product hero",
                "text": (
                    "6 premium product stills of a matte black wireless earbud case on wet black stone, "
                    "soft studio key, specular highlights, luxury catalog lighting, no text"
                ),
            },
            {
                "id": "story-short",
                "label": "Short film",
                "text": (
                    "60-second restrained sci-fi short: lone radio operator on a foggy pier receives a signal "
                    "from the sea. 4 scenes, emotional close-ups, cool teal grade, no dialogue captions in frame"
                ),
            },
        ],
        "quick_path": [
            {"step": 1, "title": "Connect stack", "hint": "Settings → Spark URL · optional Director key"},
            {"step": 2, "title": "Sample brief", "hint": "Agency → sample chips → Run live image campaign"},
            {"step": 3, "title": "Lock continuity", "hint": "Characters → Sheet from photo"},
            {"step": 4, "title": "Motion + export", "hint": "Videos First→Last · Stories export package"},
        ],
    }


@router.post("/api/product/suggestions")
async def api_product_suggestions(req: SuggestionsRequest):
    return build_suggestions(brief=req.brief, mode=req.mode, limit=max(1, min(int(req.limit or 6), 12)))


@router.get("/api/product/suggestions")
async def api_product_suggestions_get(
    brief: str = "",
    mode: str = "auto",
    limit: int = Query(6, ge=1, le=12),
):
    return build_suggestions(brief=brief, mode=mode, limit=limit)


@router.post("/api/script/export-package")
async def api_export_story_package(script_id: str = Query(..., min_length=1)):
    try:
        result = build_story_package_zip(
            script_id,
            media_root=_media_root(),
            repo_root=repo_root(),
        )
        return result
    except FileNotFoundError as exc:
        raise CinesmithAPIError(
            str(exc),
            code="script_not_found",
            status_code=404,
            hint="Save or run a story project first.",
            recovery="Open Stories and select a project with frames or clips.",
        ) from exc
    except Exception as exc:
        raise CinesmithAPIError(
            f"Export failed: {exc}",
            code="export_failed",
            status_code=500,
            hint="Check that media files still exist on disk.",
            recovery="Re-render missing frames/clips, then export again.",
            details={"error": str(exc)[:300]},
        ) from exc


@router.get("/api/script/export-package/{script_id}/download")
async def api_download_story_package(script_id: str):
    """Re-export and stream the ZIP (fresh package each download)."""
    try:
        result = build_story_package_zip(
            script_id,
            media_root=_media_root(),
            repo_root=repo_root(),
        )
    except FileNotFoundError as exc:
        raise CinesmithAPIError(str(exc), code="script_not_found", status_code=404) from exc
    path = Path(result["zip_path"])
    if not path.exists():
        raise CinesmithAPIError("Export file missing after build", code="export_missing", status_code=500)
    return FileResponse(
        path,
        media_type="application/zip",
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/api/media/probe")
async def api_media_probe(req: ProbeRequest):
    target = (req.path or req.url or "").strip()
    if not target:
        raise CinesmithAPIError(
            "path or url required",
            code="missing_path",
            status_code=400,
            recovery="Pass a video_url or absolute path.",
        )
    probe = probe_path_or_url(target, media_root=_media_root(), repo_root=repo_root())
    honest = {
        **probe,
        "audio_label": (
            "has audio" if probe.get("has_audio")
            else ("silent (no audio stream)" if probe.get("has_video") else "unknown")
        ),
        "honest_summary": (
            f"{'Video' if probe.get('has_video') else 'Media'}"
            + (f" · {probe.get('duration_sec')}s" if probe.get("duration_sec") is not None else "")
            + (" · audio OK" if probe.get("has_audio") else " · NO AUDIO")
            + (f" · {probe.get('video_codec')}" if probe.get("video_codec") else "")
        ),
    }
    return {"status": "ok", "probe": honest}


@router.post("/api/product/scorecard")
async def api_product_scorecard(req: ScorecardRequest):
    if (req.script_id or "").strip():
        try:
            project = load_script_project(req.script_id.strip())
        except FileNotFoundError as exc:
            raise CinesmithAPIError(str(exc), code="script_not_found", status_code=404) from exc
        card = score_story_consistency(project)
        return {"status": "ok", "script_id": req.script_id, "scorecard": card}
    if req.shots:
        card = score_campaign_shots(req.shots)
        return {"status": "ok", "scorecard": card}
    raise CinesmithAPIError(
        "Provide script_id or shots[]",
        code="scorecard_input",
        status_code=400,
        recovery="Pass a story project id or a list of shot records.",
    )


@router.get("/api/product/scorecard/{script_id}")
async def api_product_scorecard_get(script_id: str):
    try:
        project = load_script_project(script_id)
    except FileNotFoundError as exc:
        raise CinesmithAPIError(str(exc), code="script_not_found", status_code=404) from exc
    return {"status": "ok", "script_id": script_id, "scorecard": score_story_consistency(project)}


@router.get("/api/product/wizard-state")
async def api_wizard_state():
    """First-run wizard progress stored under data/ (not browser-only)."""
    path = repo_root() / "data" / "first_run_wizard.json"
    if not path.exists():
        return {
            "status": "ok",
            "completed": False,
            "step": "welcome",
            "steps": _wizard_steps(),
        }
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    return {
        "status": "ok",
        "completed": bool(data.get("completed")),
        "step": data.get("step") or "welcome",
        "notes": data.get("notes") or "",
        "updated_at": data.get("updated_at"),
        "steps": _wizard_steps(),
    }


@router.post("/api/product/wizard-state")
async def api_wizard_save(req: WizardSaveRequest):
    from core.script_projects import now_iso, write_json_atomic

    path = repo_root() / "data" / "first_run_wizard.json"
    payload = {
        "completed": bool(req.completed),
        "step": req.step or ("done" if req.completed else "welcome"),
        "notes": req.notes or "",
        "updated_at": now_iso(),
    }
    write_json_atomic(path, payload)
    return {"status": "ok", **payload, "steps": _wizard_steps()}


def _wizard_steps() -> List[Dict[str, str]]:
    return [
        {"id": "welcome", "title": "Hermes agency", "body": "Cinesmith is Hermes-led production — real-time planning, render, audit, memory. Not a fixed script runner. Hermes stays in this repo’s hermes_home/ only."},
        {"id": "spark", "title": "Connect Spark", "body": "Set COMFYUI_PRIMARY in Settings and test render workers so Hermes can dispatch jobs."},
        {"id": "director", "title": "Connect Director", "body": "Add a Kimi/API key or enable local Director (LM Studio) for planning Hermes relies on."},
        {"id": "try", "title": "First run", "body": "On Agency, brief Hermes and run a live image campaign — or open Stories for multi-beat production."},
        {"id": "done", "title": "Agency online", "body": "Return to Agency anytime. Export story packages when multi-beat clips finish."},
    ]


@router.get("/api/product/queue-summary")
async def api_queue_summary():
    """Lightweight queue/progress summary for the Agency hub strip."""
    projects = list_script_projects()
    active = [p for p in projects if p.get("active_job_id")]
    incomplete = [
        p for p in projects
        if int(p.get("video_shot_count") or 0) > int(p.get("video_complete_count") or 0)
    ]
    return {
        "status": "ok",
        "active_story_jobs": len(active),
        "incomplete_stories": len(incomplete[:8]),
        "items": [
            {
                "script_id": p.get("script_id"),
                "title": p.get("title"),
                "video_complete_count": p.get("video_complete_count"),
                "video_shot_count": p.get("video_shot_count"),
                "active_job_id": p.get("active_job_id"),
                "progress_pct": (
                    int(100 * int(p.get("video_complete_count") or 0) / max(1, int(p.get("video_shot_count") or 0)))
                    if int(p.get("video_shot_count") or 0)
                    else 0
                ),
            }
            for p in (active + incomplete)[:10]
        ],
    }


class ReviewDecisionRequest(BaseModel):
    shot_id: str
    decision: str = "approved"  # approved | rejected | needs_changes
    note: str = ""
    remediate: bool = False
    max_retries: int = 1


@router.post("/api/product/review")
async def api_product_review(req: ReviewDecisionRequest):
    """Frame.io-style human review on a rendered shot.

    Approvals stick on the shot record. Rejects can optionally kick Hermes
    remediation so the agency retries with corrective prompts.
    """
    from dashboard import cinesmith_dashboard as d

    shot_id = (req.shot_id or "").strip()
    if not shot_id:
        raise CinesmithAPIError("shot_id required", code="missing_shot", status_code=400)
    decision = (req.decision or "").strip().lower()
    if decision not in {"approved", "rejected", "needs_changes"}:
        raise CinesmithAPIError(
            "decision must be approved, rejected, or needs_changes",
            code="invalid_decision",
            status_code=400,
        )

    shot = d._find_shot(shot_id)
    if not shot:
        # soft-create review-only record if media path known later
        raise CinesmithAPIError(
            f"shot not found: {shot_id}",
            code="shot_not_found",
            status_code=404,
            recovery="Refresh the gallery, then open the frame again.",
        )

    from core.script_projects import now_iso
    from pathlib import Path
    import json

    now = now_iso()
    shot["review_status"] = decision
    shot["review_note"] = (req.note or "").strip()
    shot["reviewed_at"] = now
    # keep audit_status compatible
    if decision == "approved":
        shot["client_status"] = "approved"
    elif decision == "rejected":
        shot["client_status"] = "rejected"
    else:
        shot["client_status"] = "needs_changes"

    # append review log
    root = Path(d.REPO_ROOT)
    log_path = root / "data" / "reviews" / "review_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": now,
        "shot_id": shot_id,
        "decision": decision,
        "note": shot.get("review_note") or "",
        "campaign_id": shot.get("campaign_id") or "",
        "image_url": shot.get("image_url") or "",
        "remediate": bool(req.remediate and decision in {"rejected", "needs_changes"}),
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    try:
        d._append_event(
            {
                "event_type": "human_review",
                "shot_id": shot_id,
                "decision": decision,
                "note": entry["note"],
                "timestamp": now,
            }
        )
    except Exception:
        pass

    remediation = None
    if req.remediate and decision in {"rejected", "needs_changes"}:
        try:
            service = d._make_audit_service()
            remediation = await service.remediate([shot_id], max_retries=max(1, int(req.max_retries or 1)))
        except Exception as exc:
            remediation = {"status": "error", "error": str(exc)[:300]}

    return {
        "status": "ok",
        "shot_id": shot_id,
        "decision": decision,
        "shot": {
            "id": shot.get("id") or shot_id,
            "shot_id": shot.get("shot_id") or shot_id,
            "review_status": shot.get("review_status"),
            "review_note": shot.get("review_note"),
            "reviewed_at": shot.get("reviewed_at"),
            "client_status": shot.get("client_status"),
            "image_url": shot.get("image_url"),
            "audit_status": shot.get("audit_status"),
        },
        "remediation": remediation,
    }


@router.get("/api/product/review/queue")
async def api_review_queue(limit: int = Query(40, ge=1, le=200)):
    """Shots awaiting human review (rendered, not approved)."""
    from dashboard import cinesmith_dashboard as d

    pending = []
    for s in list(getattr(d, "_SHOTS_STORE", []) or []):
        if not isinstance(s, dict):
            continue
        if not (s.get("image_url") or s.get("video_url")):
            continue
        rev = str(s.get("review_status") or s.get("client_status") or "").lower()
        if rev in {"approved", "rejected"}:
            continue
        pending.append(
            {
                "id": s.get("id") or s.get("shot_id"),
                "shot_id": s.get("shot_id") or s.get("id"),
                "campaign_id": s.get("campaign_id") or "",
                "image_url": s.get("image_url") or "",
                "video_url": s.get("video_url") or "",
                "audit_status": s.get("audit_status") or "",
                "audit_score": s.get("audit_score"),
                "prompt": str(s.get("prompt") or "")[:160],
                "review_status": rev or "pending",
            }
        )
    pending = pending[-limit:]
    approved = sum(
        1
        for s in (getattr(d, "_SHOTS_STORE", []) or [])
        if isinstance(s, dict) and str(s.get("review_status") or "").lower() == "approved"
    )
    rejected = sum(
        1
        for s in (getattr(d, "_SHOTS_STORE", []) or [])
        if isinstance(s, dict) and str(s.get("review_status") or "").lower() == "rejected"
    )
    return {
        "status": "ok",
        "pending_count": len(pending),
        "approved_count": approved,
        "rejected_count": rejected,
        "pending": list(reversed(pending)),
    }


@router.get("/api/product/cost-meter")
async def api_cost_meter():
    """G5 — estimated spend for cloud image APIs (OpenAI / Gemini)."""
    from core.cost_meter import get_summary

    return get_summary()


@router.post("/api/product/cost-meter/reset")
async def api_cost_meter_reset():
    from core.cost_meter import reset_meter

    return reset_meter()


@router.get("/api/product/failure-auto-consolidate")
async def api_failure_auto_status():
    """J4 — status of auto-consolidate after N campaign/story failures."""
    from core.hermes.memory.failure_auto_consolidate import get_status

    return get_status()


@router.post("/api/product/failure-auto-consolidate")
async def api_failure_auto_run(force: bool = Query(False)):
    """Trigger failure consolidation now (force=1) or note-only status."""
    from core.hermes.memory.failure_auto_consolidate import consolidate_failures, get_status

    if force:
        result = consolidate_failures(reason="manual_api")
        return {**get_status(), **result}
    # Without force, return status (idempotent POST for clients that only POST)
    return get_status()


@router.get("/api/product/agency-desk")
async def api_agency_desk():
    """High-level desk summary for Adobe-style agency home."""
    isolation = hermes_isolation_status()
    projects = list_script_projects()[:8]
    complete = sum(1 for p in projects if int(p.get("video_complete_count") or 0) > 0)
    return {
        "status": "ok",
        "product_model": "hermes_agency",
        "tagline": "Hermes-led virtual production agency",
        "desks": [
            {"id": "images", "title": "Stills desk", "blurb": "Live campaigns with plan → render → audit"},
            {"id": "stories", "title": "Story desk", "blurb": "Multi-beat narrative into frames and clips"},
            {"id": "motion", "title": "Motion desk", "blurb": "Image-to-video with duration and aspect control"},
            {"id": "continuity", "title": "Continuity desk", "blurb": "Characters, assets, scorecards, memory"},
        ],
        "stats": {
            "story_projects": len(projects),
            "projects_with_clips": complete,
            "hermes_isolated": bool(isolation.get("isolation_ok")),
        },
        "recent_stories": projects,
    }


class AbCompareRequest(BaseModel):
    shot_a_id: str
    shot_b_id: str
    winner_id: str = ""  # shot id of preferred frame; empty or "tie" = no preference
    note: str = ""
    campaign_id: str = ""


def _ab_compare_log_path() -> Path:
    return repo_root() / "data" / "reviews" / "ab_compare_log.jsonl"


def _append_ab_log(entry: Dict[str, Any]) -> None:
    import json

    path = _ab_compare_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _shot_summary(shot: Optional[Dict[str, Any]], shot_id: str) -> Dict[str, Any]:
    if not shot:
        return {"id": shot_id, "shot_id": shot_id, "found": False}
    return {
        "id": shot.get("id") or shot_id,
        "shot_id": shot.get("shot_id") or shot.get("id") or shot_id,
        "image_url": shot.get("image_url") or "",
        "video_url": shot.get("video_url") or "",
        "prompt": str(shot.get("prompt") or "")[:200],
        "campaign_id": shot.get("campaign_id") or "",
        "review_status": shot.get("review_status") or shot.get("client_status") or "",
        "ab_wins": int(shot.get("ab_wins") or 0),
        "ab_losses": int(shot.get("ab_losses") or 0),
        "ab_preference": shot.get("ab_preference") or "",
        "found": True,
    }


@router.post("/api/product/ab-compare")
async def api_ab_compare(req: AbCompareRequest):
    """Record a side-by-side A/B preference between two rendered frames.

    Winner is stored on both shot records (ab_preference / ab_wins / ab_losses)
    and appended to data/reviews/ab_compare_log.jsonl (+ review_log for audit trail).
    """
    from dashboard import cinesmith_dashboard as d
    from core.script_projects import now_iso
    import json

    a_id = (req.shot_a_id or "").strip()
    b_id = (req.shot_b_id or "").strip()
    if not a_id or not b_id:
        raise CinesmithAPIError(
            "shot_a_id and shot_b_id required",
            code="missing_shots",
            status_code=400,
            recovery="Select two frames from the gallery, then compare.",
        )
    if a_id == b_id:
        raise CinesmithAPIError(
            "Compare requires two different shots",
            code="same_shot",
            status_code=400,
            recovery="Pick a different frame for B.",
        )

    winner_raw = (req.winner_id or "").strip()
    if winner_raw.lower() in {"", "tie", "none", "draw"}:
        winner_id = ""
        result = "tie"
    elif winner_raw in {a_id, b_id}:
        winner_id = winner_raw
        result = "a" if winner_id == a_id else "b"
    else:
        raise CinesmithAPIError(
            "winner_id must be shot_a_id, shot_b_id, or empty/tie",
            code="invalid_winner",
            status_code=400,
        )

    shot_a = d._find_shot(a_id)
    shot_b = d._find_shot(b_id)
    if not shot_a and not shot_b:
        raise CinesmithAPIError(
            f"neither shot found: {a_id}, {b_id}",
            code="shot_not_found",
            status_code=404,
            recovery="Refresh the gallery, then open the frames again.",
        )

    now = now_iso()
    note = (req.note or "").strip()
    loser_id = ""
    if result == "a":
        loser_id = b_id
    elif result == "b":
        loser_id = a_id

    def _apply(shot: Optional[Dict[str, Any]], sid: str, role: str) -> None:
        if not shot:
            return
        shot["ab_last_compared_at"] = now
        shot["ab_last_opponent"] = b_id if role == "a" else a_id
        if result == "tie":
            shot["ab_preference"] = "tie"
            return
        if sid == winner_id:
            shot["ab_preference"] = "winner"
            shot["ab_wins"] = int(shot.get("ab_wins") or 0) + 1
            # soft client preference for handoff
            if str(shot.get("review_status") or "").lower() not in {"approved", "rejected"}:
                shot["client_status"] = shot.get("client_status") or "preferred"
        else:
            shot["ab_preference"] = "loser"
            shot["ab_losses"] = int(shot.get("ab_losses") or 0) + 1

    _apply(shot_a, a_id, "a")
    _apply(shot_b, b_id, "b")

    entry = {
        "timestamp": now,
        "type": "ab_compare",
        "shot_a_id": a_id,
        "shot_b_id": b_id,
        "winner_id": winner_id or None,
        "loser_id": loser_id or None,
        "result": result,
        "note": note,
        "campaign_id": (req.campaign_id or "").strip()
        or (shot_a or {}).get("campaign_id")
        or (shot_b or {}).get("campaign_id")
        or "",
        "image_a": (shot_a or {}).get("image_url") or "",
        "image_b": (shot_b or {}).get("image_url") or "",
    }
    _append_ab_log(entry)

    # also append a compact line to the shared review log
    try:
        root = Path(d.REPO_ROOT)
        log_path = root / "data" / "reviews" / "review_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": now,
                        "decision": "ab_compare",
                        "result": result,
                        "winner_id": winner_id or None,
                        "shot_a_id": a_id,
                        "shot_b_id": b_id,
                        "note": note,
                        "campaign_id": entry["campaign_id"],
                    }
                )
                + "\n"
            )
    except Exception:
        pass

    try:
        d._append_event(
            {
                "event_type": "ab_compare",
                "shot_a_id": a_id,
                "shot_b_id": b_id,
                "winner_id": winner_id or None,
                "result": result,
                "note": note,
                "timestamp": now,
            }
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "result": result,
        "winner_id": winner_id or None,
        "loser_id": loser_id or None,
        "shot_a": _shot_summary(shot_a, a_id),
        "shot_b": _shot_summary(shot_b, b_id),
        "entry": entry,
    }


@router.get("/api/product/ab-compare/recent")
async def api_ab_compare_recent(limit: int = Query(20, ge=1, le=100)):
    """Recent A/B comparison decisions from the jsonl log."""
    import json

    path = _ab_compare_log_path()
    if not path.exists():
        return {"status": "ok", "count": 0, "items": []}
    items: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                continue
            if len(items) >= limit:
                break
    except Exception as exc:
        raise CinesmithAPIError(
            f"Failed to read A/B log: {exc}",
            code="ab_log_read_failed",
            status_code=500,
        ) from exc
    return {"status": "ok", "count": len(items), "items": items}
