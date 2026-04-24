"""
Episodic Memory — Karpathy-style explicit event store.

Every production attempt, failure, fix, and success is recorded as an immutable event.
Hermes queries this before acting: "Have I seen something like this before?"
"""

import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .embedder import BaseEmbedder, HybridEmbedder


class EpisodicMemory:
    """
    Append-only JSONL event log with embedding-based similarity retrieval.
    Defaults to HybridEmbedder (LM Studio local embeddings + numpy TF-IDF fallback).
    """

    def __init__(
        self,
        memory_dir: str = "~/Desktop/forge_nps_v01/data/hermes_memory/episodic",
        embedder: Optional[BaseEmbedder] = None,
    ):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.memory_dir / "events.jsonl"
        self.embedder = embedder or HybridEmbedder()
        self._embedding_cache: Dict[str, np.ndarray] = {}

    def record(self, event: Dict[str, Any]) -> str:
        """
        Append an event to the episodic log.
        Returns the assigned event_id.
        """
        event_id = f"evt_{uuid.uuid4().hex[:8]}"
        entry = {
            "event_id": event_id,
            "timestamp": datetime.now().isoformat(),
            **event,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return event_id

    def query_similar(
        self,
        concept: str,
        error_category: Optional[str] = None,
        kernel_id: Optional[str] = None,
        top_k: int = 3,
        min_similarity: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the top-k most similar past events using embedding cosine similarity.
        Falls back to Jaccard token overlap if embeddings are unavailable.
        """
        if not self.log_path.exists():
            return []

        query_text = concept + " " + (error_category or "")
        query_vec = self.embedder.embed(query_text)
        has_real_embedding = np.linalg.norm(query_vec) > 1e-6

        # Load all events
        events = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events.append(evt)

        if not events:
            return []

        # Build fallback corpus for TF-IDF if needed
        if isinstance(self.embedder, HybridEmbedder):
            corpus = [e.get("concept", "") + " " + e.get("error_category", "") for e in events]
            self.embedder.register_corpus(corpus)

        scored = []
        for evt in events:
            candidate_text = evt.get("concept", "") + " " + evt.get("error_category", "")
            sim = 0.0

            if has_real_embedding:
                cand_vec = self.embedder.embed(candidate_text)
                if np.linalg.norm(cand_vec) > 1e-6:
                    sim = self.embedder.similarity(query_vec, cand_vec)
                else:
                    # Embedding failed for this candidate, fall back to Jaccard
                    sim = self._jaccard_tokens(query_text, candidate_text)
            else:
                sim = self._jaccard_tokens(query_text, candidate_text)

            # Boost exact kernel match
            if kernel_id and evt.get("kernel_id") == kernel_id:
                sim = min(1.0, sim + 0.1)

            if sim >= min_similarity:
                scored.append((sim, evt))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [evt for _, evt in scored[:top_k]]

    def get_recent(self, n: int = 10) -> List[Dict[str, Any]]:
        """Return the n most recent events."""
        if not self.log_path.exists():
            return []
        events = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return events[-n:]

    def get_stats(self) -> Dict[str, Any]:
        """High-level stats for dashboard / hackathon viz."""
        total = 0
        outcomes = 0
        successes = 0
        category_counts = Counter()
        kernel_counts = Counter()

        if self.log_path.exists():
            with open(self.log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    total += 1
                    if evt.get("event_type") == "outcome":
                        outcomes += 1
                        if evt.get("success"):
                            successes += 1
                    if evt.get("error_category"):
                        category_counts[evt["error_category"]] += 1
                    if evt.get("kernel_id"):
                        kernel_counts[evt["kernel_id"]] += 1

        return {
            "total_events": total,
            "outcomes_logged": outcomes,
            "success_rate": successes / outcomes if outcomes else 0.0,
            "top_error_categories": dict(category_counts.most_common(5)),
            "top_kernels": dict(kernel_counts.most_common(5)),
        }

    @staticmethod
    def _jaccard_tokens(a: str, b: str) -> float:
        """Simple fallback similarity when embeddings are unavailable."""
        tokens_a = set(re.findall(r"[a-z0-9]+", a.lower()))
        tokens_b = set(re.findall(r"[a-z0-9]+", b.lower()))
        if not tokens_a or not tokens_b:
            return 0.0
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        return intersection / union if union else 0.0
