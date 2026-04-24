#!/usr/bin/env python3
"""
Memory Integrity Audit & Reconciliation Tool for Forge NPS Hermes Memory.

Usage:
    python scripts/memory_integrity.py --audit
    python scripts/memory_integrity.py --dedupe
    python scripts/memory_integrity.py --report

This script:
  1. Audits episodic + semantic memory health
  2. Deduplicates semantic insights
  3. Validates all session files point to v01 paths
  4. Generates a reconciled memory report
"""

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).parent.parent.resolve()
EPISODIC_PATH = REPO_ROOT / "data" / "hermes_memory" / "episodic" / "events.jsonl"
SEMANTIC_PATH = REPO_ROOT / "data" / "hermes_memory" / "semantic" / "insights.json"
SESSIONS_DIR = REPO_ROOT / "data" / "sessions"
REASONING_DIR = REPO_ROOT / "data" / "reasoning_logs"


def load_events() -> List[Dict]:
    events = []
    if not EPISODIC_PATH.exists():
        return events
    for line in EPISODIC_PATH.read_text().strip().split("\n"):
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def load_insights() -> List[Dict]:
    if not SEMANTIC_PATH.exists():
        return []
    try:
        return json.loads(SEMANTIC_PATH.read_text())
    except (json.JSONDecodeError, IOError):
        return []


def audit() -> Dict:
    """Run a full memory health audit."""
    events = load_events()
    insights = load_insights()
    sessions = list(SESSIONS_DIR.glob("*.json"))
    reasoning = list(REASONING_DIR.rglob("*"))
    reasoning_files = [f for f in reasoning if f.is_file()]

    # Episodic stats
    outcomes = [e for e in events if e.get("event_type") == "outcome"]
    successes = [e for e in outcomes if e.get("success")]
    attempts = [e for e in events if e.get("event_type") == "generation_attempt"]
    errors = Counter(e.get("error_category", "Unknown") for e in outcomes)
    kernels = Counter(e.get("kernel_id", "unknown") for e in events)
    sessions_referenced = Counter(e.get("session_id", "unknown") for e in events)

    # Check for old paths in sessions
    stale_sessions = []
    for sfile in sessions:
        text = sfile.read_text()
        if "Desktop/forge_nps/" in text and "forge_nps_v01" not in text:
            stale_sessions.append(sfile.name)

    # Check for duplicate event IDs
    event_ids = [e.get("event_id") for e in events]
    dupes = {eid: c for eid, c in Counter(event_ids).items() if c > 1}

    # Time range
    timestamps = [e.get("timestamp", "") for e in events if e.get("timestamp")]
    time_range = ""
    if timestamps:
        sorted_ts = sorted(timestamps)
        time_range = f"{sorted_ts[0][:10]} → {sorted_ts[-1][:10]}"

    report = {
        "audit_timestamp": datetime.now().isoformat(),
        "episodic": {
            "total_events": len(events),
            "generation_attempts": len(attempts),
            "outcomes": len(outcomes),
            "success_rate": round(len(successes) / len(outcomes), 3) if outcomes else 0.0,
            "error_categories": dict(errors.most_common()),
            "top_kernels": dict(kernels.most_common(5)),
            "active_sessions": len(sessions_referenced),
            "time_range": time_range,
            "duplicate_event_ids": len(dupes),
        },
        "semantic": {
            "total_insights": len(insights),
            "avg_confidence": round(sum(i["confidence"] for i in insights) / len(insights), 3) if insights else 0.0,
            "high_confidence": len([i for i in insights if i["confidence"] >= 0.8]),
            "total_confirmations": sum(i["confirmations"] for i in insights),
        },
        "sessions": {
            "total_files": len(sessions),
            "stale_path_references": len(stale_sessions),
            "stale_files": stale_sessions[:5],
        },
        "reasoning_logs": {
            "total_files": len(reasoning_files),
            "directories": len([d for d in reasoning if d.is_dir()]),
        },
    }
    return report


