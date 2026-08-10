"""G5 — Estimated spend meter for cloud image APIs (OpenAI / Gemini).

Simple counter + cost estimate from configurable per-image rates.
Persists under data/cost_meter.json (repo-local; never ~/.hermes).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Rough public list prices (USD per image) — override via env or rates file.
DEFAULT_RATES_USD: Dict[str, Dict[str, float]] = {
    "openai": {
        "gpt-image-1": 0.04,
        "gpt-image-1-mini": 0.02,
        "gpt-image-2": 0.04,
        "dall-e-3": 0.04,
        "dall-e-2": 0.02,
        "default": 0.04,
    },
    "gemini": {
        "gemini-2.0-flash-preview-image-generation": 0.039,
        "gemini-2.5-flash-image": 0.039,
        "gemini-2.5-flash-image-preview": 0.039,
        "imagen-3.0-generate-002": 0.04,
        "default": 0.04,
    },
}

_LOCK = threading.Lock()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_store_path(root: Optional[Path] = None) -> Path:
    base = (root or _repo_root()) / "data"
    base.mkdir(parents=True, exist_ok=True)
    return base / "cost_meter.json"


def rates_override_path(root: Optional[Path] = None) -> Path:
    return (root or _repo_root()) / "data" / "cost_rates.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def get_rates(root: Optional[Path] = None) -> Dict[str, Dict[str, float]]:
    """Merge default rates with optional file + env overrides."""
    rates: Dict[str, Dict[str, float]] = {
        p: dict(models) for p, models in DEFAULT_RATES_USD.items()
    }
    override = _load_json(rates_override_path(root))
    for provider, models in (override.get("rates") or override or {}).items():
        if not isinstance(models, dict):
            continue
        key = str(provider).lower()
        rates.setdefault(key, {})
        for model, price in models.items():
            try:
                rates[key][str(model)] = float(price)
            except (TypeError, ValueError):
                continue

    openai_env = (os.getenv("CINESMITH_COST_OPENAI_IMAGE_USD") or "").strip()
    gemini_env = (os.getenv("CINESMITH_COST_GEMINI_IMAGE_USD") or "").strip()
    if openai_env:
        try:
            rates.setdefault("openai", {})["default"] = float(openai_env)
        except ValueError:
            pass
    if gemini_env:
        try:
            rates.setdefault("gemini", {})["default"] = float(gemini_env)
        except ValueError:
            pass
    return rates


def estimate_cost_usd(
    provider: str,
    model: str = "",
    units: int = 1,
    *,
    root: Optional[Path] = None,
    rates: Optional[Dict[str, Dict[str, float]]] = None,
) -> float:
    rates = rates or get_rates(root)
    prov = (provider or "").strip().lower()
    if prov in {"nano_banana", "nanobanana"}:
        prov = "gemini"
    model_key = (model or "").strip()
    table = rates.get(prov) or {}
    unit_price = table.get(model_key)
    if unit_price is None:
        # fuzzy: match by substring
        low = model_key.lower()
        for k, v in table.items():
            if k != "default" and k.lower() in low:
                unit_price = v
                break
    if unit_price is None:
        unit_price = float(table.get("default") or 0.0)
    return round(float(unit_price) * max(1, int(units or 1)), 6)


def _empty_store() -> Dict[str, Any]:
    return {
        "version": 1,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "total_calls": 0,
        "total_success": 0,
        "total_failed": 0,
        "total_units": 0,
        "estimated_spend_usd": 0.0,
        "by_provider": {},
        "recent": [],
    }


def load_meter(root: Optional[Path] = None, path: Optional[Path] = None) -> Dict[str, Any]:
    store_path = path or default_store_path(root)
    data = _load_json(store_path)
    if not data:
        return _empty_store()
    data.setdefault("total_calls", 0)
    data.setdefault("total_success", 0)
    data.setdefault("total_failed", 0)
    data.setdefault("total_units", 0)
    data.setdefault("estimated_spend_usd", 0.0)
    data.setdefault("by_provider", {})
    data.setdefault("recent", [])
    return data


def save_meter(data: Dict[str, Any], root: Optional[Path] = None, path: Optional[Path] = None) -> None:
    store_path = path or default_store_path(root)
    data["updated_at"] = _now_iso()
    _save_json(store_path, data)


def record_image_call(
    provider: str,
    model: str = "",
    *,
    units: int = 1,
    success: bool = True,
    estimated_usd: Optional[float] = None,
    meta: Optional[Dict[str, Any]] = None,
    root: Optional[Path] = None,
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record one cloud image API call and return the updated summary."""
    prov = (provider or "unknown").strip().lower()
    if prov in {"nano_banana", "nanobanana"}:
        prov = "gemini"
    model_key = (model or "default").strip() or "default"
    units_n = max(1, int(units or 1))
    cost = (
        float(estimated_usd)
        if estimated_usd is not None
        else (estimate_cost_usd(prov, model_key, units_n, root=root) if success else 0.0)
    )
    if not success:
        cost = float(estimated_usd) if estimated_usd is not None else 0.0

    entry = {
        "id": f"cost_{uuid.uuid4().hex[:10]}",
        "timestamp": _now_iso(),
        "provider": prov,
        "model": model_key,
        "units": units_n,
        "success": bool(success),
        "estimated_usd": round(cost, 6),
        "meta": meta or {},
    }

    with _LOCK:
        data = load_meter(root=root, path=path)
        data["total_calls"] = int(data.get("total_calls") or 0) + 1
        data["total_units"] = int(data.get("total_units") or 0) + units_n
        if success:
            data["total_success"] = int(data.get("total_success") or 0) + 1
            data["estimated_spend_usd"] = round(
                float(data.get("estimated_spend_usd") or 0.0) + cost, 6
            )
        else:
            data["total_failed"] = int(data.get("total_failed") or 0) + 1

        by_p = data.setdefault("by_provider", {})
        bucket = by_p.setdefault(
            prov,
            {
                "calls": 0,
                "success": 0,
                "failed": 0,
                "units": 0,
                "estimated_spend_usd": 0.0,
                "by_model": {},
            },
        )
        bucket["calls"] = int(bucket.get("calls") or 0) + 1
        bucket["units"] = int(bucket.get("units") or 0) + units_n
        if success:
            bucket["success"] = int(bucket.get("success") or 0) + 1
            bucket["estimated_spend_usd"] = round(
                float(bucket.get("estimated_spend_usd") or 0.0) + cost, 6
            )
        else:
            bucket["failed"] = int(bucket.get("failed") or 0) + 1

        models = bucket.setdefault("by_model", {})
        m = models.setdefault(
            model_key,
            {"calls": 0, "success": 0, "failed": 0, "units": 0, "estimated_spend_usd": 0.0},
        )
        m["calls"] = int(m.get("calls") or 0) + 1
        m["units"] = int(m.get("units") or 0) + units_n
        if success:
            m["success"] = int(m.get("success") or 0) + 1
            m["estimated_spend_usd"] = round(float(m.get("estimated_spend_usd") or 0.0) + cost, 6)
        else:
            m["failed"] = int(m.get("failed") or 0) + 1

        recent = list(data.get("recent") or [])
        recent.append(entry)
        data["recent"] = recent[-80:]
        save_meter(data, root=root, path=path)

    return get_summary(root=root, path=path)


