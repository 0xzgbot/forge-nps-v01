from typing import Dict, Set


SHOT_STATES = {
    "planned",
    "queued",
    "rendered",
    "audit_started",
    "audited_pass",
    "audited_fail",
    "remediation_started",
    "retry_queued",
    "retry_rendered",
    "final_pass",
    "final_fail",
}


_TRANSITIONS: Dict[str, Set[str]] = {
    "planned": {"queued", "final_fail"},
    "queued": {"rendered", "final_fail"},
    "rendered": {"audit_started", "final_fail"},
    "audit_started": {"audited_pass", "audited_fail", "final_fail"},
    "audited_pass": {"final_pass"},
    "audited_fail": {"remediation_started", "final_fail"},
    "remediation_started": {"retry_queued", "final_fail"},
    "retry_queued": {"retry_rendered", "final_fail"},
    "retry_rendered": {"audit_started", "final_pass", "final_fail"},
    "final_pass": set(),
    "final_fail": set(),
}


_STATUS_BY_STATE = {
    "planned": "planned",
    "queued": "queued",
    "rendered": "rendered",
    "audit_started": "auditing",
    "audited_pass": "rendered",
    "audited_fail": "failed",
    "remediation_started": "remediating",
    "retry_queued": "queued",
    "retry_rendered": "rendered",
    "final_pass": "complete",
    "final_fail": "failed",
}


def transition_shot(shot: Dict, new_state: str) -> None:
    if new_state not in SHOT_STATES:
        raise ValueError(f"invalid_state:{new_state}")
    old_state = str(shot.get("state") or "").strip()
    if old_state and old_state in SHOT_STATES:
        allowed = _TRANSITIONS.get(old_state, set())
        if allowed and new_state not in allowed:
            raise ValueError(f"invalid_transition:{old_state}->{new_state}")
    shot["state"] = new_state
    shot["status"] = _STATUS_BY_STATE.get(new_state, shot.get("status", ""))

