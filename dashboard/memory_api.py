"""
Memory API endpoints for the Forge NPS Dashboard.
Provides structured data for visualizing Hermes memory:
- Stats overview
- Event timeline
- Semantic insights
- Graph structure (nodes + edges) for Cytoscape.js
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from collections import Counter

REPO_ROOT = Path(__file__).parent.parent.resolve()
EPISODIC_PATH = REPO_ROOT / "data" / "hermes_memory" / "episodic" / "events.jsonl"
SEMANTIC_PATH = REPO_ROOT / "data" / "hermes_memory" / "semantic" / "insights.json"
AUDIT_PATH = REPO_ROOT / "data" / "hermes_memory" / "audit_report.json"


def load_events() -> List[Dict[str, Any]]:
    events = []
    if not EPISODIC_PATH.exists():
        return events
    try:
        with open(EPISODIC_PATH, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        print(f"Error loading events: {e}")
    return events


def load_insights() -> List[Dict[str, Any]]:
    if not SEMANTIC_PATH.exists():
        return []
    try:
        with open(SEMANTIC_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading insights: {e}")
        return []


def get_memory_stats() -> Dict[str, Any]:
    """High-level memory statistics for dashboard cards."""
    events = load_events()
    insights = load_insights()

    outcome_types = {"outcome", "final_outcome", "audit_outcome", "audit_result", "render_result", "remediation_result"}
    attempt_types = {"generation_attempt", "render_attempt", "shot_planned"}
    outcomes = [e for e in events if e.get("event_type") in outcome_types]
    successes = [e for e in outcomes if e.get("success")]
    attempts = [e for e in events if e.get("event_type") in attempt_types]

    error_counts = Counter(e.get("error_category", "Unknown") for e in outcomes)
    kernel_counts = Counter(e.get("kernel_id", "unknown") for e in events)
    session_counts = Counter(e.get("session_id", "unknown") for e in events)

    # Source breakdown
    live_count = sum(1 for e in events if e.get("source") == "live")
    demo_count = sum(1 for e in events if e.get("source") == "demo")
    seed_count = sum(1 for e in events if e.get("source") == "seed")
    campaign_count = sum(1 for e in events if e.get("source") == "campaign")
    import_count = sum(1 for e in events if e.get("source") == "import")
    fallback_count = sum(1 for e in events if e.get("source") == "fallback")

    # Promotable: live remediation events with success=true, grouped by error_category
    remediation_by_cat: Dict[str, int] = Counter()
    for e in events:
        if (e.get("source") == "live"
                and e.get("event_type") in {"remediation", "remediation_result"}
                and e.get("success")
                and e.get("error_category")):
            remediation_by_cat[e["error_category"]] += 1
    promotable_count = sum(1 for c in remediation_by_cat.values() if c >= 2)

    # Time range
    timestamps = [e.get("timestamp", "") for e in events if e.get("timestamp")]
    time_range = ""
    if timestamps:
        sorted_ts = sorted(timestamps)
        time_range = f"{sorted_ts[0][:10]} → {sorted_ts[-1][:10]}"

    # Fix types for JSON serialization
    error_counts = {k: int(v) for k, v in error_counts.most_common()}
    kernel_counts = {k: int(v) for k, v in kernel_counts.most_common()}
    session_counts = {k: int(v) for k, v in session_counts.most_common()}

    stats = {
        "total_events": len(events),
        "total_insights": len(insights),
        "generation_attempts": len(attempts),
        "outcomes": len(outcomes),
        "success_rate": round(len(successes) / len(outcomes), 3) if outcomes else 0.0,
        "error_categories": error_counts,
        "top_kernels": kernel_counts,
        "active_sessions": len(session_counts),
        "time_range": time_range,
        "avg_confidence": round(
            sum(i["confidence"] for i in insights) / len(insights), 3
        ) if insights else 0.0,
        "total_confirmations": sum(i.get("confirmations", 0) for i in insights),
        # Source breakdown
        "live_count": live_count,
        "demo_count": demo_count,
        "seed_count": seed_count,
        "campaign_count": campaign_count,
        "import_count": import_count,
        "fallback_count": fallback_count,
        "promotable_count": promotable_count,
    }
    # Frontend compatibility aliases
    stats["events"] = stats["total_events"]
    stats["insights"] = stats["total_insights"]
    stats["sessions"] = stats["active_sessions"]
    stats["rules"] = stats["promotable_count"]
    return stats


def get_event_timeline(limit: int = 50) -> List[Dict[str, Any]]:
    """Recent events formatted for timeline display."""
    events = load_events()
    # Sort by timestamp descending so latest is first
    events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    
    result = []
    for e in events[:limit]:
        result.append({
            "event_id": e.get("event_id", "unknown"),
            "timestamp": e.get("timestamp", ""),
            "ts": e.get("timestamp", ""),
            "session_id": e.get("session_id", "unknown"),
            "shot_id": e.get("shot_id", ""),
            "shot": e.get("shot_id", ""),
            "type": e.get("event_type", "unknown"),
            "concept": (e.get("concept", "")[:80]),
            "kernel_id": e.get("kernel_id", ""),
            "success": e.get("success"),
            "error_category": e.get("error_category", ""),
            "fix_applied": e.get("fix_applied", ""),
            "audit_score": e.get("audit_score"),
            "iterations_required": e.get("iterations_required", 1),
            "source": e.get("source", "live"),
        })
    return result


def get_memory_health() -> Dict[str, Any]:
    events = load_events()
    valid_types = {
        "shot_planned",
        "render_attempt",
        "render_result",
        "audit_started",
        "audit_result",
        "remediation_started",
        "remediation_result",
        "retry_linked",
        "final_outcome",
        "import_completed",
    }
    unknown = [e for e in events if e.get("event_type") not in valid_types]
    remediation_events = [e for e in events if e.get("event_type") in {"remediation_started", "remediation_result", "retry_linked"}]
    orphan_remediation = [e for e in remediation_events if not e.get("shot_id")]
    fallback_events = [e for e in events if e.get("source") == "fallback"]

    rendered = {}
    audited = {}
    for e in events:
        sid = e.get("shot_id", "")
        if not sid:
            continue
        if e.get("event_type") == "render_result" and e.get("success") is True:
            rendered[sid] = True
        if e.get("event_type") == "audit_result":
            audited[sid] = True
    missing_audit = [sid for sid in rendered if sid not in audited]

    return {
        "total_events": len(events),
        "unknown_event_types": len(unknown),
        "unknown_event_samples": [e.get("event_type", "unknown") for e in unknown[:10]],
        "orphan_remediation_events": len(orphan_remediation),
        "fallback_events": len(fallback_events),
        "shots_missing_audit_after_render": len(missing_audit),
    }


def get_graph_data() -> Dict[str, List[Dict[str, Any]]]:
    """
    Build a graph structure for Cytoscape.js visualization.
    """
    events = load_events()
    insights = load_insights()
    nodes = []
    edges = []
    node_ids = set()
    edge_ids = set()

    def add_node(node_id: str, label: str, node_type: str, data: Dict = None):
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        node = {
            "id": node_id,
            "label": label,
            "type": node_type,
            "data": data or {},
        }
        if node_type == "insight":
            node["size"] = 40
        elif node_type == "session":
            node["size"] = 30
        elif node_type == "kernel":
            node["size"] = 25
        else:
            node["size"] = 20
        nodes.append(node)

    def add_edge(source: str, target: str, edge_type: str, label: str = ""):
        edge_id = f"{source}->{target}:{edge_type}"
        if edge_id in edge_ids:
            return
        edge_ids.add(edge_id)
        edges.append({
            "id": edge_id,
            "source": source,
            "target": target,
            "type": edge_type,
            "label": label,
        })

    for e in events:
        eid = e.get("event_id", "evt_unknown")
        etype = e.get("event_type", "unknown")
        session_id = e.get("session_id", "unknown")
        kernel_id = e.get("kernel_id", "unknown")
        shot_id = e.get("shot_id", "")
        concept = e.get("concept", "")[:30]

        if etype in {"generation_attempt", "render_attempt", "shot_planned"}:
            node_type = "attempt"
        elif etype in {"outcome", "final_outcome", "audit_outcome", "audit_result", "render_result", "remediation_result"}:
            node_type = "outcome_success" if e.get("success") else "outcome_fail"
        else:
            node_type = "event"

        label = f"{etype[:12]}\n{concept}"
        add_node(eid, label, node_type, {
            "timestamp": e.get("timestamp", ""),
            "session_id": session_id,
            "kernel_id": kernel_id,
            "shot_id": shot_id,
            "success": e.get("success"),
            "error_category": e.get("error_category", ""),
            "audit_score": e.get("audit_score"),
            "source": e.get("source", "live"),
        })

        session_node_id = f"session_{session_id}"
        add_node(session_node_id, f"Session\n{session_id[:16]}", "session")
        add_edge(eid, session_node_id, "belongs_to")

        if kernel_id and kernel_id != "unknown":
            kernel_node_id = f"kernel_{kernel_id}"
            add_node(kernel_node_id, f"Kernel\n{kernel_id}", "kernel")
            add_edge(eid, kernel_node_id, "uses")

    for ins in insights:
        iid = ins.get("insight_id", "ins_unknown")
        rule = ins.get("rule", "")[:40]
        conf = ins.get("confidence", 0)
        confs = ins.get("confirmations", 0)

        add_node(iid, f"Insight\n{rule}", "insight", {
            "confidence": conf,
            "confirmations": confs,
            "applies_to": ins.get("applies_to", {}),
        })

        for src_evt in ins.get("source_events", []):
            if src_evt in node_ids:
                add_edge(iid, src_evt, "learned_from")

    session_shot_attempts = {}
    for e in events:
        if e.get("event_type") in {"generation_attempt", "render_attempt", "shot_planned"}:
            key = (e.get("session_id", ""), e.get("shot_id", ""))
            session_shot_attempts.setdefault(key, []).append(e.get("event_id"))

    for e in events:
        if e.get("event_type") in {"outcome", "final_outcome", "audit_outcome", "audit_result", "render_result", "remediation_result"}:
            key = (e.get("session_id", ""), e.get("shot_id", ""))
            attempts = session_shot_attempts.get(key, [])
            if attempts:
                add_edge(attempts[-1], e.get("event_id"), "result_of")

    return {"nodes": nodes, "edges": edges}


def search_memory(query: str) -> Dict[str, List[Dict[str, Any]]]:
    query_lower = query.lower()
    events = load_events()
    insights = load_insights()

    matched_events = [e for e in events if query_lower in json.dumps(e).lower()]
    matched_insights = [i for i in insights if query_lower in json.dumps(i).lower()]

    return {
        "events": matched_events[:20],
        "insights": matched_insights,
        "total_events": len(matched_events),
        "total_insights": len(matched_insights),
    }

# --- API ROUTES ---

# NOTE: These are pure utility functions.
# FastAPI routes are defined in forge_dashboard.py which imports and calls these directly.
