"""Route Comfy jobs by capability: Spark = video/H3, 3090s = stills.

Live campaign/video/produce submit must use this, not round-robin and not
first-healthy-host across mixed boxes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

import httpx

from core.bridge.runtime_config import get_raw_config
from core.dispatch.comfy_client import ComfyUIClient
from core.dispatch.workflows import capability_for_workflow

logger = logging.getLogger(__name__)

H3_NODE_TYPES = (
    "MiniMaxH3ImageToVideo",
    "MiniMaxH3ReferenceToVideo",
    "EmptyMiniMaxH3LatentAV",
    "MiniMaxH3SigmaShift",
)


def _norm_url(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    if not text:
        return ""
    if not text.startswith(("http://", "https://")):
        text = "http://" + text
    return text


def _dedupe(urls: Sequence[str]) -> List[str]:
    out: List[str] = []
    for url in urls:
        clean = _norm_url(url)
        if clean and clean not in out:
            out.append(clean)
    return out


class CapabilityRouter:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None) -> None:
        self.cfg = cfg if cfg is not None else get_raw_config()

    def spark_url(self) -> str:
        return _norm_url(self.cfg.get("COMFYUI_PRIMARY"))

    def stills_a_url(self) -> str:
        return _norm_url(self.cfg.get("COMFYUI_STILLS_A") or self.cfg.get("COMFYUI_SECONDARY"))

    def stills_b_url(self) -> str:
        return _norm_url(self.cfg.get("COMFYUI_STILLS_B"))

    def spark_urls(self) -> List[str]:
        return _dedupe([self.spark_url()])

    def stills_urls(self) -> List[str]:
        urls = _dedupe([self.stills_a_url(), self.stills_b_url()])
        if not urls:
            return list(self.spark_urls())
        return urls

    def urls_for(self, capability: str) -> List[str]:
        cap = (capability or "stills").strip().lower()
        if cap in {"spark", "video", "h3"}:
            return self.spark_urls()
        return self.stills_urls()

    def urls_for_workflow(self, workflow_id: str) -> List[str]:
        return self.urls_for(capability_for_workflow(workflow_id))

    async def _probe(self, url: str) -> Dict[str, Any]:
        client = ComfyUIClient(url)
        ok, info = await client.check_health()
        queue_depth = None
        nodes: List[str] = []
        if ok:
            try:
                async with httpx.AsyncClient() as http:
                    queue_resp = await http.get(f"{url}/queue", timeout=2.0)
                    if queue_resp.status_code == 200:
                        payload = queue_resp.json()
                        running = payload.get("queue_running") if isinstance(payload, dict) else []
                        pending = payload.get("queue_pending") if isinstance(payload, dict) else []
                        queue_depth = len(running or []) + len(pending or [])
                    obj_resp = await http.get(f"{url}/object_info", timeout=3.0)
                    if obj_resp.status_code == 200:
                        data = obj_resp.json()
                        if isinstance(data, dict):
                            nodes = [str(k) for k in data.keys()]
            except Exception as exc:
                logger.debug("probe extras failed for %s: %s", url, exc)
        gpu = ""
        if isinstance(info, dict):
            devices = info.get("devices") if isinstance(info.get("devices"), list) else []
            if devices and isinstance(devices[0], dict):
                gpu = str(devices[0].get("name") or devices[0].get("index") or "")
        return {
            "url": url,
            "ok": bool(ok),
            "queue_depth": queue_depth,
            "gpu": gpu,
            "nodes": nodes,
            "error": "" if ok else str((info or {}).get("error") or "unreachable"),
        }

    @staticmethod
    def _has_nodes(probe: Dict[str, Any], required: Sequence[str]) -> bool:
        if not required:
            return True
        have = {str(n) for n in (probe.get("nodes") or [])}
        if not have:
            # object_info unavailable — do not treat as a hard miss
            return True
        return any(name in have for name in required)

    async def host_for(
        self,
        capability: str,
        *,
        require_nodes: Sequence[str] = (),
        allow_stills_fallback: bool = False,
    ) -> str:
        """Return a healthy host URL for the capability, or empty string."""
        cap = (capability or "stills").strip().lower()
        required = tuple(require_nodes)
        if cap in {"spark", "video", "h3"} and not required and "h3" in cap:
            required = H3_NODE_TYPES
        candidates = self.urls_for(cap)
        probes: List[Dict[str, Any]] = []
        for url in candidates:
            probe = await self._probe(url)
            if probe["ok"] and self._has_nodes(probe, required):
                probes.append(probe)
        if not probes and cap in {"stills", "image", "board"}:
            # Flux on Spark is allowed if the 3090s are down.
            for url in self.spark_urls():
                if url in candidates:
                    continue
                probe = await self._probe(url)
                if probe["ok"]:
                    probes.append(probe)
                    break
        if not probes and allow_stills_fallback and cap in {"spark", "video", "h3"}:
            logger.warning("Spark unavailable; stills fallback requested for %s", cap)
        if not probes:
            return ""
        probes.sort(key=lambda row: (row.get("queue_depth") is None, row.get("queue_depth") or 0))
        return str(probes[0]["url"])

    async def host_for_workflow(self, workflow_id: str, *, require_h3: bool = False) -> str:
        cap = capability_for_workflow(workflow_id)
        required = H3_NODE_TYPES if require_h3 or "h3" in str(workflow_id).lower() or "minimax" in str(workflow_id).lower() else ()
        return await self.host_for(cap, require_nodes=required)

    async def connect_status(self) -> Dict[str, Any]:
        spark = self.spark_url()
        stills_a = self.stills_a_url()
        stills_b = self.stills_b_url()
        rows = {
            "spark": {"url": spark, "configured": bool(spark), "label": "Spark"},
            "stills_a": {"url": stills_a, "configured": bool(stills_a), "label": "3090 A"},
            "stills_b": {"url": stills_b, "configured": bool(stills_b), "label": "3090 B"},
        }
        for key, row in rows.items():
            if not row["url"]:
                row.update({"ok": False, "queue_depth": None, "gpu": "", "has_h3": False, "error": "not configured"})
                continue
            probe = await self._probe(row["url"])
            row.update(
                {
                    "ok": probe["ok"],
                    "queue_depth": probe["queue_depth"],
                    "gpu": probe["gpu"],
                    "has_h3": any(name in (probe.get("nodes") or []) for name in H3_NODE_TYPES),
                    "error": probe["error"],
                }
            )
        return rows


async def client_for_workflow(workflow_id: str) -> ComfyUIClient:
    router = CapabilityRouter()
    host = await router.host_for_workflow(workflow_id)
    if not host:
        raise RuntimeError(f"no_healthy_host:{capability_for_workflow(workflow_id)}")
    return ComfyUIClient(host)