def reset_meter(root: Optional[Path] = None, path: Optional[Path] = None) -> Dict[str, Any]:
    with _LOCK:
        data = _empty_store()
        save_meter(data, root=root, path=path)
    return get_summary(root=root, path=path)


def get_summary(root: Optional[Path] = None, path: Optional[Path] = None) -> Dict[str, Any]:
    data = load_meter(root=root, path=path)
    rates = get_rates(root)
    spend = float(data.get("estimated_spend_usd") or 0.0)
    return {
        "status": "ok",
        "estimated_spend_usd": spend,
        "estimated_spend_display": f"${spend:.2f}",
        "total_calls": int(data.get("total_calls") or 0),
        "total_success": int(data.get("total_success") or 0),
        "total_failed": int(data.get("total_failed") or 0),
        "total_units": int(data.get("total_units") or 0),
        "by_provider": data.get("by_provider") or {},
        "recent": list(data.get("recent") or [])[-20:],
        "rates_usd": rates,
        "updated_at": data.get("updated_at"),
        "created_at": data.get("created_at"),
        "note": "Estimates only — actual invoice may differ. Configure rates via data/cost_rates.json or CINESMITH_COST_*_IMAGE_USD.",
    }


class CostMeter:
    """Object-oriented façade (optional) for callers that prefer an instance."""

    def __init__(self, root: Optional[Path] = None, path: Optional[Path] = None) -> None:
        self.root = root
        self.path = path

    def record(self, provider: str, model: str = "", **kwargs: Any) -> Dict[str, Any]:
        return record_image_call(provider, model, root=self.root, path=self.path, **kwargs)

    def summary(self) -> Dict[str, Any]:
        return get_summary(root=self.root, path=self.path)

    def reset(self) -> Dict[str, Any]:
        return reset_meter(root=self.root, path=self.path)
