"""
Runtime configuration persistence.

Reads base config from .env, then overlays user changes from data/config.json.
This lets the dashboard Settings page modify configuration without rewriting .env.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
CONFIG_PATH = REPO_ROOT / "data" / "config.json"
ENV_PATH = REPO_ROOT / ".env"

# All keys that Settings page can read/write
CONFIGURABLE_KEYS = [
    "KIMI_API_KEY",
    "NIM_ENDPOINT",
    "KIMI_INSTRUCT_MODEL",
    "KIMI_THINKING_MODEL",
    "KIMI_VISUAL_MODEL",
    "COMFYUI_PRIMARY",
    "COMFYUI_SECONDARY",
    "LMSTUDIO_HOST",
    "LMSTUDIO_EMBED_MODEL",
    "LMSTUDIO_CHAT_MODEL",
    "USE_LOCAL_MODELS",
    "DASHBOARD_PORT",
    "MOCK_MODE",
]


def _load_json_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_json_config(data: Dict[str, Any]):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _read_env_value(key: str) -> str:
    """Read a key from .env file directly (no dotenv lib)."""
    if not ENV_PATH.exists():
        return ""
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(key + "="):
                    return line[len(key) + 1:].strip().strip('"').strip("'")
    except IOError:
        pass
    return ""


def get_config() -> Dict[str, str]:
    """Return merged config: .env base + JSON overrides."""
    base = {k: _read_env_value(k) for k in CONFIGURABLE_KEYS}
    overrides = _load_json_config()
    # Merge: JSON wins over .env
    merged = {**base, **overrides}
    # Mask API key for display
    if merged.get("KIMI_API_KEY"):
        merged["KIMI_API_KEY"] = _mask(merged["KIMI_API_KEY"])
    return merged


def get_raw_config() -> Dict[str, str]:
    """Return merged config without masking (for internal use)."""
    base = {k: _read_env_value(k) for k in CONFIGURABLE_KEYS}
    overrides = _load_json_config()
    return {**base, **overrides}


def set_config(updates: Dict[str, Any]) -> Dict[str, str]:
    """Persist config updates to JSON overlay."""
    current = _load_json_config()
    for k, v in updates.items():
        if k in CONFIGURABLE_KEYS:
            current[k] = str(v) if v is not None else ""
    _save_json_config(current)
    return get_config()


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "••••••••"
    return value[:4] + "••••••••••••••••" + value[-4:]


def apply_to_environment():
    """Apply JSON overrides to os.environ so running code picks them up."""
    overrides = _load_json_config()
    for k, v in overrides.items():
        os.environ[k] = str(v)
