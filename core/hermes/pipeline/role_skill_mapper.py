import fnmatch
import json
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[3]
ROLE_MAP_PATH = REPO_ROOT / "data" / "profiles" / "role_skill_map.json"


def _safe_text(value: object) -> str:
    return str(value or "").strip()


def _load_role_map() -> Dict[str, object]:
    try:
        if ROLE_MAP_PATH.exists():
            return json.loads(ROLE_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"version": "unknown", "profiles": {}}


def role_skill_patterns(role_key: str) -> List[str]:
    data = _load_role_map()
    profiles = data.get("profiles", {})
    profile = profiles.get(role_key, {}) if isinstance(profiles, dict) else {}
    allow = profile.get("allow", []) if isinstance(profile, dict) else []
    out: List[str] = []
    for item in allow:
        t = _safe_text(item)
        if t:
            out.append(t)
    return out


def filter_skill_names(skill_names: List[str], patterns: List[str]) -> List[str]:
    if not patterns:
        return list(skill_names)
    out: List[str] = []
    for name in skill_names:
        n = _safe_text(name)
        if not n:
            continue
        if any(fnmatch.fnmatch(n, p) for p in patterns):
            out.append(n)
    return out


def role_skill_scope(role_key: str) -> Dict[str, object]:
    data = _load_role_map()
    patterns = role_skill_patterns(role_key)
    return {
        "role_key": role_key,
        "map_version": _safe_text(data.get("version")) or "unknown",
        "patterns": patterns,
    }
