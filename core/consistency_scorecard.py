"""Lightweight consistency scorecard for storyboard / multi-shot runs.

Heuristic (no vision model required): compares prompt tokens, character locks,
and package continuity fields across frames. When vision audit scores exist on
shots, they are folded in.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional, Set


_STOP = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "with", "for", "at",
    "by", "from", "into", "as", "is", "are", "shot", "frame", "camera", "lens",
}


def _tokens(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOP}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _shot_text(shot: Dict[str, Any]) -> str:
    parts = [
        shot.get("prompt"),
        shot.get("video_prompt"),
        shot.get("caption"),
        shot.get("description"),
        shot.get("character"),
        shot.get("wardrobe"),
        shot.get("location"),
    ]
    return " ".join(str(p) for p in parts if p)


def score_story_consistency(project: Dict[str, Any]) -> Dict[str, Any]:
    """Score consistency across video_shots / coverage / package locks."""
    package = project.get("package") if isinstance(project.get("package"), dict) else {}
    locks: List[str] = []
    for key in ("characters", "character_locks", "wardrobe_locks", "location", "tone", "visual_style"):
        val = package.get(key)
        if isinstance(val, str) and val.strip():
            locks.append(val)
        elif isinstance(val, list):
            locks.extend(str(x) for x in val if x)
        elif isinstance(val, dict):
            locks.extend(str(v) for v in val.values() if v)
    lock_tokens = _tokens(" ".join(locks))

    shots: List[Dict[str, Any]] = []
    for key in ("video_shots", "coverage_shots"):
        items = project.get(key)
        if isinstance(items, list):
            shots.extend([s for s in items if isinstance(s, dict)])

    # storyboard panels as pseudo-shots
    plan = project.get("storyboard_plan") if isinstance(project.get("storyboard_plan"), dict) else {}
    for board in plan.get("boards") or []:
        if not isinstance(board, dict):
            continue
        for panel in board.get("panels") or []:
            if isinstance(panel, dict):
                shots.append(panel)

    if len(shots) < 2:
        return {
            "score": 100 if shots else 0,
            "grade": "A" if shots else "N/A",
            "shot_count": len(shots),
            "summary": "Not enough shots to compare consistency." if len(shots) < 2 else "Single shot — trivially consistent.",
            "issues": [],
            "pair_scores": [],
            "lock_coverage": 1.0 if lock_tokens and shots else (1.0 if not lock_tokens else 0.0),
            "recommendations": [
                "Generate at least two storyboard frames or coverage shots for a real scorecard.",
            ] if len(shots) < 2 else [],
        }

    token_sets = [_tokens(_shot_text(s)) for s in shots]
    pair_scores: List[Dict[str, Any]] = []
    sims: List[float] = []
    for i in range(len(token_sets)):
        for j in range(i + 1, len(token_sets)):
            sim = _jaccard(token_sets[i], token_sets[j])
            sims.append(sim)
            pair_scores.append({"i": i, "j": j, "similarity": round(sim, 3)})

    avg_sim = sum(sims) / len(sims) if sims else 0.0

    # lock coverage: average fraction of lock tokens present in each shot
    lock_hits: List[float] = []
    if lock_tokens:
        for ts in token_sets:
            lock_hits.append(len(ts & lock_tokens) / max(1, len(lock_tokens)))
        lock_coverage = sum(lock_hits) / len(lock_hits)
    else:
        lock_coverage = 1.0

    # optional audit scores
    audit_vals: List[float] = []
    for s in shots:
        for key in ("audit_score", "score", "vision_score"):
            try:
                if s.get(key) is not None:
                    audit_vals.append(float(s[key]))
                    break
            except Exception:
                pass
    audit_avg = (sum(audit_vals) / len(audit_vals)) if audit_vals else None

    # weighted score 0-100
    score = (avg_sim * 55.0) + (lock_coverage * 30.0) + 15.0
    if audit_avg is not None:
        # assume audit is 0-1 or 0-100
        a = audit_avg if audit_avg <= 1.0 else audit_avg / 100.0
        score = score * 0.75 + (a * 100.0) * 0.25
    score = max(0.0, min(100.0, score))

    issues: List[str] = []
    if avg_sim < 0.18:
        issues.append("Shot prompts diverge strongly — characters/locations may drift between frames.")
    if lock_tokens and lock_coverage < 0.25:
        issues.append("Package continuity locks are weakly reflected in shot prompts.")
    if audit_avg is not None and (audit_avg if audit_avg <= 1 else audit_avg / 100) < 0.6:
        issues.append("Vision audit scores are soft — consider remediation on weak frames.")

    recommendations: List[str] = []
    if issues:
        recommendations.append("Re-run storyboard with Series Continuity / character locks enabled.")
        recommendations.append("Attach an Asset Vault package so wardrobe and product props stay locked.")
        recommendations.append("Regenerate only weak panels, then re-export the story package.")
    else:
        recommendations.append("Consistency looks solid — proceed to video or export the story package.")

    grade = (
        "A" if score >= 85 else
        "B" if score >= 70 else
        "C" if score >= 55 else
        "D" if score >= 40 else
        "F"
    )

    # top shared tokens
    all_counts: Counter = Counter()
    for ts in token_sets:
        all_counts.update(ts)
    shared = [w for w, c in all_counts.most_common(12) if c >= max(2, len(token_sets) // 2)]

    return {
        "score": round(score, 1),
        "grade": grade,
        "shot_count": len(shots),
        "avg_prompt_similarity": round(avg_sim, 3),
        "lock_coverage": round(lock_coverage, 3),
        "audit_avg": round(audit_avg, 3) if audit_avg is not None else None,
        "shared_tokens": shared,
        "summary": (
            f"Grade {grade} ({score:.0f}/100) across {len(shots)} shots — "
            f"prompt overlap {avg_sim:.0%}, lock coverage {lock_coverage:.0%}."
        ),
        "issues": issues,
        "recommendations": recommendations,
        "pair_scores": pair_scores[:40],
    }


def score_campaign_shots(shots: List[Dict[str, Any]]) -> Dict[str, Any]:
    return score_story_consistency({"video_shots": shots, "package": {}})
