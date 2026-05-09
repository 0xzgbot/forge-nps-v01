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
CONFIG_BACKUP_PATH = REPO_ROOT / "data" / "config.json.bak"
ENV_PATH = REPO_ROOT / ".env"

# All keys that Settings page can read/write
CONFIGURABLE_KEYS = [
    "NOUS_API_KEY",
    "NOUS_ENDPOINT",
    "DIRECTOR_MODEL",
    "THINKING_MODEL",
    "VISION_MODEL",
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
    "OPENROUTER_API_KEY",
    "OPENROUTER_ENDPOINT",
    "COMFYUI_PRIMARY",
    "COMFYUI_SECONDARY",
    "SPARK_WORKFLOW_FILE",
    "LMSTUDIO_HOST",
    "LMSTUDIO_PORT",
    "LMSTUDIO_EMBED_MODEL",
    "LMSTUDIO_CHAT_MODEL",
    "LMSTUDIO_VISION_MODEL",
    "USE_LOCAL_MODELS",
    "DASHBOARD_PORT",
    "MOCK_MODE",
]

SECRET_KEYS = {
    "NOUS_API_KEY",
    "KIMI_API_KEY",
    "OPENROUTER_API_KEY",
}

# Frontend/UI alias keys -> canonical env/config keys
KEY_ALIASES = {
    "nous_api_key": "NOUS_API_KEY",
    "nous_endpoint": "NOUS_ENDPOINT",
    "director_model": "DIRECTOR_MODEL",
    "thinking_model": "THINKING_MODEL",
    "vision_model": "VISION_MODEL",
    "kimi_api": "KIMI_API_KEY",
    "kimi_api_key": "KIMI_API_KEY",
    "nim_url": "NIM_ENDPOINT",
    "nim_endpoint": "NIM_ENDPOINT",
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "openrouter_endpoint": "OPENROUTER_ENDPOINT",
    "director_endpoint_api1": "KIMI_DIRECTOR_ENDPOINT_API1",
    "director_endpoint_api2": "KIMI_DIRECTOR_ENDPOINT_API2",
    "director_endpoint_active": "KIMI_DIRECTOR_ENDPOINT_ACTIVE",
    "visual_endpoint_api1": "KIMI_VISUAL_ENDPOINT_API1",
    "visual_endpoint_api2": "KIMI_VISUAL_ENDPOINT_API2",
    "visual_endpoint_active": "KIMI_VISUAL_ENDPOINT_ACTIVE",
    "comfy_primary": "COMFYUI_PRIMARY",
    "comfy_secondary": "COMFYUI_SECONDARY",
    "spark_url": "COMFYUI_PRIMARY",
    "spark_workflow_file": "SPARK_WORKFLOW_FILE",
    "lmstudio_host": "LMSTUDIO_HOST",
    "lmstudio_port": "LMSTUDIO_PORT",
    "lmstudio_chat_model": "LMSTUDIO_CHAT_MODEL",
    "lmstudio_embed_model": "LMSTUDIO_EMBED_MODEL",
    "lmstudio_vision_model": "LMSTUDIO_VISION_MODEL",
}


def _load_json_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
            if not isinstance(raw, dict):
                return {}
            return _normalize_overrides(raw)
    except (json.JSONDecodeError, IOError):
        return {}


def _normalize_overrides(raw: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}

    def put(key: str, value: Any, *, allow_empty: bool = True):
        canonical = KEY_ALIASES.get(key, key)
        if canonical in CONFIGURABLE_KEYS:
            if value is None:
                if not allow_empty:
                    return
                normalized[canonical] = ""
                return
            normalized[canonical] = "" if value is None else str(value)

    def put_legacy(container: Dict[str, Any], key: str, canonical_key: str):
        if key not in container:
            return
        value = container.get(key)
        if value is None:
            return
        # Legacy nested settings are migration inputs. They should not erase
        # explicitly saved flat settings or .env values when fields are absent.
        put(canonical_key, value, allow_empty=False)

    # Legacy nested payloads are imported first. Flat canonical keys below are
    # the source of truth and must win when both shapes are present.
    kimi = raw.get("kimi", {})
    if isinstance(kimi, dict):
        put_legacy(kimi, "api_key", "KIMI_API_KEY")
        put_legacy(kimi, "endpoint", "NIM_ENDPOINT")

    models = raw.get("models", {})
    if isinstance(models, dict):
        director = models.get("director_kimi")
        if isinstance(director, dict):
            put_legacy(director, "model_name", "KIMI_INSTRUCT_MODEL")
            put_legacy(director, "endpoint_api1", "KIMI_DIRECTOR_ENDPOINT_API1")
            put_legacy(director, "endpoint_api2", "KIMI_DIRECTOR_ENDPOINT_API2")
            put_legacy(director, "endpoint_active", "KIMI_DIRECTOR_ENDPOINT_ACTIVE")
        visual = models.get("kimi_vl")
        if isinstance(visual, dict):
            put_legacy(visual, "model_name", "KIMI_VISUAL_MODEL")
            put_legacy(visual, "endpoint_api1", "KIMI_VISUAL_ENDPOINT_API1")
            put_legacy(visual, "endpoint_api2", "KIMI_VISUAL_ENDPOINT_API2")
            put_legacy(visual, "endpoint_active", "KIMI_VISUAL_ENDPOINT_ACTIVE")
        hermes = models.get("hermes_3")
        if isinstance(hermes, dict):
            put_legacy(hermes, "host", "LMSTUDIO_HOST")
            put_legacy(hermes, "port", "LMSTUDIO_PORT")
            put_legacy(hermes, "model_name", "LMSTUDIO_CHAT_MODEL")

    comfy = raw.get("comfyui")
    if isinstance(comfy, dict):
        put_legacy(comfy, "primary", "COMFYUI_PRIMARY")
        put_legacy(comfy, "secondary", "COMFYUI_SECONDARY")

    spark = raw.get("spark")
    if isinstance(spark, dict):
        put_legacy(spark, "primary", "COMFYUI_PRIMARY")
        put_legacy(spark, "secondary", "COMFYUI_SECONDARY")
        put_legacy(spark, "workflow_file", "SPARK_WORKFLOW_FILE")

    # Direct canonical/alias keys are authoritative. This is what the Settings
    # page writes, and it must not be clobbered by stale legacy sections.
    for k, v in raw.items():
        if isinstance(k, str):
            put(k, v)

    return normalized


def _save_json_config(data: Dict[str, Any]):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = _normalize_overrides(data)
    if CONFIG_PATH.exists():
        try:
            CONFIG_BACKUP_PATH.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        except IOError:
            pass
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    tmp_path.replace(CONFIG_PATH)


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
    current = _normalize_overrides(_load_json_config())
    for k, v in updates.items():
        canonical = KEY_ALIASES.get(k, k)
        if canonical in CONFIGURABLE_KEYS:
            if canonical in SECRET_KEYS and str(v or "").strip() == "" and current.get(canonical):
                continue
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
        if k in CONFIGURABLE_KEYS:
            os.environ[k] = str(v)
