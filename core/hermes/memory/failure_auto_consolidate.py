"""J4 — Auto-consolidate episodic failure notes after N failed attempts.

After a configurable number of campaign/story failures (default 3), distill
recent failure events into a durable summary under data/hermes_memory/ so
Hermes can reuse the lessons. Never touches ~/.hermes.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("HermesFailureAutoConsolidate")

DEFAULT_THRESHOLD = 3
_FAILURE_EVENT_HINTS = (
    "fail",
    "error",
    "render_failure",
    "final_outcome",
    "outcome",
    "remediation_result",
    "render_result",
    "campaign_failed",
    "story_failed",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def memory_root(root: Optional[Path] = None) -> Path:
    base = (root or _repo_root()) / "data" / "hermes_memory"
    base.mkdir(parents=True, exist_ok=True)
    return base


def state_path(root: Optional[Path] = None) -> Path:
    return memory_root(root) / "failure_auto_state.json"


def summaries_path(root: Optional[Path] = None) -> Path:
    return memory_root(root) / "failure_summaries.json"


def episodic_log_path(root: Optional[Path] = None) -> Path:
    return memory_root(root) / "episodic" / "events.jsonl"


def get_threshold(override: Optional[int] = None) -> int:
    if override is not None:
        try:
            n = int(override)
            return max(1, n)
        except (TypeError, ValueError):
            pass
    for key in ("CINESMITH_FAILURE_CONSOLIDATE_N", "CINESMITH_AUTO_CONSOLIDATE_FAILURES"):
        raw = (os.getenv(key) or "").strip()
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                continue
    # Optional config.json key
    try:
        cfg_path = _repo_root() / "data" / "config.json"
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                for key in ("FAILURE_CONSOLIDATE_N", "CINESMITH_FAILURE_CONSOLIDATE_N"):
                    if key in cfg and str(cfg[key]).strip():
                        return max(1, int(cfg[key]))
    except Exception:
        pass
    return DEFAULT_THRESHOLD


def is_failure_event(event: Dict[str, Any]) -> bool:
    """True when an episodic/pipeline event represents a failed attempt."""
    if not isinstance(event, dict):
        return False
    if event.get("success") is False:
        return True
    et = str(event.get("event_type") or event.get("type") or "").lower()
    if "fail" in et or et.endswith("_error") or "error" in et:
        # avoid counting pure audit_error with success true
        if event.get("success") is True:
            return False
        return True
    msg = str(event.get("message") or event.get("reason") or event.get("text") or "").lower()
    if "fail" in msg and event.get("success") is not True:
        if any(h in et for h in _FAILURE_EVENT_HINTS) or not et:
            return True
    return False


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _now_iso() -> str:
    return datetime.now().isoformat()


def load_state(root: Optional[Path] = None) -> Dict[str, Any]:
    data = _load_json(state_path(root), {})
    if not isinstance(data, dict):
        data = {}
    return {
        "failure_count_since_consolidate": int(data.get("failure_count_since_consolidate") or 0),
        "total_failures_seen": int(data.get("total_failures_seen") or 0),
        "last_failure_at": data.get("last_failure_at") or None,
        "last_consolidate_at": data.get("last_consolidate_at") or None,
        "last_summary_id": data.get("last_summary_id") or None,
        "pending_event_ids": list(data.get("pending_event_ids") or []),
        "threshold": get_threshold(),
    }


def save_state(state: Dict[str, Any], root: Optional[Path] = None) -> None:
    payload = {
        "failure_count_since_consolidate": int(state.get("failure_count_since_consolidate") or 0),
        "total_failures_seen": int(state.get("total_failures_seen") or 0),
        "last_failure_at": state.get("last_failure_at"),
        "last_consolidate_at": state.get("last_consolidate_at"),
        "last_summary_id": state.get("last_summary_id"),
        "pending_event_ids": list(state.get("pending_event_ids") or [])[-40:],
        "updated_at": _now_iso(),
    }
    _save_json(state_path(root), payload)


def load_summaries(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    data = _load_json(summaries_path(root), {"summaries": []})
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("summaries") or [])
    return []


def save_summaries(summaries: List[Dict[str, Any]], root: Optional[Path] = None) -> None:
    _save_json(summaries_path(root), {"summaries": summaries, "updated_at": _now_iso()})


def _read_recent_events(root: Optional[Path] = None, limit: int = 120) -> List[Dict[str, Any]]:
    path = episodic_log_path(root)
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


def _collect_failure_notes(
    events: List[Dict[str, Any]],
    *,
    event_ids: Optional[List[str]] = None,
    max_events: int = 30,
) -> List[Dict[str, Any]]:
    wanted = set(event_ids or [])
    failures = [e for e in events if is_failure_event(e)]
    if wanted:
        matched = [e for e in failures if str(e.get("event_id") or "") in wanted]
        if matched:
            failures = matched
    return failures[-max_events:]


def _craft_lessons(failures: List[Dict[str, Any]]) -> Tuple[str, List[str], Dict[str, int], Dict[str, int]]:
    cats: Counter = Counter()
    kernels: Counter = Counter()
    reasons: Counter = Counter()
    for ev in failures:
        cat = str(ev.get("error_category") or ev.get("reason") or "general").strip() or "general"
        if cat.lower() in {"none", "null", ""}:
            cat = "general"
        cats[cat] += 1
        kid = str(ev.get("kernel_id") or ev.get("workflow_id") or "unknown").strip() or "unknown"
        kernels[kid] += 1
        reason = str(ev.get("reason") or ev.get("message") or ev.get("fix_applied") or cat).strip()
        if reason:
            reasons[reason[:120]] += 1

    lessons: List[str] = []
    top_cat = cats.most_common(3)
    top_ker = kernels.most_common(3)

    if top_cat:
        cat_bits = ", ".join(f"{c}×{n}" for c, n in top_cat)
        lessons.append(f"Recurring failure categories: {cat_bits}.")
    if top_ker:
        ker_bits = ", ".join(f"{k}×{n}" for k, n in top_ker)
        lessons.append(f"Kernels/workflows involved: {ker_bits}.")

    # Heuristic advice Hermes can reuse
    cat_keys = {c.lower() for c, _ in top_cat}
    if any(x in cat_keys for x in ("anatomy", "hands", "face", "identity", "continuity")):
        lessons.append("Prefer Flux2.Dev (not Turbo) and lock character references before regenerating.")
    if any(x in cat_keys for x in ("timeout", "oom", "queue", "comfy", "connection")):
        lessons.append("Check Spark/Comfy readiness; clear stuck queues before retrying large batches.")
    if any(x in cat_keys for x in ("audit", "score", "photometric", "lighting")):
        lessons.append("Remediate low-audit frames with corrective lighting/prompt fixes instead of full restarts.")
    if not lessons:
        lessons.append("Review recent failure reasons and simplify the brief/count before the next campaign.")

    rule = (
        f"After {len(failures)} failed campaign/story attempts "
        f"({', '.join(c for c, _ in top_cat) or 'general'}): "
        + " ".join(lessons[:3])
    )
    return rule, lessons, dict(cats), dict(kernels)


def consolidate_failures(
    *,
    root: Optional[Path] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    event_ids: Optional[List[str]] = None,
    reason: str = "threshold",
    write_semantic: bool = True,
) -> Dict[str, Any]:
    """Distill failure notes into durable summary + optional semantic insight."""
    all_events = events if events is not None else _read_recent_events(root, limit=150)
    failures = _collect_failure_notes(all_events, event_ids=event_ids)
    if not failures:
        return {
            "status": "noop",
            "reason": "no_failures",
            "summary": None,
            "insights": [],
        }

    rule, lessons, cats, kernels = _craft_lessons(failures)
    summary_id = f"fs_{uuid.uuid4().hex[:8]}"
    source_ids = [str(e.get("event_id") or "") for e in failures if e.get("event_id")][:12]
    summary: Dict[str, Any] = {
        "summary_id": summary_id,
        "created_at": _now_iso(),
        "trigger": reason,
        "failure_count": len(failures),
        "top_categories": cats,
        "top_kernels": kernels,
        "lessons": lessons,
        "rule": rule,
        "hermes_hint": lessons[0] if lessons else rule,
        "source_event_ids": source_ids,
        "sample_concepts": [
            str(e.get("concept") or e.get("prompt") or e.get("shot_id") or "")[:100]
            for e in failures[-5:]
            if (e.get("concept") or e.get("prompt") or e.get("shot_id"))
        ],
    }

    existing = load_summaries(root)
    existing.append(summary)
    # Keep last 50 summaries
    save_summaries(existing[-50:], root)

    insights: List[Dict[str, Any]] = []
    if write_semantic:
        try:
            from .semantic_memory import SemanticMemory

            semantic_dir = str(memory_root(root) / "semantic")
            semantic = SemanticMemory(memory_dir=semantic_dir)
            top_cat = next(iter(cats), "general")
            top_ker = next(iter(kernels), "any")
            insight_id = semantic.add_insight(
                rule=rule,
                confidence=min(0.9, 0.55 + 0.05 * min(len(failures), 6)),
                source_events=source_ids or [summary_id],
                applies_to={
                    "error_category": str(top_cat),
                    "kernel_id": str(top_ker),
                    "kind": "failure_auto_summary",
                },
                confirmations=len(failures),
            )
            insights.append({"insight_id": insight_id, "rule": rule})
        except Exception as exc:
            logger.warning("[FAILURE_AUTO] semantic write skipped: %s", exc)

    state = load_state(root)
    state["failure_count_since_consolidate"] = 0
    state["pending_event_ids"] = []
    state["last_consolidate_at"] = summary["created_at"]
    state["last_summary_id"] = summary_id
    save_state(state, root)

    logger.info(
        "[FAILURE_AUTO] Consolidated %s failures → %s",
        len(failures),
        summary_id,
    )
    return {
        "status": "consolidated",
        "reason": reason,
        "summary": summary,
        "insights": insights,
        "failure_count": len(failures),
    }


def note_failure(
    event: Optional[Dict[str, Any]] = None,
    *,
    root: Optional[Path] = None,
    threshold: Optional[int] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Register a failure and auto-consolidate when the threshold is reached.

    Safe to call for any event — non-failures are ignored (unless force=True
    with an explicit consolidate request).
    """
    thr = get_threshold(threshold)
    state = load_state(root)

    if event is not None and not is_failure_event(event) and not force:
        return {
            "status": "ignored",
            "reason": "not_failure",
            "failure_count_since_consolidate": state["failure_count_since_consolidate"],
            "threshold": thr,
            "consolidated": False,
        }

    if event is not None and is_failure_event(event):
        state["failure_count_since_consolidate"] = int(state.get("failure_count_since_consolidate") or 0) + 1
        state["total_failures_seen"] = int(state.get("total_failures_seen") or 0) + 1
        state["last_failure_at"] = _now_iso()
        eid = str(event.get("event_id") or "").strip()
        if eid:
            pending = list(state.get("pending_event_ids") or [])
            pending.append(eid)
            state["pending_event_ids"] = pending[-40:]
        save_state(state, root)

    count = int(state.get("failure_count_since_consolidate") or 0)
    should = force or count >= thr
    if not should:
        return {
            "status": "counted",
            "failure_count_since_consolidate": count,
            "threshold": thr,
            "consolidated": False,
            "remaining_until_consolidate": max(0, thr - count),
        }

    result = consolidate_failures(
        root=root,
        event_ids=list(state.get("pending_event_ids") or []) or None,
        reason="force" if force else "threshold",
    )
    result["threshold"] = thr
    result["consolidated"] = result.get("status") == "consolidated"
    result["failure_count_since_consolidate"] = 0
    return result


