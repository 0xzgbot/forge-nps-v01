"""
Consolidator — The "Dream" Process.

Scans episodic memory for recurring patterns and distills them into
semantic insights. This is the learning loop.

Pattern: same error_category + similar fix_applied + repeated success
         → create a durable rule in semantic memory.
"""

import logging
from collections import defaultdict
from typing import Any, Dict, List

from .episodic_memory import EpisodicMemory
from .semantic_memory import SemanticMemory

logger = logging.getLogger("HermesMemoryConsolidator")


class MemoryConsolidator:
    """
    Runs after a production session to find patterns and upgrade
    episodic experiences into semantic knowledge.
    """

    def __init__(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        min_confirmations: int = 2,
        confidence_boost_per_confirm: float = 0.15,
    ):
        self.episodic = episodic
        self.semantic = semantic
        self.min_confirmations = min_confirmations
        self.confidence_boost = confidence_boost_per_confirm

    def consolidate(self, session_events: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Analyze recent events and generate new insights.
        If session_events is provided, only those are scanned (fast path).
        Otherwise the full episodic log is scanned.
        """
        events = session_events or self.episodic.get_recent(n=500)
        if not events:
            return []

        # Group by (error_category, kernel_id) → list of events
        groups = defaultdict(list)
        for evt in events:
            if not evt.get("success"):
                continue  # Only learn from successful fixes
            key = (evt.get("error_category", "general"), evt.get("kernel_id", "any"))
            groups[key].append(evt)

        new_insights = []
        for (error_cat, kernel_id), evts in groups.items():
            if len(evts) < self.min_confirmations:
                continue

            # Check if all events used roughly the same fix
            fixes = [e.get("fix_applied", "").strip().lower() for e in evts]
            # Simple consensus: most common fix
            fix_counts = defaultdict(int)
            for f in fixes:
                fix_counts[f] += 1
            top_fix, top_count = max(fix_counts.items(), key=lambda x: x[1])

            if top_count < self.min_confirmations:
                continue

            # Derive a human-readable rule from the top fix
            rule = self._craft_rule(error_cat, kernel_id, top_fix)

            confidence = min(0.95, 0.5 + (top_count - 1) * self.confidence_boost)
            source_event_ids = [e.get("event_id", "unknown") for e in evts if e.get("fix_applied", "").strip().lower() == top_fix][:5]

            # Check if a similar insight already exists
            existing = self.semantic.query_relevant(
                error_category=error_cat,
                kernel_id=kernel_id,
                min_confidence=0.3,
            )
            if existing:
                # Increment confirmations on the closest match instead of duplicating
                closest = existing[0]
                closest["confirmations"] += top_count
                closest["confidence"] = min(0.99, closest["confidence"] + self.confidence_boost)
                closest["source_events"] = list(set(closest["source_events"] + source_event_ids))[:10]
                logger.info(f"[CONSOLIDATOR] Reinforced insight {closest['insight_id']} "
                            f"for {error_cat}/{kernel_id} (confirmations={closest['confirmations']})")
                self.semantic._save()
            else:
                insight_id = self.semantic.add_insight(
                    rule=rule,
                    confidence=confidence,
                    source_events=source_event_ids,
                    applies_to={
                        "error_category": error_cat,
                        "kernel_id": kernel_id,
                    },
                    confirmations=top_count,
                )
                new_insights.append({
                    "insight_id": insight_id,
                    "rule": rule,
                    "confidence": confidence,
                    "confirmations": top_count,
                })
                logger.info(f"[CONSOLIDATOR] New insight {insight_id}: {rule}")

        return new_insights

    @staticmethod
    def _craft_rule(error_category: str, kernel_id: str, fix: str) -> str:
        """Generate a concise, actionable rule string."""
        return (
            f"When generating with {kernel_id} and encountering a {error_category} issue, "
            f"apply this adjustment: {fix[:120]}{'...' if len(fix) > 120 else ''}"
        )
