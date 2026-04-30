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
    "KIMI_DIRECTOR_ENDPOINT_API1",
    "KIMI_DIRECTOR_ENDPOINT_API2",
    "KIMI_DIRECTOR_ENDPOINT_ACTIVE",
    "KIMI_VISUAL_ENDPOINT_API1",
    "KIMI_VISUAL_ENDPOINT_API2",
    "KIMI_VISUAL_ENDPOINT_ACTIVE",
    "COMFYUI_PRIMARY",
    "COMFYUI_SECONDARY",
    "LMSTUDIO_HOST",
    "LMSTUDIO_EMBED_MODEL",
    "LMSTUDIO_CHAT_MODEL",
    "USE_LOCAL_MODELS",
    "DASHBOARD_PORT",
    "MOCK_MODE",
]

# Frontend/UI alias keys -> canonical env/config keys
KEY_ALIASES = {
    "kimi_api": "KIMI_API_KEY",
    "kimi_api_key": "KIMI_API_KEY",
    "nim_url": "NIM_ENDPOINT",
    "nim_endpoint": "NIM_ENDPOINT",
    "director_endpoint_api1": "KIMI_DIRECTOR_ENDPOINT_API1",
    "director_endpoint_api2": "KIMI_DIRECTOR_ENDPOINT_API2",
    "director_endpoint_active": "KIMI_DIRECTOR_ENDPOINT_ACTIVE",
    "visual_endpoint_api1": "KIMI_VISUAL_ENDPOINT_API1",
    "visual_endpoint_api2": "KIMI_VISUAL_ENDPOINT_API2",
    "visual_endpoint_active": "KIMI_VISUAL_ENDPOINT_ACTIVE",
    "comfy_primary": "COMFYUI_PRIMARY",
    "comfy_secondary": "COMFYUI_SECONDARY",
    "spark_url": "COMFYUI_PRIMARY",
    "lmstudio_host": "LMSTUDIO_HOST",
    "lmstudio_chat_model": "LMSTUDIO_CHAT_MODEL",
    "lmstudio_embed_model": "LMSTUDIO_EMBED_MODEL",
}


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
        canonical = KEY_ALIASES.get(k, k)
        if canonical in CONFIGURABLE_KEYS:
            current[canonical] = str(v) if v is not None else ""
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