def maybe_auto_consolidate_from_event(
    event: Dict[str, Any],
    *,
    root: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Hook for record paths — returns result only when a consolidate fires."""
    try:
        if not is_failure_event(event):
            return None
        result = note_failure(event, root=root)
        if result.get("consolidated"):
            return result
        return None
    except Exception as exc:
        logger.warning("[FAILURE_AUTO] hook error: %s", exc)
        return None


def get_status(root: Optional[Path] = None) -> Dict[str, Any]:
    state = load_state(root)
    thr = get_threshold()
    summaries = load_summaries(root)
    latest = summaries[-1] if summaries else None
    count = int(state.get("failure_count_since_consolidate") or 0)
    return {
        "status": "ok",
        "threshold": thr,
        "failure_count_since_consolidate": count,
        "remaining_until_consolidate": max(0, thr - count),
        "total_failures_seen": int(state.get("total_failures_seen") or 0),
        "last_failure_at": state.get("last_failure_at"),
        "last_consolidate_at": state.get("last_consolidate_at"),
        "last_summary_id": state.get("last_summary_id"),
        "summary_count": len(summaries),
        "latest_summary": latest,
        "enabled": True,
    }


def latest_hermes_hint(root: Optional[Path] = None) -> Optional[str]:
    summaries = load_summaries(root)
    if not summaries:
        return None
    s = summaries[-1]
    return str(s.get("hermes_hint") or s.get("rule") or "").strip() or None