def deduplicate_insights() -> int:
    """Merge duplicate semantic insights by (rule + applies_to)."""
    insights = load_insights()
    if not insights:
        return 0

    groups = {}
    for ins in insights:
        key = (ins["rule"], json.dumps(ins.get("applies_to", {}), sort_keys=True))
        groups.setdefault(key, []).append(ins)

    merged = []
    for group in groups.values():
        best = max(group, key=lambda x: x["confidence"])
        total_confirmations = sum(g["confirmations"] for g in group)
        all_sources = set()
        for g in group:
            for eid in g.get("source_events", []):
                all_sources.add(eid)
        best["confirmations"] = total_confirmations
        best["source_events"] = sorted(list(all_sources))
        merged.append(best)

    merged.sort(key=lambda x: x["confidence"], reverse=True)
    SEMANTIC_PATH.write_text(json.dumps(merged, indent=2))
    return len(insights) - len(merged)


def print_report(report: Dict):
    print("=" * 60)
    print("HERMES MEMORY INTEGRITY REPORT")
    print("=" * 60)
    print(f"Audit time: {report['audit_timestamp']}")
    print()

    ep = report["episodic"]
    print("EPISODIC MEMORY")
    print(f"  Total events:        {ep['total_events']}")
    print(f"  Generation attempts: {ep['generation_attempts']}")
    print(f"  Outcomes logged:     {ep['outcomes']}")
    print(f"  Success rate:        {ep['success_rate']:.1%}")
    print(f"  Active sessions:     {ep['active_sessions']}")
    print(f"  Time range:          {ep['time_range']}")
    print(f"  Duplicate IDs:       {ep['duplicate_event_ids']}")
    print("  Top errors:")
    for cat, count in ep["error_categories"].items():
        print(f"    {cat}: {count}")
    print("  Top kernels:")
    for kern, count in ep["top_kernels"].items():
        print(f"    {kern}: {count}")
    print()

    sm = report["semantic"]
    print("SEMANTIC MEMORY")
    print(f"  Total insights:      {sm['total_insights']}")
    print(f"  Avg confidence:      {sm['avg_confidence']:.2f}")
    print(f"  High confidence:     {sm['high_confidence']}")
    print(f"  Total confirmations: {sm['total_confirmations']}")
    print()

    se = report["sessions"]
    print("SESSIONS")
    print(f"  Total files:         {se['total_files']}")
    print(f"  Stale references:    {se['stale_path_references']}")
    if se["stale_files"]:
        print(f"  Examples:            {', '.join(se['stale_files'])}")
    print()

    rl = report["reasoning_logs"]
    print("REASONING LOGS")
    print(f"  Total files:         {rl['total_files']}")
    print(f"  Directories:         {rl['directories']}")
    print()
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Hermes Memory Integrity Tool")
    parser.add_argument("--audit", action="store_true", help="Run full audit")
    parser.add_argument("--dedupe", action="store_true", help="Deduplicate semantic insights")
    parser.add_argument("--report", action="store_true", help="Print formatted report")
    parser.add_argument("--fix-sessions", action="store_true", help="Fix stale paths in session files")
    args = parser.parse_args()

    if args.dedupe:
        removed = deduplicate_insights()
        print(f"[DEDUPE] Removed {removed} duplicate insights")

    if args.fix_sessions:
        fixed = 0
        for sfile in SESSIONS_DIR.glob("*.json"):
            text = sfile.read_text()
            if "Desktop/forge_nps/" in text and "forge_nps_v01" not in text:
                new_text = text.replace("~/Desktop/forge_nps/", "~/Desktop/forge_nps_v01/")
                sfile.write_text(new_text)
                fixed += 1
        print(f"[FIX] Repaired {fixed} session files")

    if args.audit or args.report or not (args.dedupe or args.fix_sessions):
        report = audit()
        print_report(report)

        # Save JSON report
        report_path = REPO_ROOT / "data" / "hermes_memory" / "audit_report.json"
        report_path.write_text(json.dumps(report, indent=2))
        print(f"[SAVED] JSON report → {report_path}")


if __name__ == "__main__":
    main()
