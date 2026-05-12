import json
import uuid
import time
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, UploadFile, Form, File, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from fastapi.staticfiles import StaticFiles
import base64
import os
import re
import random
import shutil
import zipfile
from pathlib import Path
import httpx
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
from urllib.parse import urlsplit, urlunsplit

# Load .env file at import time
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# ... (existing imports from top of file)
from core.bridge.kimi_vl_client import KimiVLClient
from core.bridge.lmstudio_client import LMStudioClient
from core.bridge.config_manager import ConfigManager
from core.bridge.runtime_config import get_raw_config
from core.hermes.memory.episodic_memory import EpisodicMemory
from core.hermes.memory.semantic_memory import SemanticMemory
from core.skills.skill_registry import SkillRegistry
from forge_nexus.mcp.handlers import ForgeMCPHandlers
import asyncio
from pydantic import BaseModel, Field

from .memory_api import (
    get_memory_stats,
    get_event_timeline,
    get_graph_data,
    search_memory,
    get_memory_health,
)
from .api.prompt_builder import load_banks, build_recipe, generate_random_recipe, save_banks
from .api.spark_monitor import monitor as spark_monitor
from core.dispatch.comfy_client import ComfyUIClient
from core.affiliate.local_higgsfield import LocalHiggsfieldAdapter
from core.hermes.pipeline import HermesCampaignService, CampaignRequest, HermesAuditService, HermesVideoService
from core.hermes.pipeline.director_service import KimiDirectorService
from core.prompts.prompt_standards import apply_model_prompt_standard
from core.storyboard.image_providers import StoryboardImageProvider
from core.dispatch.lora_presets import lora_preset_payload
from core.hermes.platform_skills import (
    carousel_caption_text,
    detect_platform_skill,
    generate_hook_ideas,
)

STATIC_DIR = Path(__file__).parent / "static"
REPO_ROOT = Path(__file__).parent.parent.resolve()
MEDIA_ROOT = Path(os.getenv("FORGE_MEDIA_ROOT", "/Users/zgbot/Desktop/FORGE_NPS_MEDIA"))
MEDIA_IMAGES = MEDIA_ROOT / "images"
MEDIA_IMAGES.mkdir(parents=True, exist_ok=True)
MEDIA_VIDEOS = MEDIA_ROOT / "videos"
MEDIA_VIDEOS.mkdir(parents=True, exist_ok=True)
MEDIA_IDENTITY_ASSETS = MEDIA_ROOT / "identity_assets"
MEDIA_IDENTITY_ASSETS.mkdir(parents=True, exist_ok=True)
MEDIA_IDENTITY_TEMPLATES = MEDIA_ROOT / "identity_templates"
MEDIA_IDENTITY_TEMPLATES.mkdir(parents=True, exist_ok=True)
NEXUS_DB = REPO_ROOT / ".forge-nexus" / "forge.db"
SCRIPT_PROJECTS_DIR = REPO_ROOT / "data" / "scripts"
SCRIPT_PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
_NEXUS_HANDLERS: Optional[ForgeMCPHandlers] = None

# --- Models & State Management ---

class ConnectionManager:
    def __init__(self):
        # session_id -> list of websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def broadcast(self, message: dict, session_id: str):
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                await connection.send_json(message)

manager = ConnectionManager()
hermes_manager = ConnectionManager()  # Dedicated WebSocket for Hermes events
spark_ws_manager = ConnectionManager()  # Dedicated WebSocket for Spark events

# --- Endpoints ---

def _legacy_disabled(route: str, use_endpoint: str) -> JSONResponse:
    return JSONResponse(
        status_code=410,
        content={
            "status": "legacy_disabled",
            "route": route,
            "message": "This legacy endpoint is disabled for hackathon pipeline integrity.",
            "use_endpoint": use_endpoint,
        },
    )


def _normalize_lmstudio_base_url(host: str = "", port: Any = None) -> str:
    cfg = get_raw_config()
    value = (host or str(cfg.get("LMSTUDIO_HOST", "") or "") or os.getenv("LMSTUDIO_HOST", "") or "http://localhost").strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    raw_port = port if port not in (None, "", 0, "0") else (str(cfg.get("LMSTUDIO_PORT", "") or "") or os.getenv("LMSTUDIO_PORT", "") or "1234")
    port_text = str(raw_port or "").strip()
    parts = urlsplit(value)
    netloc = parts.netloc
    try:
        has_port = parts.port is not None
    except ValueError:
        has_port = ":" in netloc.rsplit("@", 1)[-1]
    if port_text and not has_port:
        netloc = f"{netloc}:{port_text}"
    path = parts.path.rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1"):
        if path.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break
    return urlunsplit((parts.scheme, netloc, path, "", ""))


def _truthy_config(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "local", "lmstudio"}


def _lmstudio_base_candidates(host: str = "", port: Any = None) -> List[str]:
    cfg = get_raw_config()
    primary = _normalize_lmstudio_base_url(host, port)
    candidates = [primary]
    parsed = urlsplit(primary)
    try:
        detected_port = parsed.port
    except ValueError:
        detected_port = None
    fallback_port = str(
        port
        if port not in (None, "", 0, "0")
        else (detected_port or cfg.get("LMSTUDIO_PORT", "") or os.getenv("LMSTUDIO_PORT", "") or "1234")
    ).strip()
    for local_host in ("127.0.0.1", "localhost"):
        candidates.append(_normalize_lmstudio_base_url(f"http://{local_host}", fallback_port))
    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            deduped.append(candidate)
    return deduped


class NexusQueryRequest(BaseModel):
    query: str
    top_n: int = 8
    include_impact: bool = True


class NexusImpactRequest(BaseModel):
    asset_id: str


class ClearQueueRequest(BaseModel):
    comfy_url: str


class ComfyUITestRequest(BaseModel):
    host: str

class ComfyRecoverPromptRequest(BaseModel):
    prompt_id: str
    campaign_id: str = ""
    host: str = ""


class ComfyRecoverHistoryRequest(BaseModel):
    campaign_id: str = ""
    host: str = ""
    limit: int = 250


@app.post("/api/renders/audit-batch")
async def api_renders_audit_batch(request: Request):
    """
    Legacy endpoint compatibility shim.
    Canonical endpoint is /api/audit/reprocess.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    shot_ids = body.get("shot_ids", []) if isinstance(body, dict) else []
    if isinstance(shot_ids, list) and shot_ids:
        service = _make_audit_service()
        return await service.reprocess([str(s) for s in shot_ids if str(s).strip()])
    return _legacy_disabled("/api/renders/audit-batch", "/api/audit/reprocess")

@app.get("/memory")
async def get_memory_page():
    return FileResponse(STATIC_DIR / "memory.html")

@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    return _legacy_disabled(f"/api/session/{session_id}", "/api/campaigns")

@app.get("/api/skills")
async def get_skills():
    try:
        from core.skills.skill_loader import SkillLoader
        return {"status": "ok", "skills": SkillLoader().list_skills()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"skill_loader_error:{e}")

@app.get("/api/reasoning/{shot_id}")
async def get_reasoning(shot_id: str):
    return _legacy_disabled(f"/api/reasoning/{shot_id}", "/api/campaigns/{campaign_id}/agent-exchanges")

# --- Memory API Endpoints ---

@app.get("/api/memory/stats")
async def api_memory_stats():
    """Memory statistics for dashboard cards."""
    return get_memory_stats()


@app.get("/api/stats")
async def api_stats():
    """Sidebar/system stats used by dashboard UI."""
    ram_pct = None
    try:
        import psutil  # type: ignore
        ram_pct = round(float(psutil.virtual_memory().percent), 1)
    except Exception:
        ram_pct = None
    return {
        "shots_in_store": len(_SHOTS_STORE),
        "chat_sessions": 0,
        "ram_percent": ram_pct,
    }

@app.get("/api/memory/timeline")
async def api_memory_timeline(limit: int = Query(50, ge=1, le=200)):
    """Recent episodic events formatted for timeline display."""
    return get_event_timeline(limit)

@app.get("/api/memory/insights")
async def api_memory_insights():
    """All semantic insights."""
    from .memory_api import load_insights
    return load_insights()

@app.get("/api/memory/graph")
async def api_memory_graph():
    """Graph data (nodes + edges) for Cytoscape.js visualization."""
    return get_graph_data()

@app.get("/api/memory/search")
async def api_memory_search(q: str = Query(..., min_length=1)):
    """Search events and insights by text."""
    return search_memory(q)


@app.get("/api/memory/health")
async def api_memory_health():
    return get_memory_health()


@app.post("/api/nexus/query")
async def api_nexus_query(req: NexusQueryRequest):
    query = (req.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query required")
    if not NEXUS_DB.exists():
        raise HTTPException(status_code=503, detail=f"Forge Nexus index missing at {NEXUS_DB}")

    handlers = _get_nexus_handlers()
    res = handlers.handle_forge_query({"query": query})
    if "error" in res:
        raise HTTPException(status_code=500, detail=str(res["error"]))

    raw_results = res.get("results", []) if isinstance(res, dict) else []
    top_n = max(1, min(int(req.top_n or 8), 30))
    top = raw_results[:top_n] if isinstance(raw_results, list) else []
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    root_id = f"nexus_q::{query[:120]}"
    nodes.append({
        "id": root_id,
        "label": f"Nexus Query: {query}",
        "type": "query",
        "score": 1.0,
    })

    for r in top:
        rid = str(r.get("id", "")).strip()
        if not rid:
            continue
        score = float(r.get("score", 0.0) or 0.0)
        rnode = {
            "id": rid,
            "label": rid,
            "type": _nexus_type_from_id(rid),
            "score": score,
        }
        if rnode not in nodes:
            nodes.append(rnode)
        edges.append({
            "id": f"{root_id}->{rid}:query_match",
            "source": root_id,
            "target": rid,
            "type": "query_match",
            "weight": max(1.0, round(score * 5.0, 2)),
        })

        if req.include_impact:
            impact = handlers.handle_forge_impact({"asset_id": rid})
            impacted = impact.get("affected_entities", []) if isinstance(impact, dict) else []
            if isinstance(impacted, list):
                for dep in impacted[:40]:
                    did = str(dep or "").strip()
                    if not did:
                        continue
                    dtype = _nexus_type_from_id(did)
                    dnode = {"id": did, "label": did, "type": dtype, "score": 0.5}
                    if dnode not in nodes:
                        nodes.append(dnode)
                    edges.append({
                        "id": f"{did}->{rid}:depends_on",
                        "source": did,
                        "target": rid,
                        "type": "depends_on",
                        "weight": 1.0,
                    })

    return {
        "status": "ok",
        "query": query,
        "count": len(top),
        "results": top,
        "overlay": {
            "nodes": nodes,
            "edges": edges,
        },
    }


@app.post("/api/nexus/impact")
async def api_nexus_impact(req: NexusImpactRequest):
    asset_id = (req.asset_id or "").strip()
    if not asset_id:
        raise HTTPException(status_code=400, detail="asset_id required")
    if not NEXUS_DB.exists():
        raise HTTPException(status_code=503, detail=f"Forge Nexus index missing at {NEXUS_DB}")
    handlers = _get_nexus_handlers()
    res = handlers.handle_forge_impact({"asset_id": asset_id})
    if "error" in res:
        raise HTTPException(status_code=500, detail=str(res["error"]))
    affected = res.get("affected_entities", []) if isinstance(res, dict) else []
    return {
        "status": "ok",
        "asset_id": asset_id,
        "affected_entities": affected,
        "count": len(affected) if isinstance(affected, list) else 0,
    }

@app.post("/api/memory/consolidate")
async def api_memory_consolidate():
    """Trigger memory consolidation (dream process)."""
    from core.hermes.hermes_agent import HermesAgent
    hermes = HermesAgent()
    insights = await hermes.consolidate_session()
    return {
        "status": "consolidated",
        "new_insights": len(insights),
        "insights": insights,
    }

@app.post("/api/queue/clear")
async def api_queue_clear(req: ClearQueueRequest):
    """Cancels all pending jobs in the specified ComfyUI instance."""
    from core.dispatch.comfy_client import ComfyUIClient
    client = ComfyUIClient(req.comfy_url)
    try:
        success = await client.cancel_all() 
        if success:
            return {"status": "cleared", "message": "All pending jobs cancelled."}
        else:
            raise HTTPException(status_code=502, detail="ComfyUI failed to clear queue.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/renders")
async def api_renders():
    """Return available render thumbnails with metadata."""
    repo_root = Path(__file__).parent.parent
    results = []
    
    # Scan primary renders dir
    renders_dir = repo_root / "data" / "renders"
    if renders_dir.exists():
        for f in sorted(renders_dir.iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                meta_path = f.with_suffix(f.suffix + ".json")
                meta = {"score": 0, "status": "ready", "prompt": f.stem}
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as mf:
                            meta = json.load(mf)
                    except Exception:
                        pass
                results.append({
                    "src": f"/renders/{f.name}",
                    "prompt": meta.get("prompt", f.stem),
                    "score": meta.get("score", 0),
                    "status": meta.get("status", "ready"),
                })
    
    # Scan Sienna Nomad legacy renders
    sienna_dir = repo_root / "dashboard" / "static" / "renders" / "sienna"
    if sienna_dir.exists():
        for f in sorted(sienna_dir.iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                sidecar = f.with_suffix(f.suffix + ".json")
                meta = {"score": 0, "status": "unaudited", "prompt": f"Sienna Nomad — {f.stem}"}
                if sidecar.exists():
                    try:
                        with open(sidecar, "r", encoding="utf-8") as mf:
                            meta = json.load(mf)
                    except Exception:
                        pass
                results.append({
                    "src": f"/static/renders/sienna/{f.name}",
                    "prompt": meta.get("prompt", f"Sienna Nomad — {f.stem}"),
                    "score": meta.get("score", 0),
                    "status": meta.get("status", "unaudited"),
                })

    # Scan campaigns folder recursively
    campaigns_root = repo_root / "data" / "campaigns"
    if campaigns_root.exists():
        for campaign_dir in sorted(campaigns_root.iterdir()):
            if campaign_dir.is_dir():
                campaign_name = campaign_dir.name
                # Recursively find all images in this campaign
                for f in sorted(campaign_dir.rglob("*")):
                    if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                        meta_path = f.with_suffix(f.suffix + ".json")
                        meta = {"score": 0, "status": "ready", "prompt": f.stem}
                        if meta_path.exists():
                            try:
                                with open(meta_path, "r", encoding="utf-8") as mf:
                                    meta = json.load(mf)
                            except Exception:
                                pass
                        rel = f.relative_to(campaigns_root)
                        results.append({
                            "src": f"/campaigns/{rel}",
                            "prompt": meta.get("prompt", f.stem),
                            "score": meta.get("score", 0),
                            "status": meta.get("status", "ready"),
                            "campaign": campaign_name,
                        })

    # Scan renders/campaigns folder recursively (data/renders/campaigns/**/*.png)
    renders_campaign_root = repo_root / "data" / "renders" / "campaigns"
    if renders_campaign_root.exists():
        for campaign_dir in sorted(renders_campaign_root.iterdir()):
            if not campaign_dir.is_dir():
                continue
            # Also scan nested sub-campaigns recursively
            for f in sorted(campaign_dir.rglob("*")):
                if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                    meta_path = f.with_suffix(f.suffix + ".json")
                    meta = {"score": 0, "status": "ready", "prompt": f.stem}
                    if meta_path.exists():
                        try:
                            with open(meta_path, "r", encoding="utf-8") as mf:
                                meta = json.load(mf)
                        except Exception:
                            pass
                    rel = f.relative_to(renders_campaign_root)
                    results.append({
                        "src": f"/renders/campaigns/{rel}",
                        "prompt": meta.get("prompt", f.stem),
                        "score": meta.get("score", 0),
                        "status": meta.get("status", "ready"),
                        "campaign": campaign_dir.name,
                    })

    return results

# --- WebSocket ---

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket, session_id)
    try:
        while True:
            await websocket.receive_text()
            await websocket.send_json({
                "type": "LEGACY_DISABLED",
                "payload": {
                    "status": "legacy_disabled",
                    "message": "Legacy websocket stream is disabled in production.",
                },
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)

# --- Startup & Mounts ---

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/external-renders", StaticFiles(directory=str(MEDIA_IMAGES)), name="external-renders")
app.mount("/media-assets", StaticFiles(directory=str(MEDIA_ROOT)), name="media-assets")
app.mount("/identity-assets", StaticFiles(directory=str(MEDIA_IDENTITY_ASSETS)), name="identity-assets")

_data_renders_dir = Path(__file__).parent.parent / "data" / "renders"
if _data_renders_dir.exists():
    app.mount("/renders", StaticFiles(directory=str(_data_renders_dir)), name="data-renders")

# Serve campaigns folder for render outputs
_campaigns_dir = Path(__file__).parent.parent / "data" / "campaigns"
_campaigns_dir.mkdir(parents=True, exist_ok=True)
app.mount("/campaigns", StaticFiles(directory=str(_campaigns_dir)), name="campaigns")

@app.get("/")
async def root():
    """
    Serve the active dashboard UI.
    The current app frontend lives in dashboard/templates/index.html.
    """
    template_index = Path(__file__).parent / "templates" / "index.html"
    if template_index.exists():
        return FileResponse(template_index)
    return FileResponse(STATIC_DIR / "index.html")



class ShotDispatchRequest(BaseModel):
    shot_id: str
    prompt: str
    seed: Optional[int] = None

class ProductListResponse(BaseModel):
    products: List[Dict[str, Any]]


class AssetVaultPackageRequest(BaseModel):
    name: str
    description: str = ""
    kind: str = "package"
    element_type: str = "product"
    asset_type: str = "product"
    character_ids: List[str] = Field(default_factory=list)
    character_refs: List[Dict[str, Any]] = Field(default_factory=list)
    references: List[Dict[str, Any]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    notes: str = ""
    brand_rules: str = ""
    style_rules: str = ""
    logo_notes: str = ""
    font_notes: str = ""
    prop_notes: str = ""
    location_notes: str = ""
    status: str = "draft"


class AssetVaultCharacterLinkRequest(BaseModel):
    role: str = "reference"
    notes: str = ""

class VisualAuditRequest(BaseModel):
    frame_base64: str
    mime_type: str
    shot_id: str
    expected_description: str
    lore_excerpt: str
    session_id: str = "unknown"

class VisualAuditResponse(BaseModel):
    is_consistent: bool | None
    confidence_score: float
    error_category: str | None
    mismatch_details: str
    suggested_fix: str | None
    visual_truth_used: bool = True

@app.post("/api/visual-audit", response_model=VisualAuditResponse)
async def visual_audit(req: VisualAuditRequest):
    # Validate base64
    try:
        decoded = base64.b64decode(req.frame_base64)
        if len(decoded) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Frame too large. Max 10MB.")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 frame data.")
    
    # Call Kimi VL
    vl_client = KimiVLClient() # It should handle its own config via internal init/config_manager
    
    # Check for dummy key (as per spec)
    if not vl_client.api_key or vl_client.api_key == "dummy_key":
        return VisualAuditResponse(
            is_consistent=None,
            confidence_score=0.0,
            error_category="no_api_key",
            mismatch_details="KIMI_API_KEY not configured. Set a real key in .env",
            suggested_fix=None,
        )
    
    verdict = await vl_client.audit_frame(
        image_base64=req.frame_base64,
        mime_type=req.mime_type,
        expected_description=req.expected_description,
        lore_excerpt=req.lore_excerpt,
        shot_id=req.shot_id
    )
    
    # Log to Hermes episodic memory
    episodic = EpisodicMemory()
    episodic.record({
        "session_id": req.session_id,
        "shot_id": req.shot_id,
        "event_type": "visual_audit",
        "concept": req.expected_description,
        "kernel_id": "kimi_vl_video_frame",
        "success": verdict.get("is_consistent", False),
        "error_category": verdict.get("error_category") or "visual_mismatch",
        "fix_applied": verdict.get("suggested_fix") or "none",
        "audit_score": verdict.get("confidence_score", 0.0),
        "mismatch_details": verdict.get("mismatch_details", ""),
    })
    
    return VisualAuditResponse(**verdict, visual_truth_used=True)


# --- Models API (Local vs API switch) ---

_model_mode = os.getenv("USE_LOCAL_MODELS", "false").lower() == "true"

class ModelModeRequest(BaseModel):
    mode: str  # "local" or "api"

@app.get("/api/models/status")
async def models_status():
    """Current model mode + availability of both backends."""
    cm = ConfigManager()
    local = LMStudioClient()
    api_key = cm.get_kimi_api_key()

    local_models = local.list_models() if local.is_available else []
    api_ready = bool(api_key and api_key != "dummy_key")

    return {
        "mode": "local" if _model_mode else "api",
        "local": {
            "available": local.is_available,
            "host": local.base_url,
            "models": local_models,
        },
        "api": {
            "available": api_ready,
            "endpoint": cm.get_nim_endpoint(),
            "models": [
                cm.get("KIMI_INSTRUCT_MODEL", "moonshotai/kimi-k2.5"),
                cm.get("KIMI_THINKING_MODEL", "moonshotai/kimi-k2.5"),
                cm.get("KIMI_VISUAL_MODEL", "moonshotai/kimi-k2.5"),
            ],
        },
    }

@app.post("/api/models/mode")
async def set_model_mode(req: ModelModeRequest):
    """Switch between local (LM Studio) and API (Kimi/NIM) backends."""
    global _model_mode
    if req.mode not in ("local", "api"):
        raise HTTPException(status_code=400, detail="mode must be 'local' or 'api'")
    _model_mode = (req.mode == "local")
    os.environ["USE_LOCAL_MODELS"] = "true" if _model_mode else "false"
    return {"mode": req.mode, "switched": True}

@app.get("/api/models/test-local")
async def test_local_models():
    """Ping LM Studio and return loaded models."""
    local = LMStudioClient()
    if not local.is_available:
        raise HTTPException(status_code=503, detail="LM Studio not reachable")
    return {
        "host": local.base_url,
        "models": local.list_models(),
        "embed_model": local.embed_model,
        "chat_model": local.chat_model,
    }

@app.get("/api/models/test-api")
async def test_api_models():
    """Ping NIM endpoint and verify API key."""
    cm = ConfigManager()
    from core.bridge.nim_client import NIMClient
    nim = NIMClient(cm.get_nim_endpoint())
    health = nim.check_health()
    return {
        "endpoint": cm.get_nim_endpoint(),
        "healthy": health,
        "api_key_configured": bool(cm.get_kimi_api_key() and cm.get_kimi_api_key() != "dummy_key"),
    }


# --- Prompt Builder Endpoints ---

@app.get("/api/banks")
async def api_banks(mode: str = Query("character")):
    """Load all variation bank items."""
    return load_banks(mode)


class SaveBanksRequest(BaseModel):
    mode: str = "character"
    banks: Dict[str, Any]


@app.post("/api/banks")
async def api_save_banks(req: SaveBanksRequest):
    """Save editable variation bank items."""
    saved = save_banks(req.mode, req.banks)
    return {"status": "success", "saved": saved}


class BuildRecipeRequest(BaseModel):
    selections: Dict[str, str]
    character_name: Optional[str] = None
    mode: str = "character"


@app.post("/api/build-recipe")
async def api_build_recipe(req: BuildRecipeRequest):
    """Build a prompt recipe from bank selections."""
    recipe = build_recipe(
        selections=req.selections,
        character_name=req.character_name,
        mode=req.mode,
        index=0,
    )
    return recipe


class SubmitRecipeRequest(BaseModel):
    recipe: Dict[str, Any]
    workflow_name: str = "z_image_turbo_api.json"


# --- In-memory shots store ---
_SHOTS_STORE: List[Dict[str, Any]] = []
_CAMPAIGNS: Dict[str, Dict[str, Any]] = {}
_SCRIPT_PIPELINE_JOBS: Dict[str, Dict[str, Any]] = {}
_ACTIVE_CAMPAIGN: Optional[str] = None
_CANCEL_CAMPAIGN = False


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _find_shot(shot_id: str) -> Optional[Dict[str, Any]]:
    for s in _SHOTS_STORE:
        if s.get("id") == shot_id or s.get("shot_id") == shot_id:
            return s
    return None


def _append_event(event: Dict[str, Any]):
    events_path = REPO_ROOT / "data" / "hermes_memory" / "episodic" / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _record_pipeline_event(
    event_type: str,
    shot_id: str = "",
    campaign_id: str = "",
    workflow_id: str = "",
    source: str = "campaign",
    success: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
):
    if source == "fallback" and os.getenv("FORGE_LEARN_FROM_FALLBACK", "false").lower() != "true":
        return
    payload = {
        "event_id": f"evt_{uuid.uuid4().hex[:10]}",
        "timestamp": _now_iso(),
        "event_type": event_type,
        "session_id": campaign_id or "unknown",
        "shot_id": shot_id,
        "campaign_id": campaign_id or "",
        "workflow_id": workflow_id or "",
        "pipeline_mode": "production",
        "source": source,
    }
    if success is not None:
        payload["success"] = bool(success)
    if extra:
        payload.update(extra)
    _append_event(payload)


class UpdateShotRequest(BaseModel):
    shot_id: str
    prompt: str

class ShotDescriptionUpdateRequest(BaseModel):
    description: str

class ReparseRequest(BaseModel):
    path: str = ""

class DirectorGenerateRequest(BaseModel):
    brief: str
    length: str = ""
    target_shots: Optional[int] = None

class ScriptDevelopRequest(BaseModel):
    brief: str
    title: str = ""
    runtime_seconds: int = 60
    target_scenes: int = 4
    tone: str = ""
    hook_first_dialogue: bool = True

class ScriptStoryboardRequest(BaseModel):
    script: str = ""
    package: Optional[Dict[str, Any]] = None
    asset_vault_package_id: str = ""
    panels_per_board: int = 4
    target_panels: Optional[int] = None
    resolution: str = "1920x1080"
    title: str = ""
    style: str = "cinematic"
    character_consistency: str = ""
    negative_prompt: str = "blurry, soft focus, smeared detail, low resolution, deformed, extra limbs, bad hands, text, captions, labels, panel numbers, page layout, grid, contact sheet, watermark, inconsistent characters, merged panels"
    reference_image_url: str = ""
    include_captions: bool = False

class ScriptStoryboardAssembleRequest(BaseModel):
    panel_image_urls: List[str]
    title: str = "Storyboard"
    resolution: str = "3840x2160"
    columns: int = 3
    rows: int = 3
    include_panel_numbers: bool = True
    captions: List[str] = []

class ScriptStoryboardVideoExportRequest(BaseModel):
    board: Dict[str, Any]
    panel_image_urls: List[str]
    title: str = "Storyboard"
    campaign_id: str = ""
    duration_seconds: float = 4.0
    replace_existing: bool = True
    sequence_offset: int = 0
    total_shots: Optional[int] = None


class ScriptProjectSaveRequest(BaseModel):
    script_id: str = ""
    title: str = ""
    brief: str = ""
    tone: str = ""
    runtime_seconds: int = 60
    target_scenes: int = 4
    package: Optional[Dict[str, Any]] = None
    coverage_shots: List[Dict[str, Any]] = Field(default_factory=list)
    storyboard_plan: Optional[Dict[str, Any]] = None
    storyboard_panel_jobs: Dict[str, Any] = Field(default_factory=dict)
    video_shots: List[Dict[str, Any]] = Field(default_factory=list)
    hook_first_dialogue: bool = True
    status: str = "draft"


class ScriptPipelineStartRequest(BaseModel):
    script_id: str = ""
    title: str = ""
    brief: str = ""
    tone: str = ""
    runtime_seconds: int = 60
    target_scenes: int = 4
    target_shots: Optional[int] = None
    hook_first_dialogue: bool = True
    storyboard_panels_per_board: int = 4
    storyboard_target_panels: Optional[int] = None
    storyboard_resolution: str = "1920x1080"
    storyboard_style: str = "cinematic"
    storyboard_character_consistency: str = ""
    storyboard_negative_prompt: str = "blurry, soft focus, smeared detail, low resolution, deformed, extra limbs, bad hands, text, captions, labels, panel numbers, page layout, grid, contact sheet, watermark, inconsistent characters, merged panels"
    storyboard_reference_image_url: str = ""
    storyboard_include_captions: bool = False
    storyboard_image_provider: str = "spark"
    storyboard_image_model: str = ""
    storyboard_spark_model: str = "flux2_dev"
    asset_vault_package_id: str = ""
    video_workflow_id: str = "04_ltx2.3_image_to_video"
    video_duration: int = 5
    video_fps: int = 24
    video_resolution: str = "540p"
    video_aspect_ratio: str = "16:9"
    run_video: bool = True
    wait_for_videos: bool = True
    video_wait_seconds: int = 21600
    stop_after: str = "videos"


class ScriptPipelineResumeRequest(BaseModel):
    wait_for_videos: bool = True
    video_wait_seconds: int = 21600

class StoryboardImageGenerateRequest(BaseModel):
    prompt: str
    provider: str = "spark"
    model: str = ""
    spark_model: str = "flux2_dev"
    width_and_height: str = "1920x1080"
    quality: str = "1080p"
    title: str = "storyboard"
    image_reference_url: str = ""
    enhance_prompt: bool = False
    wait_for_output: bool = False


STORYBOARD_SPARK_MODELS: Dict[str, Dict[str, str]] = {
    "z_image": {
        "label": "Spark / Z-Image",
        "workflow_id": "spark_image_z_image",
        "model_family": "z-image",
    },
    "z_image_turbo": {
        "label": "Spark / Z-Image Turbo",
        "workflow_id": "spark_image_z_image_turbo",
        "model_family": "z-image",
    },
    "flux2_dev": {
        "label": "Spark / Flux2.Dev",
        "workflow_id": "01_flux2_text_to_image",
        "model_family": "flux2-dev",
    },
    "flux2_klein": {
        "label": "Spark / Flux2 Klein",
        "workflow_id": "08_flux2_klein_9b_text_to_image",
        "model_family": "flux2-klein-9b",
    },
}

class RenameCampaignRequest(BaseModel):
    old_campaign_id: str
    new_campaign_name: str

class DeleteCampaignRequest(BaseModel):
    campaign_id: str


class CampaignIdentityPack(BaseModel):
    type: str = ""  # "", "character", "product"
    name: str = ""
    anchor_image_ids: List[str] = []
    identity_tokens: List[str] = []
    negative_tokens: List[str] = []


class CampaignIdentityRequest(BaseModel):
    campaign_id: str
    identity_pack: CampaignIdentityPack


class CampaignIdentityAssetUpdateRequest(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None
    priority: Optional[int] = None


@app.get("/api/shots")
async def api_get_shots():
    return {
        "shots": _SHOTS_STORE,
        "count": len(_SHOTS_STORE),
        "active_campaign_id": _ACTIVE_CAMPAIGN,
    }


IDEA_BOARD_COLUMNS = [
    {"id": "inbox", "label": "Inbox"},
    {"id": "spark", "label": "Spark"},
    {"id": "story", "label": "Story"},
    {"id": "visual", "label": "Visual"},
    {"id": "ready", "label": "Ready"},
]
IDEA_BOARD_FILE = MEDIA_ROOT / "idea_board.json"


def _short_text(value: Any, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _safe_script_id(value: str = "", title: str = "") -> str:
    raw = (value or "").strip() or (title or "").strip() or f"script_{uuid.uuid4().hex[:8]}"
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    if not slug:
        slug = f"script_{uuid.uuid4().hex[:8]}"
    if len(slug) > 64:
        slug = slug[:64].strip("_")
    return slug


def _script_project_dir(script_id: str) -> Path:
    sid = _safe_script_id(script_id)
    path = (SCRIPT_PROJECTS_DIR / sid).resolve()
    if not str(path).startswith(str(SCRIPT_PROJECTS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="invalid script id")
    return path


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(path)


def _read_json_file(path: Path, fallback: Any = None) -> Any:
    try:
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _script_project_summary(project: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "script_id": project.get("script_id", ""),
        "title": project.get("title", "") or "Untitled Script",
        "brief": _short_text(project.get("brief", ""), 240),
        "tone": project.get("tone", ""),
        "runtime_seconds": project.get("runtime_seconds", 60),
        "target_scenes": project.get("target_scenes", 4),
        "status": project.get("status", "draft"),
        "updated_at": project.get("updated_at", ""),
        "created_at": project.get("created_at", ""),
        "has_package": bool(project.get("has_package")),
        "coverage_count": int(project.get("coverage_count") or 0),
        "storyboard_count": int(project.get("storyboard_count") or 0),
        "video_shot_count": int(project.get("video_shot_count") or 0),
        "video_complete_count": int(project.get("video_complete_count") or 0),
        "active_job_id": project.get("active_job_id", ""),
    }


def _load_script_project(script_id: str) -> Dict[str, Any]:
    sid = _safe_script_id(script_id)
    root = _script_project_dir(sid)
    meta = _read_json_file(root / "project.json", {})
    if not isinstance(meta, dict) or not meta:
        raise HTTPException(status_code=404, detail=f"script project not found: {sid}")
    package = _read_json_file(root / "script_package.json", None)
    coverage = _read_json_file(root / "coverage_shots.json", [])
    storyboard = _read_json_file(root / "storyboard_plan.json", None)
    panel_jobs = _read_json_file(root / "storyboard_panel_jobs.json", {})
    video_shots = _read_json_file(root / "video_shots.json", [])
    job = _read_json_file(root / "pipeline_job.json", None)
    video_shots_changed = False
    if (
        not video_shots
        and isinstance(storyboard, dict)
        and isinstance(panel_jobs, dict)
        and any(isinstance(items, list) and any(isinstance(item, dict) and item.get("url") for item in items) for items in panel_jobs.values())
    ):
        video_shots = _rebuild_script_video_shots_from_storyboard_frames(sid, storyboard, panel_jobs)
        video_shots_changed = bool(video_shots)
    if isinstance(video_shots, list) and video_shots:
        video_shots_changed = _repair_script_video_urls_from_existing_outputs(sid, video_shots, job) or video_shots_changed
    if video_shots_changed and video_shots:
        _write_json_atomic(root / "video_shots.json", video_shots)
        video_complete = len([
            s for s in video_shots
            if str(s.get("video_status") or s.get("status") or "").lower() in {"complete", "completed", "video_rendered"} or s.get("video_url")
        ])
        meta = {
            **meta,
            "video_shot_count": len(video_shots),
            "video_complete_count": video_complete,
            "updated_at": meta.get("updated_at") or _now_iso(),
        }
        _write_json_atomic(root / "project.json", meta)
    return {
        **meta,
        "package": package if isinstance(package, dict) else None,
        "coverage_shots": coverage if isinstance(coverage, list) else [],
        "storyboard_plan": storyboard if isinstance(storyboard, dict) else None,
        "storyboard_panel_jobs": panel_jobs if isinstance(panel_jobs, dict) else {},
        "video_shots": video_shots if isinstance(video_shots, list) else [],
        "active_job": job if isinstance(job, dict) else None,
    }


def _save_script_project_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    sid = _safe_script_id(str(payload.get("script_id") or ""), str(payload.get("title") or ""))
    root = _script_project_dir(sid)
    existing = _read_json_file(root / "project.json", {})
    if not isinstance(existing, dict):
        existing = {}
    package = payload.get("package", None)
    coverage = payload.get("coverage_shots", [])
    storyboard = payload.get("storyboard_plan")
    panel_jobs = payload.get("storyboard_panel_jobs", {})
    video_shots = payload.get("video_shots", [])
    if not isinstance(coverage, list):
        coverage = []
    if not isinstance(panel_jobs, dict):
        panel_jobs = {}
    if not isinstance(video_shots, list):
        video_shots = []
    storyboard_boards = storyboard.get("boards", []) if isinstance(storyboard, dict) else []
    video_complete = len([
        s for s in video_shots
        if str(s.get("video_status") or s.get("status") or "").lower() in {"complete", "completed", "video_rendered"} or s.get("video_url")
    ])
    meta = {
        **existing,
        "script_id": sid,
        "title": str(payload.get("title") or existing.get("title") or "Untitled Script"),
        "brief": str(payload.get("brief") or existing.get("brief") or ""),
        "tone": str(payload.get("tone") or existing.get("tone") or ""),
        "runtime_seconds": int(payload.get("runtime_seconds") or existing.get("runtime_seconds") or 60),
        "target_scenes": int(payload.get("target_scenes") or existing.get("target_scenes") or 4),
        "status": str(payload.get("status") or existing.get("status") or "draft"),
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "has_package": isinstance(package, dict) or bool(existing.get("has_package")),
        "coverage_count": len(coverage) if "coverage_shots" in payload else int(existing.get("coverage_count") or 0),
        "storyboard_count": sum(len(b.get("panels", [])) for b in storyboard_boards if isinstance(b, dict)) if isinstance(storyboard, dict) else int(existing.get("storyboard_count") or 0),
        "video_shot_count": len(video_shots) if "video_shots" in payload else int(existing.get("video_shot_count") or 0),
        "video_complete_count": video_complete if "video_shots" in payload else int(existing.get("video_complete_count") or 0),
        "active_job_id": str(payload.get("active_job_id") or existing.get("active_job_id") or ""),
    }
    _write_json_atomic(root / "project.json", meta)
    if isinstance(package, dict):
        _write_json_atomic(root / "script_package.json", package)
    if "coverage_shots" in payload:
        _write_json_atomic(root / "coverage_shots.json", coverage)
    if isinstance(storyboard, dict):
        _write_json_atomic(root / "storyboard_plan.json", storyboard)
    if "storyboard_panel_jobs" in payload:
        _write_json_atomic(root / "storyboard_panel_jobs.json", panel_jobs)
    if "video_shots" in payload:
        _write_json_atomic(root / "video_shots.json", video_shots)
    return _load_script_project(sid)


def _list_script_projects() -> List[Dict[str, Any]]:
    projects: List[Dict[str, Any]] = []
    for path in SCRIPT_PROJECTS_DIR.glob("*/project.json"):
        data = _read_json_file(path, {})
        if isinstance(data, dict) and data.get("script_id"):
            projects.append(_script_project_summary(data))
    projects.sort(key=lambda p: str(p.get("updated_at") or ""), reverse=True)
    return projects


class IdeaCardCreateRequest(BaseModel):
    title: str
    body: str = ""
    type: str = "concept"
    campaign_id: str = ""
    stage: str = "inbox"
    tags: List[str] = []


class IdeaCardUpdateRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    type: Optional[str] = None
    campaign_id: Optional[str] = None
    stage: Optional[str] = None
    tags: Optional[List[str]] = None


def _valid_idea_stage(stage: str) -> str:
    allowed = {column["id"] for column in IDEA_BOARD_COLUMNS}
    return stage if stage in allowed else "inbox"


def _read_idea_cards() -> List[Dict[str, Any]]:
    if not IDEA_BOARD_FILE.exists():
        return []
    try:
        data = json.loads(IDEA_BOARD_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    cards = data.get("cards", []) if isinstance(data, dict) else []
    return [card for card in cards if isinstance(card, dict)]


def _write_idea_cards(cards: List[Dict[str, Any]]) -> None:
    IDEA_BOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    IDEA_BOARD_FILE.write_text(
        json.dumps({"cards": cards}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _normalize_idea_card(card: Dict[str, Any]) -> Dict[str, Any]:
    tags = card.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return {
        "id": str(card.get("id") or f"idea_{uuid.uuid4().hex[:8]}"),
        "title": _short_text(card.get("title") or "Untitled idea", 80),
        "body": _short_text(card.get("body") or "", 360),
        "type": _short_text(card.get("type") or "concept", 32).lower(),
        "campaign_id": str(card.get("campaign_id") or ""),
        "stage": _valid_idea_stage(str(card.get("stage") or "inbox")),
        "tags": [_short_text(tag, 28) for tag in tags[:6]],
        "created_at": str(card.get("created_at") or datetime.utcnow().isoformat()),
        "updated_at": str(card.get("updated_at") or card.get("created_at") or datetime.utcnow().isoformat()),
    }


def _build_idea_board(campaign_id: str = "") -> Dict[str, Any]:
    cards = [
        _normalize_idea_card(card)
        for card in _read_idea_cards()
        if not campaign_id or str(card.get("campaign_id") or "") == campaign_id
    ]
    columns = [{**column, "cards": []} for column in IDEA_BOARD_COLUMNS]
    by_stage = {column["id"]: column for column in columns}
    for card in cards:
        by_stage.get(card["stage"], by_stage["inbox"])["cards"].append(card)
    return {
        "status": "ok",
        "source": "forge_idea_board",
        "campaign_id": campaign_id,
        "columns": columns,
        "count": len(cards),
    }


@app.get("/api/ideas/board")
async def api_get_idea_board(campaign_id: str = ""):
    return _build_idea_board(campaign_id)


@app.post("/api/ideas/cards")
async def api_create_idea_card(req: IdeaCardCreateRequest):
    title = _short_text(req.title, 80)
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    cards = [_normalize_idea_card(card) for card in _read_idea_cards()]
    now = datetime.utcnow().isoformat()
    card = _normalize_idea_card({
        "id": f"idea_{uuid.uuid4().hex[:10]}",
        "title": title,
        "body": req.body,
        "type": req.type,
        "campaign_id": req.campaign_id,
        "stage": req.stage,
        "tags": req.tags,
        "created_at": now,
        "updated_at": now,
    })
    cards.append(card)
    _write_idea_cards(cards)
    return {"status": "ok", "card": card}


@app.patch("/api/ideas/cards/{card_id}")
async def api_update_idea_card(card_id: str, req: IdeaCardUpdateRequest):
    cards = [_normalize_idea_card(card) for card in _read_idea_cards()]
    for index, card in enumerate(cards):
        if card["id"] != card_id:
            continue
        updates = req.model_dump(exclude_unset=True) if hasattr(req, "model_dump") else req.dict(exclude_unset=True)
        card.update(updates)
        card["updated_at"] = datetime.utcnow().isoformat()
        cards[index] = _normalize_idea_card(card)
        _write_idea_cards(cards)
        return {"status": "ok", "card": cards[index]}
    raise HTTPException(status_code=404, detail="idea card not found")


@app.delete("/api/ideas/cards/{card_id}")
async def api_delete_idea_card(card_id: str):
    cards = [_normalize_idea_card(card) for card in _read_idea_cards()]
    kept = [card for card in cards if card["id"] != card_id]
    if len(kept) == len(cards):
        raise HTTPException(status_code=404, detail="idea card not found")
    _write_idea_cards(kept)
    return {"status": "ok", "deleted": card_id}


MEDIA_SHOT_METADATA_FILE = "_shot_metadata.json"
MEDIA_SHOT_METADATA_FIELDS = {
    "audit_status",
    "audit_score",
    "audit_issues",
    "audit_model_score",
    "audit_checks_score",
    "audit_confidence",
    "audit_model_passed",
    "audit_final_passed",
    "audit_checks",
    "audit_critical_failures",
    "audit_noncritical_issues",
    "audit_decision_reasons",
    "audit_raw_response",
    "audit_timestamp",
    "audit_model",
    "audit_error",
    "retry_of",
    "parent_shot_id",
    "remediation_reason",
    "remediated_prompt",
    "original_compiled_prompt",
    "remediation_model",
    "profile_used",
    "profile_backend",
    "skills_scope_role",
    "skills_scope_patterns",
    "skills_scope_version",
    "video_prompt",
    "video_prompt_source",
    "video_path",
    "video_url",
    "video_prompt_id",
    "video_workflow_id",
    "video_seed",
    "video_duration",
    "video_fps",
    "video_status",
    "video_error",
    "video_error_detail",
    "video_error_node",
    "video_last_checked_at",
    "video_completed_at",
    "negative_prompt",
    "workflow_profile",
    "model_standard_name",
    "model_standard_version",
    "model_standard_source",
    "model_standard_rules",
    "sections",
    "kimi_plan",
    "kimi_rationale",
}


def _read_media_shot_metadata(folder: Path) -> Dict[str, Any]:
    path = folder / MEDIA_SHOT_METADATA_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _metadata_for_media_file(image_path: Path) -> Dict[str, Any]:
    data = _read_media_shot_metadata(image_path.parent)
    record = data.get(image_path.stem)
    return record if isinstance(record, dict) else {}


def _persist_media_shot_metadata(shot: Dict[str, Any]) -> None:
    image_path = str(shot.get("image_path") or "").strip()
    if not image_path and shot.get("image_url"):
        resolved = _resolve_image_path(str(shot.get("image_url") or ""))
        image_path = str(resolved) if resolved else ""
    if not image_path:
        return
    path = Path(image_path)
    if not path.exists():
        return
    record_id = str(shot.get("id") or path.stem)
    folder = path.parent
    metadata = _read_media_shot_metadata(folder)
    existing = metadata.get(record_id)
    if not isinstance(existing, dict):
        existing = {}
    for key in MEDIA_SHOT_METADATA_FIELDS:
        if key in shot:
            existing[key] = shot.get(key)
    existing["updated_at"] = _now_iso()
    metadata[record_id] = existing
    tmp = folder / f".{MEDIA_SHOT_METADATA_FILE}.tmp"
    final = folder / MEDIA_SHOT_METADATA_FILE
    tmp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    tmp.replace(final)


def _media_video_url_for_path(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(MEDIA_VIDEOS.resolve())
        return f"/media-assets/videos/{rel.as_posix()}"
    except Exception:
        return f"/media-assets/videos/{path.name}"


def _history_output_items(history_entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    outputs = history_entry.get("outputs", {}) if isinstance(history_entry, dict) else {}
    items_out: List[Dict[str, Any]] = []
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for media_key in ("images", "gifs", "videos", "animated", "files"):
            items = node_output.get(media_key)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and item.get("filename"):
                    items_out.append(item)
    return items_out


def _has_video_output(history_entry: Dict[str, Any]) -> bool:
    for item in _history_output_items(history_entry):
        if Path(str(item.get("filename") or "")).suffix.lower() in {".mp4", ".mov", ".webm", ".m4v"}:
            return True
    return False


def _attach_video_to_shot(
    *,
    shot_id: str,
    saved_files: List[str],
    prompt_id: str = "",
    workflow_id: str = "",
    seed: Any = None,
    duration: Any = None,
    fps: Any = None,
) -> Optional[Dict[str, Any]]:
    shot = _find_shot(str(shot_id))
    if not shot:
        return None
    video_files = [
        Path(path)
        for path in saved_files
        if Path(str(path)).suffix.lower() in {".mp4", ".mov", ".webm", ".m4v"} and Path(str(path)).exists()
    ]
    if not video_files:
        return shot
    video_path = video_files[0]
    shot["video_path"] = str(video_path)
    shot["video_url"] = _media_video_url_for_path(video_path)
    shot["video_prompt_id"] = prompt_id or shot.get("video_prompt_id", "")
    shot["video_workflow_id"] = workflow_id or shot.get("video_workflow_id", "")
    shot["video_seed"] = seed if seed is not None else shot.get("video_seed")
    shot["video_duration"] = duration if duration is not None else shot.get("video_duration")
    shot["video_fps"] = fps if fps is not None else shot.get("video_fps")
    shot["video_status"] = "complete"
    shot["video_error"] = ""
    shot["video_error_detail"] = ""
    shot["video_error_node"] = ""
    shot["video_last_checked_at"] = _now_iso()
    shot["video_completed_at"] = _now_iso()
    _persist_media_shot_metadata(shot)
    return shot


def _reindex_shots_from_storage() -> Dict[str, Any]:
    """
    Rehydrate shot records from on-disk render folders so historical campaigns
    appear again in Dashboard/Video after server restarts or store drift.
    """
    roots = [
        ("external", MEDIA_IMAGES, "/external-renders", "campaign", "legacy"),
        ("media_imports", MEDIA_ROOT / "imports", "/media-assets/imports", "imported", "imports"),
        ("media_legacy", MEDIA_ROOT / "legacy", "/media-assets/legacy", "legacy", "legacy"),
        ("media_campaigns", MEDIA_ROOT / "campaigns", "/media-assets/campaigns", "campaign", "campaign"),
        ("media_videos", MEDIA_VIDEOS, "/media-assets/videos", "video", "videos"),
        ("campaigns", REPO_ROOT / "data" / "campaigns", "/campaigns", "campaign", "campaign"),
        ("renders_campaigns", REPO_ROOT / "data" / "renders" / "campaigns", "/renders/campaigns", "campaign", "campaign"),
    ]

    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    video_exts = {".mp4", ".mov", ".webm", ".m4v"}
    rebuilt: List[Dict[str, Any]] = []
    seen_ids = set()

    def _guess_campaign_and_shot(stem: str, rel_parts: List[str], default_campaign: str) -> tuple[str, str]:
        campaign = default_campaign
        shot = ""
        if rel_parts:
            campaign = rel_parts[0]
            if rel_parts[0] in {"campaigns", "videos"} and len(rel_parts) > 1:
                campaign = rel_parts[1]
        # Common id pattern: <campaign>__SHOT_001__workflow
        if "__SHOT_" in stem:
            parts = stem.split("__")
            if (not campaign or campaign in {"legacy", "imports", "videos"}) and parts:
                campaign = parts[0]
            for p in parts:
                if p.startswith("SHOT_"):
                    shot = p
                    break
        if not campaign:
            campaign = default_campaign or "legacy"
        if not shot:
            shot = stem[:40]
        return campaign, shot

    for mount_name, root, url_prefix, source, default_campaign in roots:
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            suffix = f.suffix.lower()
            if not f.is_file() or suffix not in image_exts | video_exts:
                continue
            stem = f.stem
            rel = f.relative_to(root)
            rel_parts = list(rel.parts[:-1])
            campaign_id, shot_id = _guess_campaign_and_shot(stem, rel_parts, default_campaign)
            is_video = suffix in video_exts
            record_id = f"{stem}__video" if is_video else stem
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            media_url = f"{url_prefix}/{rel.as_posix()}"
            record = {
                "id": record_id,
                "campaign_id": campaign_id,
                "shot_id": shot_id,
                "sequence": 0,
                "workflow_id": "reindexed_video" if is_video else "reindexed_media",
                "status": "complete",
                "state": "video_rendered" if is_video else "rendered",
                "seed": None,
                "prompt": f"Reindexed {'video' if is_video else 'media'}: {stem}",
                "compiled_prompt": f"Reindexed {'video' if is_video else 'media'}: {stem}",
                "video_prompt": "",
                "video_prompt_source": "",
                "negative_prompt": "",
                "workflow_profile": "reindexed",
                "skills_used": [],
                "compiler_version": "",
                "model_standard_name": "",
                "model_standard_version": "",
                "model_standard_source": "",
                "model_standard_rules": [],
                "sections": {},
                "source": source,
                "image_path": "" if is_video else str(f),
                "image_url": "" if is_video else media_url,
                "video_path": str(f) if is_video else "",
                "video_url": media_url if is_video else "",
                "created_at": _now_iso(),
            }
            if not is_video:
                stored_metadata = _metadata_for_media_file(f)
                for key in MEDIA_SHOT_METADATA_FIELDS:
                    if key in stored_metadata:
                        record[key] = stored_metadata[key]
            rebuilt.append(record)

    # Preserve any existing non-media script shots, but prioritize media records.
    non_media = [s for s in _SHOTS_STORE if not s.get("image_url") and not s.get("video_url")]
    _SHOTS_STORE.clear()
    _SHOTS_STORE.extend(rebuilt + non_media)

    return {
        "status": "ok",
        "reindexed": len(rebuilt),
        "preserved_non_media": len(non_media),
        "count": len(_SHOTS_STORE),
    }


@app.post("/api/shots/reindex-storage")
async def api_reindex_shots_from_storage():
    return _reindex_shots_from_storage()


def _campaign_from_comfy_history_outputs(history_entry: Dict[str, Any]) -> str:
    outputs = history_entry.get("outputs", {}) if isinstance(history_entry, dict) else {}
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        for media_key in ("images", "gifs", "videos", "animated", "files"):
            items = node_output.get(media_key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                filename = str((item or {}).get("filename", "") or "")
                stem = Path(filename).stem
                if "__SHOT_" in stem:
                    return _safe_campaign_name(stem.split("__SHOT_", 1)[0])
    return "imports"


@app.post("/api/comfy/recover-prompt")
async def api_recover_comfy_prompt(req: ComfyRecoverPromptRequest):
    prompt_id = (req.prompt_id or "").strip()
    if not prompt_id:
        raise HTTPException(status_code=400, detail="prompt_id is required")

    cfg = get_raw_config()
    host = (
        req.host.strip()
        or os.getenv("COMFYUI_PRIMARY", "")
        or str(cfg.get("COMFYUI_PRIMARY", ""))
    ).rstrip("/")
    if not host:
        raise HTTPException(status_code=400, detail="COMFYUI_PRIMARY is not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{host}/history/{prompt_id}")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Comfy history failed: HTTP {resp.status_code}")
    history = resp.json()
    entry = history.get(prompt_id)
    if not isinstance(entry, dict):
        raise HTTPException(status_code=404, detail=f"Prompt not found in Comfy history: {prompt_id}")
    status = entry.get("status", {}) if isinstance(entry.get("status"), dict) else {}
    if status.get("status_str") == "error":
        raise HTTPException(status_code=409, detail=f"Prompt failed in Comfy: {prompt_id}")

    campaign_id = _safe_campaign_name(req.campaign_id) if req.campaign_id else _campaign_from_comfy_history_outputs(entry)
    output_dir = (MEDIA_VIDEOS if _has_video_output(entry) else MEDIA_IMAGES) / campaign_id
    client = ComfyUIClient(host)
    saved = await client.download_outputs(prompt_id, str(output_dir))
    if not saved:
        raise HTTPException(status_code=404, detail=f"No downloadable outputs for prompt: {prompt_id}")
    reindex = _reindex_shots_from_storage()
    return {
        "status": "ok",
        "prompt_id": prompt_id,
        "campaign_id": campaign_id,
        "saved_files": saved,
        "reindex": reindex,
    }


@app.post("/api/comfy/recover-history")
async def api_recover_comfy_history(req: ComfyRecoverHistoryRequest):
    cfg = get_raw_config()
    host = (
        req.host.strip()
        or os.getenv("COMFYUI_PRIMARY", "")
        or str(cfg.get("COMFYUI_PRIMARY", ""))
    ).rstrip("/")
    if not host:
        raise HTTPException(status_code=400, detail="COMFYUI_PRIMARY is not configured")

    target_campaign = _safe_campaign_name(req.campaign_id) if req.campaign_id else ""
    limit = max(1, min(int(req.limit or 250), 1000))

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{host}/history")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Comfy history failed: HTTP {resp.status_code}")
    history = resp.json()
    if not isinstance(history, dict):
        raise HTTPException(status_code=502, detail="Comfy history response was not an object")

    comfy = ComfyUIClient(host)
    recovered: List[Dict[str, Any]] = []
    skipped_existing = 0
    inspected = 0

    for prompt_id, entry in list(history.items())[-limit:]:
        if not isinstance(entry, dict):
            continue
        status = entry.get("status", {}) if isinstance(entry.get("status"), dict) else {}
        if status.get("status_str") == "error":
            continue

        campaign_id = _campaign_from_comfy_history_outputs(entry)
        if target_campaign and campaign_id != target_campaign:
            continue
        if campaign_id in {"", "imports"} and target_campaign:
            campaign_id = target_campaign
        if campaign_id in {"", "imports"}:
            continue

        output_filenames = [
            str(item.get("filename", "") or "")
            for item in _history_output_items(entry)
            if str(item.get("filename", "") or "")
        ]
        if not output_filenames:
            continue
        inspected += 1

        media_names = [
            name for name in output_filenames
            if Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".webm", ".m4v"}
        ]
        if not media_names:
            continue
        video_only = all(Path(name).suffix.lower() in {".mp4", ".mov", ".webm", ".m4v"} for name in media_names)
        output_dir = (MEDIA_VIDEOS if video_only else MEDIA_IMAGES) / campaign_id
        existing = [output_dir / Path(name).name for name in media_names]
        if existing and all(p.exists() for p in existing):
            skipped_existing += 1
            continue

        saved = await comfy.download_outputs(str(prompt_id), str(output_dir))
        if saved:
            recovered.append({
                "prompt_id": str(prompt_id),
                "campaign_id": campaign_id,
                "saved_files": saved,
            })

    reindex = _reindex_shots_from_storage()
    return {
        "status": "ok",
        "host": host,
        "campaign_id": target_campaign,
        "inspected": inspected,
        "recovered_count": len(recovered),
        "skipped_existing": skipped_existing,
        "recovered": recovered,
        "reindex": reindex,
    }


@app.get("/api/campaigns")
async def api_get_campaigns():
    ids = set()
    for s in _SHOTS_STORE:
        cid = str(s.get("campaign_id") or "").strip()
        if cid and cid != "import":
            ids.add(cid)
    ids.update(k for k in _CAMPAIGNS.keys() if k and k != "import")

    roots = [
        MEDIA_IMAGES,
        MEDIA_IDENTITY_ASSETS,
        REPO_ROOT / "data" / "renders" / "campaigns",
        REPO_ROOT / "data" / "campaigns",
    ]
    for root in roots:
        if root.exists():
            for d in root.iterdir():
                if d.is_dir() and d.name and d.name != "import":
                    ids.add(d.name)

    campaigns = []
    for cid in sorted(ids):
        matching = [s for s in _SHOTS_STORE if str(s.get("campaign_id") or "") == cid]
        media_count = len([s for s in matching if s.get("image_url") or s.get("video_url")])
        total_shot_count = len(matching)
        meta = _CAMPAIGNS.get(cid, {}) if isinstance(_CAMPAIGNS.get(cid, {}), dict) else {}
        manifest = _campaign_manifest_load(cid)
        inferred_brief = str(meta.get("brief", "") or "")
        brief_source = "campaign_meta" if inferred_brief else ""
        if not inferred_brief:
            inferred_brief = str(manifest.get("brief", "") or "")
            if inferred_brief:
                brief_source = "manifest"
        if not inferred_brief:
            for s in matching:
                b = str(s.get("campaign_brief", "") or "").strip()
                if b:
                    inferred_brief = b
                    brief_source = "shot_record"
                    break
        if not inferred_brief:
            inferred_brief = _brief_from_campaign_manifest(cid)
            if inferred_brief:
                brief_source = "manifest_scan"
        if not inferred_brief:
            # Last-resort for older campaigns: humanize campaign id slug.
            inferred_brief = _humanize_campaign_id(cid)
            brief_source = "humanized_id"
        identity = meta.get("identity_pack", {}) if isinstance(meta.get("identity_pack", {}), dict) else {}
        if not identity and isinstance(manifest.get("identity_pack", {}), dict):
            identity = manifest.get("identity_pack", {})
        campaigns.append({
            "campaign_id": cid,
            "shot_count": media_count,
            "media_count": media_count,
            "total_shot_count": total_shot_count,
            "pending_count": max(0, total_shot_count - media_count),
            "active": cid == _ACTIVE_CAMPAIGN,
            "brief": inferred_brief,
            "brief_source": brief_source,
            "started_at": str(meta.get("started_at", "") or manifest.get("started_at", "") or ""),
            "identity_type": str(identity.get("type", "") or ""),
            "identity_name": str(identity.get("name", "") or ""),
        })

    return {
        "campaigns": campaigns,
        "count": len(campaigns),
        "active_campaign_id": _ACTIVE_CAMPAIGN,
    }


@app.get("/api/campaigns/{campaign_id}/agent-exchanges")
async def api_get_campaign_agent_exchanges(campaign_id: str):
    cid = (campaign_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="campaign_id required")
    exchanges: List[Dict[str, Any]] = []
    manifest_path = MEDIA_IMAGES / cid / "_agent_exchanges.json"
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                exchanges.extend([x for x in data if isinstance(x, dict)])
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"agent exchange log unreadable: {e}")
    in_memory = _CAMPAIGNS.get(cid, {}).get("agent_exchanges", [])
    if isinstance(in_memory, list):
        seen = {
            (
                str(x.get("timestamp", "")),
                str(x.get("stage", "")),
                json.dumps(x.get("request", {}), sort_keys=True, default=str)[:300],
            )
            for x in exchanges
        }
        for x in in_memory:
            if not isinstance(x, dict):
                continue
            key = (
                str(x.get("timestamp", "")),
                str(x.get("stage", "")),
                json.dumps(x.get("request", {}), sort_keys=True, default=str)[:300],
            )
            if key not in seen:
                exchanges.append(x)
                seen.add(key)
    legacy = _CAMPAIGNS.get(cid, {}) if isinstance(_CAMPAIGNS.get(cid, {}), dict) else {}
    for key, stage in [
        ("kimi_raw_response", "legacy_kimi_director_plan_response"),
        ("kimi_revision_raw_response", "legacy_kimi_director_revision_response"),
    ]:
        raw = str(legacy.get(key, "") or "")
        if raw:
            exchanges.append({
                "stage": stage,
                "transport": "legacy_response_only",
                "campaign_id": cid,
                "request": None,
                "response": {"content": raw},
                "note": "This response was captured before full request/response exchange logging was enabled.",
            })
    return {
        "campaign_id": cid,
        "count": len(exchanges),
        "exchanges": exchanges,
    }


def _safe_campaign_name(raw: str) -> str:
    # Keep this filesystem-safe and UI-friendly.
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", (raw or "").strip())
    name = name.strip("._-")
    return name[:80]


def _brief_from_campaign_manifest(campaign_id: str) -> str:
    if not campaign_id:
        return ""
    roots = [
        MEDIA_IMAGES / campaign_id,
        REPO_ROOT / "data" / "campaigns" / campaign_id,
        REPO_ROOT / "data" / "renders" / "campaigns" / campaign_id,
    ]
    for root in roots:
        try:
            manifest = root / "_campaign.json"
            if not manifest.exists():
                continue
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            brief = str(payload.get("brief", "") or "").strip()
            if brief:
                return brief
        except Exception:
            continue
    return ""


def _campaign_manifest_path(campaign_id: str) -> Path:
    return MEDIA_IMAGES / campaign_id / "_campaign.json"


def _campaign_manifest_load(campaign_id: str) -> Dict[str, Any]:
    try:
        p = _campaign_manifest_path(campaign_id)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _campaign_manifest_write(campaign_id: str, payload: Dict[str, Any]) -> None:
    p = _campaign_manifest_path(campaign_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _humanize_campaign_id(cid: str) -> str:
    if not cid:
        return ""
    base = cid
    if "__" in cid:
        left, right = cid.rsplit("__", 1)
        if re.fullmatch(r"[a-f0-9]{6,12}", right):
            base = left
    return base.replace("__", " ").replace("_", " ").strip()


def _campaign_asset_dir(campaign_id: str) -> Path:
    safe = _safe_campaign_name(campaign_id)
    return MEDIA_IDENTITY_ASSETS / safe


def _normalize_asset_role(role: str) -> str:
    r = (role or "").strip().lower()
    if r in {"anchor", "sheet", "detail"}:
        return r
    return "anchor"


def _identity_template_path(name: str) -> Path:
    safe = _safe_campaign_name(name or "")
    return MEDIA_IDENTITY_TEMPLATES / f"{safe}.json"


@app.post("/api/campaigns/rename")
async def api_rename_campaign(req: RenameCampaignRequest):
    global _ACTIVE_CAMPAIGN
    old_id = (req.old_campaign_id or "").strip()
    new_name = _safe_campaign_name(req.new_campaign_name)
    if not old_id:
        raise HTTPException(status_code=400, detail="old_campaign_id is required")
    if not new_name:
        raise HTTPException(status_code=400, detail="new_campaign_name is invalid")
    if old_id == new_name:
        return {"status": "ok", "old_campaign_id": old_id, "new_campaign_id": new_name, "shot_updates": 0, "folders_renamed": 0}

    existing_ids = {str(s.get("campaign_id") or "") for s in _SHOTS_STORE}
    existing_ids.update(_CAMPAIGNS.keys())
    if new_name in existing_ids:
        raise HTTPException(status_code=409, detail="new campaign name already exists")

    updated = 0
    for s in _SHOTS_STORE:
        if str(s.get("campaign_id") or "") == old_id:
            s["campaign_id"] = new_name
            updated += 1

    if old_id in _CAMPAIGNS:
        _CAMPAIGNS[new_name] = _CAMPAIGNS.pop(old_id)
    if _ACTIVE_CAMPAIGN == old_id:
        _ACTIVE_CAMPAIGN = new_name

    roots = [
        MEDIA_IMAGES,
        REPO_ROOT / "data" / "renders" / "campaigns",
        REPO_ROOT / "data" / "campaigns",
    ]
    renamed_folders = 0
    for root in roots:
        src = root / old_id
        dst = root / new_name
        try:
            if src.exists() and src.is_dir() and not dst.exists():
                src.rename(dst)
                renamed_folders += 1
        except Exception:
            # Keep rename best-effort; shot lineage is primary source of truth.
            pass

    return {
        "status": "ok",
        "old_campaign_id": old_id,
        "new_campaign_id": new_name,
        "shot_updates": updated,
        "folders_renamed": renamed_folders,
    }


@app.delete("/api/campaigns/{campaign_id}")
async def api_delete_campaign(campaign_id: str):
    global _ACTIVE_CAMPAIGN
    cid = (campaign_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="campaign_id is required")
    safe_cid = _safe_campaign_name(cid)
    candidate_ids = {cid}
    if safe_cid:
        candidate_ids.add(safe_cid)

    before = len(_SHOTS_STORE)
    _SHOTS_STORE[:] = [s for s in _SHOTS_STORE if str(s.get("campaign_id") or "") not in candidate_ids]
    removed_shots = before - len(_SHOTS_STORE)

    for k in list(_CAMPAIGNS.keys()):
        if str(k or "") in candidate_ids:
            _CAMPAIGNS.pop(k, None)
    if _ACTIVE_CAMPAIGN in candidate_ids:
        _ACTIVE_CAMPAIGN = None

    removed_paths = []
    roots = [
        MEDIA_IMAGES,
        REPO_ROOT / "data" / "renders" / "campaigns",
        REPO_ROOT / "data" / "campaigns",
        MEDIA_IDENTITY_ASSETS,
    ]
    targets: List[Path] = []
    for name in candidate_ids:
        targets.extend([root / name for root in roots])
        targets.append(_identity_template_path(name))
    # Also delete variant folders that normalize to same safe name.
    for root in roots:
        try:
            if not root.exists():
                continue
            for d in root.iterdir():
                if not d.is_dir():
                    continue
                dn = str(d.name or "")
                if dn in candidate_ids or _safe_campaign_name(dn) == safe_cid:
                    targets.append(d)
        except Exception:
            pass
    for target in targets:
        try:
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    target.unlink(missing_ok=True)
                removed_paths.append(str(target))
        except Exception:
            pass

    return {
        "status": "ok",
        "campaign_id": cid,
        "safe_campaign_id": safe_cid,
        "candidate_ids": sorted(candidate_ids),
        "removed_shots": removed_shots,
        "removed_paths": removed_paths,
    }

@app.post("/api/campaigns/delete")
async def api_delete_campaign_body(req: DeleteCampaignRequest):
    return await api_delete_campaign(req.campaign_id)


@app.get("/api/campaigns/{campaign_id}/identity")
async def api_get_campaign_identity(campaign_id: str):
    cid = (campaign_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="campaign_id is required")
    meta = _CAMPAIGNS.get(cid, {}) if isinstance(_CAMPAIGNS.get(cid, {}), dict) else {}
    manifest = _campaign_manifest_load(cid)
    identity = meta.get("identity_pack", {}) if isinstance(meta.get("identity_pack", {}), dict) else {}
    if not identity and isinstance(manifest.get("identity_pack", {}), dict):
        identity = manifest.get("identity_pack", {})
    return {"campaign_id": cid, "identity_pack": identity or {}}


@app.post("/api/campaigns/identity")
async def api_set_campaign_identity(req: CampaignIdentityRequest):
    cid = (req.campaign_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="campaign_id is required")
    if cid not in _CAMPAIGNS:
        _CAMPAIGNS[cid] = {"brief": _brief_from_campaign_manifest(cid), "started_at": ""}
    identity = req.identity_pack.model_dump()
    identity_type = str(identity.get("type", "") or "").strip().lower()
    if identity_type not in {"", "character", "product"}:
        raise HTTPException(status_code=400, detail="identity_pack.type must be character or product")
    identity["type"] = identity_type
    _CAMPAIGNS[cid]["identity_pack"] = identity

    manifest = _campaign_manifest_load(cid)
    if not manifest:
        manifest = {
            "campaign_id": cid,
            "brief": str(_CAMPAIGNS[cid].get("brief", "") or ""),
            "started_at": str(_CAMPAIGNS[cid].get("started_at", "") or ""),
        }
    manifest["identity_pack"] = identity
    _campaign_manifest_write(cid, manifest)
    return {"status": "ok", "campaign_id": cid, "identity_pack": identity}


@app.get("/api/campaigns/{campaign_id}/assets")
async def api_get_campaign_assets(campaign_id: str):
    cid = (campaign_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="campaign_id is required")
    folder = _campaign_asset_dir(cid)
    assets: List[Dict[str, Any]] = []
    if folder.exists():
        for meta_path in sorted(folder.glob("*.json")):
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                file_name = str(payload.get("file_name", "") or "")
                if not file_name:
                    continue
                p = folder / file_name
                if not p.exists():
                    continue
                assets.append({
                    "asset_id": str(payload.get("asset_id", meta_path.stem)),
                    "file_name": file_name,
                    "role": _normalize_asset_role(str(payload.get("role", "anchor"))),
                    "active": bool(payload.get("active", True)),
                    "priority": int(payload.get("priority", 1000) or 1000),
                    "created_at": str(payload.get("created_at", "") or ""),
                    "src": f"/identity-assets/{_safe_campaign_name(cid)}/{file_name}",
                })
            except Exception:
                continue
    assets.sort(key=lambda a: (int(a.get("priority", 1000)), str(a.get("created_at", ""))))
    return {"campaign_id": cid, "assets": assets, "count": len(assets)}


@app.post("/api/campaigns/{campaign_id}/assets/upload")
async def api_upload_campaign_asset(
    campaign_id: str,
    file: UploadFile,
    role: str = Form("anchor"),
):
    cid = (campaign_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="campaign_id is required")
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required")
    ext = Path(file.filename).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="unsupported file type")
    asset_id = uuid.uuid4().hex[:12]
    safe_cid = _safe_campaign_name(cid)
    out_dir = _campaign_asset_dir(safe_cid)
    out_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{asset_id}{ext}"
    out_path = out_dir / file_name
    content = await file.read()
    out_path.write_bytes(content)
    meta = {
        "asset_id": asset_id,
        "campaign_id": safe_cid,
        "file_name": file_name,
        "role": _normalize_asset_role(role),
        "active": True,
        "priority": int(time.time()),
        "created_at": _now_iso(),
    }
    (out_dir / f"{asset_id}.json").write_text(json.dumps(meta, ensure_ascii=True, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "asset": {
            "asset_id": asset_id,
            "file_name": file_name,
            "role": meta["role"],
            "active": True,
            "created_at": meta["created_at"],
            "src": f"/identity-assets/{safe_cid}/{file_name}",
        },
    }


@app.post("/api/campaigns/{campaign_id}/assets/{asset_id}")
async def api_update_campaign_asset(campaign_id: str, asset_id: str, req: CampaignIdentityAssetUpdateRequest):
    cid = _safe_campaign_name(campaign_id or "")
    aid = (asset_id or "").strip()
    if not cid or not aid:
        raise HTTPException(status_code=400, detail="campaign_id and asset_id required")
    meta_path = _campaign_asset_dir(cid) / f"{aid}.json"
    if not meta_path.exists():
        raise HTTPException(status_code=404, detail="asset not found")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if req.role is not None:
        meta["role"] = _normalize_asset_role(req.role)
    if req.active is not None:
        meta["active"] = bool(req.active)
    if req.priority is not None:
        meta["priority"] = int(req.priority)
    meta_path.write_text(json.dumps(meta, ensure_ascii=True, indent=2), encoding="utf-8")
    return {
        "status": "ok",
        "asset_id": aid,
        "role": meta.get("role"),
        "active": bool(meta.get("active", True)),
        "priority": int(meta.get("priority", 1000) or 1000),
    }


@app.post("/api/campaigns/{campaign_id}/identity/clone/{source_campaign_id}")
async def api_clone_campaign_identity(campaign_id: str, source_campaign_id: str):
    dst = (campaign_id or "").strip()
    src = (source_campaign_id or "").strip()
    if not dst or not src:
        raise HTTPException(status_code=400, detail="campaign ids required")
    src_identity = (await api_get_campaign_identity(src)).get("identity_pack", {})
    if dst not in _CAMPAIGNS:
        _CAMPAIGNS[dst] = {"brief": _brief_from_campaign_manifest(dst), "started_at": ""}
    _CAMPAIGNS[dst]["identity_pack"] = src_identity
    manifest = _campaign_manifest_load(dst) or {"campaign_id": dst, "brief": str(_CAMPAIGNS[dst].get("brief", "") or ""), "started_at": str(_CAMPAIGNS[dst].get("started_at", "") or "")}
    manifest["identity_pack"] = src_identity
    _campaign_manifest_write(dst, manifest)
    return {"status": "ok", "campaign_id": dst, "source_campaign_id": src, "identity_pack": src_identity}


@app.post("/api/campaigns/{campaign_id}/assets/auto-select")
async def api_auto_select_identity_assets(campaign_id: str):
    cid = (campaign_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="campaign_id required")
    folder = _campaign_asset_dir(cid)
    if not folder.exists():
        return {"status": "ok", "selected": 0}
    from PIL import Image  # type: ignore
    scored: List[tuple[str, float]] = []
    for meta_path in folder.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            fn = str(meta.get("file_name", "") or "")
            p = folder / fn
            if not p.exists():
                continue
            im = Image.open(p).convert("L")
            w, h = im.size
            px = list(im.resize((max(32, min(256, w // 4)), max(32, min(256, h // 4)))).getdata())
            if len(px) < 2:
                continue
            diffs = [abs(px[i] - px[i - 1]) for i in range(1, len(px))]
            sharp = (sum(diffs) / len(diffs)) if diffs else 0.0
            score = float(w * h) * 0.000001 + sharp
            scored.append((meta_path.stem, score))
        except Exception:
            continue
    scored.sort(key=lambda x: x[1], reverse=True)
    top = {aid for aid, _ in scored[:5]}
    selected = 0
    for meta_path in folder.glob("*.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            aid = meta_path.stem
            active = aid in top
            meta["active"] = active
            if active:
                meta["role"] = "anchor"
                selected += 1
            meta_path.write_text(json.dumps(meta, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception:
            continue
    return {"status": "ok", "selected": selected}


@app.get("/api/identity/templates")
async def api_list_identity_templates():
    names = []
    for f in sorted(MEDIA_IDENTITY_TEMPLATES.glob("*.json")):
        names.append(f.stem)
    return {"templates": names, "count": len(names)}


@app.post("/api/identity/templates/{template_name}")
async def api_save_identity_template(template_name: str, req: CampaignIdentityPack):
    p = _identity_template_path(template_name)
    payload = req.model_dump()
    payload["type"] = str(payload.get("type", "") or "").strip().lower()
    p.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return {"status": "ok", "template": p.stem}


@app.get("/api/identity/templates/{template_name}")
async def api_get_identity_template(template_name: str):
    p = _identity_template_path(template_name)
    if not p.exists():
        raise HTTPException(status_code=404, detail="template not found")
    payload = json.loads(p.read_text(encoding="utf-8"))
    return {"template": p.stem, "identity_pack": payload}


@app.get("/api/scripts")
async def api_list_scripts():
    """Return all available script/bible files from disk."""
    repo_root = Path(__file__).parent.parent
    scripts = []

    # Brand bibles from data/projects/*/brand_bible/BRAND_BIBLE.md
    projects_dir = repo_root / "data" / "projects"
    if projects_dir.exists():
        for project_dir in sorted(projects_dir.iterdir()):
            bible = project_dir / "brand_bible" / "BRAND_BIBLE.md"
            if bible.exists():
                scripts.append({
                    "name": bible.name,
                    "label": project_dir.name.replace("_", " ").title() + " — Brand Guide",
                    "path": str(bible.relative_to(repo_root)),
                    "type": "brand_bible",
                })

    return scripts


@app.post("/api/script/reparse")
async def api_script_reparse(req: ReparseRequest = None):
    """Re-read shot list from a script file. Accepts optional path relative to repo root.
    Uses Kimi to extract shots from brand guides when available, falls back to regex."""
    repo_root = Path(__file__).parent.parent

    if req and req.path:
        # Sanitize — must stay inside repo root
        candidate = (repo_root / req.path).resolve()
        if not str(candidate).startswith(str(repo_root)):
            raise HTTPException(status_code=400, detail="Invalid path")
        script_path = candidate
    else:
        script_path = repo_root / "data" / "lore_bible" / "world_bible.md"

    if not script_path.exists():
        return {"status": "ok", "count": len(_SHOTS_STORE)}

    text = script_path.read_text(encoding="utf-8")

    # Try Kimi-powered parsing first
    kimi_shots = await _parse_shots_with_kimi(text, str(script_path))
    if kimi_shots:
        _SHOTS_STORE.clear()
        _SHOTS_STORE.extend(kimi_shots)
        # Persist shots to disk
        _persist_shots(script_path, kimi_shots)
        return {"status": "parsed_by_kimi", "count": len(_SHOTS_STORE), "parser": "kimi"}

    # Fallback: regex-based parsing for ## SHOT headers
    shots_found = []
    for i, line in enumerate(text.splitlines()):
        if line.strip().startswith("## SHOT") or line.strip().startswith("### SHOT"):
            parts = line.strip().lstrip("#").strip().split("—", 1)
            shot_id = parts[0].strip().replace(" ", "_")
            prompt = parts[1].strip() if len(parts) > 1 else "TBD"
            shots_found.append({
                "id": shot_id, "n": len(shots_found) + 1, "chars": [],
                "status": "ready", "prompt": prompt,
                "seed": random.randint(100000, 999999)
            })
    if shots_found:
        _SHOTS_STORE.clear()
        _SHOTS_STORE.extend(shots_found)
    return {"status": "ok", "count": len(_SHOTS_STORE), "parser": "regex"}


KIMI_SHOT_PARSER_SYSTEM = """You are a cinematic shot list extractor for an AI filmmaking pipeline.
Given a brand guide or creative brief, extract individual shots as a JSON array.

Rules:
- Extract every visual scene, character moment, or product shot implied by the text
- Each shot must have: id, n (sequential number), chars (array of character names), status, prompt, seed
- The prompt must be a complete, self-contained image generation prompt (1-2 sentences)
- Include camera direction, lighting, composition details
- Derive character names from the text; use empty array if none mentioned
- Seed is a random integer between 100000 and 999999
- Status is always "ready"
- IDs follow format SHOT_001, SHOT_002, etc.
- Generate 8-15 shots unless the source material clearly dictates fewer

Return ONLY a JSON array. No markdown, no explanation."""


async def _parse_shots_with_kimi(bible_text: str, source_path: str) -> Optional[List[Dict[str, Any]]]:
    """Send brand guide to Kimi for shot extraction."""
    cm = ConfigManager()
    api_key = cm.get_kimi_api_key()
    if not api_key or api_key == "dummy_key":
        return None

    endpoint = cm.get("KIMI_ENDPOINT", "") or cm.get_nim_endpoint()
    if not endpoint:
        endpoint = "https://integrate.api.nvidia.com/v1/chat/completions"
    # Ensure endpoint has /chat/completions path
    if not endpoint.endswith("/chat/completions"):
        endpoint = endpoint.rstrip("/") + "/chat/completions"

    user_prompt = f"""Extract a complete shot list from the following creative brief/brand guide.

--- SOURCE DOCUMENT ---
{bible_text}
--- END SOURCE ---

Return a JSON array of shot objects."""

    payload = {
        "model": cm.get("KIMI_INSTRUCT_MODEL", "moonshotai/kimi-k2.5"),
        "messages": [
            {"role": "system", "content": KIMI_SHOT_PARSER_SYSTEM},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "response_format": {"type": "json_object"}
    }

    try:
        # Ensure API key is ASCII-safe for HTTP headers
        safe_key = api_key.encode("ascii", "ignore").decode("ascii")
        if not safe_key:
            return None

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {safe_key}", "Content-Type": "application/json"},
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            content_str = data["choices"][0]["message"]["content"]

            # Parse JSON — strip markdown fences if present
            raw = content_str.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            shots = json.loads(raw.strip())

            if not isinstance(shots, list):
                shots = shots.get("shots", []) if isinstance(shots, dict) else []

            # Normalize each shot
            normalized = []
            for i, s in enumerate(shots):
                normalized.append({
                    "id": s.get("id", f"SHOT_{str(i+1).zfill(3)}"),
                    "n": s.get("n", i + 1),
                    "chars": s.get("chars", []),
                    "status": "ready",
                    "prompt": s.get("prompt", "TBD"),
                    "seed": s.get("seed", random.randint(100000, 999999))
                })

            return normalized if normalized else None

    except Exception as e:
        print(f"WARNING: Kimi shot parsing failed, falling back to regex: {e}")
        return None


def _persist_shots(source_path: Path, shots: List[Dict[str, Any]]) -> None:
    """Persist shots to data/projects/{project}/shots.json alongside the source bible."""
    try:
        source_dir = source_path.parent
        shots_path = source_dir / "shots.json"
        with open(shots_path, "w") as f:
            json.dump(shots, f, indent=2)
    except Exception as e:
        # Also try project-level directory
        try:
            shots_path = source_path.parent.parent / "shots.json"
            with open(shots_path, "w") as f:
                json.dump(shots, f, indent=2)
        except Exception:
            pass


def _script_director_event(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True) + "\n"


def _extract_json_response(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1]
            if raw.lstrip().startswith("json"):
                raw = raw.lstrip()[4:]
    parsed = json.loads(raw.strip())
    if not isinstance(parsed, dict):
        raise ValueError("json response must be an object")
    return parsed


def _fallback_script_package(req: ScriptDevelopRequest) -> Dict[str, Any]:
    brief = (req.brief or "").strip()
    title = (req.title or "").strip() or "Untitled Forge Film"
    scene_count = max(1, min(int(req.target_scenes or 4), 12))
    runtime = max(15, min(int(req.runtime_seconds or 60), 720))
    scene_duration = max(6, round(runtime / scene_count))
    scene_names = [
        "Opening Image",
        "Inciting Signal",
        "Escalation",
        "Point of No Return",
        "Confrontation",
        "Resolution",
    ]
    scenes = []
    continuity_characters = []
    for idx in range(1, scene_count + 1):
        scene_id = f"SC_{idx:03d}"
        beat_a = f"{scene_id}_B01"
        beat_b = f"{scene_id}_B02"
        label = scene_names[min(idx - 1, len(scene_names) - 1)]
        scenes.append({
            "scene_id": scene_id,
            "title": label,
            "duration_sec": scene_duration,
            "location": "primary story environment established by the brief",
            "time_of_day": "continuity-locked production lighting",
            "emotional_turn": "advance the central promise, tension, or reveal",
            "beats": [
                {
                    "beat_id": beat_a,
                    "action": f"{label}: establish the visible stakes from the brief.",
                    "dialogue": "Hero: Wait. Did that just move?",
                    "audio_cue": "immediate curiosity sting, close foreground breath, environment drops slightly under the line",
                    "performance": "deliver as a low, urgent hook that makes the viewer lean in within the first two seconds",
                    "characters": ["Hero"],
                    "continuity": {
                        "wardrobe": "locked hero wardrobe from continuity panel",
                        "props": ["primary story object"],
                        "screen_direction": "maintain consistent left-to-right progression unless the edit intentionally reverses momentum",
                    },
                },
                {
                    "beat_id": beat_b,
                    "action": "Turn the scene into a concrete visual decision that sets up the next scene.",
                    "dialogue": "Hero: If I am wrong, why is it answering me?",
                    "audio_cue": "tight rhythmic pulse, prop detail sound, subtle rising room tone into the cut",
                    "performance": "confident but unsettled, with a clear emotional turn at the end of the line",
                    "characters": ["Hero"],
                    "continuity": {
                        "wardrobe": "same as previous beat",
                        "props": ["primary story object"],
                        "screen_direction": "match previous axis",
                    },
                },
            ],
        })
    continuity_characters.append({
        "name": "Hero",
        "visual_lock": "derive exact age, wardrobe, silhouette, and face details from the approved character/brief",
        "wardrobe": "single locked outfit unless a scene explicitly changes it",
        "performance": "clear readable emotional progression across scenes",
    })
    return {
        "title": title,
        "source": "fallback",
        "brief": brief,
        "treatment": {
            "logline": brief[:220] if brief else "A concise visual story built for a cohesive AI-generated edit.",
            "synopsis": "Hermes structured the prompt into scenes, beats, continuity locks, and edit intent. Configure the Director API for model-authored prose.",
            "visual_language": req.tone or "precise, continuity-first cinematic coverage",
            "runtime_seconds": runtime,
        },
        "script": {
            "acts": [
                {
                    "act_id": "ACT_01",
                    "function": "Setup, escalation, and resolution sized for the requested runtime.",
                    "scenes": scenes,
                }
            ],
        },
        "continuity": {
            "characters": continuity_characters,
            "locations": [{
                "name": "primary story environment",
                "visual_lock": "same geography, lighting family, and screen direction across scene coverage",
            }],
            "props": [{
                "name": "primary story object",
                "state": "state changes must be explicit beat-to-beat",
            }],
            "motifs": ["recurring color accent", "repeated camera move", "sound bridge"],
        },
        "edit_plan": {
            "pacing": "open with orientation, accelerate through the midpoint, resolve with one readable final image",
            "audio_strategy": "J-cuts for anticipation, restrained music lift at each reveal, hard silence before the final turn",
            "transition_strategy": "motivated hard cuts, match cuts on motion or object state, no decorative transitions without narrative purpose",
        },
    }


def _package_from_shotlist_brief(brief: str) -> Optional[Dict[str, Any]]:
    text = brief or ""
    marker = "LOCKED SCRIPT PACKAGE FOR SHOTLIST GENERATION:"
    start = text.find(marker)
    if start < 0:
        return None
    json_start = text.find("{", start)
    if json_start < 0:
        return None
    try:
        parsed, _end = json.JSONDecoder().raw_decode(text[json_start:])
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _fallback_director_shots_from_brief(brief: str, campaign_id: str, target_shots: int) -> List[Dict[str, Any]]:
    package = _package_from_shotlist_brief(brief)
    source_scenes: List[Dict[str, Any]] = []
    if package:
        acts = package.get("script", {}).get("acts", [])
        if isinstance(acts, list):
            for act in acts:
                scenes = act.get("scenes", []) if isinstance(act, dict) else []
                if isinstance(scenes, list):
                    source_scenes.extend([s for s in scenes if isinstance(s, dict)])
    if not source_scenes:
        source_scenes = [{
            "scene_id": "SC_001",
            "title": "Brief Coverage",
            "duration_sec": 30,
            "location": "environment established by the brief",
            "time_of_day": "consistent production lighting",
            "emotional_turn": "make the prompt readable as a sequence",
            "beats": [{"beat_id": "SC_001_B01", "action": _short_text(brief, 260), "characters": ["Hero"], "continuity": {}}],
        }]

    coverage_cycle = [
        ("ESTABLISH", "wide establishing shot", "orient geography and lighting"),
        ("MASTER", "locked master shot", "preserve blocking and screen direction"),
        ("DETAIL", "insert detail", "anchor prop, hand, or environment state"),
        ("REACTION", "close reaction shot", "make the emotional turn readable"),
        ("TRANSITION", "transition plate", "bridge into the next beat"),
    ]
    planned: List[Dict[str, Any]] = []
    for scene in source_scenes:
        beats = scene.get("beats", [])
        if not isinstance(beats, list) or not beats:
            beats = [{"beat_id": f"{scene.get('scene_id', 'SC')}_B01", "action": scene.get("emotional_turn", ""), "characters": [], "continuity": {}}]
        for beat in beats:
            if not isinstance(beat, dict):
                continue
            role, coverage, purpose = coverage_cycle[len(planned) % len(coverage_cycle)]
            continuity = beat.get("continuity", {}) if isinstance(beat.get("continuity"), dict) else {}
            characters = beat.get("characters", []) if isinstance(beat.get("characters"), list) else []
            scene_id = str(scene.get("scene_id") or "SC_001")
            beat_id = str(beat.get("beat_id") or f"{scene_id}_B01")
            shot_num = len(planned) + 1
            visual = (
                f"{coverage} for {scene_id}/{beat_id}: {beat.get('action') or scene.get('emotional_turn') or 'story beat'}. "
                f"Location: {scene.get('location', 'locked location')}. Time/light: {scene.get('time_of_day', 'locked light')}. "
                f"Continuity: wardrobe {continuity.get('wardrobe', 'locked')}; props {', '.join(continuity.get('props', [])) if isinstance(continuity.get('props'), list) else continuity.get('props', 'locked')}; "
                f"screen direction {continuity.get('screen_direction', 'match prior axis')}. "
                f"Edit role: {role}; purpose: {purpose}; transition should motivate the next beat."
            )
            planned.append({
                "shot_id": f"{scene_id}_{beat_id}_SH_{shot_num:03d}".replace("__", "_"),
                "sequence": shot_num,
                "narrative_intent": f"{role}: {purpose}",
                "visual_brief": visual,
                "characters": characters,
                "environment": str(scene.get("location") or ""),
                "camera_direction": coverage,
                "lighting_direction": str(scene.get("time_of_day") or "match scene lighting"),
                "rationale": "Fallback coverage generated from locked script package after Director API failure.",
                "constraints": "Preserve scene continuity, wardrobe, prop state, screen direction, and edit role.",
            })
            if len(planned) >= target_shots:
                return planned

    while len(planned) < target_shots and planned:
        clone = dict(planned[len(planned) % len(planned)])
        clone["sequence"] = len(planned) + 1
        clone["shot_id"] = f"SHOT_{len(planned) + 1:03d}"
        clone["narrative_intent"] = "SUPPLEMENTAL COVERAGE: continuity-safe alternate angle"
        planned.append(clone)
    return planned[:target_shots]


def _storyboard_source_package(req: ScriptStoryboardRequest) -> Optional[Dict[str, Any]]:
    if isinstance(req.package, dict) and req.package:
        return req.package
    return _package_from_shotlist_brief(req.script or "")


def _asset_vault_prompt_context(package: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not package:
        return {"summary": "", "character_consistency": "", "reference_urls": []}
    pieces = [
        f"Asset Vault package: {package.get('name', '')}",
        f"Package type: {package.get('asset_type') or package.get('element_type') or 'package'}",
        f"Description: {_short_text(str(package.get('description') or ''), 420)}",
    ]
    for key, label in [
        ("brand_rules", "Brand rules"),
        ("style_rules", "Style rules"),
        ("logo_notes", "Logo notes"),
        ("font_notes", "Font notes"),
        ("prop_notes", "Prop notes"),
        ("location_notes", "Location notes"),
        ("notes", "Production notes"),
    ]:
        value = _short_text(str(package.get(key) or ""), 360)
        if value:
            pieces.append(f"{label}: {value}")
    tags = package.get("tags") if isinstance(package.get("tags"), list) else []
    if tags:
        pieces.append("Tags: " + ", ".join(str(t) for t in tags[:16]))

    character_lines: List[str] = []
    for char in package.get("characters", []) if isinstance(package.get("characters"), list) else []:
        if not isinstance(char, dict):
            continue
        character_lines.append(
            _short_text(
                f"{char.get('name') or char.get('id')}: package role {char.get('vault_role') or 'reference'}; "
                f"character role {char.get('role') or 'Character'}; notes {char.get('vault_notes') or ''}",
                260,
            )
        )
    if character_lines:
        pieces.append("Linked character references: " + " | ".join(character_lines[:10]))

    reference_urls: List[str] = []
    reference_lines: List[str] = []
    refs = package.get("references") if isinstance(package.get("references"), list) else []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        if str(ref.get("url") or "").strip():
            reference_urls.append(str(ref.get("url")).strip())
        reference_lines.append(
            _short_text(
                f"{ref.get('type') or 'reference'} - {ref.get('name') or ''}: {ref.get('prompt') or ref.get('notes') or ''}",
                260,
            )
        )
    if reference_lines:
        pieces.append("Package assets: " + " | ".join(reference_lines[:18]))

    return {
        "summary": _short_text(" ".join(p for p in pieces if p), 2400),
        "character_consistency": "; ".join(character_lines[:10]),
        "reference_urls": reference_urls[:12],
    }


def _apply_asset_vault_to_panels(panels: List[Dict[str, Any]], package: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    context = _asset_vault_prompt_context(package)
    summary = str(context.get("summary") or "")
    if not summary:
        return panels
    linked_names = [
        str(char.get("name") or char.get("id") or "").strip()
        for char in package.get("characters", []) if isinstance(char, dict)
    ] if isinstance(package, dict) and isinstance(package.get("characters"), list) else []
    for panel in panels:
        existing_chars = panel.get("characters") if isinstance(panel.get("characters"), list) else []
        merged_chars = list(existing_chars)
        for name in linked_names:
            if name and name not in merged_chars:
                merged_chars.append(name)
        panel["characters"] = merged_chars
        panel["asset_vault_context"] = summary
        panel["visual_prompt"] = _short_text(
            f"{panel.get('visual_prompt', '')} Asset Vault continuity lock: {summary}",
            1600,
        )
        panel["continuity"] = _short_text(
            f"{panel.get('continuity', '')} Asset Vault: {package.get('name', '')}; preserve package product, logo, font, style, prop, location, and linked character references exactly.",
            520,
        )
    return panels


def _storyboard_panels_from_package(package: Dict[str, Any], target_panels: Optional[int]) -> List[Dict[str, Any]]:
    panels: List[Dict[str, Any]] = []
    acts = package.get("script", {}).get("acts", [])
    scenes: List[Dict[str, Any]] = []
    if isinstance(acts, list):
        for act in acts:
            if isinstance(act, dict) and isinstance(act.get("scenes"), list):
                scenes.extend([s for s in act["scenes"] if isinstance(s, dict)])
    continuity = package.get("continuity", {}) if isinstance(package.get("continuity"), dict) else {}
    continuity_text = _short_text(json.dumps(continuity, ensure_ascii=True), 520)
    edit_plan = package.get("edit_plan", {}) if isinstance(package.get("edit_plan"), dict) else {}
    audio_strategy = str(edit_plan.get("audio_strategy") or "").strip()
    character_performance = "; ".join([
        f"{c.get('name')}: {c.get('performance')}"
        for c in continuity.get("characters", [])
        if isinstance(c, dict) and (c.get("name") or c.get("performance"))
    ])
    for scene in scenes:
        beats = scene.get("beats", [])
        if not isinstance(beats, list) or not beats:
            beats = [{"beat_id": f"{scene.get('scene_id', 'SC')}_B01", "action": scene.get("emotional_turn", ""), "characters": [], "continuity": {}}]
        for beat in beats:
            if not isinstance(beat, dict):
                continue
            panel_num = len(panels) + 1
            continuity_lock = beat.get("continuity", {}) if isinstance(beat.get("continuity"), dict) else {}
            dialogue = _short_text(str(beat.get("dialogue") or ""), 260)
            audio_cue = _short_text(str(beat.get("audio_cue") or scene.get("audio_cue") or audio_strategy or ""), 300)
            performance = _short_text(str(beat.get("performance") or scene.get("performance") or character_performance or ""), 320)
            panels.append({
                "panel_id": f"PANEL_{panel_num:03d}",
                "scene_id": str(scene.get("scene_id") or ""),
                "beat_id": str(beat.get("beat_id") or ""),
                "caption": _short_text(beat.get("action") or scene.get("emotional_turn") or "Story beat", 180),
                "characters": beat.get("characters", []) if isinstance(beat.get("characters"), list) else [],
                "location": str(scene.get("location") or ""),
                "camera": "filmic storyboard composition, clear subject silhouette, readable blocking, specific lens angle",
                "lighting": str(scene.get("time_of_day") or "motivated source-based light with consistent shadow direction"),
                "mood": str(scene.get("emotional_turn") or "narrative tension"),
                "text": _short_text(dialogue or beat.get("action") or scene.get("emotional_turn") or "", 120),
                "dialogue": dialogue,
                "audio_prompt": audio_cue,
                "performance_direction": performance,
                "continuity": _short_text(json.dumps(continuity_lock, ensure_ascii=True), 260),
                "visual_prompt": (
                    f"{beat.get('action') or scene.get('emotional_turn') or 'story beat'}. "
                    f"Scene {scene.get('scene_id', '')}: {scene.get('title', '')}. "
                    f"Location: {scene.get('location', '')}; time/light: {scene.get('time_of_day', '')}. "
                    f"Characters: {', '.join(beat.get('characters', [])) if isinstance(beat.get('characters'), list) else 'none specified'}. "
                    f"Continuity: {json.dumps(continuity_lock, ensure_ascii=True)}."
                ),
            })
            if target_panels and len(panels) >= target_panels:
                return panels
    if not panels:
        panels.append({
            "panel_id": "PANEL_001",
            "scene_id": "SC_001",
            "beat_id": "SC_001_B01",
            "caption": _short_text(package.get("brief") or package.get("title") or "Opening storyboard panel", 180),
            "characters": [],
            "location": "script environment",
            "camera": "wide establishing frame",
            "lighting": "motivated source-based light with consistent shadow direction",
            "mood": "opening image",
            "text": _short_text(package.get("brief") or package.get("title") or "", 120),
            "continuity": continuity_text,
            "visual_prompt": _short_text(package.get("brief") or json.dumps(package, ensure_ascii=True), 700),
        })
    return panels


def _storyboard_panels_from_text(script: str, target_panels: Optional[int]) -> List[Dict[str, Any]]:
    raw = re.sub(r"\s+", " ", script or "").strip()
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", raw) if p.strip()]
    if not parts:
        parts = [raw]
    desired = target_panels or min(9, max(3, len(parts)))
    desired = max(1, min(int(desired), 60))
    chunks: List[str] = []
    if len(parts) >= desired:
        step = max(1, round(len(parts) / desired))
        for i in range(0, len(parts), step):
            chunks.append(" ".join(parts[i:i + step]))
            if len(chunks) >= desired:
                break
    else:
        chunks = parts[:]
    coverage_expansion = [
        ("Opening wide shot", "wide establishing shot", "establish geography, weather, and screen direction"),
        ("Character approach", "medium tracking shot", "show the protagonist moving through the space"),
        ("Important object insert", "close-up insert", "isolate the clue, prop, signal, or hand action"),
        ("Reaction beat", "close-up reaction shot", "show the character processing new information"),
        ("Threshold reveal", "low angle reveal", "show the doorway, portal, enemy, or changed environment"),
        ("Environmental scale", "high wide shot", "show the larger space and relationship between character and threat"),
        ("Tension detail", "Dutch tilt detail shot", "increase unease through a visual fragment"),
        ("Confrontation", "over-the-shoulder shot", "stage the opposing force or discovery"),
        ("Closing image", "locked final frame", "resolve the page with a readable final image"),
    ]
    story_context = _short_text(raw, 900)
    panels = []
    for idx in range(1, desired + 1):
        source_idx = min(len(parts) - 1, round((idx - 1) * (len(parts) - 1) / max(1, desired - 1)))
        chunk = chunks[idx - 1] if idx - 1 < len(chunks) else parts[source_idx]
        stage, camera, purpose = coverage_expansion[(idx - 1) % len(coverage_expansion)]
        caption = _short_text(chunk, 130)
        action = f"{stage}: {caption}. Full story context: {story_context}. Visual purpose: {purpose}."
        panels.append({
            "panel_id": f"PANEL_{idx:03d}",
            "scene_id": "",
            "beat_id": "",
            "caption": _short_text(action, 180),
            "characters": [],
            "location": "script environment",
            "camera": f"{camera}, clear subject silhouette, readable blocking, filmic 16:9 frame",
            "lighting": "motivated source-based light with consistent shadow direction",
            "mood": "narrative progression",
            "text": _short_text(chunk, 120),
            "continuity": "derive wardrobe, props, geography, and screen direction from adjacent panels",
            "visual_prompt": action,
        })
    return panels


def _parse_storyboard_resolution(value: str) -> tuple[int, int]:
    match = re.match(r"^\s*(\d{3,5})\s*x\s*(\d{3,5})\s*$", value or "", re.I)
    if not match:
        return 3840, 2160
    width = max(512, min(int(match.group(1)), 8192))
    height = max(512, min(int(match.group(2)), 8192))
    return width, height


def _storyboard_layout_dimensions(panel_count: int) -> tuple[int, int, str]:
    count = max(1, min(int(panel_count or 1), 9))
    if count >= 9:
        return 3, 3, "3x3"
    if count >= 7:
        return 4, 2, "4x2"
    if count >= 5:
        return 3, 2, "3x2"
    if count >= 3:
        return 2, 2, "2x2"
    if count == 2:
        return 2, 1, "2x1"
    return 1, 1, "1x1"


def _storyboard_panel_render_size(resolution: str, columns: int, rows: int) -> str:
    width, height = _parse_storyboard_resolution(resolution)
    aspect = width / max(1, height)
    if aspect >= 1.2:
        return "1920x1080"
    if aspect <= 0.85:
        return "1080x1920"
    return "1536x1536"


def _single_storyboard_panel_prompt(
    *,
    panel: Dict[str, Any],
    local_idx: int,
    board_idx: int,
    title: str,
    style: str,
    character_consistency: str,
    include_captions: bool,
    reference_note: str,
    negative_prompt: str,
) -> str:
    character_text = ", ".join(panel.get("characters") or []) or "same character design as established in the script"
    text_clause = (
        f"Optional small production note below frame: \"{panel.get('text') or panel.get('caption') or ''}\"."
        if include_captions
        else "No text, no captions, no dialogue, no titles, no panel number."
    )
    prompt = (
        f"Single high-resolution cinematic production keyframe for board {board_idx} shot {local_idx} of '{title}'. "
        "This is an image-to-video start frame, not a storyboard page, not a contact sheet, not a grid. "
        f"Style: {style}. "
        f"Scene action: {panel.get('visual_prompt', '')} "
        f"Setting: {panel.get('location', '')}. Camera: {panel.get('camera', '')}. "
        f"Lighting: {panel.get('lighting', 'motivated source-based light with consistent shadow direction')}. "
        f"Mood: {panel.get('mood', 'narrative progression')}. "
        f"Characters: {character_text}. Character consistency: {character_consistency}. "
        f"Continuity: {panel.get('continuity', '')}. {text_clause} "
        "Make one clean cinematic frame with readable blocking, crisp subject edges, sharp eyes, clear hands, detailed textures, "
        "controlled depth of field, consistent wardrobe, consistent face, cinematic composition, tactile material detail, "
        "natural skin or surface imperfections, no border, no panel frame, no page layout, no watermark."
        + reference_note
    )
    if panel.get("asset_vault_context"):
        prompt += f" Asset Vault production package lock: {panel.get('asset_vault_context')}."
    if negative_prompt:
        prompt += f" Negative prompt: {negative_prompt}."
    return prompt


def _storyboard_font(size: int) -> ImageFont.ImageFont:
    for font_path in [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _draw_text_fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int],
    max_size: int,
    min_size: int = 18,
) -> None:
    clean = _short_text(re.sub(r"\s+", " ", text or "").strip(), 160)
    if not clean:
        return
    x1, y1, x2, y2 = box
    size = max_size
    while size >= min_size:
        font = _storyboard_font(size)
        bbox = draw.textbbox((0, 0), clean, font=font)
        if bbox[2] - bbox[0] <= x2 - x1 and bbox[3] - bbox[1] <= y2 - y1:
            draw.text((x1, y1), clean, fill=fill, font=font)
            return
        size -= 2
    draw.text((x1, y1), clean, fill=fill, font=_storyboard_font(min_size))


def _assemble_storyboard_page(req: ScriptStoryboardAssembleRequest) -> Dict[str, Any]:
    panel_urls = [u for u in req.panel_image_urls if (u or "").strip()]
    if not panel_urls:
        raise HTTPException(status_code=400, detail="panel_image_urls required")
    panel_paths: List[Path] = []
    for url in panel_urls:
        path = _resolve_image_path(url.strip())
        if not path:
            raise HTTPException(status_code=400, detail=f"panel image not found: {url}")
        panel_paths.append(path)

    width, height = _parse_storyboard_resolution(req.resolution or "3840x2160")
    columns = max(1, min(int(req.columns or 3), 9))
    rows = max(1, min(int(req.rows or 3), 9))
    if columns * rows < len(panel_paths):
        rows = max(rows, (len(panel_paths) + columns - 1) // columns)

    canvas = Image.new("RGB", (width, height), (248, 248, 246))
    draw = ImageDraw.Draw(canvas)
    margin = max(32, width // 80)
    gutter = max(16, width // 240)
    title = _short_text(req.title or "", 96)
    title_h = max(0, height // 24) if title else 0
    if title:
        _draw_text_fit(
            draw,
            title,
            (margin, max(12, margin // 2), width - margin, margin // 2 + title_h),
            fill=(22, 22, 22),
            max_size=max(32, height // 42),
            min_size=20,
        )

    grid_top = margin + title_h
    grid_h = height - grid_top - margin
    cell_w = max(64, (width - (margin * 2) - gutter * (columns - 1)) // columns)
    cell_h = max(64, (grid_h - gutter * (rows - 1)) // rows)
    captions = req.captions if isinstance(req.captions, list) else []
    caption_h = max(0, min(cell_h // 5, height // 18)) if captions else 0
    image_h = max(64, cell_h - caption_h)
    number_font = _storyboard_font(max(24, min(width, height) // 70))
    caption_font = _storyboard_font(max(16, min(width, height) // 110))

    for idx, path in enumerate(panel_paths):
        col = idx % columns
        row = idx // columns
        if row >= rows:
            break
        x = margin + col * (cell_w + gutter)
        y = grid_top + row * (cell_h + gutter)
        shadow = max(6, width // 500)
        draw.rectangle((x + shadow, y + shadow, x + cell_w + shadow, y + image_h + shadow), fill=(210, 210, 210))
        with Image.open(path) as source:
            frame = ImageOps.fit(source.convert("RGB"), (cell_w, image_h), method=Image.Resampling.LANCZOS)
        canvas.paste(frame, (x, y))
        draw.rectangle((x, y, x + cell_w, y + image_h), outline=(255, 255, 255), width=max(4, width // 700))
        draw.rectangle((x, y, x + cell_w, y + image_h), outline=(18, 18, 18), width=max(1, width // 1800))
        if req.include_panel_numbers:
            label = str(idx + 1)
            bbox = draw.textbbox((0, 0), label, font=number_font)
            pad = max(8, width // 420)
            label_w = bbox[2] - bbox[0] + pad * 2
            label_h = bbox[3] - bbox[1] + pad * 2
            draw.rectangle((x + pad, y + pad, x + pad + label_w, y + pad + label_h), fill=(255, 255, 255))
            draw.rectangle((x + pad, y + pad, x + pad + label_w, y + pad + label_h), outline=(20, 20, 20), width=2)
            draw.text((x + pad * 2, y + pad * 2), label, fill=(18, 18, 18), font=number_font)
        if caption_h and idx < len(captions):
            cap_y = y + image_h + max(8, gutter // 2)
            draw.text((x, cap_y), _short_text(str(captions[idx] or ""), 120), fill=(24, 24, 24), font=caption_font)

    out_dir = MEDIA_ROOT / "storyboards"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"storyboard_{uuid.uuid4().hex[:12]}.png"
    canvas.save(out_path, format="PNG", optimize=True)
    return {
        "status": "ok",
        "url": _media_url_for_path(out_path),
        "path": str(out_path),
        "resolution": f"{width}x{height}",
        "columns": columns,
        "rows": rows,
        "panel_count": len(panel_paths),
    }


def _storyboard_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value or "").strip("_").lower()
    return slug[:42] or f"storyboard_{uuid.uuid4().hex[:8]}"


def _storyboard_edit_role(sequence: int, total: int, panel: Dict[str, Any]) -> str:
    text = f"{panel.get('caption', '')} {panel.get('camera', '')} {panel.get('visual_prompt', '')}".lower()
    if sequence == 1 or "establish" in text or "wide" in text:
        return "establish geography and screen direction"
    if sequence == total or "closing" in text or "final" in text:
        return "transition out / end frame"
    if "insert" in text or "detail" in text or "prop" in text:
        return "insert detail for edit emphasis"
    if "reaction" in text or "close-up" in text:
        return "performance reaction beat"
    if "reveal" in text or "threshold" in text:
        return "reveal / escalation beat"
    if "over-the-shoulder" in text or "confrontation" in text:
        return "shot reverse / confrontation coverage"
    return "continuity coverage beat"


def _ltx_dialogue_sentence(dialogue: str) -> str:
    text = _short_text(str(dialogue or "").strip(), 220)
    if not text:
        return "none; silent acting only, do not invent spoken words"
    speaker = "The character"
    line = text
    if ":" in text:
        left, right = text.split(":", 1)
        if left.strip() and right.strip():
            speaker = left.strip()
            line = right.strip()
    line = line.strip().strip('"')
    return f'{speaker}: "{line}"'


def _storyboard_motion_prompt(panel: Dict[str, Any], sequence: int, total: int, edit_role: str) -> str:
    camera = str(panel.get("camera") or "subtle cinematic camera move").strip()
    action = _short_text(str(panel.get("visual_prompt") or panel.get("caption") or "Continue the scene from this frame."), 420)
    continuity = _short_text(str(panel.get("continuity") or "preserve wardrobe, subject identity, props, lighting, and screen direction"), 240)
    dialogue = _short_text(str(panel.get("dialogue") or ""), 260)
    audio_prompt = _short_text(str(panel.get("audio_prompt") or ""), 320)
    performance = _short_text(str(panel.get("performance_direction") or ""), 320)
    dialogue_line = _ltx_dialogue_sentence(dialogue)
    audio_line = audio_prompt or "natural location ambience and motivated foley only"
    performance_line = performance or "subtle, readable acting timed to the spoken or silent beat"
    return (
        f"LTX 2.3 short shot prompt. Shot {sequence} of {total}; edit role: {edit_role}. "
        f"Use the supplied image as the locked first frame. "
        f"Visual action: {action} "
        f"Exact dialogue: {dialogue_line}. "
        f"Audio cue: {audio_line}. "
        f"Performance: {performance_line}. "
        f"Camera: {camera}; controlled cinematic motion, no abrupt reframing. "
        f"Continuity lock: {continuity}. "
        "Generate synchronized audio for this short clip from the dialogue and audio cue only. "
        "Do not add extra dialogue, subtitles, captions, text overlays, new characters, morphing, or cuts inside the clip. "
        "Preserve character identity, wardrobe, props, lighting, lens feel, and location geometry."
    )


def _storyboard_panel_sequence(panel: Dict[str, Any], fallback_index: int, sequence_offset: int = 0) -> int:
    if sequence_offset:
        return max(1, int(sequence_offset) + int(fallback_index))
    raw_id = str(panel.get("panel_id") or panel.get("id") or "")
    match = re.search(r"(\d+)$", raw_id)
    if match:
        try:
            return max(1, int(match.group(1)))
        except ValueError:
            pass
    return max(1, int(fallback_index))


def _export_storyboard_video_shots(req: ScriptStoryboardVideoExportRequest) -> Dict[str, Any]:
    board = req.board if isinstance(req.board, dict) else {}
    panels = board.get("panels") if isinstance(board.get("panels"), list) else []
    urls = [u for u in req.panel_image_urls if (u or "").strip()]
    if not panels:
        raise HTTPException(status_code=400, detail="board.panels required")
    if len(urls) != len(panels):
        raise HTTPException(status_code=400, detail="panel_image_urls must match board.panels length")

    title = (req.title or board.get("title") or "Storyboard").strip() or "Storyboard"
    campaign_id = (req.campaign_id or f"storyboard_{_storyboard_slug(title)}_{uuid.uuid4().hex[:8]}").strip()
    duration = max(1.0, min(float(req.duration_seconds or 4.0), 20.0))
    if req.replace_existing:
        _SHOTS_STORE[:] = [
            shot for shot in _SHOTS_STORE
            if not (
                str(shot.get("source") or "") == "storyboard_start_frame"
                and str(shot.get("campaign_id") or "") == campaign_id
            )
        ]

    created: List[Dict[str, Any]] = []
    total = len(panels)
    total_for_prompt = max(total, int(req.total_shots or 0))
    for index, (panel, url) in enumerate(zip(panels, urls), start=1):
        if not isinstance(panel, dict):
            panel = {}
        image_path = _resolve_image_path(url)
        edit_role = _storyboard_edit_role(index, total, panel)
        sequence = _storyboard_panel_sequence(panel, index, int(req.sequence_offset or 0))
        shot_id = f"SB_{sequence:03d}"
        record_id = f"{campaign_id}__{shot_id}"
        visual = _short_text(str(panel.get("visual_prompt") or panel.get("caption") or f"Storyboard panel {index}"), 900)
        video_prompt = _storyboard_motion_prompt(panel, sequence, total_for_prompt, edit_role)
        shot = {
            "id": record_id,
            "shot_id": shot_id,
            "source": "storyboard_start_frame",
            "campaign_id": campaign_id,
            "campaign_title": title,
            "n": sequence,
            "sequence": sequence,
            "status": "rendered",
            "intent": "video",
            "description": visual,
            "prompt": visual,
            "image_url": url,
            "image_path": str(image_path) if image_path else "",
            "start_frame_url": url,
            "video_prompt": video_prompt,
            "video_prompt_source": "storyboard_export",
            "dialogue": str(panel.get("dialogue") or ""),
            "audio_prompt": str(panel.get("audio_prompt") or ""),
            "performance_direction": str(panel.get("performance_direction") or ""),
            "duration_sec": duration,
            "scene_id": str(panel.get("scene_id") or ""),
            "beat_id": str(panel.get("beat_id") or ""),
            "panel_id": str(panel.get("panel_id") or f"PANEL_{index:03d}"),
            "storyboard_board_id": str(board.get("board_id") or ""),
            "storyboard_panel_index": index,
            "camera_direction": str(panel.get("camera") or ""),
            "lighting_direction": str(panel.get("lighting") or ""),
            "mood": str(panel.get("mood") or ""),
            "environment": str(panel.get("location") or ""),
            "characters": panel.get("characters", []) if isinstance(panel.get("characters"), list) else [],
            "constraints": str(panel.get("continuity") or ""),
            "edit_role": edit_role,
            "seed": random.randint(100000, 999999),
            "created_at": _now_iso(),
        }
        _SHOTS_STORE.append(shot)
        created.append(shot)

    _record_pipeline_event(
        "storyboard_export_video_shots",
        campaign_id=campaign_id,
        source="script",
        success=True,
        extra={"shot_count": len(created), "title": title},
    )
    return {
        "status": "ok",
        "campaign_id": campaign_id,
        "title": title,
        "count": len(created),
        "shot_ids": [shot["id"] for shot in created],
        "shots": created,
    }


def _storyboard_payload_url(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    if payload.get("url"):
        return str(payload.get("url") or "")
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    first = jobs[0] if jobs and isinstance(jobs[0], dict) else {}
    results = first.get("results") if isinstance(first.get("results"), dict) else {}
    for key in ("raw", "min"):
        item = results.get(key) if isinstance(results.get(key), dict) else {}
        if item.get("url"):
            return str(item.get("url") or "")
    all_items = results.get("all") if isinstance(results.get("all"), list) else []
    for item in all_items:
        if isinstance(item, dict) and item.get("url"):
            return str(item.get("url") or "")
    return ""


def _script_project_shots(campaign_id: str) -> List[Dict[str, Any]]:
    return [
        dict(shot)
        for shot in _SHOTS_STORE
        if str(shot.get("campaign_id") or "") == campaign_id
    ]


def _script_video_shots(campaign_id: str) -> List[Dict[str, Any]]:
    return [
        dict(shot)
        for shot in _SHOTS_STORE
        if str(shot.get("campaign_id") or "") == campaign_id
        and str(shot.get("source") or "") == "storyboard_start_frame"
    ]


def _rebuild_script_video_shots_from_storyboard_frames(script_id: str, storyboard: Dict[str, Any], panel_jobs: Dict[str, Any]) -> List[Dict[str, Any]]:
    campaign_id = f"script_{_safe_script_id(script_id)}"
    existing = _script_video_shots(campaign_id)
    if existing:
        return existing
    boards = storyboard.get("boards", []) if isinstance(storyboard, dict) else []
    if not isinstance(boards, list) or not boards:
        return []
    total_panels = sum(
        len(board.get("panels", []))
        for board in boards
        if isinstance(board, dict) and isinstance(board.get("panels"), list)
    )
    rebuilt: List[Dict[str, Any]] = []
    sequence_offset = 0
    first_board = True
    for board in boards:
        if not isinstance(board, dict):
            continue
        panels = board.get("panels") if isinstance(board.get("panels"), list) else []
        board_index = str(int(board.get("index") or 1))
        jobs = panel_jobs.get(board_index, []) if isinstance(panel_jobs.get(board_index), list) else []
        urls = [
            str(item.get("url") or "")
            for item in jobs
            if isinstance(item, dict) and str(item.get("url") or "").strip()
        ]
        if not panels or not urls:
            sequence_offset += len(panels)
            continue
        paired_count = min(len(panels), len(urls))
        board_for_export = {**board, "panels": panels[:paired_count]}
        try:
            export = _export_storyboard_video_shots(ScriptStoryboardVideoExportRequest(
                board=board_for_export,
                panel_image_urls=urls[:paired_count],
                title=str(storyboard.get("title") or board.get("title") or "Storyboard"),
                campaign_id=campaign_id,
                duration_seconds=5,
                replace_existing=first_board,
                sequence_offset=sequence_offset,
                total_shots=total_panels,
            ))
        except Exception:
            sequence_offset += len(panels)
            continue
        first_board = False
        rebuilt.extend(export.get("shots", []) if isinstance(export.get("shots"), list) else [])
        sequence_offset += len(panels)
    return rebuilt


def _script_video_file_candidates(record_id: str, campaign_id: str) -> List[Path]:
    safe_campaign = _safe_campaign_name(campaign_id)
    root = MEDIA_VIDEOS / safe_campaign
    if not root.exists():
        return []
    exts = {".mp4", ".mov", ".webm", ".m4v"}
    return sorted(
        path for path in root.glob(f"{record_id}__video*")
        if path.is_file() and path.suffix.lower() in exts
    )


def _attach_existing_video_file_to_script_shot(
    shot: Dict[str, Any],
    video_path: Path,
    job: Optional[Dict[str, Any]] = None,
) -> bool:
    if not video_path.exists():
        return False
    shot["video_path"] = str(video_path)
    shot["video_url"] = _media_video_url_for_path(video_path)
    if isinstance(job, dict):
        shot["video_prompt_id"] = job.get("prompt_id") or shot.get("video_prompt_id", "")
        shot["video_workflow_id"] = job.get("workflow_id") or shot.get("video_workflow_id", "")
        shot["video_seed"] = job.get("seed", shot.get("video_seed"))
        shot["video_duration"] = job.get("duration", shot.get("video_duration"))
        shot["video_fps"] = job.get("fps", shot.get("video_fps"))
    shot["video_status"] = "complete"
    shot["video_error"] = ""
    shot["video_error_detail"] = ""
    shot["video_error_node"] = ""
    shot["video_last_checked_at"] = _now_iso()
    shot["video_completed_at"] = shot.get("video_completed_at") or _now_iso()
    _persist_media_shot_metadata(shot)
    return True


def _repair_script_video_urls_from_existing_outputs(script_id: str, video_shots: List[Dict[str, Any]], job: Any = None) -> bool:
    if not video_shots:
        return False
    campaign_id = f"script_{_safe_script_id(script_id)}"
    changed = False
    video_jobs = job.get("video_jobs", []) if isinstance(job, dict) and isinstance(job.get("video_jobs"), list) else []
    jobs_by_shot: Dict[str, List[Dict[str, Any]]] = {}
    for item in video_jobs:
        if isinstance(item, dict):
            jobs_by_shot.setdefault(str(item.get("shot_id") or ""), []).append(item)

    for shot in video_shots:
        if not isinstance(shot, dict) or shot.get("video_url"):
            continue
        record_id = str(shot.get("id") or "")
        if not record_id:
            continue
        candidates = _script_video_file_candidates(record_id, campaign_id)
        if candidates and _attach_existing_video_file_to_script_shot(shot, candidates[0], (jobs_by_shot.get(record_id) or [{}])[0]):
            changed = True

    if all(isinstance(shot, dict) and shot.get("video_url") for shot in video_shots):
        return changed

    complete_jobs = [
        item for item in video_jobs
        if isinstance(item, dict) and str(item.get("status") or "").lower() in {"complete", "completed"} and item.get("shot_id")
    ]
    old_shot_ids = sorted({str(item.get("shot_id") or "") for item in complete_jobs})
    if len(old_shot_ids) < 2:
        return changed
    match_numbers = [
        int(match.group(1))
        for old_id in old_shot_ids
        for match in [re.search(r"__SB_(\d+)$", old_id)]
        if match
    ]
    if not match_numbers:
        return changed
    per_board = max(match_numbers)
    if per_board <= 0:
        return changed

    legacy_files_by_base: Dict[int, List[Path]] = {}
    legacy_jobs_by_base: Dict[int, List[Dict[str, Any]]] = {}
    for old_id in old_shot_ids:
        match = re.search(r"__SB_(\d+)$", old_id)
        if not match:
            continue
        base_num = int(match.group(1))
        legacy_files_by_base[base_num] = _script_video_file_candidates(old_id, campaign_id)
        legacy_jobs_by_base[base_num] = jobs_by_shot.get(old_id, [])

    ordered_shots = sorted(
        [shot for shot in video_shots if isinstance(shot, dict)],
        key=lambda shot: int(shot.get("sequence") or shot.get("n") or 0),
    )
    for shot in ordered_shots:
        if shot.get("video_url"):
            continue
        sequence = int(shot.get("sequence") or shot.get("n") or 0)
        if sequence <= 0:
            continue
        base_num = ((sequence - 1) % per_board) + 1
        occurrence = (sequence - 1) // per_board
        candidates = legacy_files_by_base.get(base_num, [])
        if occurrence >= len(candidates):
            continue
        legacy_jobs = legacy_jobs_by_base.get(base_num, [])
        legacy_job = legacy_jobs[occurrence] if occurrence < len(legacy_jobs) else None
        if _attach_existing_video_file_to_script_shot(shot, candidates[occurrence], legacy_job):
            changed = True
    return changed


def _pipeline_job_path(project_id: str) -> Path:
    return _script_project_dir(project_id) / "pipeline_job.json"


def _save_pipeline_job(job: Dict[str, Any]) -> None:
    job["updated_at"] = _now_iso()
    _SCRIPT_PIPELINE_JOBS[str(job.get("job_id") or "")] = job
    project_id = str(job.get("script_id") or "")
    if project_id:
        _write_json_atomic(_pipeline_job_path(project_id), job)


def _pipeline_log(job: Dict[str, Any], phase: str, message: str, level: str = "info", **extra: Any) -> None:
    entry = {
        "timestamp": _now_iso(),
        "phase": phase,
        "level": level,
        "message": message,
        **extra,
    }
    logs = job.setdefault("logs", [])
    if isinstance(logs, list):
        logs.append(entry)
        if len(logs) > 300:
            del logs[: len(logs) - 300]
    job["phase"] = phase
    _save_pipeline_job(job)


def _coverage_brief_from_package(package: Dict[str, Any], original_brief: str = "") -> str:
    return "\n".join([
        "LOCKED SCRIPT PACKAGE FOR SHOTLIST GENERATION:",
        json.dumps(package, ensure_ascii=True, indent=2),
        "",
        "Generate coverage from the locked package. Preserve scene_id, beat_id, continuity, screen direction, edit role, duration, transition intent, audio cue, character wardrobe, prop state, and location state. Do not invent unrelated scenes.",
        ("\nORIGINAL USER BRIEF:\n" + original_brief.strip()) if original_brief.strip() else "",
    ]).strip()


async def _ensure_local_director_model_loaded(job: Dict[str, Any]) -> None:
    cfg = get_raw_config()
    if not _truthy_config(cfg.get("USE_LOCAL_DIRECTOR", "")):
        return
    model = str(cfg.get("LMSTUDIO_CHAT_MODEL") or cfg.get("KIMI_VISUAL_MODEL") or "").strip()
    if not model:
        raise RuntimeError("Local LM Studio Director is enabled, but no Director model is configured.")
    base = _normalize_lmstudio_base_url(cfg.get("LMSTUDIO_HOST", ""), cfg.get("LMSTUDIO_PORT", ""))
    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            loaded_resp = await client.get(f"{base}/v1/models")
            loaded_resp.raise_for_status()
            loaded = [
                item.get("id")
                for item in loaded_resp.json().get("data", [])
                if isinstance(item, dict) and item.get("id")
            ]
        except Exception as exc:
            raise RuntimeError(f"Local LM Studio Director is unreachable at {base}: {exc}") from exc
        if model in loaded:
            return
        _pipeline_log(job, "script", f"Loading local Director model in LM Studio: {model}")
        load_resp = await client.post(
            f"{base}/api/v1/models/load",
            headers={"Content-Type": "application/json"},
            json={"model": model, "echo_load_config": True},
        )
        if load_resp.status_code >= 400:
            raise RuntimeError(f"Local LM Studio model load failed: http {load_resp.status_code}: {load_resp.text[:500]}")
        _pipeline_log(job, "script", f"Local Director model loaded: {model}")


async def _coverage_from_script_package(
    *,
    package: Dict[str, Any],
    original_brief: str,
    campaign_id: str,
    runtime_seconds: int,
    target_shots: Optional[int],
) -> List[Dict[str, Any]]:
    brief = _coverage_brief_from_package(package, original_brief)
    director = KimiDirectorService()
    target = int(target_shots or director.requested_shot_count(brief, str(runtime_seconds or "")))
    target = max(1, min(target, 120))
    try:
        plan = await director.request_plan(
            brief=brief,
            campaign_id=campaign_id,
            length=str(runtime_seconds or ""),
            target_shots=target,
        )
        normalized = director.normalize_shots(plan, campaign_id)
    except Exception:
        normalized = _fallback_director_shots_from_brief(brief, campaign_id, target)
    shots = [_script_shot_from_director_plan(s, campaign_id) for s in normalized]
    _SHOTS_STORE[:] = [
        s for s in _SHOTS_STORE
        if not (str(s.get("source") or "") == "script_director" and str(s.get("campaign_id") or "") == campaign_id)
    ]
    _SHOTS_STORE.extend(shots)
    return shots


async def _run_script_pipeline_job(job_id: str, req: ScriptPipelineStartRequest) -> None:
    job = _SCRIPT_PIPELINE_JOBS.get(job_id)
    if not job:
        return
    script_id = str(job.get("script_id") or "")
    campaign_id = f"script_{script_id}"
    try:
        job["status"] = "running"
        _pipeline_log(job, "project", "Pipeline started")
        project = _load_script_project(script_id)
        package = project.get("package") if isinstance(project.get("package"), dict) else None

        if not package:
            _pipeline_log(job, "script", "Generating locked script package")
            await _ensure_local_director_model_loaded(job)
            package = await _request_script_package(ScriptDevelopRequest(
                title=req.title,
                brief=req.brief,
                tone=req.tone,
                runtime_seconds=req.runtime_seconds,
                target_scenes=req.target_scenes,
                hook_first_dialogue=req.hook_first_dialogue,
            ))
            project = _save_script_project_payload({
                "script_id": script_id,
                "title": req.title,
                "brief": req.brief,
                "tone": req.tone,
                "runtime_seconds": req.runtime_seconds,
                "target_scenes": req.target_scenes,
                "hook_first_dialogue": req.hook_first_dialogue,
                "package": package,
                "status": "script_ready",
                "active_job_id": job_id,
            })
        else:
            _pipeline_log(job, "script", "Using saved script package")

        if req.stop_after == "script":
            job["status"] = "complete"
            _pipeline_log(job, "script", "Pipeline stopped after script package")
            return

        _pipeline_log(job, "coverage", "Generating coverage shot list")
        await _ensure_local_director_model_loaded(job)
        coverage_shots = await _coverage_from_script_package(
            package=package,
            original_brief=req.brief,
            campaign_id=campaign_id,
            runtime_seconds=req.runtime_seconds,
            target_shots=req.target_shots,
        )
        project = _save_script_project_payload({
            "script_id": script_id,
            "title": req.title,
            "brief": req.brief,
            "tone": req.tone,
            "runtime_seconds": req.runtime_seconds,
            "target_scenes": req.target_scenes,
            "hook_first_dialogue": req.hook_first_dialogue,
            "package": package,
            "coverage_shots": coverage_shots,
            "status": "coverage_ready",
            "active_job_id": job_id,
        })
        job["coverage_count"] = len(coverage_shots)
        _pipeline_log(job, "coverage", f"Coverage ready: {len(coverage_shots)} shot(s)")

        if req.stop_after == "coverage":
            job["status"] = "complete"
            _pipeline_log(job, "coverage", "Pipeline stopped after coverage")
            return

        _pipeline_log(job, "storyboard", "Building storyboard plan")
        storyboard_plan = _build_storyboard_boards(ScriptStoryboardRequest(
            script=_coverage_brief_from_package(package, req.brief),
            package=package,
            asset_vault_package_id=req.asset_vault_package_id,
            panels_per_board=req.storyboard_panels_per_board,
            target_panels=req.storyboard_target_panels,
            resolution=req.storyboard_resolution,
            title=req.title,
            style=req.storyboard_style,
            character_consistency=req.storyboard_character_consistency,
            negative_prompt=req.storyboard_negative_prompt,
            reference_image_url=req.storyboard_reference_image_url,
            include_captions=req.storyboard_include_captions,
        ))
        project = _save_script_project_payload({
            "script_id": script_id,
            "title": req.title,
            "brief": req.brief,
            "tone": req.tone,
            "runtime_seconds": req.runtime_seconds,
            "target_scenes": req.target_scenes,
            "hook_first_dialogue": req.hook_first_dialogue,
            "package": package,
            "coverage_shots": coverage_shots,
            "storyboard_plan": storyboard_plan,
            "status": "storyboard_ready",
            "active_job_id": job_id,
        })
        job["storyboard_count"] = int(storyboard_plan.get("panel_count") or 0)
        _pipeline_log(job, "storyboard", f"Storyboard ready: {storyboard_plan.get('panel_count', 0)} panel(s)")

        if req.stop_after == "storyboard":
            job["status"] = "complete"
            _pipeline_log(job, "storyboard", "Pipeline stopped after storyboard plan")
            return

        panel_jobs: Dict[str, Any] = {}
        _pipeline_log(job, "frames", "Queueing storyboard panel start frames")
        adapter = _make_local_higgsfield_adapter()
        for board in storyboard_plan.get("boards", []) if isinstance(storyboard_plan.get("boards"), list) else []:
            if not isinstance(board, dict):
                continue
            board_index = str(int(board.get("index") or 1))
            panel_jobs[board_index] = []
            panels = board.get("panels") if isinstance(board.get("panels"), list) else []
            for idx, panel in enumerate(panels, start=1):
                if not isinstance(panel, dict):
                    panel = {}
                payload = await _generate_storyboard_image(StoryboardImageGenerateRequest(
                    provider=req.storyboard_image_provider,
                    model=req.storyboard_image_model,
                    spark_model=req.storyboard_spark_model,
                    prompt=str(panel.get("single_panel_prompt") or panel.get("visual_prompt") or panel.get("caption") or ""),
                    width_and_height=str(panel.get("width_and_height") or board.get("panel_width_and_height") or "1920x1080"),
                    quality="1080p",
                    title=f"{script_id}_board_{board_index}_panel_{idx}",
                    enhance_prompt=False,
                    wait_for_output=False,
                    image_reference_url=str(board.get("reference_image_url") or ""),
                ))
                url = _storyboard_payload_url(payload)
                item = {
                    "index": idx,
                    "status": payload.get("status", "queued"),
                    "job_set_id": payload.get("job_set_id") or payload.get("id") or "",
                    "provider": payload.get("provider") or req.storyboard_image_provider,
                    "model": payload.get("model") or req.storyboard_spark_model or req.storyboard_image_model,
                    "url": url,
                    "raw": payload,
                }
                panel_jobs[board_index].append(item)
                _save_script_project_payload({
                    "script_id": script_id,
                    "storyboard_panel_jobs": panel_jobs,
                    "status": "frames_rendering",
                    "active_job_id": job_id,
                })
                _pipeline_log(job, "frames", f"Queued board {board_index} panel {idx}", url=url)

        pending = [
            (board_idx, item)
            for board_idx, items in panel_jobs.items()
            for item in items
            if not item.get("url") and item.get("job_set_id")
        ]
        frame_wait_seconds = int(os.getenv("FORGE_STORYBOARD_FRAME_WAIT_SEC", "0") or "0") or int(req.video_wait_seconds or 21600)
        deadline = time.time() + max(21600, frame_wait_seconds)
        completed_keys: set[str] = set()
        while pending and time.time() < deadline:
            remaining = []
            for board_idx, item in pending:
                try:
                    status_payload = await adapter.get_job_status(str(item.get("job_set_id") or ""))
                except Exception as exc:
                    item["status"] = "queued"
                    item["error"] = str(exc)[:300]
                    remaining.append((board_idx, item))
                    continue
                item["status"] = status_payload.get("status", item.get("status", "queued"))
                item["raw"] = status_payload
                url = _storyboard_payload_url(status_payload)
                if url:
                    item["url"] = url
                    key = f"{board_idx}:{item.get('index')}"
                    if key not in completed_keys:
                        completed_keys.add(key)
                        _pipeline_log(job, "frames", f"Rendered board {board_idx} panel {item.get('index')}", url=url)
                else:
                    remaining.append((board_idx, item))
            _save_script_project_payload({
                "script_id": script_id,
                "storyboard_panel_jobs": panel_jobs,
                "status": "frames_rendering",
                "active_job_id": job_id,
            })
            pending = remaining
            if pending:
                await asyncio.sleep(5)
        missing = [
            f"{board_idx}:{item.get('index')}"
            for board_idx, items in panel_jobs.items()
            for item in items
            if not item.get("url")
        ]
        if missing:
            raise RuntimeError("missing storyboard frame outputs: " + ", ".join(missing[:12]))
        project = _save_script_project_payload({
            "script_id": script_id,
            "storyboard_panel_jobs": panel_jobs,
            "status": "frames_ready",
            "active_job_id": job_id,
        })

        if req.stop_after == "frames":
            job["status"] = "complete"
            _pipeline_log(job, "frames", "Pipeline stopped after start frames")
            return

        _pipeline_log(job, "videos", "Exporting storyboard frames as video shots")
        all_video_shots: List[Dict[str, Any]] = []
        first_board = True
        sequence_offset = 0
        total_storyboard_panels = int(storyboard_plan.get("panel_count") or 0)
        for board in storyboard_plan.get("boards", []) if isinstance(storyboard_plan.get("boards"), list) else []:
            if not isinstance(board, dict):
                continue
            board_index = str(int(board.get("index") or 1))
            panels = board.get("panels") if isinstance(board.get("panels"), list) else []
            urls = [str(item.get("url") or "") for item in panel_jobs.get(board_index, []) if item.get("url")]
            export = _export_storyboard_video_shots(ScriptStoryboardVideoExportRequest(
                board=board,
                panel_image_urls=urls,
                title=req.title or str(storyboard_plan.get("title") or "Storyboard"),
                campaign_id=campaign_id,
                duration_seconds=float(req.video_duration or 5),
                replace_existing=first_board,
                sequence_offset=sequence_offset,
                total_shots=total_storyboard_panels,
            ))
            first_board = False
            all_video_shots.extend(export.get("shots", []) if isinstance(export.get("shots"), list) else [])
            sequence_offset += len(panels)
        current_video_shots = _script_video_shots(campaign_id) or all_video_shots
        project = _save_script_project_payload({
            "script_id": script_id,
            "video_shots": current_video_shots,
            "status": "video_shots_ready",
            "active_job_id": job_id,
        })
        _pipeline_log(job, "videos", f"Created {len(all_video_shots)} video shot record(s)")

        if req.run_video:
            preflight = _video_workflow_preflight(req.video_workflow_id)
            if not preflight.get("available"):
                raise RuntimeError(f"video workflow not found: {preflight.get('workflow_id')}")
            workflow_id = str(preflight.get("workflow_id") or req.video_workflow_id)
            service = HermesVideoService(
                media_videos=MEDIA_VIDEOS,
                active_campaign_getter=lambda: campaign_id,
                find_shot=_find_shot,
                resolve_image_path=_resolve_image_path,
                workflow_file_for_id=_workflow_file_for_id,
            )
            shot_ids = [str(s.get("id") or "") for s in current_video_shots if s.get("id")]
            _pipeline_log(job, "videos", f"Queueing {len(shot_ids)} image-to-video job(s)")
            result = await service.process(
                shot_ids=shot_ids,
                workflow_id=workflow_id,
                duration=int(req.video_duration or 5),
                fps=int(req.video_fps or 24),
                width=None,
                height=None,
                prompt="",
                min_audit_score=0,
                min_audit_confidence=0,
                require_audit_pass=False,
                allow_failed_override=True,
            )
            if result.get("status") == "error":
                raise RuntimeError(str(result.get("error") or "video_process_error"))
            video_jobs = []
            for item in result.get("results", []) if isinstance(result.get("results"), list) else []:
                if not isinstance(item, dict):
                    continue
                shot = _find_shot(str(item.get("shot_id") or ""))
                if item.get("status") == "ok" and shot:
                    shot["video_status"] = "queued"
                    shot["video_prompt_id"] = item.get("prompt_id") or ""
                    shot["video_workflow_id"] = item.get("workflow_id") or workflow_id
                    shot["video_seed"] = item.get("seed")
                    shot["video_duration"] = int(req.video_duration or 5)
                    shot["video_fps"] = int(req.video_fps or 24)
                    shot["video_last_checked_at"] = _now_iso()
                    _persist_media_shot_metadata(shot)
                    video_jobs.append({
                        "shot_id": item.get("shot_id"),
                        "prompt_id": item.get("prompt_id"),
                        "campaign_id": campaign_id,
                        "workflow_id": item.get("workflow_id") or workflow_id,
                        "seed": item.get("seed"),
                        "duration": int(req.video_duration or 5),
                        "fps": int(req.video_fps or 24),
                        "host": item.get("host") or "",
                        "status": "queued",
                    })
                elif shot:
                    shot["video_status"] = item.get("status") or "error"
                    shot["video_error"] = item.get("error") or ", ".join(item.get("reasons") or [])
            job["video_jobs"] = video_jobs
            current_video_shots = _script_video_shots(campaign_id) or current_video_shots
            _save_script_project_payload({
                "script_id": script_id,
                "video_shots": current_video_shots,
                "status": "video_queued",
                "active_job_id": job_id,
            })
            _pipeline_log(job, "videos", f"Queued {len(video_jobs)} ComfyUI video job(s)")

            if req.wait_for_videos and video_jobs:
                video_wait_seconds = int(os.getenv("FORGE_SCRIPT_VIDEO_WAIT_SEC", "0") or "0") or int(req.video_wait_seconds or 21600)
                deadline = time.time() + max(21600, video_wait_seconds)
                while time.time() < deadline:
                    sync_req = VideoJobSyncRequest(jobs=[VideoJobSyncItem(**vj) for vj in video_jobs])
                    sync = await api_video_sync_jobs(sync_req)
                    sync_results = sync.get("results", []) if isinstance(sync, dict) else []
                    by_prompt = {str(r.get("prompt_id") or ""): r for r in sync_results if isinstance(r, dict)}
                    running = 0
                    complete = 0
                    errors = 0
                    for vj in video_jobs:
                        r = by_prompt.get(str(vj.get("prompt_id") or ""))
                        if not r:
                            continue
                        vj["status"] = r.get("status") or vj.get("status")
                        if r.get("video_url"):
                            vj["video_url"] = r.get("video_url")
                        if vj["status"] == "complete":
                            complete += 1
                        elif vj["status"] in {"running", "queued", "in_progress"}:
                            running += 1
                        elif vj["status"] == "error":
                            errors += 1
                    job["video_jobs"] = video_jobs
                    current_video_shots = _script_video_shots(campaign_id) or current_video_shots
                    _save_script_project_payload({
                        "script_id": script_id,
                        "video_shots": current_video_shots,
                        "status": "video_rendering" if running else "video_complete",
                        "active_job_id": job_id,
                    })
                    _pipeline_log(job, "videos", f"Video sync: {complete} complete, {running} running, {errors} error(s)")
                    if not running:
                        break
                    await asyncio.sleep(10)

        current_video_shots = _script_video_shots(campaign_id) or locals().get("current_video_shots", [])
        _save_script_project_payload({
            "script_id": script_id,
            "video_shots": current_video_shots,
            "status": "complete",
            "active_job_id": job_id,
        })
        job["status"] = "complete"
        _pipeline_log(job, "complete", "Pipeline complete")
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)[:1000]
        _pipeline_log(job, str(job.get("phase") or "error"), f"Pipeline failed: {str(e)[:500]}", level="error")
        try:
            _save_script_project_payload({
                "script_id": script_id,
                "status": "error",
                "active_job_id": job_id,
            })
        except Exception:
            pass


def _build_storyboard_boards(req: ScriptStoryboardRequest) -> Dict[str, Any]:
    panels_per_board = max(1, min(int(req.panels_per_board or 9), 9))
    target_panels = req.target_panels
    if target_panels is not None:
        target_panels = max(1, min(int(target_panels), 60))
    package = _storyboard_source_package(req)
    asset_vault_package = _asset_vault_package_by_id(req.asset_vault_package_id) if (req.asset_vault_package_id or "").strip() else None
    asset_context = _asset_vault_prompt_context(asset_vault_package)
    if package:
        panels = _storyboard_panels_from_package(package, target_panels)
        title = req.title or str(package.get("title") or "Storyboard")
    else:
        panels = _storyboard_panels_from_text(req.script or "", target_panels)
        title = req.title or "Storyboard"
    panels = _apply_asset_vault_to_panels(panels, asset_vault_package)
    if not panels:
        raise HTTPException(status_code=400, detail="script or package required")

    boards = []
    total_boards = (len(panels) + panels_per_board - 1) // panels_per_board
    style = (req.style or "").strip()
    resolution = (req.resolution or "1920x1080").strip() or "1920x1080"
    character_consistency = (req.character_consistency or "").strip()
    if not character_consistency and package:
        chars = package.get("continuity", {}).get("characters", []) if isinstance(package.get("continuity"), dict) else []
        if isinstance(chars, list) and chars:
            character_consistency = "; ".join(
                _short_text(
                    f"{c.get('name', 'Character')}: {c.get('visual_lock') or c.get('wardrobe') or c.get('performance') or ''}",
                    220,
                )
                for c in chars[:6]
                if isinstance(c, dict)
            )
    if asset_context.get("character_consistency"):
        character_consistency = (
            f"{character_consistency}; {asset_context['character_consistency']}"
            if character_consistency
            else str(asset_context["character_consistency"])
        )
    if not character_consistency:
        character_consistency = "highly consistent character design, same face and clothing across all panels"
    negative_prompt = (req.negative_prompt or "").strip()
    include_captions = bool(req.include_captions)
    reference_note = ""
    if (req.reference_image_url or "").strip():
        reference_note = f" Use the supplied character sheet/reference image for identity consistency: {req.reference_image_url.strip()}."
    if asset_context.get("reference_urls"):
        reference_note += " Use these Asset Vault visual references when the provider supports references: " + ", ".join(asset_context["reference_urls"]) + "."
    for index in range(total_boards):
        board_panels = [dict(panel) for panel in panels[index * panels_per_board:(index + 1) * panels_per_board]]
        layout_columns, layout_rows, layout = _storyboard_layout_dimensions(len(board_panels) or panels_per_board)
        panel_width_and_height = _storyboard_panel_render_size(resolution, layout_columns, layout_rows)
        panel_lines = []
        for local_idx, panel in enumerate(board_panels, start=1):
            character_text = ", ".join(panel.get("characters") or []) or "same character design as established in adjacent panels"
            text_clause = f" Caption text: \"{panel.get('text') or panel.get('caption') or ''}\"" if include_captions else " No caption text inside this panel."
            panel["single_panel_prompt"] = _single_storyboard_panel_prompt(
                panel=panel,
                local_idx=local_idx,
                board_idx=index + 1,
                title=title,
                style=style,
                character_consistency=character_consistency,
                include_captions=include_captions,
                reference_note=reference_note,
                negative_prompt=negative_prompt,
            )
            panel["width_and_height"] = panel_width_and_height
            panel_lines.append(
                f"Panel {local_idx}: {panel.get('visual_prompt', '')} "
                f"Setting: {panel.get('location', '')}. Camera: {panel.get('camera', '')}. "
                f"Lighting: {panel.get('lighting', 'motivated source-based light with consistent shadow direction')}. Mood: {panel.get('mood', 'narrative progression')}. "
                f"Character consistency: {character_text}; {character_consistency}. Continuity: {panel.get('continuity', '')}. "
                f"Asset Vault: {panel.get('asset_vault_context', '')}.{text_clause}"
            )
        empty_slots = panels_per_board - len(board_panels)
        empty_note = f"\nLeave {empty_slots} unused panel slot(s) as clean black empty frames with white borders." if empty_slots else ""
        image_prompt = (
            f"A professional {len(board_panels)}-panel storyboard page in {style} style, "
            f"arranged in a clean {layout} grid layout at {resolution} with white borders and subtle drop shadows between panels. "
            f"Each panel is numbered only with a small plain numeral in the top-left corner. "
            f"{'Include only the requested short caption text under each panel.' if include_captions else 'Do not render captions, dialogue, titles, paragraphs, or any text except the panel numbers.'} "
            f"This is board {index + 1} of {total_boards} for '{title}'.\n\n"
            + "\n\n".join(panel_lines)
            + empty_note
            + "\n\nOverall style: consistent character design across all panels, repeated wardrobe and facial details, "
            "consistent age, skin tone, hair, clothing, and build, source-based lighting, sharp focal priority, clean readable compositions, "
            "visible skin and fabric texture, film grain, no watermark, no malformed text, no fake captions."
            + (f"\n\nAsset Vault production lock: {asset_context.get('summary', '')}" if asset_context.get("summary") else "")
            + reference_note
            + (f"\n\nNegative prompt: {negative_prompt}." if negative_prompt else "")
        )
        boards.append({
            "board_id": f"STORYBOARD_{index + 1:02d}",
            "index": index + 1,
            "total_boards": total_boards,
            "resolution": resolution,
            "panels_per_board": panels_per_board,
            "panel_count": len(board_panels),
            "layout": layout,
            "layout_columns": layout_columns,
            "layout_rows": layout_rows,
            "panels": board_panels,
            "image_prompt": image_prompt,
            "negative_prompt": negative_prompt,
            "reference_image_url": (req.reference_image_url or "").strip(),
            "width_and_height": resolution,
            "panel_width_and_height": panel_width_and_height,
        })
    return {
        "status": "ok",
        "title": title,
        "resolution": resolution,
        "panels_per_board": panels_per_board,
        "panel_count": len(panels),
        "board_count": len(boards),
        "asset_vault_package": asset_vault_package or None,
        "boards": boards,
    }


async def _request_script_package(req: ScriptDevelopRequest) -> Dict[str, Any]:
    director = KimiDirectorService()
    director._require_ready()

    title = (req.title or "").strip() or "Untitled Forge Film"
    scene_count = max(1, min(int(req.target_scenes or 4), 12))
    runtime = max(15, min(int(req.runtime_seconds or 60), 720))
    schema_hint = {
        "title": "string",
        "treatment": {
            "logline": "string",
            "synopsis": "string",
            "visual_language": "string",
            "runtime_seconds": runtime,
        },
        "script": {
            "acts": [{
                "act_id": "ACT_01",
                "function": "string",
                "scenes": [{
                    "scene_id": "SC_001",
                    "title": "string",
                    "duration_sec": 15,
                    "location": "string",
                    "time_of_day": "string",
                    "emotional_turn": "string",
                    "beats": [{
                        "beat_id": "SC_001_B01",
                        "action": "string",
                        "dialogue": "string; compelling spoken line or nonverbal vocalization that hooks attention and reveals character intent",
                        "audio_cue": "string; sound design, ambience, music, silence, breath, foley, or voice treatment for this beat",
                        "performance": "string; delivery, timing, subtext, and emotional shift for the actor or character",
                        "characters": ["string"],
                        "continuity": {
                            "wardrobe": "string",
                            "props": ["string"],
                            "screen_direction": "string",
                        },
                    }],
                }],
            }],
        },
        "continuity": {
            "characters": [{"name": "string", "visual_lock": "string", "wardrobe": "string", "performance": "string"}],
            "locations": [{"name": "string", "visual_lock": "string"}],
            "props": [{"name": "string", "state": "string"}],
            "motifs": ["string"],
        },
        "edit_plan": {
            "pacing": "string",
            "audio_strategy": "string",
            "transition_strategy": "string",
        },
    }
    hook_system = (
        "Dialogue must be cinematic, immediate, and playable: every spoken line should create curiosity, conflict, reversal, or emotional pressure."
        if req.hook_first_dialogue
        else "Dialogue should be natural, concise, and playable; prioritize story clarity over short-form hook tactics."
    )
    dialogue_instruction = (
        "Write a structured screenplay package with hook-first dialogue. The first beat must grab attention within 2 seconds. "
        "Every spoken line must be short, specific, performable, and emotionally loaded; avoid generic exposition. "
        if req.hook_first_dialogue
        else "Write a structured screenplay package with natural scene dialogue. Spoken lines should be specific and performable without forcing a short-form hook. "
    )
    system_prompt = (
        "You are Hermes Script Architect for FORGE NPS. Return only valid JSON. "
        "Your job is not to make isolated pretty shots; produce a locked script package "
        "that can be converted into scene-by-scene coverage for a cohesive movie edit. "
        f"{hook_system}"
    )
    user_prompt = (
        f"title: {title}\n"
        f"runtime_seconds: {runtime}\n"
        f"target_scenes: {scene_count}\n"
        f"tone: {(req.tone or 'unspecified').strip()}\n"
        f"brief:\n{(req.brief or '').strip()}\n\n"
        f"{dialogue_instruction}"
        "If a beat is silent, use nonverbal vocalization or sound design intentionally instead of leaving the moment empty. "
        "Every scene must include concrete beats, continuity locks, emotional turns, edit pacing, audio strategy, transitions, "
        "per-beat dialogue, per-beat audio_cue, and per-beat performance direction. "
        "Keep output concise enough for downstream shot planning.\n\n"
        f"Required JSON schema:\n{json.dumps(schema_hint, indent=2)}"
    )
    payload = {
        "model": director.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.45,
        "response_format": director._response_format(),
        "max_tokens": 12000,
    }
    timeout_sec = max(float(os.getenv("FORGE_KIMI_TIMEOUT_SEC", "120")), 180.0)
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.post(
            director.endpoint,
            headers=director._auth_headers(),
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"http_error status={resp.status_code} error={resp.text[:500]}")
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        package = _extract_json_response(content)
        package["source"] = "lmstudio_director" if director.backend == "lmstudio" else "director_api"
        package["director_backend"] = director.backend
        package["director_model"] = director.model_name
        return package


def _script_shot_from_director_plan(shot: Dict[str, Any], campaign_id: str) -> Dict[str, Any]:
    shot_id = str(shot.get("shot_id") or shot.get("id") or f"SHOT_{int(shot.get('sequence') or 1):03d}")
    record_id = f"{campaign_id}__{shot_id}"
    sequence = int(shot.get("sequence") or shot.get("n") or 1)
    visual_brief = str(shot.get("visual_brief") or shot.get("prompt") or "").strip()
    camera = str(shot.get("camera_direction") or "").strip()
    lighting = str(shot.get("lighting_direction") or "").strip()
    constraints = str(shot.get("constraints") or "").strip()
    description_parts = [visual_brief]
    if camera:
        description_parts.append(f"Camera: {camera}")
    if lighting:
        description_parts.append(f"Lighting: {lighting}")
    if constraints:
        description_parts.append(f"Constraints: {constraints}")
    description = ". ".join(part.rstrip(".") for part in description_parts if part).strip()
    characters = shot.get("characters") if isinstance(shot.get("characters"), list) else []
    return {
        "id": record_id,
        "shot_id": shot_id,
        "source": "script_director",
        "campaign_id": campaign_id,
        "n": sequence,
        "sequence": sequence,
        "intent": "image",
        "status": "ready",
        "description": description or visual_brief or "Untitled shot",
        "prompt": description or visual_brief or "Untitled shot",
        "characters": characters,
        "mood": str(shot.get("narrative_intent") or ""),
        "environment": str(shot.get("environment") or ""),
        "camera_direction": camera,
        "lighting_direction": lighting,
        "rationale": str(shot.get("rationale") or ""),
        "constraints": constraints,
        "seed": random.randint(100000, 999999),
    }


async def _stream_director_shot_generation(req: DirectorGenerateRequest) -> AsyncGenerator[str, None]:
    brief = (req.brief or "").strip()
    if not brief:
        yield _script_director_event({"type": "error", "text": "Brief is required"})
        return

    campaign_id = f"script_{uuid.uuid4().hex[:10]}"
    director = KimiDirectorService()
    target_shots = int(req.target_shots or director.requested_shot_count(brief, req.length))
    target_shots = max(1, min(target_shots, 120))

    try:
        yield _script_director_event({"type": "status", "text": f"Kimi Director planning {target_shots} shots..."})
        plan = await director.request_plan(
            brief=brief,
            campaign_id=campaign_id,
            length=req.length or "",
            target_shots=target_shots,
        )
        normalized = director.normalize_shots(plan, campaign_id)
        yield _script_director_event({"type": "status", "text": f"Kimi plan received: {len(normalized)} shots"})

        try:
            yield _script_director_event({"type": "status", "text": "Kimi critique pass running..."})
            review = await director.self_check_plan(brief, campaign_id, normalized)
            score = director.score_from_review(review)
            status = str(review.get("status", "reviewed") or "reviewed")
            yield _script_director_event({
                "type": "status",
                "text": f"Kimi critique: {status}" + (f" ({score})" if score is not None else ""),
            })
            if status.lower() in {"warn", "fail"} or (score is not None and score < 70):
                yield _script_director_event({"type": "status", "text": "Kimi revision pass running..."})
                revised = await director.revise_plan(
                    brief=brief,
                    campaign_id=campaign_id,
                    normalized_shots=normalized,
                    review=review,
                    target_shots=target_shots,
                    length=req.length or "",
                )
                normalized = director.normalize_shots(revised, campaign_id)
                yield _script_director_event({"type": "status", "text": f"Kimi revision applied: {len(normalized)} shots"})
        except Exception as e:
            yield _script_director_event({"type": "status", "text": f"Warning: Kimi critique unavailable: {str(e)[:240]}"})

        script_shots = [_script_shot_from_director_plan(s, campaign_id) for s in normalized]
        _SHOTS_STORE[:] = [s for s in _SHOTS_STORE if str(s.get("source") or "") != "script_director"]
        _SHOTS_STORE.extend(script_shots)

        total = len(script_shots)
        for idx, shot in enumerate(script_shots, start=1):
            yield _script_director_event({"type": "shot", "shot": shot, "index": idx, "total": total})
        yield _script_director_event({"type": "done", "text": f"Shot list ready: {total} shots", "count": total})
    except Exception as e:
        yield _script_director_event({"type": "status", "text": f"Director API unavailable; using package fallback coverage: {str(e)[:180]}"})
        fallback_plan = _fallback_director_shots_from_brief(brief, campaign_id, target_shots)
        script_shots = [_script_shot_from_director_plan(s, campaign_id) for s in fallback_plan]
        _SHOTS_STORE[:] = [s for s in _SHOTS_STORE if str(s.get("source") or "") != "script_director"]
        _SHOTS_STORE.extend(script_shots)
        total = len(script_shots)
        for idx, shot in enumerate(script_shots, start=1):
            yield _script_director_event({"type": "shot", "shot": shot, "index": idx, "total": total})
        yield _script_director_event({"type": "done", "text": f"Fallback coverage ready: {total} shots", "count": total})


@app.post("/api/director/generate")
async def api_director_generate(req: DirectorGenerateRequest):
    return StreamingResponse(_stream_director_shot_generation(req), media_type="application/x-ndjson")


@app.post("/api/script/develop")
async def api_script_develop(req: ScriptDevelopRequest):
    brief = (req.brief or "").strip()
    if not brief:
        raise HTTPException(status_code=400, detail="brief required")
    try:
        package = await _request_script_package(req)
        return {"status": "ok", "package": package, "source": package.get("source", "director_api")}
    except Exception as e:
        fallback = _fallback_script_package(req)
        fallback["error"] = str(e)[:500]
        return {"status": "fallback", "package": fallback, "source": "fallback", "error": str(e)[:500]}


@app.get("/api/script/projects")
async def api_script_projects():
    return {"status": "ok", "projects": _list_script_projects()}


@app.get("/api/script/projects/{script_id}")
async def api_script_project(script_id: str):
    project = _load_script_project(script_id)
    return {"status": "ok", "project": project}


@app.post("/api/script/projects/save")
async def api_script_project_save(req: ScriptProjectSaveRequest):
    project = _save_script_project_payload(req.model_dump())
    return {"status": "ok", "project": project}


@app.post("/api/script/pipeline/start")
async def api_script_pipeline_start(req: ScriptPipelineStartRequest):
    if not (req.brief or "").strip() and not (req.script_id or "").strip():
        raise HTTPException(status_code=400, detail="brief or script_id required")
    script_id = _safe_script_id(req.script_id, req.title)
    existing_package = None
    existing_coverage: List[Dict[str, Any]] = []
    existing_storyboard = None
    existing_panel_jobs: Dict[str, Any] = {}
    existing_video_shots: List[Dict[str, Any]] = []
    try:
        existing = _load_script_project(script_id)
        existing_package = existing.get("package") if isinstance(existing.get("package"), dict) else None
        existing_coverage = existing.get("coverage_shots") if isinstance(existing.get("coverage_shots"), list) else []
        existing_storyboard = existing.get("storyboard_plan") if isinstance(existing.get("storyboard_plan"), dict) else None
        existing_panel_jobs = existing.get("storyboard_panel_jobs") if isinstance(existing.get("storyboard_panel_jobs"), dict) else {}
        existing_video_shots = existing.get("video_shots") if isinstance(existing.get("video_shots"), list) else []
        if not req.title:
            req.title = str(existing.get("title") or "")
        if not req.brief:
            req.brief = str(existing.get("brief") or "")
        if not req.tone:
            req.tone = str(existing.get("tone") or "")
        if not req.runtime_seconds:
            req.runtime_seconds = int(existing.get("runtime_seconds") or 60)
        if not req.target_scenes:
            req.target_scenes = int(existing.get("target_scenes") or 4)
        if not req.hook_first_dialogue and "hook_first_dialogue" in existing:
            req.hook_first_dialogue = bool(existing.get("hook_first_dialogue"))
    except HTTPException:
        pass
    project = _save_script_project_payload({
        "script_id": script_id,
        "title": req.title,
        "brief": req.brief,
        "tone": req.tone,
        "runtime_seconds": req.runtime_seconds,
        "target_scenes": req.target_scenes,
        "hook_first_dialogue": req.hook_first_dialogue,
        "package": existing_package,
        "coverage_shots": existing_coverage,
        "storyboard_plan": existing_storyboard,
        "storyboard_panel_jobs": existing_panel_jobs,
        "video_shots": existing_video_shots,
        "status": "queued",
    })
    job_id = f"scriptjob_{uuid.uuid4().hex[:12]}"
    job = {
        "job_id": job_id,
        "script_id": script_id,
        "status": "queued",
        "phase": "queued",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "request": req.model_dump(),
        "logs": [],
        "coverage_count": 0,
        "storyboard_count": 0,
        "video_jobs": [],
        "error": "",
    }
    _SCRIPT_PIPELINE_JOBS[job_id] = job
    _save_script_project_payload({
        "script_id": script_id,
        "title": req.title,
        "brief": req.brief,
        "tone": req.tone,
        "runtime_seconds": req.runtime_seconds,
        "target_scenes": req.target_scenes,
        "hook_first_dialogue": req.hook_first_dialogue,
        "package": existing_package,
        "coverage_shots": existing_coverage,
        "storyboard_plan": existing_storyboard,
        "storyboard_panel_jobs": existing_panel_jobs,
        "video_shots": existing_video_shots,
        "status": "queued",
        "active_job_id": job_id,
    })
    _save_pipeline_job(job)
    asyncio.create_task(_run_script_pipeline_job(job_id, req))
    return {"status": "ok", "job": job, "project": project}


@app.get("/api/script/pipeline/jobs/{job_id}")
async def api_script_pipeline_job(job_id: str):
    job = _SCRIPT_PIPELINE_JOBS.get(job_id)
    if not job:
        for path in SCRIPT_PROJECTS_DIR.glob("*/pipeline_job.json"):
            data = _read_json_file(path, {})
            if isinstance(data, dict) and data.get("job_id") == job_id:
                job = data
                _SCRIPT_PIPELINE_JOBS[job_id] = data
                break
    if not job:
        raise HTTPException(status_code=404, detail=f"pipeline job not found: {job_id}")
    project = None
    try:
        project = _load_script_project(str(job.get("script_id") or ""))
    except Exception:
        project = None
    return {"status": "ok", "job": job, "project": project}


@app.post("/api/script/storyboard")
async def api_script_storyboard(req: ScriptStoryboardRequest):
    return _build_storyboard_boards(req)


@app.get("/api/script/storyboard/image-models")
async def api_script_storyboard_image_models():
    cfg = get_raw_config()
    openai_model = str(cfg.get("OPENAI_IMAGE_MODEL", "") or os.getenv("OPENAI_IMAGE_MODEL", "") or "gpt-image-2")
    gemini_model = str(cfg.get("GEMINI_IMAGE_MODEL", "") or os.getenv("GEMINI_IMAGE_MODEL", "") or "gemini-2.5-flash-image")
    default_provider = str(cfg.get("STORYBOARD_IMAGE_PROVIDER", "") or os.getenv("STORYBOARD_IMAGE_PROVIDER", "") or "spark:flux2_dev")
    if default_provider == "spark":
        default_provider = "spark:flux2_dev"
    return {
        "status": "ok",
        "default": default_provider,
        "models": [
            {
                "id": f"spark:{key}",
                "provider": "spark",
                "model": key,
                "label": meta["label"],
                "workflow_id": meta["workflow_id"],
                "available": bool(_workflow_file_for_id(meta["workflow_id"])),
                "local": True,
            }
            for key, meta in STORYBOARD_SPARK_MODELS.items()
        ] + [
            {
                "id": "openai",
                "provider": "openai",
                "model": openai_model,
                "label": f"OpenAI / {openai_model}",
                "available": bool(os.getenv("OPENAI_API_KEY", "") or str(cfg.get("OPENAI_API_KEY", "") or "")),
                "local": False,
            },
            {
                "id": "gemini",
                "provider": "gemini",
                "model": gemini_model,
                "label": f"Nano Banana / {gemini_model}",
                "available": bool(os.getenv("GEMINI_API_KEY", "") or str(cfg.get("GEMINI_API_KEY", "") or "")),
                "local": False,
            },
        ],
    }


@app.get("/api/script/storyboard/provider-health")
async def api_script_storyboard_provider_health():
    cfg = get_raw_config()
    openai_key_set = bool(os.getenv("OPENAI_API_KEY", "") or str(cfg.get("OPENAI_API_KEY", "") or ""))
    gemini_key_set = bool(os.getenv("GEMINI_API_KEY", "") or str(cfg.get("GEMINI_API_KEY", "") or ""))
    spark_models = [
        {
            "id": f"spark:{key}",
            "label": meta["label"],
            "workflow_id": meta["workflow_id"],
            "available": bool(_workflow_file_for_id(meta["workflow_id"])),
        }
        for key, meta in STORYBOARD_SPARK_MODELS.items()
    ]
    return {
        "status": "ok",
        "default": str(cfg.get("STORYBOARD_IMAGE_PROVIDER", "") or os.getenv("STORYBOARD_IMAGE_PROVIDER", "") or "spark:flux2_dev"),
        "providers": {
            "spark": {
                "available": any(item["available"] for item in spark_models),
                "models": spark_models,
                "message": "Local Spark/ComfyUI workflows are used only by Script -> Storyboard for this selector.",
            },
            "openai": {
                "available": openai_key_set,
                "key_set": openai_key_set,
                "model": str(cfg.get("OPENAI_IMAGE_MODEL", "") or os.getenv("OPENAI_IMAGE_MODEL", "") or "gpt-image-2"),
            },
            "gemini": {
                "available": gemini_key_set,
                "key_set": gemini_key_set,
                "model": str(cfg.get("GEMINI_IMAGE_MODEL", "") or os.getenv("GEMINI_IMAGE_MODEL", "") or "gemini-2.5-flash-image"),
            },
        },
    }


@app.post("/api/script/storyboard/render-image")
async def api_script_storyboard_render_image(req: StoryboardImageGenerateRequest):
    return await _generate_storyboard_image(req)


@app.post("/api/script/storyboard/assemble")
async def api_script_storyboard_assemble(req: ScriptStoryboardAssembleRequest):
    return _assemble_storyboard_page(req)


@app.post("/api/script/storyboard/export-video-shots")
async def api_script_storyboard_export_video_shots(req: ScriptStoryboardVideoExportRequest):
    return _export_storyboard_video_shots(req)


@app.patch("/api/shots/{shot_id}")
async def api_update_script_shot_description(shot_id: str, req: ShotDescriptionUpdateRequest):
    desc = (req.description or "").strip()
    for shot in _SHOTS_STORE:
        if str(shot.get("id") or shot.get("shot_id") or "") == shot_id:
            shot["description"] = desc
            shot["prompt"] = desc
            return {"status": "ok", "shot": shot}
    raise HTTPException(status_code=404, detail=f"Shot {shot_id} not found")


@app.delete("/api/director/shots/{shot_id}")
async def api_delete_script_director_shot(shot_id: str):
    before = len(_SHOTS_STORE)
    _SHOTS_STORE[:] = [
        shot for shot in _SHOTS_STORE
        if str(shot.get("id") or shot.get("shot_id") or "") != shot_id
    ]
    if len(_SHOTS_STORE) == before:
        raise HTTPException(status_code=404, detail=f"Shot {shot_id} not found")
    return {"status": "ok", "shot_id": shot_id}


class ParseScriptRequest(BaseModel):
    path: str = ""
    use_kimi: bool = True


@app.post("/api/script/parse-with-kimi")
async def api_parse_with_kimi(req: ParseScriptRequest = None):
    """Explicitly parse a brand guide with Kimi to extract shots.
    Returns detailed status including whether Kimi was used."""
    repo_root = Path(__file__).parent.parent
    use_kimi = (req and req.use_kimi) if req else True

    if req and req.path:
        candidate = (repo_root / req.path).resolve()
        if not str(candidate).startswith(str(repo_root)):
            raise HTTPException(status_code=400, detail="Invalid path")
        script_path = candidate
    else:
        script_path = repo_root / "data" / "lore_bible" / "world_bible.md"

    if not script_path.exists():
        raise HTTPException(status_code=404, detail=f"Script not found: {script_path}")

    text = script_path.read_text(encoding="utf-8")

    if use_kimi:
        kimi_shots = await _parse_shots_with_kimi(text, str(script_path))
        if kimi_shots:
            _SHOTS_STORE.clear()
            _SHOTS_STORE.extend(kimi_shots)
            _persist_shots(script_path, kimi_shots)
            return {
                "status": "parsed_by_kimi",
                "count": len(_SHOTS_STORE),
                "parser": "kimi",
                "source": str(script_path.name),
                "shots": kimi_shots
            }

    # Fallback: regex-based parsing
    shots_found = []
    for i, line in enumerate(text.splitlines()):
        if line.strip().startswith("## SHOT") or line.strip().startswith("### SHOT"):
            parts = line.strip().lstrip("#").strip().split("—", 1)
            shot_id = parts[0].strip().replace(" ", "_")
            prompt = parts[1].strip() if len(parts) > 1 else "TBD"
            shots_found.append({
                "id": shot_id, "n": len(shots_found) + 1, "chars": [],
                "status": "ready", "prompt": prompt,
                "seed": random.randint(100000, 999999)
            })

    if shots_found:
        _SHOTS_STORE.clear()
        _SHOTS_STORE.extend(shots_found)

    return {
        "status": "parsed_by_regex" if shots_found else "no_shots_found",
        "count": len(_SHOTS_STORE),
        "parser": "regex",
        "source": str(script_path.name),
        "shots": shots_found if shots_found else _SHOTS_STORE
    }


@app.post("/api/script/load-shots")
async def api_load_shots(req: ReparseRequest = None):
    """Load persisted shots from disk (shots.json alongside the bible)."""
    repo_root = Path(__file__).parent.parent

    if req and req.path:
        candidate = (repo_root / req.path).resolve()
        if not str(candidate).startswith(str(repo_root)):
            raise HTTPException(status_code=400, detail="Invalid path")
        script_path = candidate
    else:
        script_path = repo_root / "data" / "lore_bible" / "world_bible.md"

    # Look for shots.json next to the bible or in parent dir
    for shots_path in [
        script_path.parent / "shots.json",
        script_path.parent.parent / "shots.json"
    ]:
        if shots_path.exists():
            with open(shots_path) as f:
                shots = json.load(f)
            _SHOTS_STORE.clear()
            _SHOTS_STORE.extend(shots)
            return {"status": "loaded", "count": len(_SHOTS_STORE), "source": str(shots_path.name)}

    return {"status": "no_persisted_shots", "count": len(_SHOTS_STORE)}


@app.post("/api/script/add-shot")
async def api_script_add_shot():
    n = len(_SHOTS_STORE) + 1
    new_shot = {
        "id": f"SHOT_{str(n).zfill(3)}",
        "n": n, "chars": [], "status": "ready",
        "prompt": "New shot — edit prompt here",
        "seed": random.randint(100000, 999999)
    }
    _SHOTS_STORE.append(new_shot)
    return new_shot


@app.post("/api/script/update-shot")
async def api_script_update_shot(req: UpdateShotRequest):
    for shot in _SHOTS_STORE:
        if shot["id"] == req.shot_id:
            shot["prompt"] = req.prompt
            return {"status": "ok"}
    raise HTTPException(status_code=404, detail=f"Shot {req.shot_id} not found")


class RunCampaignRequest(BaseModel):
    brief: str
    bible_path: str = ""
    length: str = ""
    target_shots: Optional[int] = None
    workflow_ids: List[str] = []
    identity_pack: Optional[CampaignIdentityPack] = None
    campaign_id: str = ""
    append_to_campaign: bool = False
    platform_mode: str = "auto"
    series_continuity: Optional[bool] = None


class PlatformDetectRequest(BaseModel):
    brief: str = ""
    platform_mode: str = "auto"
    series_continuity: Optional[bool] = None


class HookGenerateRequest(BaseModel):
    brief: str = ""
    platform_mode: str = "auto"
    campaign_id: str = ""
    save_to_board: bool = False


class CarouselExportRequest(BaseModel):
    campaign_id: str = ""
    shot_ids: List[str] = []
    platform_mode: str = "auto"


class ReAuditRequest(BaseModel):
    shot_ids: List[str]


class RemediateRequest(BaseModel):
    shot_ids: List[str]
    max_retries: int = 1


class ImportBatchRequest(BaseModel):
    report_path: str


DEFAULT_VIDEO_WORKFLOW_ID = "04_ltx2.3_image_to_video"
VIDEO_WORKFLOW_LABELS = {
    "04_ltx2.3_image_to_video": "LTX 2.3 Fast Image-to-Video",
    "02_ltx2.3_T2V_I2V_distilled": "LTX 2.3 Distilled",
    "03_ltx2.3_T2V_two_stage": "LTX 2.3 Two Stage",
}
DISABLED_VIDEO_WORKFLOW_IDS = {
    "02_ltx2.3_T2V_I2V_distilled",
    "03_ltx2.3_T2V_two_stage",
}


def _normalize_video_workflow_id(workflow_id: str = "") -> str:
    requested = (workflow_id or "").strip()
    if not requested or requested in DISABLED_VIDEO_WORKFLOW_IDS:
        return DEFAULT_VIDEO_WORKFLOW_ID
    return requested


def _video_workflow_preflight(workflow_id: str = "") -> Dict[str, Any]:
    requested = (workflow_id or "").strip() or DEFAULT_VIDEO_WORKFLOW_ID
    normalized = _normalize_video_workflow_id(requested)
    workflow_path = _workflow_file_for_id(normalized)
    return {
        "requested": requested,
        "workflow_id": normalized,
        "label": VIDEO_WORKFLOW_LABELS.get(normalized, normalized),
        "available": bool(workflow_path),
        "disabled": requested in DISABLED_VIDEO_WORKFLOW_IDS,
        "reason": "disabled_after_comfy_sampler_failures" if requested in DISABLED_VIDEO_WORKFLOW_IDS else "",
        "path": str(workflow_path) if workflow_path else "",
    }


def _compact_comfy_error(status: Dict[str, Any], fallback: str = "comfy_execution_error") -> Dict[str, str]:
    messages = status.get("messages", []) if isinstance(status, dict) else []
    for item in reversed(messages if isinstance(messages, list) else []):
        if not (isinstance(item, list) and len(item) >= 2 and item[0] == "execution_error" and isinstance(item[1], dict)):
            continue
        detail = item[1]
        return {
            "error": str(detail.get("exception_type") or fallback),
            "detail": str(detail.get("exception_message") or fallback).strip()[:500],
            "node": str(detail.get("node_id") or ""),
            "node_type": str(detail.get("node_type") or ""),
        }
    return {"error": fallback, "detail": fallback, "node": "", "node_type": ""}


class VideoProcessRequest(BaseModel):
    shot_ids: List[str]
    duration: int = 5
    fps: int = 24
    workflow_id: str = DEFAULT_VIDEO_WORKFLOW_ID
    mode: str = "videos"
    resolution: str = "540p"
    aspect_ratio: str = "16:9"
    prompt: str = ""
    platform_mode: str = "auto"
    min_audit_score: float = 0.85
    min_audit_confidence: float = 0.70
    require_audit_pass: bool = True
    allow_failed_override: bool = False


class VideoGeneratePromptsRequest(BaseModel):
    shot_ids: List[str]
    duration: int = 5
    fps: int = 24
    campaign_id: str = ""
    workflow_id: str = DEFAULT_VIDEO_WORKFLOW_ID
    mode: str = "videos"
    resolution: str = "540p"
    aspect_ratio: str = "16:9"
    platform_mode: str = "auto"


class VideoJobSyncItem(BaseModel):
    shot_id: str
    prompt_id: str
    campaign_id: str = ""
    workflow_id: str = ""
    seed: Optional[int] = None
    duration: Optional[int] = None
    fps: Optional[int] = None
    host: str = ""


class VideoJobSyncRequest(BaseModel):
    jobs: List[VideoJobSyncItem]
    host: str = ""


@app.get("/api/video/workflows")
async def api_video_workflows():
    workflows = []
    for workflow_id, label in VIDEO_WORKFLOW_LABELS.items():
        preflight = _video_workflow_preflight(workflow_id)
        workflows.append({
            **preflight,
            "label": label,
            "recommended": workflow_id == DEFAULT_VIDEO_WORKFLOW_ID,
        })
    return {
        "status": "ok",
        "default_workflow_id": DEFAULT_VIDEO_WORKFLOW_ID,
        "workflows": workflows,
    }


class LocalHiggsfieldImageRequest(BaseModel):
    prompt: str
    width_and_height: str = "1696x960"
    enhance_prompt: bool = False
    quality: str = "1080p"
    batch_size: int = 1
    style_id: Optional[str] = None
    style_strength: float = 1.0
    seed: Optional[int] = None
    custom_reference_id: Optional[str] = None
    custom_reference_strength: float = 1.0
    image_reference_url: Optional[str] = None
    wait_for_output: bool = False


class LocalHiggsfieldMotion(BaseModel):
    id: str
    strength: float = 1.0


class LocalHiggsfieldVideoRequest(BaseModel):
    input_image_url: str
    prompt: str
    model: str = "dop-turbo"
    seed: Optional[int] = None
    motions: List[LocalHiggsfieldMotion] = []
    input_image_end_url: Optional[str] = None
    enhance_prompt: bool = True
    wait_for_output: bool = False


class LocalHiggsfieldCharacterRequest(BaseModel):
    name: str
    image_urls: List[str]


class LMStudioLoadRequest(BaseModel):
    host: str = ""
    port: int = 0
    model: str = ""


def _video_dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
    res = str(resolution or "540p").strip().lower()
    aspect = str(aspect_ratio or "16:9").strip()
    heights = {
        "540p": 540,
        "720p": 720,
        "1080p": 1080,
    }
    height = heights.get(res, 540)
    if aspect == "9:16":
        return int(round(height * 9 / 16)), height
    if aspect == "1:1":
        return height, height
    return int(round(height * 16 / 9)), height


def _workflow_file_for_id(workflow_id: str) -> Optional[Path]:
    candidates = [
        REPO_ROOT / "workflows" / f"{workflow_id}.json",
        REPO_ROOT / "workflows" / f"{workflow_id}_api.json",
        REPO_ROOT / "workflows" / "_disabled_non_numbered" / f"{workflow_id}.json",
        REPO_ROOT / "workflows" / "_disabled_non_numbered" / f"{workflow_id}_api.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _resolve_comfy_primary() -> str:
    cfg = get_raw_config()
    host = (
        os.getenv("COMFYUI_PRIMARY", "")
        or str(cfg.get("COMFYUI_PRIMARY", ""))
        or "http://localhost:8188"
    ).strip().rstrip("/")
    if host and not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


def _make_local_higgsfield_adapter() -> LocalHiggsfieldAdapter:
    return LocalHiggsfieldAdapter(
        repo_root=REPO_ROOT,
        media_root=MEDIA_ROOT,
        media_images=MEDIA_IMAGES,
        comfy_url=_resolve_comfy_primary(),
        workflow_file_for_id=_workflow_file_for_id,
        resolve_image_path=_resolve_image_path,
    )


def _resolve_image_path(image_url: str) -> Optional[Path]:
    if not image_url:
        return None
    p = Path(image_url)
    if p.is_absolute() and p.exists():
        return p
    if image_url.startswith("/campaigns/"):
        c = REPO_ROOT / "data" / "campaigns" / image_url.replace("/campaigns/", "", 1)
        if c.exists():
            return c
    if image_url.startswith("/renders/"):
        r = REPO_ROOT / "data" / "renders" / image_url.replace("/renders/", "", 1)
        if r.exists():
            return r
    if image_url.startswith("/external-renders/"):
        rel = image_url.replace("/external-renders/", "", 1).lstrip("/")
        ex = MEDIA_IMAGES / rel
        if ex.exists():
            return ex
    if image_url.startswith("/media-assets/"):
        rel = image_url.replace("/media-assets/", "", 1).lstrip("/")
        ex = MEDIA_ROOT / rel
        if ex.exists():
            return ex
    if image_url.startswith("/api/characters/reference/"):
        rel = image_url.replace("/api/characters/reference/", "", 1).lstrip("/")
        parts = rel.split("/", 1)
        if len(parts) == 2:
            ex = CHARACTER_BANKS_DIR / "references" / _character_slug(parts[0]) / Path(parts[1]).name
            if ex.exists():
                return ex
    if image_url.startswith("/api/characters/anchor/"):
        safe_name = _character_slug(image_url.replace("/api/characters/anchor/", "", 1).lstrip("/"))
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            ex = CHARACTERS_ANCHORS_DIR / f"{safe_name}{ext}"
            if ex.exists():
                return ex
    c2 = MEDIA_IMAGES / Path(image_url).name
    if c2.exists():
        return c2
    return None


def _media_url_for_path(path: Path, *, is_video: bool = False) -> str:
    try:
        rel = path.resolve().relative_to(MEDIA_IMAGES.resolve())
        return f"/external-renders/{rel.as_posix()}"
    except Exception:
        pass
    try:
        rel = path.resolve().relative_to(MEDIA_ROOT.resolve())
        return f"/media-assets/{rel.as_posix()}"
    except Exception:
        pass
    try:
        rel = path.resolve().relative_to((REPO_ROOT / "data" / "campaigns").resolve())
        return f"/campaigns/{rel.as_posix()}"
    except Exception:
        pass
    try:
        rel = path.resolve().relative_to((REPO_ROOT / "data" / "renders").resolve())
        return f"/renders/{rel.as_posix()}"
    except Exception:
        pass
    folder = "videos" if is_video else "imports"
    dest_dir = MEDIA_ROOT / folder
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / path.name
    if not dest.exists() or dest.stat().st_size != path.stat().st_size:
        shutil.copy2(path, dest)
    return f"/media-assets/{folder}/{dest.name}"


def _storyboard_image_job_payload(
    *,
    provider: str,
    model: str,
    url: str,
    path: str,
    status: str = "completed",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    job_id = f"storyboard_{provider}_{uuid.uuid4().hex[:10]}"
    return {
        "status": status,
        "provider": provider,
        "model": model,
        "job_set_id": job_id,
        "id": job_id,
        "url": url,
        "path": path,
        "metadata": metadata or {},
        "jobs": [
            {
                "id": job_id,
                "status": status,
                "provider": provider,
                "model": model,
                "results": {
                    "raw": {"url": url, "path": path},
                    "min": {"url": url, "path": path},
                    "all": [{"url": url, "path": path}],
                },
            }
        ],
    }


async def _generate_storyboard_image(req: StoryboardImageGenerateRequest) -> Dict[str, Any]:
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    provider = (req.provider or "spark").strip().lower()
    if provider in {"spark", "comfy", "comfyui", "local"}:
        spark_key = (req.spark_model or req.model or "flux2_dev").strip().lower()
        spark_model = STORYBOARD_SPARK_MODELS.get(spark_key, STORYBOARD_SPARK_MODELS["flux2_dev"])
        workflow_id = spark_model["workflow_id"]
        if not _workflow_file_for_id(workflow_id):
            raise HTTPException(status_code=404, detail=f"Storyboard Spark workflow not found: {workflow_id}")
        prompt, _ = apply_model_prompt_standard(
            prompt,
            workflow_id=workflow_id,
            model_family=spark_model["model_family"],
            render_type="storyboard",
        )
        adapter = _make_local_higgsfield_adapter()
        payload = await adapter.generate_image_soul(
            prompt=prompt,
            width_and_height=req.width_and_height,
            enhance_prompt=req.enhance_prompt,
            quality=req.quality,
            batch_size=1,
            style_id="",
            style_strength=0.0,
            seed=None,
            custom_reference_id="",
            custom_reference_strength=0.0,
            image_reference_url=req.image_reference_url,
            wait_for_output=req.wait_for_output,
            workflow_id=workflow_id,
            output_label=spark_key,
        )
        payload["provider"] = "spark"
        payload["model"] = spark_key
        payload["workflow_id"] = workflow_id
        payload["model_label"] = spark_model["label"]
        return payload

    cfg = get_raw_config()
    service = StoryboardImageProvider(
        openai_api_key=os.getenv("OPENAI_API_KEY", "") or str(cfg.get("OPENAI_API_KEY", "") or ""),
        openai_model=str(cfg.get("OPENAI_IMAGE_MODEL", "") or os.getenv("OPENAI_IMAGE_MODEL", "") or "gpt-image-2"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "") or str(cfg.get("GEMINI_API_KEY", "") or ""),
        gemini_model=str(cfg.get("GEMINI_IMAGE_MODEL", "") or os.getenv("GEMINI_IMAGE_MODEL", "") or "gemini-2.5-flash-image"),
    )
    output_dir = MEDIA_ROOT / "storyboards" / "generated"
    try:
        result = await service.generate(
            provider=provider,
            prompt=prompt,
            output_dir=output_dir,
            title=req.title,
            model=req.model,
            size="auto",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    url = _media_url_for_path(result.path)
    _record_pipeline_event(
        "storyboard_image_generated",
        source="script",
        success=True,
        extra={"provider": result.provider, "model": result.model, "url": url},
    )
    return _storyboard_image_job_payload(
        provider=result.provider,
        model=result.model,
        url=url,
        path=str(result.path),
        metadata=result.metadata,
    )


def _make_audit_service() -> HermesAuditService:
    return HermesAuditService(
        shots_store=_SHOTS_STORE,
        find_shot=_find_shot,
        resolve_image_path=_resolve_image_path,
        now_iso=_now_iso,
        record_event=_record_pipeline_event,
        audit_render=audit_render_with_kimi_vl,
        workflow_file_for_id=_workflow_file_for_id,
        media_images=MEDIA_IMAGES,
        get_hermes_bridge=_get_hermes_bridge,
    )


def _get_nexus_handlers() -> ForgeMCPHandlers:
    global _NEXUS_HANDLERS
    if _NEXUS_HANDLERS is None:
        _NEXUS_HANDLERS = ForgeMCPHandlers(REPO_ROOT)
    return _NEXUS_HANDLERS


def _nexus_type_from_id(asset_id: str) -> str:
    aid = str(asset_id or "").lower()
    if aid.startswith("char_"):
        return "character"
    if aid.startswith("prompt_"):
        return "prompt"
    if aid.startswith("wf_") or "workflow" in aid:
        return "workflow"
    return "asset"


@app.post("/api/hermes/cancel")
async def api_hermes_cancel():
    global _CANCEL_CAMPAIGN
    _CANCEL_CAMPAIGN = True
    return {"status": "ok", "cancelled": True}


@app.post("/api/platform/detect")
async def api_platform_detect(req: PlatformDetectRequest):
    platform = detect_platform_skill(
        req.brief,
        requested_mode=req.platform_mode,
        series_continuity=req.series_continuity,
    )
    hooks = generate_hook_ideas(req.brief, platform, limit=3) if platform.get("active") else []
    return {"status": "ok", "platform": platform, "hooks": hooks}


@app.post("/api/ideas/hooks")
async def api_generate_hook_ideas(req: HookGenerateRequest):
    platform = detect_platform_skill(req.brief, requested_mode=req.platform_mode)
    hooks = generate_hook_ideas(req.brief, platform, limit=5)
    created: List[Dict[str, Any]] = []
    if req.save_to_board:
        cards = [_normalize_idea_card(card) for card in _read_idea_cards()]
        now = datetime.utcnow().isoformat()
        for item in hooks:
            card = _normalize_idea_card({
                "id": f"idea_{uuid.uuid4().hex[:10]}",
                "title": item.get("caption") or item.get("hook") or "TikTok hook",
                "body": f"{item.get('hook', '')} Audio direction: {item.get('audio', '')}".strip(),
                "type": "hook",
                "campaign_id": req.campaign_id,
                "stage": "spark",
                "tags": ["tiktok", "hook", "audio"],
                "created_at": now,
                "updated_at": now,
            })
            cards.append(card)
            created.append(card)
        _write_idea_cards(cards)
    return {"status": "ok", "platform": platform, "hooks": hooks, "created": created}


@app.post("/api/hermes/run-campaign")
async def api_hermes_run_campaign(req: RunCampaignRequest):
    async def _stream():
        global _CANCEL_CAMPAIGN, _ACTIVE_CAMPAIGN
        _CANCEL_CAMPAIGN = False

        def _set_active(campaign_id: str) -> None:
            global _ACTIVE_CAMPAIGN
            _ACTIVE_CAMPAIGN = campaign_id

        service = HermesCampaignService(
            repo_root=REPO_ROOT,
            media_images=MEDIA_IMAGES,
            shots_store=_SHOTS_STORE,
            campaigns=_CAMPAIGNS,
            now_iso=_now_iso,
            record_event=_record_pipeline_event,
            audit_render=audit_render_with_kimi_vl,
            workflow_file_for_id=_workflow_file_for_id,
            is_cancelled=lambda: _CANCEL_CAMPAIGN,
            active_campaign_setter=_set_active,
            remediate_failed=lambda shot_ids: _make_audit_service().remediate(shot_ids, max_retries=1),
            get_hermes_bridge=_get_hermes_bridge,
        )
        payload = CampaignRequest(
            brief=req.brief,
            bible_path=req.bible_path,
            length=req.length,
            target_shots=req.target_shots,
            workflow_ids=req.workflow_ids,
            identity_pack=req.identity_pack.model_dump() if req.identity_pack else None,
            campaign_id=req.campaign_id,
            append_to_campaign=req.append_to_campaign,
            platform_mode=req.platform_mode,
            series_continuity=req.series_continuity,
        )
        async for event in service.stream_campaign(payload):
            yield json.dumps(event) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.get("/api/local-higgsfield/styles")
async def api_local_higgsfield_styles():
    """Higgsfield-like style presets implemented locally through Forge."""
    return {"available_styles": _make_local_higgsfield_adapter().list_styles()}


@app.get("/api/local-higgsfield/motions")
async def api_local_higgsfield_motions():
    """Higgsfield-like motion presets mapped to local LTX/ComfyUI prompts."""
    return {"available_motions": _make_local_higgsfield_adapter().list_motions()}


@app.post("/api/local-higgsfield/generate-image")
async def api_local_higgsfield_generate_image(req: LocalHiggsfieldImageRequest):
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    prompt, _ = apply_model_prompt_standard(
        prompt,
        workflow_id="spark_image_flux2_text_to_image",
        model_family="flux2-dev",
        render_type="storyboard" if "storyboard" in prompt.lower() else "image",
    )
    adapter = _make_local_higgsfield_adapter()
    return await adapter.generate_image_soul(
        prompt=prompt,
        width_and_height=req.width_and_height,
        enhance_prompt=req.enhance_prompt,
        quality=req.quality,
        batch_size=req.batch_size,
        style_id=req.style_id,
        style_strength=req.style_strength,
        seed=req.seed,
        custom_reference_id=req.custom_reference_id,
        custom_reference_strength=req.custom_reference_strength,
        image_reference_url=req.image_reference_url,
        wait_for_output=req.wait_for_output,
        output_label="flux2_dev",
    )


@app.post("/api/local-higgsfield/generate-video")
async def api_local_higgsfield_generate_video(req: LocalHiggsfieldVideoRequest):
    if not (req.input_image_url or "").strip():
        raise HTTPException(status_code=400, detail="input_image_url is required")
    if not (req.prompt or "").strip():
        raise HTTPException(status_code=400, detail="prompt is required")
    prompt, _ = apply_model_prompt_standard(
        req.prompt,
        workflow_id="04_ltx2.3_image_to_video",
        model_family="ltx",
        render_type="video",
    )
    motions = [m.model_dump() for m in req.motions]
    adapter = _make_local_higgsfield_adapter()
    return await adapter.generate_video_dop(
        input_image_url=req.input_image_url,
        prompt=prompt,
        model=req.model,
        seed=req.seed,
        motions=motions,
        input_image_end_url=req.input_image_end_url,
        enhance_prompt=req.enhance_prompt,
        wait_for_output=req.wait_for_output,
    )


@app.get("/api/local-higgsfield/jobs/{job_set_id}")
async def api_local_higgsfield_job_status(job_set_id: str):
    try:
        return await _make_local_higgsfield_adapter().get_job_status(job_set_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/local-higgsfield/characters")
async def api_local_higgsfield_create_character(req: LocalHiggsfieldCharacterRequest):
    if not (req.name or "").strip():
        raise HTTPException(status_code=400, detail="name is required")
    if not req.image_urls:
        raise HTTPException(status_code=400, detail="image_urls is required")
    return await _make_local_higgsfield_adapter().create_character(name=req.name, image_urls=req.image_urls)


@app.get("/api/local-higgsfield/characters")
async def api_local_higgsfield_list_characters():
    return _make_local_higgsfield_adapter().list_characters()


@app.get("/api/local-higgsfield/characters/{reference_id}")
async def api_local_higgsfield_get_character(reference_id: str):
    try:
        return _make_local_higgsfield_adapter().get_character(reference_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/api/local-higgsfield/characters/{reference_id}")
async def api_local_higgsfield_delete_character(reference_id: str):
    try:
        return _make_local_higgsfield_adapter().delete_character(reference_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/audit/reprocess")
async def api_audit_reprocess(req: ReAuditRequest):
    service = _make_audit_service()
    return await service.reprocess(req.shot_ids)


@app.post("/api/audit/remediate")
async def api_audit_remediate(req: RemediateRequest):
    service = _make_audit_service()
    return await service.remediate(req.shot_ids, max_retries=req.max_retries)


@app.post("/api/video/process")
async def api_video_process(req: VideoProcessRequest):
    campaign_id_for_platform = (_ACTIVE_CAMPAIGN or "").strip()
    platform_brief = ""
    if campaign_id_for_platform:
        manifest_path = MEDIA_IMAGES / campaign_id_for_platform / "_campaign.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                platform_brief = str(manifest.get("brief") or "")
            except Exception:
                platform_brief = ""
    if not platform_brief:
        platform_brief = str(req.prompt or "")
    platform_skill = detect_platform_skill(platform_brief, requested_mode=req.platform_mode)
    if platform_skill.get("active"):
        constraints = platform_skill.get("constraints") or {}
        if int(req.duration or 0) < int(constraints.get("duration_min_sec", 8)):
            req.duration = int(constraints.get("duration_default_sec", 12))
        if not req.fps:
            req.fps = int(constraints.get("fps", 24))
    requested_width, requested_height = _video_dimensions(req.resolution, req.aspect_ratio)
    service = HermesVideoService(
        media_videos=MEDIA_VIDEOS,
        active_campaign_getter=lambda: _ACTIVE_CAMPAIGN,
        find_shot=_find_shot,
        resolve_image_path=_resolve_image_path,
        workflow_file_for_id=_workflow_file_for_id,
    )
    preflight = _video_workflow_preflight(req.workflow_id)
    if not preflight.get("available"):
        raise HTTPException(status_code=404, detail=f"Workflow not found: {preflight.get('workflow_id')}")
    workflow_id = str(preflight["workflow_id"])
    result = await service.process(
        shot_ids=[str(x) for x in req.shot_ids],
        workflow_id=workflow_id,
        duration=int(req.duration or 0),
        fps=int(req.fps or 0),
        width=requested_width,
        height=requested_height,
        prompt=str(req.prompt or ""),
        platform_skill=platform_skill,
        min_audit_score=float(req.min_audit_score),
        min_audit_confidence=float(req.min_audit_confidence),
        require_audit_pass=bool(req.require_audit_pass),
        allow_failed_override=bool(req.allow_failed_override),
    )
    if result.get("status") == "error":
        err = str(result.get("error") or "video_process_error")
        if err == "shot_ids_required":
            raise HTTPException(status_code=400, detail="shot_ids required")
        if err == "workflow_id_required":
            raise HTTPException(status_code=400, detail="workflow_id required")
        if err.startswith("workflow_missing:"):
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        raise HTTPException(status_code=500, detail=err)
    for item in result.get("results", []) if isinstance(result.get("results"), list) else []:
        if not isinstance(item, dict) or item.get("status") != "ok":
            continue
        shot = _find_shot(str(item.get("shot_id") or ""))
        if not shot:
            continue
        shot["video_status"] = "queued"
        shot["video_error"] = ""
        shot["video_error_detail"] = ""
        shot["video_error_node"] = ""
        shot["video_last_checked_at"] = _now_iso()
        shot["video_prompt_id"] = item.get("prompt_id") or ""
        shot["video_workflow_id"] = item.get("workflow_id") or workflow_id
        shot["video_seed"] = item.get("seed")
        shot["video_duration"] = int(req.duration or 0)
        shot["video_fps"] = int(req.fps or 0)
        _persist_media_shot_metadata(shot)
    result["workflow_preflight"] = preflight
    return result


@app.post("/api/video/sync-jobs")
async def api_video_sync_jobs(req: VideoJobSyncRequest):
    cfg = get_raw_config()
    default_host = (
        req.host.strip()
        or os.getenv("COMFYUI_PRIMARY", "")
        or str(cfg.get("COMFYUI_PRIMARY", ""))
    ).rstrip("/")
    if not default_host:
        raise HTTPException(status_code=400, detail="COMFYUI_PRIMARY is not configured")

    results: List[Dict[str, Any]] = []
    any_saved = False
    async with httpx.AsyncClient(timeout=15.0) as http:
        for job in req.jobs:
            prompt_id = str(job.prompt_id or "").strip()
            shot_id = str(job.shot_id or "").strip()
            host = (job.host.strip() or default_host).rstrip("/")
            if not prompt_id or not shot_id:
                results.append({"shot_id": shot_id, "prompt_id": prompt_id, "status": "error", "error": "shot_id_and_prompt_id_required"})
                continue
            try:
                hist_resp = await http.get(f"{host}/history/{prompt_id}")
                if hist_resp.status_code != 200:
                    results.append({"shot_id": shot_id, "prompt_id": prompt_id, "status": "error", "error": f"history_http_{hist_resp.status_code}"})
                    continue
                history = hist_resp.json()
                entry = history.get(prompt_id) if isinstance(history, dict) else None
                if not isinstance(entry, dict):
                    queue_state = ""
                    try:
                        queue_resp = await http.get(f"{host}/queue")
                        if queue_resp.status_code == 200:
                            queue_data = queue_resp.json()
                            running = queue_data.get("queue_running") if isinstance(queue_data, dict) else []
                            pending = queue_data.get("queue_pending") if isinstance(queue_data, dict) else []
                            if any(len(x) > 1 and x[1] == prompt_id for x in running if isinstance(x, list)):
                                queue_state = "running"
                            elif any(len(x) > 1 and x[1] == prompt_id for x in pending if isinstance(x, list)):
                                queue_state = "queued"
                    except Exception:
                        queue_state = "queued"
                    if not queue_state:
                        shot = _find_shot(shot_id)
                        if shot:
                            shot["video_status"] = "error"
                            shot["video_prompt_id"] = prompt_id
                            shot["video_error"] = "prompt_not_in_history_or_queue"
                            shot["video_error_detail"] = "ComfyUI no longer has this prompt in history or queue."
                            shot["video_error_node"] = ""
                            shot["video_last_checked_at"] = _now_iso()
                            _persist_media_shot_metadata(shot)
                        results.append({
                            "shot_id": shot_id,
                            "prompt_id": prompt_id,
                            "status": "error",
                            "error": "prompt_not_in_history_or_queue",
                        })
                        continue
                    shot = _find_shot(shot_id)
                    if shot:
                        shot["video_status"] = queue_state
                        shot["video_last_checked_at"] = _now_iso()
                        _persist_media_shot_metadata(shot)
                    results.append({"shot_id": shot_id, "prompt_id": prompt_id, "status": queue_state})
                    continue

                status = entry.get("status", {}) if isinstance(entry.get("status"), dict) else {}
                if status.get("status_str") == "error":
                    compact_error = _compact_comfy_error(status)
                    shot = _find_shot(shot_id)
                    if shot:
                        shot["video_status"] = "error"
                        shot["video_prompt_id"] = prompt_id
                        shot["video_error"] = compact_error["error"]
                        shot["video_error_detail"] = compact_error["detail"]
                        shot["video_error_node"] = " / ".join([x for x in (compact_error["node"], compact_error["node_type"]) if x])
                        shot["video_last_checked_at"] = _now_iso()
                        _persist_media_shot_metadata(shot)
                    results.append({
                        "shot_id": shot_id,
                        "prompt_id": prompt_id,
                        "status": "error",
                        "error": compact_error["error"],
                        "error_detail": compact_error["detail"],
                        "error_node": compact_error["node"],
                        "error_node_type": compact_error["node_type"],
                    })
                    continue

                if not status.get("completed"):
                    shot = _find_shot(shot_id)
                    if shot:
                        shot["video_status"] = "running"
                        shot["video_last_checked_at"] = _now_iso()
                        _persist_media_shot_metadata(shot)
                    results.append({"shot_id": shot_id, "prompt_id": prompt_id, "status": "running"})
                    continue

                campaign_id = _safe_campaign_name(job.campaign_id) if job.campaign_id else _campaign_from_comfy_history_outputs(entry)
                if not campaign_id or campaign_id == "imports":
                    shot = _find_shot(shot_id)
                    campaign_id = _safe_campaign_name(str((shot or {}).get("campaign_id") or _ACTIVE_CAMPAIGN or "video_batch"))
                output_dir = MEDIA_VIDEOS / campaign_id
                comfy = ComfyUIClient(host)
                saved = await comfy.download_outputs(prompt_id, str(output_dir))
                video_saved = [path for path in saved if Path(path).suffix.lower() in {".mp4", ".mov", ".webm", ".m4v"}]
                if not video_saved:
                    shot = _find_shot(shot_id)
                    if shot:
                        shot["video_status"] = "error"
                        shot["video_prompt_id"] = prompt_id
                        shot["video_error"] = "no_video_output_found"
                        shot["video_error_detail"] = "ComfyUI completed the prompt but no MP4/MOV/WEBM output was found."
                        shot["video_error_node"] = ""
                        shot["video_last_checked_at"] = _now_iso()
                        _persist_media_shot_metadata(shot)
                    results.append({"shot_id": shot_id, "prompt_id": prompt_id, "status": "error", "error": "no_video_output_found"})
                    continue
                attached = _attach_video_to_shot(
                    shot_id=shot_id,
                    saved_files=video_saved,
                    prompt_id=prompt_id,
                    workflow_id=job.workflow_id,
                    seed=job.seed,
                    duration=job.duration,
                    fps=job.fps,
                )
                any_saved = any_saved or bool(video_saved)
                results.append({
                    "shot_id": shot_id,
                    "prompt_id": prompt_id,
                    "status": "complete",
                    "campaign_id": campaign_id,
                    "saved_files": video_saved,
                    "video_url": (attached or {}).get("video_url", ""),
                })
            except Exception as e:
                results.append({"shot_id": shot_id, "prompt_id": prompt_id, "status": "error", "error": str(e)})

    reindex = _reindex_shots_from_storage() if any_saved else {"status": "skipped"}
    return {
        "status": "ok",
        "results": results,
        "complete": len([r for r in results if r.get("status") == "complete"]),
        "running": len([r for r in results if r.get("status") in {"running", "queued"}]),
        "errors": len([r for r in results if r.get("status") == "error"]),
        "reindex": reindex,
    }


@app.post("/api/video/generate-prompts")
async def api_video_generate_prompts(req: VideoGeneratePromptsRequest):
    """Stream LTX video prompt generation via Vision analysis + Hermes prompt profiles."""
    from fastapi.responses import StreamingResponse
    import asyncio

    shot_ids = [str(x) for x in req.shot_ids]
    duration = int(req.duration or 4)
    fps = int(req.fps or 24)
    workflow_id = _normalize_video_workflow_id(req.workflow_id)
    campaign_id = (req.campaign_id or _ACTIVE_CAMPAIGN or "video_batch").strip()

    # Resolve bible text if available
    bible_text = ""
    manifest_path = MEDIA_IMAGES / campaign_id / "_campaign.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            brief = manifest.get("brief", "")
            if brief:
                bible_text = brief
        except Exception:
            pass
    platform_skill = detect_platform_skill(bible_text, requested_mode=req.platform_mode)
    if platform_skill.get("active"):
        constraints = platform_skill.get("constraints") or {}
        if duration < int(constraints.get("duration_min_sec", 8)):
            duration = int(constraints.get("duration_default_sec", 12))
        if not fps:
            fps = int(constraints.get("fps", 24))

    service = HermesVideoService(
        media_videos=MEDIA_VIDEOS,
        active_campaign_getter=lambda: _ACTIVE_CAMPAIGN,
        find_shot=_find_shot,
        resolve_image_path=_resolve_image_path,
        workflow_file_for_id=_workflow_file_for_id,
    )

    async def event_generator():
        try:
            result = await service.generate_prompts(
                shot_ids=shot_ids,
                duration=duration,
                fps=fps,
                workflow_id=workflow_id,
                bible_text=bible_text,
                platform_skill=platform_skill,
            )

            if result.get("status") == "error":
                yield json.dumps({"agent": "System", "error": result.get("error", "generation_failed")}) + "\n"
                return

            analysis_results = result.get("analysis_results", [])
            duration_plan = result.get("duration_plan", "")
            prompts = result.get("prompts", {})
            raw = result.get("raw", {})

            # Agent 1: Vision Analyst
            yield json.dumps({"agent": "Vision Analyst", "status": "thinking"}) + "\n"
            for a in analysis_results:
                yield json.dumps({
                    "agent": "Vision Analyst",
                    "shot_id": a.get("shot_id", ""),
                    "result": a.get("analysis", ""),
                }) + "\n"

            # Agent 2: Duration Planner
            yield json.dumps({"agent": "Hermes / Duration Planner", "status": "thinking"}) + "\n"
            try:
                dp = json.loads(duration_plan) if isinstance(duration_plan, str) else duration_plan
                plan_items = dp.get("plan", []) if isinstance(dp, dict) else []
                for item in plan_items:
                    yield json.dumps({
                        "agent": "Hermes / Duration Planner",
                        "shot_id": item.get("shot_id", ""),
                        "result": f"{item.get('duration_sec', 0)}s ({item.get('frames', 0)} frames) — {item.get('reasoning', '')}",
                    }) + "\n"
            except Exception:
                yield json.dumps({"agent": "Hermes / Duration Planner", "result": str(duration_plan)[:500]}) + "\n"

            # Agent 3: Prompt Engineer
            yield json.dumps({"agent": "Hermes / LTX Prompt Engineer", "status": "thinking"}) + "\n"
            for sid, pdata in raw.items():
                if isinstance(pdata, dict):
                    segments = pdata.get("segments", [])
                    if segments:
                        for seg in segments:
                            yield json.dumps({
                                "agent": "Hermes / LTX Prompt Engineer",
                                "shot_id": sid,
                                "result": f"[{seg.get('time_range', '')}] {seg.get('prompt', '')}",
                            }) + "\n"
                    else:
                        yield json.dumps({"agent": "Hermes / LTX Prompt Engineer", "shot_id": sid, "result": str(pdata)}) + "\n"
                else:
                    yield json.dumps({"agent": "Hermes / LTX Prompt Engineer", "shot_id": sid, "result": str(pdata)}) + "\n"

            # Save prompts to shot records
            saved = 0
            save_misses = []
            for sid, prompt_text in prompts.items():
                shot = _find_shot(sid)
                if not shot:
                    # Fallback: model may return short ids (e.g. SHOT_001)
                    shot = next((s for s in _SHOTS_STORE if str(s.get("shot_id", "")) == str(sid)), None)
                if shot:
                    shot["video_prompt"] = prompt_text
                    shot["video_prompt_source"] = "vision_prompt_agent"
                    _persist_media_shot_metadata(shot)
                    saved += 1
                else:
                    save_misses.append(sid)

            if save_misses:
                yield json.dumps({
                    "agent": "System",
                    "error": f"Prompt save miss for {len(save_misses)} key(s): {', '.join(save_misses[:5])}"
                }) + "\n"

            yield json.dumps({
                "agent": "Hermes / LTX Prompt Engineer",
                "done": True,
                "saved": saved,
                "prompts": prompts,
                "video_prompt_source": "vision_prompt_agent",
                "selected": result.get("selected_count", len(shot_ids)),
                "unmapped_prompt_keys": result.get("unmapped_prompt_keys", []),
            }) + "\n"

        except Exception as e:
            yield json.dumps({"agent": "System", "error": str(e)}) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/export/carousel")
async def api_export_carousel(req: CarouselExportRequest):
    campaign_id = (req.campaign_id or _ACTIVE_CAMPAIGN or "carousel").strip() or "carousel"
    selected_ids = {str(x) for x in (req.shot_ids or []) if str(x).strip()}
    shots = [
        s for s in _SHOTS_STORE
        if (not selected_ids or str(s.get("id") or "") in selected_ids or str(s.get("shot_id") or "") in selected_ids)
        and (not req.campaign_id or str(s.get("campaign_id") or "") == req.campaign_id)
    ]
    if not shots:
        raise HTTPException(status_code=400, detail="No matching shots to export")

    manifest_path = MEDIA_IMAGES / campaign_id / "_campaign.json"
    brief = ""
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            brief = str(manifest.get("brief") or "")
        except Exception:
            brief = ""
    if not brief:
        brief = str(shots[0].get("campaign_brief") or "")
    platform = detect_platform_skill(brief, requested_mode=req.platform_mode)

    export_dir = MEDIA_ROOT / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_campaign = re.sub(r"[^a-zA-Z0-9_.-]+", "_", campaign_id).strip("_") or "carousel"
    zip_name = f"{safe_campaign}_tiktok_carousel_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = export_dir / zip_name
    caption_text = carousel_caption_text(brief, platform)
    manifest: Dict[str, Any] = {
        "campaign_id": campaign_id,
        "platform": platform,
        "created_at": datetime.utcnow().isoformat(),
        "items": [],
    }

    def _path_from_shot_url(value: str) -> Optional[Path]:
        if not value:
            return None
        p = _resolve_image_path(value)
        if p and p.exists():
            return p
        if value.startswith("/media-assets/"):
            candidate = MEDIA_ROOT / value.replace("/media-assets/", "", 1).lstrip("/")
            return candidate if candidate.exists() else None
        return None

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("captions.txt", caption_text)
        for idx, shot in enumerate(shots, start=1):
            media_paths: List[Path] = []
            for key in ("image_path", "video_path"):
                raw = str(shot.get(key) or "")
                if raw and Path(raw).exists():
                    media_paths.append(Path(raw))
            for key in ("image_url", "video_url"):
                p = _path_from_shot_url(str(shot.get(key) or ""))
                if p and p.exists():
                    media_paths.append(p)
            unique: List[Path] = []
            for p in media_paths:
                if p not in unique:
                    unique.append(p)
            for p in unique:
                folder = "clips" if p.suffix.lower() in {".mp4", ".mov", ".webm", ".m4v"} else "stills"
                arcname = f"{folder}/{idx:02d}_{p.name}"
                zf.write(p, arcname)
                manifest["items"].append({
                    "shot_id": shot.get("shot_id") or shot.get("id"),
                    "source": str(p),
                    "archive_path": arcname,
                })
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=True, indent=2))

    return {
        "status": "ok",
        "campaign_id": campaign_id,
        "count": len(manifest["items"]),
        "zip_url": f"/media-assets/exports/{zip_name}",
        "zip_path": str(zip_path),
        "caption_preview": caption_text,
    }


@app.post("/api/import/sienna-batch")
async def api_import_sienna_batch(req: ImportBatchRequest):
    report_path = Path(req.report_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_path}")
    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    video_exts = {".mp4", ".mov", ".webm", ".m4v"}
    media_exts = image_exts | video_exts
    if report_path.is_dir():
        files = sorted([p for p in report_path.rglob("*") if p.suffix.lower() in media_exts])
    elif report_path.suffix.lower() in {".json"}:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            files = []
            for key in ("images", "videos", "media", "files"):
                values = report.get(key, [])
                if isinstance(values, str):
                    values = [values]
                if not isinstance(values, list):
                    continue
                for item in values:
                    p = Path(item) if Path(str(item)).is_absolute() else report_path.parent / str(item)
                    if p.exists() and p.suffix.lower() in media_exts:
                        files.append(p)
            for item in report.get("outputs", []):
                if isinstance(item, dict):
                    item = item.get("path") or item.get("file") or item.get("filename") or ""
                p = Path(str(item)) if Path(str(item)).is_absolute() else report_path.parent / str(item)
                if p.exists() and p.suffix.lower() in media_exts:
                    files.append(p)
        except Exception:
            files = []
    else:
        files = [report_path]
    files = sorted({p.resolve(): p for p in files if p.suffix.lower() in media_exts}.values())

    imported = 0
    updated_existing = 0
    imported_videos = 0
    imported_images = 0
    for f in files:
        stem = f.stem
        is_video = f.suffix.lower() in video_exts
        shot_id = f"sienna_{stem}{'__video' if is_video else ''}"
        existing = _find_shot(shot_id)
        media_url = _media_url_for_path(f, is_video=is_video)
        if not existing:
            path_key = "video_path" if is_video else "image_path"
            url_key = "video_url" if is_video else "image_url"
            existing = next(
                (
                    s for s in _SHOTS_STORE
                    if str(s.get(path_key) or "") == str(f)
                    or str(s.get(url_key) or "") == media_url
                ),
                None,
            )
        shot_payload = {
            "id": shot_id,
            "campaign_id": "import",
            "shot_id": shot_id,
            "sequence": 0,
            "workflow_id": "imported_video" if is_video else "imported_media",
            "status": "complete" if is_video else "rendered",
            "state": "video_rendered" if is_video else "rendered",
            "seed": None,
            "prompt": f"Imported {'video' if is_video else 'media'}: {stem}",
            "compiled_prompt": f"Imported {'video' if is_video else 'media'}: {stem}",
            "video_prompt": "",
            "video_prompt_source": "",
            "negative_prompt": "",
            "workflow_profile": "import",
            "skills_used": [],
            "compiler_version": "",
            "model_standard_name": "",
            "model_standard_version": "",
            "model_standard_source": "",
            "model_standard_rules": [],
            "sections": {},
            "source": "import",
            "image_path": "" if is_video else str(f),
            "image_url": "" if is_video else media_url,
            "video_path": str(f) if is_video else "",
            "video_url": media_url if is_video else "",
            "created_at": _now_iso(),
        }
        if existing:
            existing.update(shot_payload)
            updated_existing += 1
        else:
            _SHOTS_STORE.append(shot_payload)
            imported += 1
        if is_video:
            imported_videos += 1
        else:
            imported_images += 1

    _record_pipeline_event(
        "import_completed",
        campaign_id="import",
        source="import",
        extra={"imported": imported, "updated_existing": updated_existing, "images": imported_images, "videos": imported_videos, "report_path": str(report_path)},
    )
    return {
        "status": "ok",
        "imported": imported,
        "updated_existing": updated_existing,
        "images": imported_images,
        "videos": imported_videos,
        "report": str(report_path),
    }


@app.post("/api/shots/dispatch-all")
async def api_shots_dispatch_all():
    return _legacy_disabled("/api/shots/dispatch-all", "/api/hermes/run-campaign")


@app.post("/api/shots/dispatch")
async def api_shots_dispatch(req: ShotDispatchRequest):
    _ = req
    return _legacy_disabled("/api/shots/dispatch", "/api/hermes/run-campaign")


@app.post("/api/submit-recipe")
async def api_submit_recipe(req: SubmitRecipeRequest):
    _ = req
    return _legacy_disabled("/api/submit-recipe", "/api/hermes/run-campaign")


class InjectPromptRequest(BaseModel):
    """Request to inject a Hermes-generated prompt into a ComfyUI workflow node."""
    prompt: str = ""
    node_id: str = "6"  # Default to node "6" (CLIPTextEncode)
    workflow_name: str = "default.json"
    comfy_url: str = "http://localhost:8188"
    filename: str = "FORGE"
    seed: int = 42


@app.post("/api/inject-prompt")
async def api_inject_prompt(req: InjectPromptRequest):
    _ = req
    return _legacy_disabled("/api/inject-prompt", "/api/hermes/run-campaign")


class RenderRequest(BaseModel):
    """Full render pipeline: inject prompt, submit, poll, download, save."""
    prompt: str = ""
    node_id: str = "6"
    workflow_name: str = "default.json"
    workflow: str = "default.json"
    target_node: str = "6"
    comfy_url: str = "http://localhost:8188"
    campaign: str = "default"
    filename: str = "FORGE"
    seed: int = 42
    poll_timeout: int = 300
    audit: bool = True  # Run Kimi-VL audit after render
    max_retries: int = 1
    audit_threshold: float = 0.6


class AuditRenderRequest(BaseModel):
    """Audit a specific render with Kimi-VL."""
    image_path: str = ""
    prompt: str = ""
    campaign: str = "default"


class FullImageAuditSchema(BaseModel):
    overall_score: float | int | None = None
    model_passed: bool | None = None
    passed: bool | None = None
    confidence: float | int | None = None
    checks: Dict[str, Any] | None = None
    critical_failures: List[Any] | None = None
    noncritical_issues: List[Any] | None = None
    issues: List[Any] | None = None
    feedback: str | None = None
    reasoning: str | None = None


_AUDIT_CHECK_KEYS = [
    "framing_ok",
    "hands_ok",
    "limbs_ok",
    "face_ok",
    "reflection_ok",
    "vehicle_geometry_ok",
    "text_artifacts_ok",
    "prompt_adherence_ok",
]
_AUDIT_CRITICAL_CHECKS = {"framing_ok", "hands_ok", "limbs_ok", "reflection_ok", "vehicle_geometry_ok"}
_AUDIT_CHECK_WEIGHTS = {
    "framing_ok": 3.0,
    "hands_ok": 3.0,
    "limbs_ok": 3.0,
    "face_ok": 2.0,
    "reflection_ok": 3.0,
    "vehicle_geometry_ok": 3.0,
    "text_artifacts_ok": 1.0,
    "prompt_adherence_ok": 2.0,
}
_AUDIT_KEYWORD_TO_CHECK = {
    "framing_ok": [
        "not full body",
        "not a full-body",
        "not strictly full-body",
        "not strictly full body",
        "full-body requirement",
        "full body requirement",
        "head-to-toe",
        "head to toe",
        "feet are cut",
        "feet cut",
        "feet not visible",
        "shoes not visible",
        "cut off",
        "cuts off",
        "cropped",
        "mid-thigh",
        "mid thigh",
        "below the knees",
        "at the knees",
        "at shins",
        "at the shins",
        "ankles",
    ],
    "hands_ok": ["finger", "thumb", "hand", "extra fingers", "missing fingers"],
    "limbs_ok": ["extra arm", "extra limb", "arm sticking", "arm through", "deformed anatomy", "broken limb"],
    "reflection_ok": ["reflection", "mirror", "window reflection", "inconsistent reflection"],
    "vehicle_geometry_ok": ["vehicle geometry", "wheel geometry", "door geometry", "impossible perspective", "car body"],
    "face_ok": ["deformed face", "facial distortion", "asymmetric face"],
    "text_artifacts_ok": ["watermark", "text artifact", "gibberish text"],
    "prompt_adherence_ok": ["off prompt", "not matching prompt", "wrong scene", "prompt mismatch"],
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_issue_list(values: Any) -> List[str]:
    if isinstance(values, list):
        out: List[str] = []
        for v in values:
            text = str(v).strip()
            if text:
                out.append(text)
        return out
    if values is None:
        return []
    text = str(values).strip()
    return [text] if text else []


def _merge_checks(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, bool]:
    merged: Dict[str, bool] = {}
    for key in _AUDIT_CHECK_KEYS:
        p = primary.get(key)
        s = secondary.get(key)
        if isinstance(p, bool) and isinstance(s, bool):
            merged[key] = p and s
        elif isinstance(p, bool):
            merged[key] = p
        elif isinstance(s, bool):
            merged[key] = s
        else:
            merged[key] = True
    return merged


def _requires_full_body(prompt: str) -> bool:
    text = str(prompt or "").lower()
    return any(
        phrase in text
        for phrase in (
            "full-body",
            "full body",
            "full-length",
            "full length",
            "head-to-toe",
            "head to toe",
            "feet fully visible",
            "both feet",
        )
    )


def _apply_keyword_fails(checks: Dict[str, bool], issues: List[str], feedback: str, prompt: str = "") -> Dict[str, bool]:
    merged_text = " ".join(issues + [feedback]).lower()
    if not merged_text:
        return checks
    absence_phrases = (
        "hands are not visible",
        "hands not visible",
        "no hands visible",
        "hand is not visible",
        "hand not visible",
        "not visible on controls",
    )
    for check_key, keywords in _AUDIT_KEYWORD_TO_CHECK.items():
        if check_key == "hands_ok" and any(p in merged_text for p in absence_phrases):
            continue
        if any(k in merged_text for k in keywords):
            checks[check_key] = False
    if _requires_full_body(prompt) and any(
        p in merged_text
        for p in (
            "not full body",
            "not a full-body",
            "full-body requirement",
            "full body requirement",
            "cut off",
            "cuts off",
            "cropped",
            "feet",
            "knees",
            "shins",
            "thigh",
        )
    ):
        checks["framing_ok"] = False
        checks["prompt_adherence_ok"] = False
    return checks


def _remove_absent_hand_issues(issues: List[str]) -> List[str]:
    absence_phrases = (
        "hands are not visible",
        "hands not visible",
        "no hands visible",
        "hand is not visible",
        "hand not visible",
        "not visible on controls",
    )
    filtered = []
    for issue in issues:
        text = str(issue or "")
        if any(p in text.lower() for p in absence_phrases):
            continue
        filtered.append(text)
    return filtered


def _extract_checks(raw: Dict[str, Any]) -> Dict[str, Any]:
    checks = raw.get("checks")
    if isinstance(checks, dict):
        return checks
    return {}


def _aggregate_audit_results(pass_a: Dict[str, Any], pass_b: Dict[str, Any], prompt: str = "") -> Dict[str, Any]:
    score_a = _safe_float(pass_a.get("overall_score", pass_a.get("score", 0)), 0.0)
    score_b = _safe_float(pass_b.get("overall_score", pass_b.get("score", 0)), 0.0)
    score_model = max(score_a, score_b)
    confidence = max(_safe_float(pass_a.get("confidence"), 0.0), _safe_float(pass_b.get("confidence"), 0.0))

    checks_a = _extract_checks(pass_a)
    checks_b = _extract_checks(pass_b)
    checks = _merge_checks(checks_a, checks_b)

    issues = _normalize_issue_list(pass_a.get("issues")) + _normalize_issue_list(pass_b.get("issues"))
    noncritical = _normalize_issue_list(pass_a.get("noncritical_issues")) + _normalize_issue_list(pass_b.get("noncritical_issues"))
    critical = _normalize_issue_list(pass_a.get("critical_failures")) + _normalize_issue_list(pass_b.get("critical_failures"))
    feedback = " | ".join([x for x in [pass_a.get("feedback"), pass_b.get("feedback")] if isinstance(x, str) and x.strip()]).strip()

    checks = _apply_keyword_fails(checks, issues + noncritical + critical, feedback, prompt)
    merged_audit_text = " ".join(issues + noncritical + critical + [feedback]).lower()
    if any(p in merged_audit_text for p in ("hands are not visible", "hands not visible", "no hands visible", "hand is not visible", "hand not visible", "not visible on controls")):
        checks["hands_ok"] = True
        issues = _remove_absent_hand_issues(issues)
        noncritical = _remove_absent_hand_issues(noncritical)
        critical = _remove_absent_hand_issues(critical)
    for key in _AUDIT_CRITICAL_CHECKS:
        if checks.get(key) is False and not any(key in c for c in critical):
            critical.append(f"{key} failed")

    total_weight = sum(_AUDIT_CHECK_WEIGHTS.values())
    passed_weight = sum(weight for key, weight in _AUDIT_CHECK_WEIGHTS.items() if checks.get(key, True))
    check_score = (passed_weight / total_weight) * 100.0 if total_weight > 0 else 0.0
    score_backend = round((0.55 * score_model) + (0.45 * check_score), 1)

    model_passed_a = bool(pass_a.get("model_passed", pass_a.get("passed", True)))
    model_passed_b = bool(pass_b.get("model_passed", pass_b.get("passed", True)))
    model_passed = model_passed_a and model_passed_b

    min_score = _safe_float(os.getenv("FORGE_AUDIT_MIN_SCORE", "80"), 80.0)
    min_conf = _safe_float(os.getenv("FORGE_AUDIT_MIN_CONFIDENCE", "0.55"), 0.55)
    decision_reasons: List[str] = []

    failed_critical_checks = [k for k in _AUDIT_CRITICAL_CHECKS if checks.get(k) is False]
    if failed_critical_checks:
        decision_reasons.append("critical_check_failed:" + ",".join(sorted(failed_critical_checks)))
    if critical:
        decision_reasons.append("critical_issues_present")
    if score_backend < min_score:
        decision_reasons.append(f"backend_score_below_threshold:{score_backend}<{min_score}")
    if confidence < min_conf:
        decision_reasons.append(f"confidence_below_threshold:{confidence:.2f}<{min_conf:.2f}")
    if not model_passed:
        decision_reasons.append("model_marked_fail")

    final_passed = len(decision_reasons) == 0
    all_issues = []
    seen = set()
    for item in critical + issues + noncritical:
        t = str(item).strip()
        if t and t not in seen:
            seen.add(t)
            all_issues.append(t)
    if decision_reasons and not all_issues:
        all_issues = decision_reasons.copy()

    return {
        "score": score_backend,
        "passed": final_passed,
        "feedback": feedback or ("Passed forensic and cinematic checks." if final_passed else "Failed deterministic audit gates."),
        "issues": all_issues,
        "overall_score": score_backend,
        "model_score": round(score_model, 1),
        "checks_score": round(check_score, 1),
        "confidence": round(confidence, 3),
        "model_passed": model_passed,
        "final_passed": final_passed,
        "checks": checks,
        "critical_failures": critical,
        "noncritical_issues": noncritical,
        "audit_decision_reasons": decision_reasons,
        "audit_passes": {
            "cinematic": pass_a,
            "forensic": pass_b,
        },
    }


def _extract_json_response(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise RuntimeError("vision_empty_response")
    if raw.startswith("```"):
        parts = raw.split("```")
        if len(parts) >= 2:
            raw = parts[1].strip()
            if raw.startswith("json"):
                raw = raw[4:].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start < 0:
            raise
        decoder = json.JSONDecoder()
        parsed, _ = decoder.raw_decode(raw[start:])
        if not isinstance(parsed, dict):
            raise RuntimeError("vision_response_json_not_object")
        return parsed


def _image_mime_type(image_path: str) -> str:
    suffix = Path(image_path).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


async def _run_vision_audit_pass(
    *,
    endpoint: str,
    api_key: str,
    model: str,
    image_path: str,
    system_prompt: str,
    user_prompt: str,
    task_description: str,
) -> Dict[str, Any]:
    endpoint = endpoint.strip().rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint = f"{endpoint}/chat/completions"
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    mime_type = _image_mime_type(image_path)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "/no_think\n" + system_prompt + "\nReturn compact JSON only. No markdown."},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "/no_think\n"
                            + user_prompt
                            + "\n\nIMPORTANT: Put the final answer in assistant content as raw JSON only. "
                            "Do not leave the final answer only in reasoning_content. Keep the JSON compact."
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                ],
            },
        ],
        "temperature": 0,
        "max_tokens": int(os.getenv("FORGE_VISION_AUDIT_MAX_TOKENS", "16384")),
        "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
    }
    headers = {"Content-Type": "application/json"}
    if api_key and endpoint.startswith("https://"):
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=120.0) as http:
        resp = await http.post(endpoint, headers=headers, json=payload)
    if resp.status_code >= 400:
        raise RuntimeError(f"vision_audit_http_error status={resp.status_code} error={resp.text[:500]}")
    data = resp.json()
    message = (data.get("choices") or [{}])[0].get("message", {})
    content = message.get("content", "")
    reasoning_content = message.get("reasoning_content", "")
    finish_reason = (data.get("choices") or [{}])[0].get("finish_reason", "")
    if isinstance(content, dict):
        result = content
    else:
        if not str(content or "").strip() and finish_reason == "length":
            if str(reasoning_content or "").strip():
                try:
                    result = _extract_json_response(str(reasoning_content))
                    result["_audit_warning"] = "parsed_from_reasoning_content_after_length"
                except Exception:
                    raise RuntimeError("vision_no_final_content_token_limit")
            else:
                raise RuntimeError("vision_no_final_content_token_limit")
        else:
            result = _extract_json_response(str(content))
    if not isinstance(result, dict):
        raise RuntimeError(f"vision_audit_invalid_response:{task_description}")
    return result


async def audit_render_with_kimi_vl(image_path: str, prompt: str = "", campaign: str = "default"):
    """
    Run Kimi-VL audit on a rendered image.
    Returns audit result dict with score, passed, feedback.
    """
    cfg = get_raw_config()
    try:
        active = str(cfg.get("KIMI_VISUAL_ENDPOINT_ACTIVE", "api1") or "api1").strip().lower()
        api1 = str(cfg.get("KIMI_VISUAL_ENDPOINT_API1", "") or "").strip()
        api2 = str(cfg.get("KIMI_VISUAL_ENDPOINT_API2", "") or "").strip()
        endpoint = api2 if active == "api2" and api2 else api1
        if not endpoint:
            endpoint = str(cfg.get("NIM_ENDPOINT", "") or "").strip()
        api_key = str(cfg.get("KIMI_API_KEY", "") or os.getenv("KIMI_API_KEY", "")).strip()
        model = str(cfg.get("KIMI_VISUAL_MODEL", "") or cfg.get("LMSTUDIO_VISION_MODEL", "") or "").strip()
        if not endpoint:
            raise RuntimeError("missing_kimi_visual_endpoint")
        if endpoint.startswith("https://") and not api_key:
            raise RuntimeError("missing_kimi_api_key")
        if not model:
            raise RuntimeError("missing_kimi_visual_model")
        audit_system_prompt = "You are a compact visual QA auditor. Return only JSON."
        audit_user_prompt = (
            "Return ONLY minified JSON, no markdown, no explanation. "
            f"Audit this image for campaign '{campaign}'. Prompt excerpt: {prompt[:180] if prompt else 'N/A'}. "
            "Schema: {\"overall_score\":0-100,\"model_passed\":true/false,\"confidence\":0-1,"
            "\"checks\":{\"framing_ok\":true,\"hands_ok\":true,\"limbs_ok\":true,\"face_ok\":true,\"reflection_ok\":true,"
            "\"vehicle_geometry_ok\":true,\"text_artifacts_ok\":true,\"prompt_adherence_ok\":true},"
            "\"critical_failures\":[],\"noncritical_issues\":[],\"issues\":[],\"feedback\":\"short\"}. "
            "If the prompt asks for full-body, full-length, or head-to-toe framing, framing_ok MUST be false and model_passed MUST be false when feet, shoes, legs, knees, shins, or ankles are cropped or not visible. "
            "Fail only visible hard defects. If hands/faces/reflections/vehicles are not visible or not applicable, mark that check true."
        )

        audit_pass = await _run_vision_audit_pass(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            image_path=image_path,
            system_prompt=audit_system_prompt,
            user_prompt=audit_user_prompt,
            task_description=f"Compact audit for {campaign}",
        )
        result = _aggregate_audit_results(audit_pass, {}, prompt)
        result["audit_backend"] = "vision_config"
        result["audit_endpoint"] = endpoint
        result["audit_model"] = model
        print(
            "[FORGE] [KIMI-VL] Audit result: "
            f"backend_score={result.get('score', 'N/A')}, "
            f"final_passed={result.get('passed', 'N/A')}, "
            f"model_passed={result.get('model_passed', 'N/A')}"
        )
        return result
    except Exception as e:
        kimi_error = str(e)
        print(f"[FORGE] [KIMI-VL] Audit failed: {kimi_error}")
        return {
            "score": 0,
            "passed": False,
            "feedback": f"Kimi-VL audit failed: {kimi_error}",
            "issues": [kimi_error],
            "overall_score": 0,
            "model_score": 0,
            "checks_score": 0,
            "confidence": 0,
            "model_passed": False,
            "final_passed": False,
            "checks": {k: False for k in _AUDIT_CHECK_KEYS},
            "critical_failures": ["audit_execution_failure"],
            "noncritical_issues": [],
            "audit_backend": "kimi_vl",
            "audit_decision_reasons": [f"audit_execution_failure:kimi_vl={kimi_error}"],
            "error": True,
        }


async def write_audit_to_memory(audit_result: dict, image_path: str, prompt: str = "", campaign: str = "default"):
    """
    Write audit result to episodic memory (events.jsonl) and emit [MEM] event.
    """
    import uuid
    from datetime import datetime

    repo_root = Path(__file__).parent.parent
    episodic_dir = repo_root / "data" / "hermes_memory" / "episodic"
    episodic_dir.mkdir(parents=True, exist_ok=True)
    events_path = episodic_dir / "events.jsonl"

    event = {
        "event_id": f"audit_{uuid.uuid4().hex[:8]}",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event_type": "audit_result",
        "session_id": campaign,
        "shot_id": Path(image_path).stem if image_path else "",
        "campaign_id": campaign,
        "workflow_id": "",
        "pipeline_mode": "production",
        "source": "campaign",
        "concept": prompt[:80] if prompt else "render_audit",
        "success": audit_result.get("passed", False),
        "audit_score": audit_result.get("score", 0),
        "error_category": "quality_fail" if not audit_result.get("passed") else "none",
        "fix_applied": "",
        "iterations_required": 1,
        "feedback": audit_result.get("feedback", ""),
        "issues": audit_result.get("issues", []),
        "image_path": image_path,
    }

    # Append to events.jsonl
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    print(f"[FORGE] [MEM] Written audit to memory: {event['event_id']} (score={event['audit_score']})")

    # Emit [MEM] event
    await emit_hermes_event("memory_written", {
        "concept": f"Audit: {prompt[:50] if prompt else 'render'}",
        "event_id": event["event_id"],
        "score": event["audit_score"],
        "passed": event["success"],
        "feedback": event["feedback"][:100],
    })

    return event


@app.post("/api/render/audit")
async def api_render_audit(req: AuditRenderRequest):
    _ = req
    return _legacy_disabled("/api/render/audit", "/api/audit/reprocess")


@app.post("/api/render")
async def api_render(req: RenderRequest):
    _ = req
    return _legacy_disabled("/api/render", "/api/hermes/run-campaign")


# --- Spark Monitor Endpoints ---

@app.get("/api/spark/test")
async def api_spark_test(url: str):
    """Test a ComfyUI host and return system info."""
    from core.dispatch.comfy_client import ComfyUIClient
    client = ComfyUIClient(url)
    ok, info = await client.check_health()
    if not ok:
        raise HTTPException(status_code=503, detail=info.get("error", "Unreachable"))
    return {"url": url, "healthy": True, "info": info}


@app.post("/api/test/comfyui")
async def api_test_comfyui(req: ComfyUITestRequest):
    """Settings-page ComfyUI connection test."""
    host = (req.host or "").strip().rstrip("/")
    if not host:
        return {"status": "error", "error": "missing host"}
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    t0 = time.time()
    client = ComfyUIClient(host)
    ok, info = await client.check_health()
    latency_ms = int((time.time() - t0) * 1000)
    if not ok:
        return {
            "status": "error",
            "error": info.get("error", "unreachable"),
            "host": host,
            "latency_ms": latency_ms,
        }
    return {
        "status": "ok",
        "host": host,
        "latency_ms": latency_ms,
        "info": info,
    }


@app.get("/api/spark/state")
async def api_spark_state():
    """Current Spark queue state."""
    return spark_monitor.get_state()


@app.websocket("/ws/spark")
async def spark_websocket(websocket: WebSocket):
    await spark_ws_manager.connect(websocket, "spark")
    # Register callback to push updates
    async def push_spark_update(payload):
        try:
            await websocket.send_json(payload)
        except Exception:
            pass
    spark_monitor.register_callback(push_spark_update)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        spark_monitor.unregister_callback(push_spark_update)
        spark_ws_manager.disconnect(websocket, "spark")


# --- Hermes WebSocket ---

hermes_event_queue: asyncio.Queue = asyncio.Queue()

@app.websocket("/ws/hermes")
async def hermes_websocket(websocket: WebSocket):
    await hermes_manager.connect(websocket, "hermes")
    try:
        while True:
            event = await hermes_event_queue.get()
            await hermes_manager.broadcast(event, "hermes")
    except WebSocketDisconnect:
        hermes_manager.disconnect(websocket, "hermes")


async def emit_hermes_event(event_type: str, payload: Dict[str, Any]):
    """Emit a Hermes decision event to all connected dashboard clients."""
    await hermes_event_queue.put({
        "type": event_type,
        "payload": payload,
        "timestamp": time.time(),
    })


# --- Teach Mode Endpoint ---

class TeachModeRequest(BaseModel):
    concept: str = ""
    error_type: str = "strip_hair_color"  # strip_hair_color | wrong_lighting | remove_anchor


@app.post("/api/hermes/teach")
async def api_hermes_teach(req: TeachModeRequest):
    """
    Run a controlled teach cycle:
    1. Inject deliberate error
    2. Generate through the configured render backend
    3. Record failure + fix
    4. Trigger consolidation
    5. Return before/after trace
    """
    if os.getenv("FORGE_ENABLE_TEACH_MODE", "false").lower() != "true":
        return _legacy_disabled("/api/hermes/teach", "FORGE_ENABLE_TEACH_MODE=true")
    from core.hermes.hermes_agent import HermesAgent

    hermes = HermesAgent()
    episodic = hermes.episodic
    semantic = hermes.semantic

    # Build the "before" prompt (with error)
    base_prompt = req.concept
    if req.error_type == "strip_hair_color":
        bad_prompt = base_prompt.replace("dyed iridescent silver", "")
        fix = "add 'dyed iridescent silver' to prompt"
        error_category = "Photometric"
    elif req.error_type == "wrong_lighting":
        bad_prompt = base_prompt.replace("neon glow", "warm candlelight")
        fix = "replace 'warm candlelight' with 'neon glow'"
        error_category = "Photometric"
    else:
        bad_prompt = base_prompt
        fix = "re-inject character anchor descriptors"
        error_category = "Semantic"

    # Simulate failure event
    failure_event = {
        "event_id": f"evt_teach_fail_{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": "teach_mode",
        "shot_id": "TEACH_001",
        "event_type": "outcome",
        "concept": bad_prompt,
        "kernel_id": "zimage_turbo",
        "success": False,
        "error_category": error_category,
        "fix_applied": fix,
        "audit_score": 45.0,
        "iterations_required": 1,
    }
    episodic.record(failure_event)

    # Simulate success event (with fix applied)
    success_event = {
        "event_id": f"evt_teach_ok_{uuid.uuid4().hex[:8]}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "session_id": "teach_mode",
        "shot_id": "TEACH_001",
        "event_type": "outcome",
        "concept": base_prompt,
        "kernel_id": "zimage_turbo",
        "success": True,
        "error_category": error_category,
        "fix_applied": fix,
        "audit_score": 94.0,
        "iterations_required": 2,
    }
    episodic.record(success_event)

    # Trigger consolidation
    new_insights = await hermes.consolidate_session(session_events=[failure_event, success_event])

    return {
        "before": {
            "prompt": bad_prompt,
            "score": 45.0,
            "status": "failed",
        },
        "after": {
            "prompt": base_prompt,
            "score": 94.0,
            "status": "passed",
        },
        "fix": fix,
        "insight": new_insights[0] if new_insights else None,
        "events_recorded": 2,
    }


# --- Export Brain Endpoint ---

@app.get("/api/hermes/export")
async def api_hermes_export():
    """Download Hermes's learned skills as a JSON pack."""
    episodic = EpisodicMemory()
    semantic = SemanticMemory()
    skills = SkillRegistry()

    insights = semantic.get_all_insights()
    registry_data = {}
    if Path(skills.registry_path).exists():
        import json as _json
        with open(skills.registry_path, "r", encoding="utf-8") as f:
            registry_data = _json.load(f)

    return {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "semantic_insights": insights,
        "skill_registry": registry_data,
        "episodic_summary": {
            "total_events": len(episodic.get_recent(n=99999)),
            "top_error_categories": {},  # Could compute if needed
        },
    }


# --- Consistency Score Endpoint ---

class ScoreRequest(BaseModel):
    render_path: str  # relative to repo root, e.g. "data/seed_outputs/VAR_000.png"
    anchor_path: str = "data/character_banks/anchors/elara_vance.jpg"


@app.post("/api/consistency/score")
async def api_consistency_score(req: ScoreRequest):
    """Score a render against the anchor image (0-100)."""
    from PIL import Image
    import numpy as np

    repo_root = Path(__file__).parent.parent
    render_file = repo_root / req.render_path
    anchor_file = repo_root / req.anchor_path

    if not render_file.exists():
        raise HTTPException(status_code=404, detail=f"Render not found: {req.render_path}")
    if not anchor_file.exists():
        raise HTTPException(status_code=404, detail=f"Anchor not found: {req.anchor_path}")

    try:
        render = Image.open(render_file).convert("RGB").resize((256, 256))
        anchor = Image.open(anchor_file).convert("RGB").resize((256, 256))

        # Histogram correlation per channel
        scores = []
        for i in range(3):
            rh = np.array(render.split()[i].histogram(), dtype=np.float32)
            ah = np.array(anchor.split()[i].histogram(), dtype=np.float32)
            # Normalize
            rh /= rh.sum() + 1e-9
            ah /= ah.sum() + 1e-9
            # Correlation
            mean_r, mean_a = rh.mean(), ah.mean()
            num = ((rh - mean_r) * (ah - mean_a)).sum()
            den = np.sqrt(((rh - mean_r)**2).sum() * ((ah - mean_a)**2).sum()) + 1e-9
            corr = max(0, num / den)
            scores.append(corr)

        avg_score = float(np.mean(scores) * 100)

        # Also log to episodic memory
        episodic = EpisodicMemory()
        episodic.record({
            "event_id": f"evt_score_{uuid.uuid4().hex[:8]}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "session_id": "consistency_audit",
            "shot_id": Path(req.render_path).stem,
            "event_type": "outcome",
            "concept": f"Consistency score for {req.render_path}",
            "kernel_id": "consistency_scorer",
            "success": avg_score >= 70,
            "error_category": "" if avg_score >= 70 else "Photometric",
            "fix_applied": "" if avg_score >= 70 else "review_anchor",
            "audit_score": round(avg_score, 1),
        })

        return {
            "render": req.render_path,
            "anchor": req.anchor_path,
            "score": round(avg_score, 1),
            "passed": avg_score >= 70,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Startup: wire Hermes event emitter + begin Spark Monitor ---

@app.on_event("startup")
async def on_startup():
    # Wire HermesAgent events to dashboard WebSocket
    from core.hermes.hermes_agent import set_event_emitter
    set_event_emitter(emit_hermes_event)
    spark_monitor.start()
    # Apply data/config.json overrides to environment on boot
    from core.bridge.runtime_config import apply_to_environment
    apply_to_environment()
    reindex_result = _reindex_shots_from_storage()
    print(
        "[FORGE] Media shots reindexed at startup: "
        f"{reindex_result.get('reindexed', 0)} media, "
        f"{reindex_result.get('preserved_non_media', 0)} non-media"
    )
    # Auto-detect LM Studio using the same saved host/port as Settings.
    from core.bridge.lmstudio_client import LMStudioClient
    cfg = get_raw_config()
    local = LMStudioClient(
        base_url=_normalize_lmstudio_base_url(cfg.get("LMSTUDIO_HOST", ""), cfg.get("LMSTUDIO_PORT", "")),
        chat_model=str(cfg.get("LMSTUDIO_CHAT_MODEL", "") or ""),
        embed_model=str(cfg.get("LMSTUDIO_EMBED_MODEL", "") or ""),
    )
    if local.is_available:
        success, models, selected = await local.auto_detect_model()
        if success:
            print(f"[FORGE] LM Studio auto-detected model: {selected} (available: {models})")
            # Persist auto-detected model to config
            from core.bridge.runtime_config import set_config
            set_config({
                "LMSTUDIO_CHAT_MODEL": local.chat_model,
                "LMSTUDIO_EMBED_MODEL": local.embed_model,
            })
            await emit_hermes_event("lmstudio_detected", {
                "model": selected,
                "models": models,
                "host": local.base_url,
            })
        else:
            print("[FORGE] LM Studio reachable but no models loaded")
            await emit_hermes_event("lmstudio_empty", {"host": local.base_url})
    else:
        print(f"[FORGE] LM Studio not reachable at startup: {local.base_url}")
        await emit_hermes_event("lmstudio_offline", {"host": local.base_url})


@app.on_event("shutdown")
async def on_shutdown():
    spark_monitor.stop()


# --- Settings / Config API ---

@app.get("/api/config")
async def api_config():
    """Return UI-oriented nested config structure."""
    from core.bridge.runtime_config import get_raw_config
    cfg = get_raw_config()
    kimi_key = str(cfg.get("KIMI_API_KEY", "") or "")
    endpoint = str(cfg.get("NIM_ENDPOINT", "") or "")
    comfy_primary = str(cfg.get("COMFYUI_PRIMARY", "") or "")
    comfy_secondary = str(cfg.get("COMFYUI_SECONDARY", "") or "")
    spark_workflow_file = str(cfg.get("SPARK_WORKFLOW_FILE", "") or "")
    lm_host = str(cfg.get("LMSTUDIO_HOST", "") or "")
    lm_port = str(cfg.get("LMSTUDIO_PORT", "") or "")
    lm_model = str(cfg.get("LMSTUDIO_CHAT_MODEL", "") or "")
    vision_model = str(cfg.get("KIMI_VISUAL_MODEL", "") or cfg.get("LMSTUDIO_VISION_MODEL", "") or "")
    director_api1 = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API1", "") or endpoint or "")
    director_api2 = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API2", "") or "")
    director_active = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_ACTIVE", "") or "api1")
    visual_api1 = str(cfg.get("KIMI_VISUAL_ENDPOINT_API1", "") or endpoint or "")
    visual_api2 = str(cfg.get("KIMI_VISUAL_ENDPOINT_API2", "") or "")
    visual_active = str(cfg.get("KIMI_VISUAL_ENDPOINT_ACTIVE", "") or "api1")
    use_local_director = _truthy_config(cfg.get("USE_LOCAL_DIRECTOR", ""))
    director_selected = director_api2 if director_active == "api2" and director_api2 else director_api1
    visual_selected = visual_api2 if visual_active == "api2" and visual_api2 else visual_api1
    openai_key = str(cfg.get("OPENAI_API_KEY", "") or "")
    gemini_key = str(cfg.get("GEMINI_API_KEY", "") or "")
    try:
        lm_port_value: Any = int(lm_port or "1234") if lm_host else ""
    except ValueError:
        lm_port_value = 1234 if lm_host else ""
    return {
        "backend_mode": "remote" if endpoint.startswith("http") else "local",
        "kimi": {
            "api_key_set": bool(kimi_key),
            "endpoint": endpoint,
        },
        "models": {
            "director_kimi": {
                "model_name": str(cfg.get("KIMI_INSTRUCT_MODEL", "") or ""),
                "endpoint": director_selected,
                "endpoint_api1": director_api1,
                "endpoint_api2": director_api2,
                "endpoint_active": director_active,
                "use_local": use_local_director,
                "active_backend": "lmstudio" if use_local_director else "nvidia",
                "local_model_name": lm_model,
                "local_endpoint": f"{_normalize_lmstudio_base_url(lm_host, lm_port)}/v1/chat/completions",
            },
            "kimi_vl": {
                "model_name": vision_model,
                "endpoint": visual_selected,
                "endpoint_api1": visual_api1,
                "endpoint_api2": visual_api2,
                "endpoint_active": visual_active,
            },
            "hermes_3": {
                "host": lm_host,
                "port": lm_port_value,
                "model_name": lm_model,
            },
        },
        "comfyui": {"primary": comfy_primary, "secondary": comfy_secondary},
        "spark": {
            "primary": comfy_primary,
            "secondary": comfy_secondary,
            "workflow_file": spark_workflow_file,
        },
        "storyboard_images": {
            "default_provider": str(cfg.get("STORYBOARD_IMAGE_PROVIDER", "") or "spark:flux2_dev"),
            "openai_api_key_set": bool(openai_key),
            "openai_model": str(cfg.get("OPENAI_IMAGE_MODEL", "") or "gpt-image-2"),
            "gemini_api_key_set": bool(gemini_key),
            "gemini_model": str(cfg.get("GEMINI_IMAGE_MODEL", "") or "gemini-2.5-flash-image"),
        },
    }


@app.get("/api/lora/presets")
async def api_lora_presets():
    """Return LoRA presets the app knows how to apply when installed in ComfyUI."""
    return {"presets": lora_preset_payload()}


class ConfigUpdateRequest(BaseModel):
    updates: Dict[str, Any]


@app.post("/api/config")
async def api_config_update(req: ConfigUpdateRequest):
    """Update configuration values. Persists to data/config.json."""
    from core.bridge.runtime_config import set_config, apply_to_environment
    updated = set_config(req.updates)
    apply_to_environment()
    return {"status": "saved", "config": updated}


class FlatConfigUpdateRequest(BaseModel):
    """Flat key-value config update (no nested 'updates' key)."""
    model_config = {"extra": "allow"}
    updates: Optional[Dict[str, Any]] = None


@app.post("/api/config/save")
async def api_config_save(req: FlatConfigUpdateRequest):
    """Save config updates from frontend dot-path payloads."""
    from core.bridge.runtime_config import set_config, apply_to_environment
    incoming: Dict[str, Any] = {}
    if isinstance(req.updates, dict):
        incoming = dict(req.updates)
    extra = getattr(req, "__pydantic_extra__", None)
    if not incoming and isinstance(extra, dict):
        if isinstance(extra.get("updates"), dict):
            incoming = dict(extra["updates"])
        else:
            incoming = dict(extra)
    updates = incoming

    mapped: Dict[str, Any] = {}
    key_map = {
        "nous.api_key": "NOUS_API_KEY",
        "nous.endpoint": "NOUS_ENDPOINT",
        "director_model": "DIRECTOR_MODEL",
        "thinking_model": "THINKING_MODEL",
        "vision_model": "VISION_MODEL",
        "kimi.api_key": "KIMI_API_KEY",
        "kimi.endpoint": "NIM_ENDPOINT",
        "models.director_kimi.model_name": "KIMI_INSTRUCT_MODEL",
        "models.director_kimi.endpoint": "NIM_ENDPOINT",
        "models.director_kimi.endpoint_api1": "KIMI_DIRECTOR_ENDPOINT_API1",
        "models.director_kimi.endpoint_api2": "KIMI_DIRECTOR_ENDPOINT_API2",
        "models.director_kimi.endpoint_active": "KIMI_DIRECTOR_ENDPOINT_ACTIVE",
        "models.director_kimi.use_local": "USE_LOCAL_DIRECTOR",
        "models.kimi_vl.model_name": "KIMI_VISUAL_MODEL",
        "models.kimi_vl.endpoint": "NIM_ENDPOINT",
        "models.kimi_vl.endpoint_api1": "KIMI_VISUAL_ENDPOINT_API1",
        "models.kimi_vl.endpoint_api2": "KIMI_VISUAL_ENDPOINT_API2",
        "models.kimi_vl.endpoint_active": "KIMI_VISUAL_ENDPOINT_ACTIVE",
        "models.hermes_3.host": "LMSTUDIO_HOST",
        "models.hermes_3.port": "LMSTUDIO_PORT",
        "models.hermes_3.model_name": "LMSTUDIO_CHAT_MODEL",
        "comfyui.primary": "COMFYUI_PRIMARY",
        "comfyui.secondary": "COMFYUI_SECONDARY",
        "spark.primary": "COMFYUI_PRIMARY",
        "spark.secondary": "COMFYUI_SECONDARY",
        "spark.workflow_file": "SPARK_WORKFLOW_FILE",
        "storyboard_images.default_provider": "STORYBOARD_IMAGE_PROVIDER",
        "storyboard_images.openai_api_key": "OPENAI_API_KEY",
        "storyboard_images.openai_model": "OPENAI_IMAGE_MODEL",
        "storyboard_images.gemini_api_key": "GEMINI_API_KEY",
        "storyboard_images.gemini_model": "GEMINI_IMAGE_MODEL",
    }
    for k, v in (updates or {}).items():
        mapped[key_map.get(k, k)] = v
    current_cfg = get_raw_config()
    for secret_key in ["NOUS_API_KEY", "KIMI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
        if secret_key in mapped and not str(mapped.get(secret_key) or "").strip() and str(current_cfg.get(secret_key, "") or "").strip():
            mapped.pop(secret_key, None)
    updated = set_config(mapped)
    apply_to_environment()
    return {"status": "success", "saved": list(mapped.keys()), "config": updated}


@app.get("/api/config/effective")
async def api_config_effective():
    """Return canonical runtime config values currently effective (masked keys)."""
    from core.bridge.runtime_config import get_config, get_raw_config
    masked = get_config()
    raw = get_raw_config()
    director_api1 = str(raw.get("KIMI_DIRECTOR_ENDPOINT_API1", "") or raw.get("NIM_ENDPOINT", "") or "").strip()
    director_api2 = str(raw.get("KIMI_DIRECTOR_ENDPOINT_API2", "") or "").strip()
    director_active = str(raw.get("KIMI_DIRECTOR_ENDPOINT_ACTIVE", "api1") or "api1").strip().lower()
    vision_api1 = str(raw.get("KIMI_VISUAL_ENDPOINT_API1", "") or raw.get("NIM_ENDPOINT", "") or "").strip()
    vision_api2 = str(raw.get("KIMI_VISUAL_ENDPOINT_API2", "") or "").strip()
    vision_active = str(raw.get("KIMI_VISUAL_ENDPOINT_ACTIVE", "api1") or "api1").strip().lower()
    return {
        "status": "ok",
        "effective": masked,
        "active": {
            "director_backend": "lmstudio" if _truthy_config(raw.get("USE_LOCAL_DIRECTOR", "")) else "nvidia",
            "director_endpoint": director_api2 if director_active == "api2" and director_api2 else director_api1,
            "vision_endpoint": vision_api2 if vision_active == "api2" and vision_api2 else vision_api1,
            "comfy_primary": str(raw.get("COMFYUI_PRIMARY", "")).strip(),
            "comfy_secondary": str(raw.get("COMFYUI_SECONDARY", "")).strip(),
            "lmstudio_host": str(raw.get("LMSTUDIO_HOST", "")).strip(),
            "lmstudio_port": str(raw.get("LMSTUDIO_PORT", "") or "1234").strip() if str(raw.get("LMSTUDIO_HOST", "")).strip() else "",
        },
    }


class KimiTestRequest(BaseModel):
    api_key: str = ""
    endpoint: str = ""
    model: str = ""
    host: str = ""
    port: Any = ""
    use_local: Optional[bool] = None


def _director_test_target(cfg: Dict[str, Any], req: Optional[KimiTestRequest] = None, *, self_check: bool = False) -> Dict[str, Any]:
    use_local = _truthy_config(cfg.get("USE_LOCAL_DIRECTOR", ""))
    if req is not None and req.use_local is not None:
        use_local = bool(req.use_local)
    if use_local:
        host = req.host if req and req.host else str(cfg.get("LMSTUDIO_HOST", "") or "")
        port = req.port if req and req.port not in (None, "", 0, "0") else str(cfg.get("LMSTUDIO_PORT", "") or "")
        model = (
            (req.model if req and req.model else "")
            or str(cfg.get("LMSTUDIO_CHAT_MODEL", "") or "")
            or str(cfg.get("KIMI_THINKING_MODEL" if self_check else "KIMI_INSTRUCT_MODEL", "") or "")
        ).strip()
        return {
            "backend": "lmstudio",
            "endpoint": f"{_normalize_lmstudio_base_url(host, port)}/v1/chat/completions",
            "api_key": "",
            "model": model,
        }
    active = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_ACTIVE", "api1") or "api1").strip().lower()
    api1 = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API1", "") or cfg.get("NIM_ENDPOINT", "") or "").strip()
    api2 = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API2", "") or "").strip()
    endpoint = api2 if active == "api2" and api2 else api1
    if req is not None and req.endpoint:
        endpoint = req.endpoint
    model_key = "KIMI_THINKING_MODEL" if self_check else "KIMI_INSTRUCT_MODEL"
    return {
        "backend": "nvidia",
        "endpoint": endpoint,
        "api_key": (req.api_key if req and req.api_key else str(cfg.get("KIMI_API_KEY", "") or "")).strip(),
        "model": (req.model if req and req.model else str(cfg.get(model_key, "") or "")).strip(),
    }


async def _test_chat_completion(endpoint: str, api_key: str, model: str) -> Dict[str, Any]:
    endpoint = (endpoint or "").strip().rstrip("/")
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    if endpoint and not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/chat/completions"
    if not endpoint:
        return {"status": "error", "error": "missing endpoint"}
    if not model:
        return {"status": "error", "error": "missing model"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
        "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    t0 = time.time()
    try:
        timeout = httpx.Timeout(float(os.getenv("FORGE_PROVIDER_TEST_TIMEOUT_SEC", "75")), connect=8.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(endpoint, headers=headers, json=payload)
        if r.status_code >= 400:
            return {"status": "error", "error": f"http {r.status_code}: {r.text[:200]}", "endpoint": endpoint, "model": model}
        return {"status": "ok", "latency_ms": int((time.time() - t0) * 1000), "endpoint": endpoint, "model": model}
    except Exception as e:
        reason = str(e).strip() or e.__class__.__name__
        return {"status": "error", "error": reason, "endpoint": endpoint, "model": model}


def _sample_self_check_shots() -> List[Dict[str, Any]]:
    return [
        {
            "shot_id": "SHOT_001",
            "sequence": 1,
            "visual_brief": "Wide establishing shot of a founder entering a clean studio with a matte black product case on a white sweep.",
            "rationale": "Establishes geography, product presence, and restrained premium tone.",
            "constraints": "Keep product case geometry consistent; no logos invented.",
            "camera": "wide 24mm locked-off frame",
            "lighting_direction": "large soft key from camera left with subtle rim",
        },
        {
            "shot_id": "SHOT_002",
            "sequence": 2,
            "visual_brief": "Medium shot of the founder opening the case, revealing a compact silver device with one amber status light.",
            "rationale": "Introduces the hero object and hand interaction.",
            "constraints": "Same founder wardrobe, same product case, amber light only.",
            "camera": "medium 50mm over-table angle",
            "lighting_direction": "same soft key, controlled reflection on metal",
        },
        {
            "shot_id": "SHOT_003",
            "sequence": 3,
            "visual_brief": "Close-up insert of the device surface, showing brushed metal texture, clean seams, and the amber light reflected on the table.",
            "rationale": "Gives product detail coverage for edit emphasis.",
            "constraints": "No text, no extra buttons, no shape change.",
            "camera": "macro close-up",
            "lighting_direction": "soft specular highlight from camera left",
        },
        {
            "shot_id": "SHOT_004",
            "sequence": 4,
            "visual_brief": "Final hero frame with founder in soft focus behind the product, product centered and readable on the white sweep.",
            "rationale": "Creates final campaign image with clear product priority.",
            "constraints": "Preserve founder identity and product shape from prior shots.",
            "camera": "85mm shallow depth hero frame",
            "lighting_direction": "same soft key plus narrow rim on product edge",
        },
    ]


async def _test_director_self_check(endpoint: str, api_key: str, model: str) -> Dict[str, Any]:
    cfg = get_raw_config()
    endpoint = (
        endpoint
        or str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API1", "") or cfg.get("NIM_ENDPOINT", "") or "")
    ).strip().rstrip("/")
    if endpoint and not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    api_key = (api_key or str(cfg.get("KIMI_API_KEY", "") or "")).strip()
    model = (model or str(cfg.get("KIMI_THINKING_MODEL", "") or cfg.get("KIMI_INSTRUCT_MODEL", "") or "")).strip()
    if endpoint.startswith("https://") and not api_key:
        return {"status": "error", "error": "missing api key"}
    if not endpoint:
        return {"status": "error", "error": "missing endpoint"}
    if not model:
        return {"status": "error", "error": "missing model"}

    director = KimiDirectorService()
    director.endpoint = endpoint
    director.api_key = director._sanitize_api_key(api_key)
    director.model_name = model
    director.thinking_model_name = model
    if not api_key and not endpoint.startswith("https://"):
        director.use_local_director = True
        director.backend = "lmstudio"
    brief = (
        "Representative self-check test: four-shot premium product campaign in a clean studio. "
        "The critic should evaluate coverage, continuity, and renderability."
    )
    t0 = time.time()
    try:
        review = await director.self_check_plan(brief, f"settings_self_check_{uuid.uuid4().hex[:8]}", _sample_self_check_shots())
        return {
            "status": "ok",
            "latency_ms": int((time.time() - t0) * 1000),
            "endpoint": endpoint,
            "model": model,
            "score": review.get("score"),
            "review_status": review.get("status"),
            "director_notes": _short_text(str(review.get("director_notes") or ""), 300),
            "coverage_gaps": review.get("coverage_gaps", []),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e).strip() or e.__class__.__name__,
            "latency_ms": int((time.time() - t0) * 1000),
            "endpoint": endpoint,
            "model": model,
        }


async def _test_vision_completion(endpoint: str, api_key: str, model: str) -> Dict[str, Any]:
    endpoint = (endpoint or "").strip().rstrip("/")
    api_key = (api_key or "").strip()
    model = (model or "").strip()
    if endpoint and not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/chat/completions"
    if not endpoint:
        return {"status": "error", "error": "missing endpoint"}
    if not model:
        return {"status": "error", "error": "missing model"}
    def encode_vision_probe_image(path: Optional[Path] = None) -> tuple[str, str]:
        if path:
            with Image.open(path) as img:
                img.load()
                width, height = img.size
                if width > 224 and height > 224:
                    return base64.b64encode(path.read_bytes()).decode("utf-8"), _image_mime_type(str(path))
                scale = max(512 / max(width, 1), 512 / max(height, 1))
                resized = img.convert("RGB").resize((max(512, int(width * scale)), max(512, int(height * scale))))
        else:
            resized = Image.new("RGB", (512, 512), color=(28, 45, 72))
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8"), "image/png"

    image_b64 = ""
    mime_type = "image/png"
    for root in [MEDIA_IMAGES, MEDIA_ROOT / "imports", MEDIA_ROOT / "legacy"]:
        try:
            candidate = next(
                f for f in sorted(root.rglob("*"))
                if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            )
            image_b64, mime_type = encode_vision_probe_image(candidate)
            break
        except StopIteration:
            continue
        except Exception:
            continue
    if not image_b64:
        image_b64, mime_type = encode_vision_probe_image()
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "/no_think\nReturn JSON only: {\"ok\":true}."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": 64,
        "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
    }
    headers = {"Content-Type": "application/json"}
    if api_key and endpoint.startswith("https://"):
        headers["Authorization"] = f"Bearer {api_key}"
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(endpoint, headers=headers, json=payload)
        if r.status_code >= 400:
            return {"status": "error", "error": f"http {r.status_code}: {r.text[:300]}", "endpoint": endpoint, "model": model}
        return {"status": "ok", "latency_ms": int((time.time() - t0) * 1000), "endpoint": endpoint, "model": model}
    except Exception as e:
        reason = str(e).strip() or e.__class__.__name__
        return {"status": "error", "error": reason, "endpoint": endpoint, "model": model}


@app.post("/api/test/nous")
async def api_test_nous(req: KimiTestRequest):
    """Test connection to Nous Research Portal (or any OpenAI-compatible endpoint)."""
    cfg = get_raw_config()
    endpoint = (
        req.endpoint
        or str(cfg.get("NIM_ENDPOINT", "") or "")
        or str(cfg.get("NOUS_ENDPOINT", "") or "")
    ).strip().rstrip("/")
    if endpoint and not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/chat/completions"
    api_key = (req.api_key or str(cfg.get("KIMI_API_KEY", "") or "")).strip()
    model = str(req.model or cfg.get("KIMI_INSTRUCT_MODEL", "") or cfg.get("DIRECTOR_MODEL", "") or "").strip()
    if not endpoint:
        return {"status": "error", "error": "missing endpoint"}
    if not api_key:
        return {"status": "error", "error": "missing api key"}
    return await _test_chat_completion(endpoint, api_key, model)


@app.get("/api/test/director")
async def api_test_director():
    cfg = get_raw_config()
    target = _director_test_target(cfg)
    if target["endpoint"].startswith("https://") and not target["api_key"]:
        return {"status": "error", "error": "missing api key"}
    result = await _test_chat_completion(target["endpoint"], target["api_key"], target["model"])
    result["backend"] = target["backend"]
    return result


@app.post("/api/test/director")
async def api_test_director_post(req: KimiTestRequest):
    cfg = get_raw_config()
    target = _director_test_target(cfg, req)
    if target["endpoint"].startswith("https://") and not target["api_key"]:
        return {"status": "error", "error": "missing api key"}
    result = await _test_chat_completion(target["endpoint"], target["api_key"], target["model"])
    result["backend"] = target["backend"]
    return result


@app.get("/api/test/director-self-check")
async def api_test_director_self_check():
    cfg = get_raw_config()
    target = _director_test_target(cfg, self_check=True)
    result = await _test_director_self_check(target["endpoint"], target["api_key"], target["model"])
    result["backend"] = target["backend"]
    return result


@app.post("/api/test/director-self-check")
async def api_test_director_self_check_post(req: KimiTestRequest):
    cfg = get_raw_config()
    target = _director_test_target(cfg, req, self_check=True)
    result = await _test_director_self_check(target["endpoint"], target["api_key"], target["model"])
    result["backend"] = target["backend"]
    return result


@app.get("/api/test/vision")
async def api_test_vision():
    cfg = get_raw_config()
    active = str(cfg.get("KIMI_VISUAL_ENDPOINT_ACTIVE", "api1") or "api1").strip().lower()
    api1 = str(cfg.get("KIMI_VISUAL_ENDPOINT_API1", "") or cfg.get("NIM_ENDPOINT", "") or "").strip()
    api2 = str(cfg.get("KIMI_VISUAL_ENDPOINT_API2", "") or "").strip()
    endpoint = api2 if active == "api2" and api2 else api1
    api_key = str(cfg.get("KIMI_API_KEY", "") or "").strip()
    model = str(cfg.get("KIMI_VISUAL_MODEL", "") or "").strip()
    if endpoint.startswith("https://") and not api_key:
        return {"status": "error", "error": "missing api key"}
    return await _test_vision_completion(endpoint, api_key, model)


@app.post("/api/test/vision")
async def api_test_vision_post(req: KimiTestRequest):
    cfg = get_raw_config()
    endpoint = (req.endpoint or str(cfg.get("KIMI_VISUAL_ENDPOINT_API1", "") or cfg.get("NIM_ENDPOINT", "") or "")).strip()
    api_key = (req.api_key or str(cfg.get("KIMI_API_KEY", "") or "")).strip()
    model = (req.model or str(cfg.get("KIMI_VISUAL_MODEL", "") or cfg.get("LMSTUDIO_VISION_MODEL", "") or "")).strip()
    candidates: List[str] = []
    if endpoint:
        candidates.append(endpoint)
    for base in _lmstudio_base_candidates(req.host or str(cfg.get("LMSTUDIO_HOST", "") or ""), req.port or cfg.get("LMSTUDIO_PORT", "")):
        candidates.append(f"{base}/v1")
    deduped: List[str] = []
    seen = set()
    for candidate in candidates:
        normalized = candidate.strip().rstrip("/")
        if normalized and normalized not in seen:
            seen.add(normalized)
            deduped.append(normalized)
    errors: List[Dict[str, str]] = []
    for candidate in deduped:
        if candidate.startswith("https://") and not api_key:
            errors.append({"endpoint": candidate, "error": "missing api key"})
            continue
        result = await _test_vision_completion(candidate, api_key, model)
        if result.get("status") == "ok":
            result["attempted"] = deduped
            return result
        errors.append({"endpoint": result.get("endpoint", candidate), "error": str(result.get("error", "unknown error"))})
    return {
        "status": "error",
        "error": errors[-1]["error"] if errors else "missing endpoint",
        "attempted": deduped,
        "errors": errors,
        "model": model,
    }


@app.get("/api/test/lmstudio")
async def api_test_lmstudio(host: str = "", port: int = 0):
    bases = _lmstudio_base_candidates(host, port)
    t0 = time.time()
    errors: List[Dict[str, str]] = []
    for base in bases:
        url = f"{base}/v1/models"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                r = await client.get(url)
            if r.status_code >= 400:
                errors.append({"url": url, "error": f"http {r.status_code}: {r.text[:200]}"})
                continue
            data = r.json()
            models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
            return {"status": "ok", "base_url": base, "models": models, "latency_ms": int((time.time() - t0) * 1000), "message": f"{len(models)} model(s)", "attempted": bases}
        except Exception as e:
            errors.append({"url": url, "error": str(e).strip() or e.__class__.__name__})
    return {"status": "error", "error": errors[-1]["error"] if errors else "unreachable", "models": [], "attempted": bases, "errors": errors}


@app.get("/api/lmstudio/status")
async def api_lmstudio_status(host: str = "", port: int = 0):
    t0 = time.time()
    bases = _lmstudio_base_candidates(host, port)
    errors: List[Dict[str, str]] = []
    for base in bases:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                loaded_resp = await client.get(f"{base}/v1/models")
                available_resp = await client.get(f"{base}/api/v1/models")
            if loaded_resp.status_code >= 400:
                errors.append({"base_url": base, "error": f"http {loaded_resp.status_code}: {loaded_resp.text[:200]}"})
                continue
            loaded_data = loaded_resp.json()
            loaded = [m.get("id") for m in loaded_data.get("data", []) if isinstance(m, dict) and m.get("id")]
            available: List[Dict[str, Any]] = []
            if available_resp.status_code < 400:
                available_data = available_resp.json()
                available = [
                    {
                        "key": m.get("key"),
                        "display_name": m.get("display_name"),
                        "type": m.get("type"),
                        "vision": bool((m.get("capabilities") or {}).get("vision")),
                        "loaded_instances": m.get("loaded_instances") or [],
                    }
                    for m in available_data.get("models", [])
                    if isinstance(m, dict) and m.get("key")
                ]
            return {
                "status": "ok",
                "base_url": base,
                "attempted": bases,
                "loaded_models": loaded,
                "available_models": available,
                "loaded_count": len(loaded),
                "available_count": len(available),
                "hermes_usable": bool(loaded),
                "vision_usable": bool(loaded),
                "latency_ms": int((time.time() - t0) * 1000),
            }
        except Exception as e:
            errors.append({"base_url": base, "error": str(e).strip() or e.__class__.__name__})
    return {"status": "error", "error": errors[-1]["error"] if errors else "unreachable", "base_url": bases[0] if bases else "", "attempted": bases, "errors": errors}


@app.post("/api/lmstudio/load")
async def api_lmstudio_load(req: LMStudioLoadRequest):
    from core.bridge.runtime_config import set_config, apply_to_environment

    cfg = get_raw_config()
    model = (req.model or str(cfg.get("LMSTUDIO_CHAT_MODEL", "") or "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="LM Studio model is required")
    base = _normalize_lmstudio_base_url(req.host, req.port)
    payload = {
        "model": model,
        "echo_load_config": True,
    }
    t0 = time.time()
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(f"{base}/api/v1/models/load", headers={"Content-Type": "application/json"}, json=payload)
    if resp.status_code >= 400:
        return {"status": "error", "error": f"http {resp.status_code}: {resp.text[:500]}", "base_url": base, "model": model}
    data = resp.json()
    updates = {
        "LMSTUDIO_HOST": req.host or str(cfg.get("LMSTUDIO_HOST", "") or ""),
        "LMSTUDIO_PORT": str(req.port or cfg.get("LMSTUDIO_PORT", "") or "1234"),
        "LMSTUDIO_CHAT_MODEL": model,
        "LMSTUDIO_VISION_MODEL": model,
        "KIMI_VISUAL_MODEL": model,
    }
    set_config(updates)
    apply_to_environment()
    return {
        "status": "ok",
        "base_url": base,
        "model": model,
        "load_time_seconds": data.get("load_time_seconds"),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "lmstudio_response": data,
        "saved": sorted(updates.keys()),
    }


@app.get("/api/test/nim")
async def api_test_nim():
    """Test the saved NVIDIA/NIM-compatible Kimi config."""
    cfg = get_raw_config()
    endpoint = str(cfg.get("NIM_ENDPOINT", "") or "").strip().rstrip("/")
    if endpoint and not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/chat/completions"
    api_key = str(cfg.get("KIMI_API_KEY", "") or "").strip()
    model = str(cfg.get("KIMI_INSTRUCT_MODEL", "") or "").strip()
    if not endpoint:
        return {"status": "error", "error": "missing endpoint"}
    if not api_key:
        return {"status": "error", "error": "missing api key"}
    if not model:
        return {"status": "error", "error": "missing model"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
    }
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if r.status_code >= 400:
            return {"status": "error", "error": f"http {r.status_code}: {r.text[:200]}"}
        return {"status": "ok", "latency_ms": int((time.time() - t0) * 1000), "endpoint": endpoint, "model": model}
    except Exception as e:
        return {"status": "error", "error": str(e), "endpoint": endpoint}


@app.post("/api/restart")


@app.post("/api/restart")
async def api_restart():
    """Trigger graceful shutdown. Uvicorn should be running with --reload or managed by systemd."""
    import sys
    import threading

    def _delayed_exit():
        import time
        time.sleep(1)
        os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()
    return {"status": "restarting", "message": "Server will restart in 1 second"}


# --- Spark Stats ---

@app.get("/api/spark/stats")
async def api_spark_stats():
    import httpx
    from core.bridge.runtime_config import get_raw_config
    cfg = get_raw_config()
    host = (os.getenv("COMFYUI_PRIMARY", "") or str(cfg.get("COMFYUI_PRIMARY", "")) or "").rstrip("/")
    if not host:
        raise HTTPException(status_code=400, detail="COMFYUI_PRIMARY is not configured")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{host}/system_stats")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    system = data.get("system", {})
    devices = data.get("devices", [])
    gpu = devices[0] if devices else {}
    ram_total = system.get("ram_total", 0)
    ram_free = system.get("ram_free", 0)
    vram_total = gpu.get("vram_total", 0)
    vram_free = gpu.get("vram_free", 0)
    def gb(b): return round(b / 1024**3, 1)
    def pct(used, total): return round(used / total * 100) if total else 0
    vram_used = vram_total - vram_free
    ram_used = ram_total - ram_free
    return {
        "gpu_name": gpu.get("name", "Unknown"),
        "vram_used_gb": gb(vram_used), "vram_total_gb": gb(vram_total), "vram_pct": pct(vram_used, vram_total),
        "ram_used_gb": gb(ram_used), "ram_total_gb": gb(ram_total), "ram_pct": pct(ram_used, ram_total),
        "comfyui_version": system.get("comfyui_version", ""),
    }


# --- Character Generation & Rendering ---

_hermes_bridge = None

def _get_hermes_bridge():
    global _hermes_bridge
    if _hermes_bridge is None:
        from core.bridge.nous_hermes_bridge import NousHermesBridge
        _hermes_bridge = NousHermesBridge()
    return _hermes_bridge


# --- Character Store & /api/characters ---

CHARACTER_BANKS_DIR = Path(__file__).parent.parent / "data" / "character_banks"
CHARACTERS_ANCHORS_DIR = CHARACTER_BANKS_DIR / "anchors"
CHARACTERS_ANCHORS_DIR.mkdir(parents=True, exist_ok=True)

# In-memory character store — persisted to character_banks/*.json
# Keyed by character id (lowercase slug)
_CHARACTERS_STORE: Dict[str, Dict[str, Any]] = {}

CHARACTER_NO_TEXT_PROMPT_RULE = "no text, no captions, no labels, no typography, no letters, no numbers, no logos, no watermark"


def _with_character_no_text_rule(prompt: str) -> str:
    clean = re.sub(r"[,\s]+$", "", str(prompt or "").strip())
    if not clean:
        return CHARACTER_NO_TEXT_PROMPT_RULE
    lower = clean.lower()
    required = ["no text", "no captions", "no labels", "no typography", "no letters", "no numbers", "no logos", "no watermark"]
    if all(term in lower for term in required):
        return clean
    return f"{clean}, {CHARACTER_NO_TEXT_PROMPT_RULE}"


def _strip_character_no_text_rule(prompt: str) -> str:
    clean = str(prompt or "")
    for term in CHARACTER_NO_TEXT_PROMPT_RULE.split(", "):
        clean = re.sub(rf",?\s*{re.escape(term)}", "", clean, flags=re.IGNORECASE)
    return re.sub(r"\s*,\s*,", ", ", clean).strip(" ,")


def _character_slug(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', str(value or "").lower().strip()).strip('_')


def _empty_character_benchmark_suite() -> List[Dict[str, Any]]:
    return [
        {
            "id": "neutral_portrait",
            "label": "Neutral Portrait",
            "prompt": "neutral studio portrait, direct eye contact, even soft light, canonical hair and face",
            "goal": "face identity, age, hair, and skin detail remain stable",
        },
        {
            "id": "full_body_turnaround",
            "label": "Full Body Turnaround",
            "prompt": "full body production reference, front view, side view, rear view, neutral stance",
            "goal": "body proportions, silhouette, wardrobe anchors, and footwear remain stable",
        },
        {
            "id": "low_light_scene",
            "label": "Low Light Stress Test",
            "prompt": "cinematic low light interior, practical lamp, shallow depth of field, realistic shadows",
            "goal": "identity does not drift under difficult lighting",
        },
        {
            "id": "wardrobe_change",
            "label": "Wardrobe Change",
            "prompt": "same character in alternate wardrobe, face and body locked, clothing changed only",
            "goal": "outfit can change without changing face, age, or body",
        },
        {
            "id": "action_pose",
            "label": "Action Pose",
            "prompt": "dynamic walking action pose, three-quarter camera angle, natural motion, stable face",
            "goal": "pose changes without anatomy or identity collapse",
        },
        {
            "id": "multi_character_scene",
            "label": "Multi-Character Scene",
            "prompt": "same character standing beside a second character, clear spatial separation, no identity blending",
            "goal": "identity remains distinct in a multi-character composition",
        },
    ]


def _default_character_profile(char: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    cid = _character_slug(char.get("id") or char.get("name"))
    name = str(char.get("name") or cid.replace("_", " ").title()).strip()
    role = str(char.get("role") or char.get("description") or "Character").strip()
    anchor_url = str(char.get("anchor_url") or "")
    anchor_prompt = _with_character_no_text_rule(str(char.get("anchor_prompt") or f"Portrait of {name}, {role}"))
    master_references = char.get("master_references")
    if not isinstance(master_references, list):
        master_references = []
    if anchor_url and not any(ref.get("url") == anchor_url for ref in master_references if isinstance(ref, dict)):
        master_references.insert(0, {
            "id": "master_001",
            "url": anchor_url,
            "type": "face_closeup",
            "source": "anchor_url",
            "locked": True,
            "score": int(char.get("score") or 0),
            "created_at": str(char.get("created_at") or now),
        })
    dna = char.get("dna") if isinstance(char.get("dna"), dict) else {}
    visual_dna = char.get("visual_dna") if isinstance(char.get("visual_dna"), dict) else {}
    merged_visual_dna = {**dna, **visual_dna}
    profile = {
        "schema_version": 1,
        "status": char.get("status") or ("production_approved" if master_references else "draft"),
        "bio": char.get("bio") or char.get("description") or "",
        "personality_notes": char.get("personality_notes") or "",
        "visual_dna": merged_visual_dna,
        "voice_profile": char.get("voice_profile") or "",
        "gait_style": char.get("gait_style") or "",
        "master_references": master_references[:5],
        "reference_requirements": char.get("reference_requirements") or {
            "minimum_for_production": ["face_closeup", "full_body", "three_quarter", "neutral_expression"],
            "recommended": ["profile", "rear", "expression_sheet", "hands", "wardrobe_sheet", "motion_clip"],
        },
        "prompt_rules": char.get("prompt_rules") or {
            "positive_lock": "use the approved master references for identity, age, face, body proportions, hair, and signature traits",
            "negative_lock": CHARACTER_NO_TEXT_PROMPT_RULE + ", no identity drift, no duplicate person, no unintended age change",
            "inheritance": ["base_visual_dna", "master_references", "task_prompt", "workflow_settings", "negative_lock"],
        },
        "outfits": char.get("outfits") if isinstance(char.get("outfits"), list) else [],
        "approved_assets": char.get("approved_assets") if isinstance(char.get("approved_assets"), list) else [],
        "rejected_assets": char.get("rejected_assets") if isinstance(char.get("rejected_assets"), list) else [],
        "character_sheets": char.get("character_sheets") if isinstance(char.get("character_sheets"), list) else [],
        "sheet_panels": char.get("sheet_panels") if isinstance(char.get("sheet_panels"), list) else [],
        "version_history": char.get("version_history") if isinstance(char.get("version_history"), list) else [{
            "version": "v1",
            "label": "Initial profile",
            "created_at": str(char.get("created_at") or now),
            "notes": "Generated from legacy character record",
        }],
        "training": char.get("training") or {
            "status": "not_started",
            "lora_versions": [],
            "embedding_versions": [],
            "dataset_requirements": "10-50 approved images before training",
        },
        "quality_gate": char.get("quality_gate") or {
            "minimum_overall_score": 80,
            "minimum_face_score": 85,
            "minimum_body_score": 70,
            "auto_retry_below": 75,
            "human_approval_required": True,
        },
        "benchmark_suite": char.get("benchmark_suite") if isinstance(char.get("benchmark_suite"), list) else _empty_character_benchmark_suite(),
        "analytics": char.get("analytics") or {
            "used_in_shots": int(char.get("used_in_shots") or 0),
            "last_used_at": char.get("last_used_at") or "",
            "best_workflows": {},
            "consistency_trend": [],
        },
        "collaboration": char.get("collaboration") or {
            "comments": [],
            "approvals": [],
        },
    }
    return {**char, "id": cid, "name": name, "role": role, "anchor_prompt": anchor_prompt, **profile}


def _normalize_character(char_id: str, char: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _default_character_profile({**char, "id": char_id or char.get("id")})
    normalized["score"] = int(max(0, min(100, normalized.get("score") or _estimate_character_score(normalized))))
    normalized["consistency_score"] = normalized["score"]
    return normalized


def _estimate_character_score(char: Dict[str, Any]) -> int:
    refs = [r for r in char.get("master_references", []) if isinstance(r, dict) and r.get("url")]
    dna = char.get("visual_dna") if isinstance(char.get("visual_dna"), dict) else {}
    history = char.get("render_history") if isinstance(char.get("render_history"), list) else []
    score = 20
    score += min(35, len(refs) * 10)
    score += min(25, len(dna) * 3)
    score += min(10, len(history) * 2)
    if char.get("status") == "production_approved":
        score += 10
    return max(0, min(100, score))


def _persist_normalized_character(char_id: str, char_data: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_character(char_id, char_data)
    _CHARACTERS_STORE[char_id] = normalized
    _persist_character(char_id, normalized)
    return normalized

def _scan_character_files() -> None:
    """Scan character_banks for JSON character files and character images, merge into store."""
    for json_file in CHARACTER_BANKS_DIR.glob("*.json"):
        if json_file.name.startswith("demo_"):
            continue
        try:
            with open(json_file, "r") as f:
                data = json.load(f)
            chars = data if isinstance(data, list) else [data]
            for c in chars:
                cid = _character_slug(c.get("id") or c.get("name", ""))
                if cid and cid not in _CHARACTERS_STORE:
                    _CHARACTERS_STORE[cid] = _normalize_character(cid, c)
        except Exception:
            pass

    # Scan anchors dir for images, link them to existing characters or create stubs
    for img in CHARACTERS_ANCHORS_DIR.glob("*"):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        # Derive character id from filename: e.g. "elara_vance.jpg" -> "elara"
        stem = img.stem.lower()
        parts = re.split(r'[_\s-]+', stem)
        cid = stem if stem in _CHARACTERS_STORE else (parts[0] if parts and parts[0] in _CHARACTERS_STORE else stem)
        anchor_url = f"/api/characters/anchor/{stem}"
        if cid in _CHARACTERS_STORE:
            _CHARACTERS_STORE[cid]["anchor_url"] = anchor_url
            _CHARACTERS_STORE[cid] = _normalize_character(cid, _CHARACTERS_STORE[cid])
        elif cid:
            _CHARACTERS_STORE[cid] = _normalize_character(cid, {
                "id": cid,
                "name": stem.replace("_", " ").title(),
                "role": "Character",
                "accent": "cyan",
                "score": 0,
                "anchor_url": anchor_url,
                "anchor_prompt": "",
                "dna": {}
            })


def _persist_character(char_id: str, char_data: Dict[str, Any]) -> None:
    """Persist a character to a JSON file in character_banks."""
    out_path = CHARACTER_BANKS_DIR / f"char_{char_id}.json"
    with open(out_path, "w") as f:
        json.dump(char_data, f, indent=2)


_scan_character_files()


ASSET_VAULT_DIR = REPO_ROOT / "data" / "asset_vault"
ASSET_VAULT_PACKAGES_PATH = ASSET_VAULT_DIR / "packages.json"


def _asset_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower().strip()).strip("_")
    return slug[:80] or f"vault_{uuid.uuid4().hex[:8]}"


def _read_asset_vault_packages() -> List[Dict[str, Any]]:
    if not ASSET_VAULT_PACKAGES_PATH.exists():
        return []
    try:
        data = json.loads(ASSET_VAULT_PACKAGES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get("packages"), list):
            return [item for item in data["packages"] if isinstance(item, dict)]
    except Exception:
        return []
    return []


def _write_asset_vault_packages(packages: List[Dict[str, Any]]) -> None:
    ASSET_VAULT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ASSET_VAULT_PACKAGES_PATH.with_suffix(".json.tmp")
    stored = [_asset_vault_storage_package(pkg) for pkg in packages]
    tmp.write_text(json.dumps(stored, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp.replace(ASSET_VAULT_PACKAGES_PATH)


def _character_summary_for_vault(char_id: str) -> Optional[Dict[str, Any]]:
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        return None
    normalized = _normalize_character(cid, char)
    return {
        "id": normalized.get("id", cid),
        "name": normalized.get("name", cid.replace("_", " ").title()),
        "role": normalized.get("role", "Character"),
        "anchor_url": normalized.get("anchor_url", ""),
        "score": normalized.get("score", 0),
        "status": normalized.get("status", ""),
    }


def _normalize_vault_tags(tags: Any) -> List[str]:
    if isinstance(tags, str):
        raw = re.split(r"[,;\n]+", tags)
    elif isinstance(tags, list):
        raw = tags
    else:
        raw = []
    normalized: List[str] = []
    seen: set[str] = set()
    for tag in raw:
        value = re.sub(r"\s+", " ", str(tag or "").strip())
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value[:48])
    return normalized[:40]


def _normalize_vault_references(references: Any) -> List[Dict[str, Any]]:
    if not isinstance(references, list):
        return []
    normalized: List[Dict[str, Any]] = []
    for index, ref in enumerate(references):
        if not isinstance(ref, dict):
            continue
        ref_type = str(ref.get("type") or ref.get("asset_type") or "reference").strip().lower()
        if ref_type not in {"product", "logo", "font", "style", "prop", "location", "reference", "image", "brand"}:
            ref_type = "reference"
        name = _short_text(str(ref.get("name") or ref.get("title") or f"{ref_type.title()} {index + 1}"), 90)
        url = str(ref.get("url") or ref.get("image_url") or ref.get("anchor_url") or "").strip()
        prompt = _short_text(str(ref.get("prompt") or ref.get("description") or ref.get("notes") or ""), 360)
        normalized.append({
            "id": _asset_slug(str(ref.get("id") or f"{ref_type}_{name}_{index}")),
            "type": ref_type,
            "name": name,
            "url": url,
            "prompt": prompt,
            "notes": _short_text(str(ref.get("notes") or ""), 260),
        })
    return normalized[:80]


def _normalize_vault_character_refs(package: Dict[str, Any]) -> List[Dict[str, Any]]:
    refs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    raw_refs = package.get("character_refs") if isinstance(package.get("character_refs"), list) else []
    for ref in raw_refs:
        if not isinstance(ref, dict):
            continue
        cid = _character_slug(str(ref.get("id") or ref.get("character_id") or ""))
        if not cid or cid in seen:
            continue
        seen.add(cid)
        refs.append({
            "id": cid,
            "role": _short_text(str(ref.get("role") or "reference"), 48),
            "notes": _short_text(str(ref.get("notes") or ""), 240),
        })
    raw_ids = package.get("character_ids") if isinstance(package.get("character_ids"), list) else []
    for cid_raw in raw_ids:
        cid = _character_slug(str(cid_raw or ""))
        if not cid or cid in seen:
            continue
        seen.add(cid)
        refs.append({"id": cid, "role": "reference", "notes": ""})
    return refs[:40]


def _normalize_asset_vault_package(package: Dict[str, Any]) -> Dict[str, Any]:
    now = _now_iso()
    name = str(package.get("name") or package.get("title") or "Untitled Package").strip()
    package_id = _asset_slug(str(package.get("id") or name))
    character_refs = _normalize_vault_character_refs(package)
    character_ids = [ref["id"] for ref in character_refs]
    characters = []
    for ref in character_refs:
        summary = _character_summary_for_vault(ref["id"])
        if not summary:
            continue
        hydrated = dict(summary)
        hydrated["vault_role"] = ref.get("role", "reference")
        hydrated["vault_notes"] = ref.get("notes", "")
        characters.append(hydrated)
    return {
        "id": package_id,
        "name": name,
        "description": str(package.get("description") or "").strip(),
        "kind": str(package.get("kind") or "package").strip() or "package",
        "element_type": str(package.get("element_type") or "product").strip() or "product",
        "asset_type": str(package.get("asset_type") or package.get("element_type") or "product").strip() or "product",
        "character_ids": character_ids,
        "character_refs": character_refs,
        "characters": characters,
        "references": _normalize_vault_references(package.get("references")),
        "tags": _normalize_vault_tags(package.get("tags")),
        "notes": str(package.get("notes") or "").strip(),
        "brand_rules": str(package.get("brand_rules") or "").strip(),
        "style_rules": str(package.get("style_rules") or "").strip(),
        "logo_notes": str(package.get("logo_notes") or "").strip(),
        "font_notes": str(package.get("font_notes") or "").strip(),
        "prop_notes": str(package.get("prop_notes") or "").strip(),
        "location_notes": str(package.get("location_notes") or "").strip(),
        "status": str(package.get("status") or "draft").strip() or "draft",
        "created_at": str(package.get("created_at") or now),
        "updated_at": str(package.get("updated_at") or now),
    }


def _asset_vault_storage_package(package: Dict[str, Any]) -> Dict[str, Any]:
    stored = _normalize_asset_vault_package(package)
    stored.pop("characters", None)
    return stored


def _list_asset_vault_packages() -> List[Dict[str, Any]]:
    return [_normalize_asset_vault_package(pkg) for pkg in _read_asset_vault_packages()]


def _asset_vault_package_by_id(package_id: str) -> Optional[Dict[str, Any]]:
    pid = _asset_slug(package_id)
    for package in _list_asset_vault_packages():
        if package.get("id") == pid:
            return package
    return None


def _asset_vault_request_payload(req: AssetVaultPackageRequest, existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = dict(existing or {})
    payload.update({
        "name": req.name,
        "description": req.description,
        "kind": req.kind,
        "element_type": req.element_type,
        "asset_type": req.asset_type,
        "character_ids": req.character_ids,
        "character_refs": req.character_refs,
        "references": req.references,
        "tags": req.tags,
        "notes": req.notes,
        "brand_rules": req.brand_rules,
        "style_rules": req.style_rules,
        "logo_notes": req.logo_notes,
        "font_notes": req.font_notes,
        "prop_notes": req.prop_notes,
        "location_notes": req.location_notes,
        "status": req.status,
        "updated_at": _now_iso(),
    })
    if existing and existing.get("id"):
        payload["id"] = existing["id"]
        payload["created_at"] = existing.get("created_at") or payload["updated_at"]
    return payload


@app.get("/api/characters")
async def api_get_characters():
    """Return the full character list from the store."""
    return [_normalize_character(cid, char) for cid, char in _CHARACTERS_STORE.items()]


@app.get("/api/characters/{char_id}/profile")
async def api_get_character_profile(char_id: str):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    normalized = _normalize_character(cid, char)
    _CHARACTERS_STORE[cid] = normalized
    return normalized


@app.get("/api/characters/{char_id}/variations")
async def api_get_character_variations(char_id: str):
    """Return variations for a character. Scans renders dir for matching character tags."""
    repo_root = Path(__file__).parent.parent
    renders_dir = repo_root / "data" / "renders"
    variations = []
    if renders_dir.exists():
        char_slug = char_id.lower()
        for f in sorted(renders_dir.iterdir()):
            if f.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
                continue
            # Check if this render is associated with the character
            meta_path = f.with_suffix(f.suffix + ".json")
            if meta_path.exists():
                try:
                    with open(meta_path) as mf:
                        meta = json.load(mf)
                    if char_slug in str(meta.get("chars", [])).lower() or char_slug in meta.get("prompt", "").lower():
                        variations.append({
                            "id": f.stem,
                            "src": "/renders/" + f.name,
                            "type": meta.get("type", "pose"),
                            "score": meta.get("score", 0),
                            "seed": meta.get("seed", 0),
                            "prompt": meta.get("prompt", "")
                        })
                except Exception:
                    pass
    return variations


@app.get("/api/characters/{char_id}/export")
async def api_export_character(char_id: str):
    """Export a character's full DNA as JSON."""
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    return _normalize_character(cid, char)


class SaveDNARequest(BaseModel):
    id: str
    dna: Dict[str, Any]


class CharacterProfilePatchRequest(BaseModel):
    status: Optional[str] = None
    bio: Optional[str] = None
    personality_notes: Optional[str] = None
    visual_dna: Optional[Dict[str, Any]] = None
    voice_profile: Optional[str] = None
    gait_style: Optional[str] = None
    prompt_rules: Optional[Dict[str, Any]] = None
    outfits: Optional[List[Dict[str, Any]]] = None
    quality_gate: Optional[Dict[str, Any]] = None
    analytics: Optional[Dict[str, Any]] = None
    collaboration: Optional[Dict[str, Any]] = None


class MasterReferenceRequest(BaseModel):
    url: str
    type: str = "face_closeup"
    source: str = "manual"
    score: Optional[int] = None
    prompt_id: Optional[str] = None
    notes: str = ""


class CharacterAuditRequest(BaseModel):
    image_url: str = ""
    prompt: str = ""
    render_type: str = "character"
    workflow_id: str = ""
    seed: Optional[int] = None


class CharacterSheetExtractRequest(BaseModel):
    image_url: str
    rows: int = 2
    columns: int = 4
    panel_types: List[str] = []
    make_master: bool = False
    source_prompt_id: str = ""
    notes: str = ""


class CharacterLoraPackRequest(BaseModel):
    trigger_token: str = ""
    notes: str = ""


CHARACTER_SHEET_PANEL_TYPES = [
    "front_full_body",
    "three_quarter_left",
    "three_quarter_right",
    "side_profile",
    "rear_full_body",
    "portrait_closeup",
    "hands_detail",
    "footwear_detail",
    "neutral_expression",
    "smile_expression",
    "serious_expression",
    "outfit_detail",
    "side_full_body",
    "back_detail",
    "action_pose",
    "lighting_variant",
]


@app.post("/api/characters/save-dna")
async def api_save_character_dna(req: SaveDNARequest):
    """Persist updated character DNA to disk."""
    cid = _character_slug(req.id)
    if cid in _CHARACTERS_STORE:
        _CHARACTERS_STORE[cid]["dna"] = req.dna
        _CHARACTERS_STORE[cid]["visual_dna"] = {**(_CHARACTERS_STORE[cid].get("visual_dna") or {}), **req.dna}
        _persist_normalized_character(cid, _CHARACTERS_STORE[cid])
        return {"status": "saved", "message": f"DNA saved for {cid}"}
    else:
        # Create new character entry
        new_char = {
            "id": cid,
            "name": cid.upper(),
            "role": "Character",
            "accent": "cyan",
            "score": 0,
            "anchor_url": "",
            "anchor_prompt": "",
            "dna": req.dna
        }
        _persist_normalized_character(cid, new_char)
        return {"status": "created", "message": f"Character {cid} created with DNA"}


@app.patch("/api/characters/{char_id}/profile")
async def api_patch_character_profile(char_id: str, req: CharacterProfilePatchRequest):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    updates = req.model_dump(exclude_unset=True) if hasattr(req, "model_dump") else req.dict(exclude_unset=True)
    if "visual_dna" in updates and isinstance(updates["visual_dna"], dict):
        updates["dna"] = {**(char.get("dna") if isinstance(char.get("dna"), dict) else {}), **updates["visual_dna"]}
    char.update(updates)
    char.setdefault("version_history", []).append({
        "version": f"v{len(char.get('version_history') or []) + 1}",
        "label": "Profile update",
        "created_at": _now_iso(),
        "notes": "Updated character profile fields",
    })
    return _persist_normalized_character(cid, char)


@app.post("/api/characters/{char_id}/master-reference")
async def api_add_character_master_reference(char_id: str, req: MasterReferenceRequest):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    normalized = _normalize_character(cid, char)
    refs = [r for r in normalized.get("master_references", []) if isinstance(r, dict)]
    refs = [r for r in refs if r.get("url") != req.url]
    refs.insert(0, {
        "id": f"master_{int(time.time())}",
        "url": req.url,
        "type": req.type or "face_closeup",
        "source": req.source or "manual",
        "locked": True,
        "score": int(req.score if req.score is not None else normalized.get("score") or 0),
        "prompt_id": req.prompt_id or "",
        "notes": req.notes or "",
        "created_at": _now_iso(),
    })
    normalized["master_references"] = refs[:5]
    normalized["status"] = "production_approved" if len(normalized["master_references"]) >= 3 else normalized.get("status", "draft")
    if req.url:
        normalized["anchor_url"] = req.url
    return _persist_normalized_character(cid, normalized)


@app.post("/api/characters/{char_id}/references")
async def api_upload_character_reference(
    char_id: str,
    reference_image: UploadFile = File(...),
    reference_type: str = Form("auto"),
    notes: str = Form(""),
):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    ext = Path(reference_image.filename or "").suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"):
        raise HTTPException(status_code=400, detail="Unsupported reference file type")
    inferred = reference_type if reference_type and reference_type != "auto" else _infer_reference_type(reference_image.filename or "")
    ref_dir = CHARACTER_BANKS_DIR / "references" / cid
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_id = f"{inferred}_{int(time.time())}"
    dest = ref_dir / f"{ref_id}{ext}"
    dest.write_bytes(await reference_image.read())
    url = f"/api/characters/reference/{cid}/{dest.name}"
    normalized = _normalize_character(cid, char)
    normalized.setdefault("reference_uploads", []).append({
        "id": ref_id,
        "url": url,
        "type": inferred,
        "source": "upload",
        "notes": notes,
        "created_at": _now_iso(),
    })
    if not normalized.get("anchor_url") and ext in (".jpg", ".jpeg", ".png", ".webp"):
        normalized["anchor_url"] = url
    return _persist_normalized_character(cid, normalized)


def _character_reference_url(cid: str, filename: str) -> str:
    return f"/api/characters/reference/{cid}/{filename}"


def _sheet_panel_type(index: int, custom_types: List[str]) -> str:
    if index < len(custom_types):
        explicit = _character_slug(custom_types[index])
        if explicit:
            return explicit
    if index < len(CHARACTER_SHEET_PANEL_TYPES):
        return CHARACTER_SHEET_PANEL_TYPES[index]
    return f"panel_{index + 1:02d}"


@app.post("/api/characters/{char_id}/sheet-panels")
async def api_extract_character_sheet_panels(char_id: str, req: CharacterSheetExtractRequest):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    source_path = _resolve_image_path(req.image_url)
    if not source_path or not source_path.exists():
        raise HTTPException(status_code=404, detail="Character sheet image could not be resolved locally")
    if source_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(status_code=400, detail="Character sheet must be an image file")

    rows = max(1, min(int(req.rows or 2), 4))
    columns = max(1, min(int(req.columns or 4), 4))
    max_panels = rows * columns
    ref_dir = CHARACTER_BANKS_DIR / "references" / cid
    ref_dir.mkdir(parents=True, exist_ok=True)
    extracted_at = _now_iso()
    stamp = str(int(time.time()))
    panel_records: List[Dict[str, Any]] = []

    with Image.open(source_path) as source:
        image = source.convert("RGB")
        width, height = image.size
        cell_w = width // columns
        cell_h = height // rows
        if cell_w < 32 or cell_h < 32:
            raise HTTPException(status_code=400, detail="Sheet grid cells are too small to extract useful references")
        for row in range(rows):
            for col in range(columns):
                index = row * columns + col
                if index >= max_panels:
                    break
                left = col * cell_w
                top = row * cell_h
                right = width if col == columns - 1 else (col + 1) * cell_w
                bottom = height if row == rows - 1 else (row + 1) * cell_h
                inset_x = max(0, int((right - left) * 0.015))
                inset_y = max(0, int((bottom - top) * 0.015))
                crop_box = (left + inset_x, top + inset_y, right - inset_x, bottom - inset_y)
                panel_type = _sheet_panel_type(index, req.panel_types or [])
                panel = image.crop(crop_box)
                filename = f"sheet_{stamp}_{index + 1:02d}_{panel_type}.png"
                dest = ref_dir / filename
                panel.save(dest, format="PNG")
                url = _character_reference_url(cid, filename)
                panel_records.append({
                    "id": f"sheet_{stamp}_{index + 1:02d}",
                    "url": url,
                    "type": panel_type,
                    "source": "sheet_extract",
                    "source_image_url": req.image_url,
                    "source_prompt_id": req.source_prompt_id or "",
                    "panel_index": index,
                    "row": row,
                    "column": col,
                    "bbox": list(crop_box),
                    "notes": req.notes or "extracted from character sheet",
                    "created_at": extracted_at,
                })

    normalized = _normalize_character(cid, char)
    existing_uploads = [r for r in normalized.get("reference_uploads", []) if isinstance(r, dict)]
    existing_panels = [r for r in normalized.get("sheet_panels", []) if isinstance(r, dict)]
    normalized["reference_uploads"] = existing_uploads + panel_records
    normalized["sheet_panels"] = existing_panels + panel_records
    normalized.setdefault("character_sheets", []).append({
        "id": f"sheet_{stamp}",
        "url": req.image_url,
        "source_path": str(source_path),
        "rows": rows,
        "columns": columns,
        "panel_count": len(panel_records),
        "panel_ids": [p["id"] for p in panel_records],
        "source_prompt_id": req.source_prompt_id or "",
        "created_at": extracted_at,
    })
    if req.make_master:
        master_refs = [r for r in normalized.get("master_references", []) if isinstance(r, dict)]
        master_types = {"face_closeup", "portrait_closeup", "front_full_body", "three_quarter_left", "side_profile"}
        for panel in panel_records:
            if len(master_refs) >= 5:
                break
            if panel["type"] in master_types and not any(r.get("url") == panel["url"] for r in master_refs):
                master_refs.append({
                    "id": f"master_{panel['id']}",
                    "url": panel["url"],
                    "type": panel["type"],
                    "source": "sheet_extract",
                    "locked": True,
                    "score": int(normalized.get("score") or 0),
                    "prompt_id": req.source_prompt_id or "",
                    "notes": "promoted from extracted character sheet panel",
                    "created_at": extracted_at,
                })
        normalized["master_references"] = master_refs[:5]
        if not normalized.get("anchor_url") and master_refs:
            normalized["anchor_url"] = master_refs[0].get("url", "")
    saved = _persist_normalized_character(cid, normalized)
    return {
        "status": "ok",
        "character": saved,
        "sheet_url": req.image_url,
        "rows": rows,
        "columns": columns,
        "panels": panel_records,
    }


def _infer_reference_type(filename: str) -> str:
    lower = filename.lower()
    if any(token in lower for token in ["face", "head", "close"]):
        return "face_closeup"
    if any(token in lower for token in ["full", "body", "turnaround"]):
        return "full_body"
    if any(token in lower for token in ["outfit", "wardrobe", "costume"]):
        return "outfit"
    if any(token in lower for token in ["expression", "emotion"]):
        return "expression_sheet"
    if any(token in lower for token in ["motion", "walk", "video"]):
        return "motion_clip"
    if any(token in lower for token in ["pose", "openpose"]):
        return "pose"
    return "reference"


def _character_lora_trigger_token(cid: str, raw: str = "") -> str:
    token = _character_slug(raw or f"{cid}_char")
    if not token:
        token = f"{cid}_char"
    if not token.endswith("_char"):
        token = f"{token}_char"
    return token


def _collect_character_lora_sources(char: Dict[str, Any]) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def add(url: Any, source: str, ref_type: str = "reference", meta: Optional[Dict[str, Any]] = None) -> None:
        clean = str(url or "").strip()
        if not clean or clean in seen:
            return
        if re.search(r"\.(mp4|mov|webm)(\?|$)", clean, flags=re.IGNORECASE):
            return
        seen.add(clean)
        sources.append({
            "url": clean,
            "source": source,
            "type": ref_type or "reference",
            "meta": meta or {},
        })

    add(char.get("anchor_url"), "anchor_url", "anchor")
    for key, source in [
        ("master_references", "master_reference"),
        ("reference_uploads", "reference_upload"),
        ("sheet_panels", "sheet_panel"),
        ("character_sheets", "character_sheet"),
        ("approved_assets", "approved_asset"),
    ]:
        refs = char.get(key) if isinstance(char.get(key), list) else []
        for ref in refs:
            if isinstance(ref, dict):
                add(ref.get("url") or ref.get("image_url"), source, str(ref.get("type") or key), ref)
            else:
                add(ref, source, key)

    render_history = char.get("render_history") if isinstance(char.get("render_history"), list) else []
    for entry in render_history:
        if not isinstance(entry, dict):
            continue
        for image_url in entry.get("image_urls") if isinstance(entry.get("image_urls"), list) else []:
            add(image_url, "render_history", str(entry.get("type") or "render"), entry)

    return sources


@app.post("/api/characters/{char_id}/lora-pack")
async def api_prepare_character_lora_pack(char_id: str, req: CharacterLoraPackRequest):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")

    normalized = _normalize_character(cid, char)
    trigger_token = _character_lora_trigger_token(cid, req.trigger_token)
    pack_id = f"{cid}_lora_{int(time.time())}"
    pack_dir = CHARACTER_BANKS_DIR / "lora_packs" / cid / pack_id
    images_dir = pack_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    source_records = _collect_character_lora_sources(normalized)
    image_records: List[Dict[str, Any]] = []
    unresolved_records: List[Dict[str, Any]] = []
    caption_lines: List[str] = []

    for index, source in enumerate(source_records, start=1):
        resolved = _resolve_image_path(source["url"])
        if not resolved or not resolved.exists() or resolved.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            unresolved_records.append(source)
            continue
        suffix = resolved.suffix.lower()
        dest_name = f"{index:03d}_{_character_slug(source.get('type') or 'reference')}{suffix}"
        dest_path = images_dir / dest_name
        shutil.copy2(resolved, dest_path)
        caption = ", ".join([
            trigger_token,
            normalized.get("name", cid),
            normalized.get("role", "character"),
            source.get("type", "reference"),
            "same identity, consistent face, consistent body proportions, realistic skin texture",
        ])
        record = {
            "file_name": f"images/{dest_name}",
            "source_url": source["url"],
            "source": source["source"],
            "type": source.get("type", "reference"),
            "caption": caption,
        }
        image_records.append(record)
        caption_lines.append(json.dumps(record, ensure_ascii=False))

    ready_for_training = len(image_records) >= 10
    trainer_status = "not_configured"
    manifest = {
        "schema_version": 1,
        "pack_id": pack_id,
        "created_at": _now_iso(),
        "character_id": cid,
        "character_name": normalized.get("name", cid),
        "role": normalized.get("role", "Character"),
        "trigger_token": trigger_token,
        "ready_for_training": ready_for_training,
        "trainer_status": trainer_status,
        "minimum_recommended_images": 10,
        "target_recommended_images": 30,
        "image_count": len(image_records),
        "images": image_records,
        "unresolved_sources": unresolved_records,
        "base_prompt": normalized.get("anchor_prompt", ""),
        "negative_prompt": (normalized.get("prompt_rules") or {}).get("negative_lock", CHARACTER_NO_TEXT_PROMPT_RULE),
        "notes": req.notes or "",
        "training_note": "Dataset package prepared only. No local FLUX2 LoRA trainer is configured in this app yet.",
    }
    manifest_path = pack_dir / "manifest.json"
    captions_path = pack_dir / "captions.jsonl"
    readme_path = pack_dir / "README.txt"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    captions_path.write_text("\n".join(caption_lines) + ("\n" if caption_lines else ""), encoding="utf-8")
    readme_path.write_text(
        "\n".join([
            f"Character LoRA dataset pack: {pack_id}",
            f"Character: {normalized.get('name', cid)}",
            f"Trigger token: {trigger_token}",
            f"Image count: {len(image_records)}",
            f"Ready for training: {ready_for_training}",
            "",
            "Use manifest.json and captions.jsonl with a FLUX2-compatible LoRA trainer.",
            "This app currently prepares the dataset package; it does not launch a trainer.",
        ]),
        encoding="utf-8",
    )

    lora_version = {
        "id": pack_id,
        "status": "dataset_ready" if ready_for_training else "needs_more_references",
        "created_at": manifest["created_at"],
        "trigger_token": trigger_token,
        "image_count": len(image_records),
        "minimum_recommended_images": 10,
        "ready_for_training": ready_for_training,
        "trainer_status": trainer_status,
        "pack_path": str(pack_dir),
        "manifest_path": str(manifest_path),
        "notes": req.notes or "Prepared from character references",
    }
    training = normalized.get("training") if isinstance(normalized.get("training"), dict) else {}
    versions = training.get("lora_versions") if isinstance(training.get("lora_versions"), list) else []
    training.update({
        "status": lora_version["status"],
        "latest_lora_pack": pack_id,
        "lora_versions": [lora_version] + versions,
        "dataset_requirements": "10-50 approved images before training",
    })
    normalized["training"] = training
    saved = _persist_normalized_character(cid, normalized)

    return {
        "status": lora_version["status"],
        "character_id": cid,
        "trigger_token": trigger_token,
        "pack_id": pack_id,
        "pack_path": str(pack_dir),
        "manifest_path": str(manifest_path),
        "captions_path": str(captions_path),
        "image_count": len(image_records),
        "ready_for_training": ready_for_training,
        "trainer_status": trainer_status,
        "lora_version": lora_version,
        "character": saved,
        "unresolved_count": len(unresolved_records),
    }


@app.get("/api/characters/reference/{char_id}/{filename}")
async def api_character_reference_file(char_id: str, filename: str):
    cid = _character_slug(char_id)
    safe_filename = Path(filename).name
    ref_path = CHARACTER_BANKS_DIR / "references" / cid / safe_filename
    if ref_path.exists():
        return FileResponse(str(ref_path))
    raise HTTPException(status_code=404, detail="Reference not found")


@app.post("/api/characters/{char_id}/audit")
async def api_audit_character_generation(char_id: str, req: CharacterAuditRequest):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    normalized = _normalize_character(cid, char)
    refs = normalized.get("master_references") or []
    prompt = (req.prompt or "").lower()
    visual_terms = " ".join(str(v).lower() for v in (normalized.get("visual_dna") or {}).values())
    prompt_overlap = sum(1 for token in re.findall(r"[a-z0-9]{4,}", visual_terms) if token in prompt)
    face_score = min(100, 45 + len(refs) * 12 + prompt_overlap * 3)
    body_score = min(100, 45 + (10 if "full body" in prompt or "body" in prompt else 0) + len(refs) * 8)
    wardrobe_score = min(100, 50 + (15 if any(w in prompt for w in ["wardrobe", "outfit", "clothes", "costume"]) else 0))
    prompt_score = 90 if CHARACTER_NO_TEXT_PROMPT_RULE in _with_character_no_text_rule(req.prompt).lower() else 65
    overall = int(round((face_score * 0.4) + (body_score * 0.2) + (wardrobe_score * 0.15) + (prompt_score * 0.25)))
    fail_reasons = []
    gate = normalized.get("quality_gate") or {}
    if face_score < int(gate.get("minimum_face_score", 85)):
        fail_reasons.append("face identity confidence below threshold")
    if body_score < int(gate.get("minimum_body_score", 70)):
        fail_reasons.append("body/proportion lock below threshold")
    if "text" not in prompt:
        fail_reasons.append("prompt lacked explicit no-text guardrail before compilation")
    audit = {
        "status": "pass" if overall >= int(gate.get("minimum_overall_score", 80)) and not fail_reasons else "needs_review",
        "overall_score": overall,
        "face_score": int(face_score),
        "body_score": int(body_score),
        "wardrobe_score": int(wardrobe_score),
        "prompt_score": int(prompt_score),
        "fail_reasons": fail_reasons,
        "image_url": req.image_url,
        "render_type": req.render_type,
        "workflow_id": req.workflow_id,
        "seed": req.seed,
        "created_at": _now_iso(),
        "note": "Heuristic audit scaffold; replace with embedding/vision scoring when those services are wired.",
    }
    normalized.setdefault("audit_history", []).append(audit)
    normalized["score"] = overall
    _persist_normalized_character(cid, normalized)
    return audit


@app.get("/api/characters/{char_id}/benchmarks")
async def api_get_character_benchmarks(char_id: str):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    normalized = _normalize_character(cid, char)
    base = normalized.get("anchor_prompt") or normalized.get("name", cid)
    return {
        "character_id": cid,
        "benchmarks": [
            {
                **bench,
                "compiled_prompt": _with_character_no_text_rule(f"{base}, {bench.get('prompt', '')}"),
            }
            for bench in normalized.get("benchmark_suite", [])
        ],
    }


@app.get("/api/characters/{char_id}/export-package")
async def api_export_character_package(char_id: str):
    cid = _character_slug(char_id)
    char = _CHARACTERS_STORE.get(cid)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    normalized = _normalize_character(cid, char)
    return {
        "package_version": 1,
        "exported_at": _now_iso(),
        "character": normalized,
        "references": normalized.get("master_references", []) + normalized.get("reference_uploads", []),
        "character_sheets": normalized.get("character_sheets", []),
        "sheet_panels": normalized.get("sheet_panels", []),
        "prompts": {
            "base": normalized.get("anchor_prompt", ""),
            "negative": (normalized.get("prompt_rules") or {}).get("negative_lock", CHARACTER_NO_TEXT_PROMPT_RULE),
            "benchmarks": [
                _with_character_no_text_rule(f"{normalized.get('anchor_prompt', normalized.get('name', cid))}, {bench.get('prompt', '')}")
                for bench in normalized.get("benchmark_suite", [])
            ],
        },
        "training": normalized.get("training", {}),
        "quality_gate": normalized.get("quality_gate", {}),
        "lineage": normalized.get("render_history", []),
    }


class GenerateCharacterRequest(BaseModel):
    name: Optional[str] = None
    description: str


@app.post("/api/hermes/generate-character")
async def api_generate_character(req: GenerateCharacterRequest):
    bridge = _get_hermes_bridge()
    if not bridge.is_available:
        raise HTTPException(status_code=503, detail="Hermes (LM Studio) is offline")
    result = await bridge.generate_character(req.description)
    if not result:
        raise HTTPException(status_code=500, detail="Hermes failed to generate character")
    # Persist generated character to store
    cid = _character_slug(req.name or result.get("name", "unknown"))
    char_entry = {
        "id": cid,
        "name": (req.name or result.get("name", "Unknown")).upper(),
        "role": result.get("role", "Character"),
        "accent": result.get("accent", "cyan"),
        "score": result.get("score", 0),
        "anchor_url": "",
        "anchor_prompt": result.get("anchor_prompt", req.description),
        "dna": result.get("dna", result.get("visual_traits", {}))
    }
    _persist_normalized_character(cid, char_entry)
    return result


class RenderCharacterRequest(BaseModel):
    name: str
    prompt: str
    seed: Optional[int] = None


class CharacterSparkRenderRequest(BaseModel):
    name: str
    prompt: str
    role: Optional[str] = ""
    render_type: str = "character"  # character | sheet | variation
    workflow_id: str = "01_flux2_text_to_image"
    seed: Optional[int] = None
    save_character: bool = True
    character_id: Optional[str] = ""
    reference_image_url: Optional[str] = ""
    reference_image_urls: List[str] = Field(default_factory=list)


class CharacterRolePromptRequest(BaseModel):
    role: str
    name: Optional[str] = ""
    gender: Optional[str] = ""


def _configured_kimi_director() -> Dict[str, str]:
    cfg = get_raw_config()
    active = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_ACTIVE", "api1") or "api1").strip().lower()
    endpoint = ""
    if active == "api2":
        endpoint = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API2", "") or "").strip()
    if not endpoint:
        endpoint = str(
            cfg.get("KIMI_DIRECTOR_ENDPOINT_API1", "")
            or cfg.get("KIMI_ENDPOINT", "")
            or cfg.get("NIM_ENDPOINT", "")
            or ""
        ).strip()
    if endpoint and not endpoint.rstrip("/").endswith("/chat/completions"):
        endpoint = endpoint.rstrip("/") + "/chat/completions"
    return {
        "endpoint": endpoint,
        "api_key": str(cfg.get("KIMI_API_KEY", "") or os.getenv("KIMI_API_KEY", "") or "").strip(),
        "model": str(cfg.get("KIMI_INSTRUCT_MODEL", "") or os.getenv("KIMI_INSTRUCT_MODEL", "") or "moonshotai/kimi-k2.6").strip(),
    }


def _extract_json_object(text: str) -> Dict[str, Any]:
    clean = (text or "").strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE).strip()
    clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        parsed = json.loads(clean)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        start = clean.find("{")
        end = clean.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(clean[start:end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except Exception:
                return {}
    return {}


def _clean_string_list(value: Any, fallback: List[str], limit: int = 8) -> List[str]:
    if isinstance(value, str):
        parts = [p.strip() for p in re.split(r"[,;\n]+", value) if p.strip()]
    elif isinstance(value, list):
        parts = [str(p).strip() for p in value if str(p).strip()]
    else:
        parts = []
    return (parts or fallback)[:limit]


@app.post("/api/characters/role-prompt")
async def api_character_role_prompt(req: CharacterRolePromptRequest):
    role = (req.role or "").strip()
    if not role:
        raise HTTPException(status_code=400, detail="role is required")
    gender = (req.gender or "").strip().lower()
    if gender not in {"male", "female"}:
        gender = ""

    director = _configured_kimi_director()
    endpoint = director["endpoint"]
    api_key = director["api_key"]
    model = director["model"]
    if not endpoint:
        raise HTTPException(status_code=503, detail="Kimi endpoint is not configured")
    if endpoint.startswith("https://") and not api_key:
        raise HTTPException(status_code=503, detail="Kimi API key is not configured")
    if not model:
        raise HTTPException(status_code=503, detail="Kimi model is not configured")

    system_prompt = (
        "You are Forge NPS Character Casting Director. Return only strict JSON. "
        "Design a realistic adult character prompt plan for image generation. "
        "Reason from the requested role instead of randomizing incompatible ages, wardrobe, locations, or body type. "
        "When the role implies attractiveness, modeling, fitness, celebrity, or influencer work, make the person attractive and camera-ready while realistic. "
        "Never include captions, labels, typography, letters, numbers, logos, watermarks, or visible text in normal image prompts. "
        "Character sheet prompts must default to a no-text 3840x2160 horizontal 16:9 reference layout with exactly six large sharp panels, not a square grid. "
        "Apply the flux-ltx-prompt-engineering-standard: concrete materiality, optical capture details, named light source, and positive anti-smoothness details."
    )
    user_prompt = f"""
Role / archetype: {role}
Existing name, if any: {(req.name or '').strip() or 'none'}
Gender selection: {gender or 'unspecified'}

Return JSON with this exact shape:
{{
  "name": "realistic full name",
  "role": "cleaned role",
  "age": "specific adult age range",
  "face": "face description",
  "hair": "hair description",
  "body": "body/build description",
  "wardrobe": "main wardrobe description",
  "style_notes": "attractiveness/casting/realism notes",
  "locations": ["location 1", "location 2", "location 3", "location 4"],
  "clothes": ["outfit 1", "outfit 2", "outfit 3", "outfit 4"],
  "angles": ["front", "3/4 left", "3/4 right", "side profile", "rear", "full body", "portrait close-up", "hands detail"],
  "base_prompt": "single complete photorealistic prompt",
  "sheet_prompt": "multi-angle character sheet prompt",
  "variation_prompt": "controlled variation grid prompt"
}}

Rules:
- If role is "instagram fitness model" or similar, use a young adult range like early 20s to early 30s, athletic physique, premium activewear, gym/studio/social-media lifestyle locations.
- Do not choose elderly ages unless the role asks for retired, elder, senior, grandparent, etc.
- Make the character attractive when the role implies model/influencer/lead/cinematic talent, but keep skin texture and anatomy realistic.
- Include adult-only wording if the role could be confused with teen styling.
- Include physical specificity: visible natural skin texture, slight facial asymmetry, flyaway hairs, realistic under-eye shadows, fabric weave, seam stitching, and a specific lens/light setup.
- base_prompt and variation_prompt must include: no text, no captions, no labels, no typography, no letters, no numbers, no logos, no watermark.
- sheet_prompt should describe a 3840x2160 horizontal 16:9 character reference turnaround sheet with exactly six large panels in a wide 3-by-2 layout: top row three full-body views and bottom row three face/detail panels.
- sheet_prompt must include positive blank-layout language plus sharp eyelashes, hair strands, fabric weave, clean divider lines, no captions, no labels, no typography, no letters, no numbers, no logos, no watermark, no fake writing, no barcode artifacts.
""".strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.55,
        "max_tokens": 1400,
        "response_format": {"type": "json_object"},
        "chat_template_kwargs": {"thinking": False, "enable_thinking": False},
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Kimi request failed: {e}") from e
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Kimi returned HTTP {resp.status_code}: {resp.text[:240]}")

    data = resp.json()
    content = str(data.get("choices", [{}])[0].get("message", {}).get("content", "") or "").strip()
    plan = _extract_json_object(content)
    if not plan:
        raise HTTPException(status_code=502, detail="Kimi did not return valid character JSON")

    fallback_angles = ["front", "3/4 left", "3/4 right", "side profile", "rear", "full body", "portrait close-up", "hands detail"]
    fallback_locations = ["neutral studio background", f"realistic setting suited to {role}", "sidewalk in natural daylight", "simple indoor room with practical lighting"]
    fallback_clothes = ["main role-appropriate outfit", "casual everyday outfit", "work outfit variation", "simple jacket layer"]
    name = str(plan.get("name") or req.name or "Generated Character").strip()
    clean_role = str(plan.get("role") or role).strip()
    base_prompt = str(plan.get("base_prompt") or "").strip()
    if not base_prompt:
        base_prompt = ", ".join([
            f"Photorealistic character portrait of {name}",
            f"role / archetype: {clean_role}",
            str(plan.get("age") or "").strip(),
            f"{gender} person" if gender else "",
            str(plan.get("face") or "").strip(),
            str(plan.get("hair") or "").strip(),
            str(plan.get("body") or "").strip(),
            str(plan.get("wardrobe") or "").strip(),
            str(plan.get("style_notes") or "").strip(),
            "realistic skin texture, stable anatomy, cinematic casting quality",
        ]).strip(", ")

    return {
        "status": "ok",
        "source": "kimi",
        "model": model,
        "name": name,
        "role": clean_role,
        "base_prompt": _with_character_no_text_rule(base_prompt),
        "sheet_prompt": _with_character_no_text_rule(str(plan.get("sheet_prompt") or "").strip()),
        "variation_prompt": _with_character_no_text_rule(str(plan.get("variation_prompt") or "").strip()),
        "locations": _clean_string_list(plan.get("locations"), fallback_locations, 6),
        "clothes": _clean_string_list(plan.get("clothes"), fallback_clothes, 6),
        "angles": _clean_string_list(plan.get("angles"), fallback_angles, 10),
        "raw": {k: plan.get(k) for k in ("age", "face", "hair", "body", "wardrobe", "style_notes")},
    }


def _default_character_workflow_path(workflow_id: str = "") -> Optional[Path]:
    requested = (workflow_id or "").strip()
    candidates: List[Path] = []
    if requested:
        wf = _workflow_file_for_id(requested)
        if wf:
            candidates.append(wf)
    candidates.extend([
        REPO_ROOT / "workflows" / "01_flux2_text_to_image.json",
        REPO_ROOT / "workflows" / "08_flux2_klein_9b_text_to_image.json",
    ])
    return next((p for p in candidates if p and p.exists()), None)


def _character_host_from_config() -> str:
    cfg = get_raw_config()
    comfyui = cfg.get("comfyui", {}) if isinstance(cfg.get("comfyui"), dict) else {}
    host = (
        os.getenv("COMFYUI_PRIMARY", "")
        or str(cfg.get("COMFYUI_PRIMARY", ""))
        or str(comfyui.get("primary", ""))
        or ""
    ).strip().rstrip("/")
    if host and not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


def _latest_character_generated_reference(char: Dict[str, Any]) -> str:
    approved = char.get("approved_assets") if isinstance(char.get("approved_assets"), list) else []
    for asset in reversed(approved):
        if isinstance(asset, dict) and asset.get("type") == "character" and asset.get("url"):
            return str(asset.get("url") or "")
    history = char.get("render_history") if isinstance(char.get("render_history"), list) else []
    for entry in reversed(history):
        urls = entry.get("image_urls") if isinstance(entry, dict) else []
        if entry.get("type") == "character" and isinstance(urls, list) and urls:
            return str(urls[0] or "")
    if char.get("anchor_url"):
        return str(char.get("anchor_url") or "")
    refs = char.get("master_references") if isinstance(char.get("master_references"), list) else []
    for ref in refs:
        if isinstance(ref, dict) and ref.get("url"):
            return str(ref.get("url") or "")
    return ""


def _character_reference_urls(char: Dict[str, Any], *, limit: int = 10) -> List[str]:
    urls: List[str] = []

    def add(url: Any) -> None:
        clean = str(url or "").strip()
        if clean and clean not in urls and len(urls) < limit:
            urls.append(clean)

    add(_latest_character_generated_reference(char))
    approved = char.get("approved_assets") if isinstance(char.get("approved_assets"), list) else []
    for asset in reversed(approved):
        if isinstance(asset, dict) and asset.get("type") == "character":
            add(asset.get("url"))
    for key in ("master_references", "reference_uploads", "sheet_panels"):
        refs = char.get(key) if isinstance(char.get(key), list) else []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            url = str(ref.get("url") or "").strip()
            if re.search(r"\.(mp4|mov|webm)(\?|$)", url, re.IGNORECASE):
                continue
            add(url)
    return urls[:limit]


def _workflow_has_image_input(workflow_path: Path) -> bool:
    try:
        text = workflow_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    return any(marker in text for marker in ("LoadImage", "LoadImageMask", "VHS_LoadImagePath"))


def _character_sheet_prompt(prompt: str, char: Optional[Dict[str, Any]] = None) -> str:
    char = char or {}
    name = str(char.get("name") or char.get("id") or "the character").strip()
    role = str(char.get("role") or char.get("description") or "character").strip()
    dna = char.get("visual_dna") if isinstance(char.get("visual_dna"), dict) else {}
    anchor = str(char.get("anchor_prompt") or "").strip()
    identity = ", ".join(
        part for part in [
            name,
            role,
            anchor[:600],
            str(dna.get("face") or ""),
            str(dna.get("hair") or ""),
            str(dna.get("body") or ""),
            str(dna.get("wardrobe") or ""),
        ]
        if str(part or "").strip()
    )
    user_prompt = str(prompt or "").strip()
    return _with_character_no_text_rule(
        "3840x2160 horizontal 16:9 professional character reference sheet, not square. "
        "Clean white or neutral light-gray studio background, six large sharp panels in a wide 3-by-2 layout, generous margins, clean divider lines only. "
        "No captions, no labels, no typography, no letters, no numbers, no fake writing, no barcode artifacts, no watermark. "
        "Top row: full-body front view, full-body three-quarter view, full-body side/rear three-quarter view. "
        "Bottom row: front portrait close-up, three-quarter portrait close-up, hands/wardrobe/detail close-up. "
        "Every panel shows the same exact adult character identity, same face, same age, same hair, same body proportions, same wardrobe materials, same skin tone. "
        "Sharp eyelashes, individual hair strands, visible pores, subtle under-eye texture, faint asymmetry, fabric weave, seam stitching, realistic hands, crisp studio optics. "
        "Use the supplied reference images as identity lock when present. "
        f"Character identity: {identity}. "
        f"Additional user direction: {user_prompt}"
    )


@app.post("/api/characters/spark-render")
async def api_character_spark_render(req: CharacterSparkRenderRequest):
    requested_type = (req.render_type or "character").strip().lower()
    if requested_type == "anchor":
        requested_type = "character"
    if requested_type not in {"character", "sheet", "variation"}:
        raise HTTPException(status_code=400, detail="render_type must be character, sheet, or variation")

    selected_char: Optional[Dict[str, Any]] = None
    selected_id = _character_slug(req.character_id or "")
    if requested_type in {"sheet", "variation"}:
        if not selected_id:
            raise HTTPException(status_code=400, detail="Select a character before generating a character sheet or variation set")
        selected_char = _CHARACTERS_STORE.get(selected_id)
        if not selected_char:
            raise HTTPException(status_code=404, detail=f"Character '{selected_id}' not found")
        safe_name = selected_id
    else:
        safe_name = _character_slug(req.name)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Character name is required")
    prompt = _character_sheet_prompt(req.prompt, selected_char) if requested_type == "sheet" else _with_character_no_text_rule(req.prompt)
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    prompt, _ = apply_model_prompt_standard(
        prompt,
        workflow_id=req.workflow_id or "01_flux2_text_to_image",
        model_family="flux2-dev",
        render_type=requested_type,
    )

    storage_type = "anchor" if requested_type == "character" else requested_type

    host = _character_host_from_config()
    if not host:
        raise HTTPException(status_code=400, detail="COMFYUI_PRIMARY is not configured. Turn on Spark or set the ComfyUI primary host in Settings.")

    workflow_path = _default_character_workflow_path(req.workflow_id)
    if not workflow_path:
        raise HTTPException(status_code=404, detail="No text-to-image workflow file found for character rendering")

    reference_url = ""
    reference_urls: List[str] = []
    reference_paths: List[Path] = []
    if requested_type in {"sheet", "variation"}:
        for url in list(req.reference_image_urls or []) + [(req.reference_image_url or "").strip()] + _character_reference_urls(selected_char or {}):
            clean = str(url or "").strip()
            if clean and clean not in reference_urls and len(reference_urls) < 10:
                reference_urls.append(clean)
        reference_url = reference_urls[0] if reference_urls else ""
        if not reference_urls:
            raise HTTPException(status_code=400, detail="Selected character has no generated image to use as a reference")
        for url in reference_urls:
            resolved = _resolve_image_path(url)
            if resolved:
                reference_paths.append(resolved)
        if not reference_paths:
            raise HTTPException(status_code=404, detail="Selected character reference images could not be resolved locally")
        reference_instruction = (
            " Use the supplied reference images as the identity lock. Reference image 1 is the primary latest character portrait. "
            "Match the exact same person, face, age, hair, body proportions, skin tone, expression family, and signature wardrobe cues. "
            "Do not invent a new character."
        )
        prompt = _with_character_no_text_rule(prompt + reference_instruction)
    workflow_accepts_references = bool(reference_paths) and _workflow_has_image_input(workflow_path)

    client = ComfyUIClient(host)
    ok, info = await client.check_health()
    if not ok:
        raise HTTPException(status_code=503, detail=f"Spark/ComfyUI is offline at {host}: {info.get('error', 'unreachable')}")

    seed = req.seed if req.seed is not None else random.randint(1, 2**32 - 1)
    output_dir = MEDIA_IMAGES / "characters" / safe_name
    output_dir.mkdir(parents=True, exist_ok=True)
    shot_id = f"char_{safe_name}_{requested_type}_{int(time.time())}"
    result = await client.submit_prompt_for_shot(
        shot_id=shot_id,
        prompt=prompt,
        workflow_path=str(workflow_path),
        seed=seed,
        output_dir=str(output_dir),
        image_paths=[str(path) for path in reference_paths],
        width=3840 if requested_type == "sheet" else None,
        height=2160 if requested_type == "sheet" else None,
        wait_for_output=True,
    )
    if result.get("status") != "success":
        raise HTTPException(status_code=502, detail=result.get("error", "Spark character render failed"))

    saved_files = [str(p) for p in result.get("saved_files") or []]
    image_urls = [_media_url_for_path(Path(p)) for p in saved_files if Path(p).exists()]

    anchor_url = ""
    if requested_type == "character" and saved_files:
        first = Path(saved_files[0])
        ext = first.suffix.lower() if first.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} else ".png"
        dest = CHARACTERS_ANCHORS_DIR / f"{safe_name}{ext}"
        shutil.copy2(first, dest)
        anchor_url = f"/api/characters/anchor/{safe_name}"

    char = _normalize_character(safe_name, _CHARACTERS_STORE.get(safe_name, {
        "id": safe_name,
        "name": req.name.strip(),
        "role": (req.role or "Character").strip() or "Character",
        "accent": "cyan",
        "score": 0,
        "anchor_url": "",
        "anchor_prompt": "",
        "dna": {},
    }))
    if req.role:
        char["role"] = req.role.strip()
    if requested_type == "character":
        char["anchor_prompt"] = prompt
        if anchor_url:
            char["anchor_url"] = anchor_url
    char.setdefault("render_prompts", {})[requested_type] = prompt
    if storage_type != requested_type:
        char.setdefault("render_prompts", {})[storage_type] = prompt
    char.setdefault("render_history", []).append({
        "type": requested_type,
        "prompt": prompt,
        "prompt_id": result.get("prompt_id"),
        "seed": seed,
        "workflow_id": req.workflow_id,
        "image_urls": image_urls,
        "reference_image_url": reference_url,
        "reference_image_urls": reference_urls,
        "reference_image_used": workflow_accepts_references,
        "reference_image_count": len(reference_paths),
        "created_at": _now_iso(),
    })
    if image_urls:
        asset = {
            "type": requested_type,
            "url": image_urls[0],
            "all_urls": image_urls,
            "prompt_id": result.get("prompt_id"),
            "seed": seed,
            "workflow_id": req.workflow_id,
            "reference_image_url": reference_url,
            "reference_image_urls": reference_urls,
            "reference_image_used": workflow_accepts_references,
            "reference_image_count": len(reference_paths),
            "created_at": _now_iso(),
        }
        char.setdefault("approved_assets" if requested_type == "character" else "candidate_assets", []).append(asset)
        if requested_type == "character":
            refs = [r for r in char.get("master_references", []) if isinstance(r, dict)]
            if not refs and anchor_url:
                refs.append({
                    "id": f"master_{int(time.time())}",
                    "url": anchor_url,
                    "type": "face_closeup",
                    "source": "spark_character_render",
                    "locked": True,
                    "score": int(char.get("score") or 0),
                    "prompt_id": result.get("prompt_id") or "",
                    "created_at": _now_iso(),
                })
                char["master_references"] = refs[:5]
    if req.save_character:
        char = _persist_normalized_character(safe_name, char)

    meta_path = output_dir / f"{shot_id}.json"
    meta_path.write_text(json.dumps({
        "id": shot_id,
        "character_id": safe_name,
        "render_type": requested_type,
        "prompt": prompt,
        "seed": seed,
        "workflow_id": req.workflow_id,
        "prompt_id": result.get("prompt_id"),
        "image_urls": image_urls,
        "reference_image_url": reference_url,
        "reference_image_urls": reference_urls,
        "reference_image_used": workflow_accepts_references,
        "reference_image_count": len(reference_paths),
    }, indent=2), encoding="utf-8")

    return {
        "status": "complete",
        "character": char,
        "render_type": requested_type,
        "prompt_id": result.get("prompt_id"),
        "seed": seed,
        "image_urls": image_urls,
        "anchor_url": anchor_url or char.get("anchor_url", ""),
        "saved_files": saved_files,
        "reference_image_url": reference_url,
        "reference_image_urls": reference_urls,
        "reference_image_used": workflow_accepts_references,
        "reference_image_count": len(reference_paths),
    }


@app.post("/api/characters/render")
async def api_render_character(req: RenderCharacterRequest):
    from core.dispatch.comfy_client import ComfyUIClient
    import json as _json

    workflow_path = Path("/Users/zgbot/workflows/hermes_z_image_turbo_api.json")
    if not workflow_path.exists():
        workflow_path = Path(__file__).parent.parent / "workflows" / "z_image_turbo_api.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail="No ComfyUI workflow file found")

    with open(workflow_path, "r") as f:
        workflow = _json.load(f)

    seed = req.seed or random.randint(1, 999_999_999)
    safe_name = _character_slug(req.name)
    prompt = _with_character_no_text_rule(req.prompt)
    negative_markers = ["blurry,", "low quality,", "distorted,", "worst quality,", "deformed", "bad anatomy", "extra fingers", "watermark"]
    prompt_block = workflow.get("prompt", workflow)
    for node_id, node in prompt_block.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        if ct == "CLIPTextEncode":
            text = node.get("inputs", {}).get("text", "")
            is_negative = len(text) < 200 and sum(1 for m in negative_markers if m in text.lower()) >= 2
            if not is_negative:
                prompt_block[node_id]["inputs"]["text"] = prompt
        if ct in ("KSampler", "SamplerCustom", "SamplerCustomAdvanced") and "seed" in node.get("inputs", {}):
            prompt_block[node_id]["inputs"]["seed"] = seed
        if ct in ("RandomNoise", "FluxNoise") and "noise_seed" in node.get("inputs", {}):
            prompt_block[node_id]["inputs"]["noise_seed"] = seed
        if ct == "SaveImage":
            prompt_block[node_id]["inputs"]["filename_prefix"] = f"char_{safe_name}"

    from core.bridge.runtime_config import get_raw_config
    cfg = get_raw_config()
    host = (
        os.getenv("COMFYUI_PRIMARY", "")
        or str(cfg.get("COMFYUI_PRIMARY", ""))
        or ""
    ).rstrip("/")
    if not host:
        raise HTTPException(status_code=400, detail="COMFYUI_PRIMARY is not configured")
    client = ComfyUIClient(host)
    submit = await client.submit_prompt(workflow)
    if not submit.get("ok"):
        raise HTTPException(status_code=502, detail=submit.get("error", "ComfyUI submission failed"))
    prompt_id = submit.get("prompt_id")
    if not prompt_id:
        raise HTTPException(status_code=502, detail="ComfyUI submission failed")

    filename = await client.poll_job(prompt_id, timeout_sec=300)
    if not filename:
        raise HTTPException(status_code=504, detail="Render timed out")

    anchors_dir = Path(__file__).parent.parent / "data" / "character_banks" / "anchors"
    anchors_dir.mkdir(parents=True, exist_ok=True)
    saved = await client.download_outputs(prompt_id, str(anchors_dir))
    if not saved:
        raise HTTPException(status_code=500, detail="Image download from Spark failed")

    dest = anchors_dir / f"{safe_name}.jpg"
    shutil.copy(saved[0], str(dest))
    anchor_url = f"/api/characters/anchor/{safe_name}"
    char = _normalize_character(safe_name, _CHARACTERS_STORE.get(safe_name, {
        "id": safe_name,
        "name": req.name.strip(),
        "role": "Character",
        "accent": "cyan",
        "score": 0,
        "anchor_url": anchor_url,
        "anchor_prompt": prompt,
        "dna": {},
    }))
    char["anchor_url"] = anchor_url
    char["anchor_prompt"] = prompt
    char.setdefault("render_history", []).append({
        "type": "character",
        "prompt": prompt,
        "prompt_id": prompt_id,
        "seed": seed,
        "workflow_id": str(workflow_path),
        "image_urls": [anchor_url],
        "created_at": _now_iso(),
    })
    if not char.get("master_references"):
        char["master_references"] = [{
            "id": f"master_{int(time.time())}",
            "url": anchor_url,
            "type": "face_closeup",
            "source": "legacy_character_render",
            "locked": True,
            "score": int(char.get("score") or 0),
            "prompt_id": prompt_id,
            "created_at": _now_iso(),
        }]
    _persist_normalized_character(safe_name, char)
    return {"status": "complete", "anchor_url": anchor_url, "prompt_id": prompt_id}


@app.get("/api/characters/anchor/{name}")
async def api_character_anchor(name: str):
    safe_name = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    anchors_dir = Path(__file__).parent.parent / "data" / "character_banks" / "anchors"
    for ext in ['.jpg', '.jpeg', '.png', '.webp']:
        img_path = anchors_dir / f"{safe_name}{ext}"
        if img_path.exists():
            return FileResponse(str(img_path))
    raise HTTPException(status_code=404, detail=f"No character image for '{name}'")


class NewCharacterRequest(BaseModel):
    name: str
    description: Optional[str] = ""


@app.post("/api/characters")
async def api_create_character(
    name: str = Form(...),
    description: str = Form(""),
    anchor_prompt: str = Form(""),
    anchor_image: UploadFile | None = Form(None),
):
    """Create or update character metadata with an optional drag-drop character image."""

    safe_name = _character_slug(name)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid character name")

    existing = _CHARACTERS_STORE.get(safe_name)

    # Assign accent color from palette
    accents = ["cyan", "magenta", "amber", "green"]
    existing_accents = {c.get("accent") for c in _CHARACTERS_STORE.values()}
    accent = existing.get("accent") if existing else next((a for a in accents if a not in existing_accents), "cyan")

    # Save character image if provided
    anchor_url = ""
    final_name = ""
    if anchor_image and anchor_image.filename:
        raw_name = _character_slug(Path(anchor_image.filename).stem)
        img_ext = Path(anchor_image.filename).suffix.lower() or '.jpg'
        if img_ext not in ('.jpg', '.jpeg', '.png', '.webp'):
            img_ext = '.jpg'
        # Use raw filename but deduplicate
        final_name = f"{safe_name}_{raw_name}{img_ext}" if raw_name != safe_name else f"{safe_name}{img_ext}"
        idx = 1
        dest_path = CHARACTERS_ANCHORS_DIR / final_name
        while dest_path.exists():
            final_name = f"{safe_name}_{raw_name}_{idx}{img_ext}"
            dest_path = CHARACTERS_ANCHORS_DIR / final_name
            idx += 1

        content = await anchor_image.read()
        with open(dest_path, "wb") as fout:
            fout.write(content)
        anchor_url = f"/api/characters/anchor/{Path(final_name).stem}"

    prompt = anchor_prompt.strip() or (existing or {}).get("anchor_prompt") or f"Portrait of {name.strip()}, {description or ''}"
    master_references = list((existing or {}).get("master_references") or [])
    if anchor_url:
        master_references.insert(0, {
            "id": f"master_{len(master_references) + 1:03d}",
            "url": anchor_url,
            "type": "face_closeup",
            "source": "create_character_upload",
            "locked": True,
            "score": int((existing or {}).get("score") or 0),
            "created_at": _now_iso(),
        })

    # Build character record while preserving existing profile fields.
    char_data = {
        **(existing or {}),
        "id": safe_name,
        "name": name.strip().upper(),
        "role": description[:60] if description else "Character",
        "description": description,
        "bio": description,
        "accent": accent,
        "score": int((existing or {}).get("score") or 0),
        "anchor_url": anchor_url or (existing or {}).get("anchor_url", ""),
        "anchor_prompt": prompt,
        "dna": (existing or {}).get("dna", {}),
        "master_references": master_references,
    }

    # Persist to character_banks/char_{id}.json
    char_data = _persist_normalized_character(safe_name, char_data)

    # Append to world guide
    world_bible_path = Path(__file__).parent.parent / "data" / "lore_bible" / "world_bible.md"
    try:
        if world_bible_path.exists():
            wb_text = world_bible_path.read_text(encoding="utf-8")
        else:
            wb_text = ""

        char_section = (
            f"\n## KEY CHARACTER: {name.strip().upper()}\n"
            f"- **Role:** {description or 'Character'}\n"
            + (f"- **Character Image:** `{Path(final_name).stem}`\n" if final_name else "")
            + "\n"
        )
        if not world_bible_path.exists():
            world_bible_path.parent.mkdir(parents=True, exist_ok=True)
            wb_text = "# WORLD GUIDE: CHARACTER ROSTER\n\n" + char_section
        elif f"## KEY CHARACTER: {name.strip().upper()}" in wb_text:
            char_section = ""
        elif "## KEY CHARACTER:" not in wb_text:
            wb_text += "\n" + char_section
        else:
            # Insert before ## CORE CONFLICT or append at end
            conflict_marker = "## CORE CONFLICT"
            if conflict_marker in wb_text:
                wb_text = wb_text.replace(conflict_marker, char_section + conflict_marker)
            else:
                wb_text += "\n" + char_section

        world_bible_path.write_text(wb_text, encoding="utf-8")
    except Exception:
        pass  # Non-fatal — character is still created

    return {
        "status": "updated" if existing else "created",
        "character": char_data,
        "metadata_path": str(CHARACTER_BANKS_DIR / f"char_{safe_name}.json"),
        "anchor_saved": bool(anchor_url),
    }


# --- Hermes Agent Profile Chat ---

HERMES_PROFILES = {
    "live": "Creative Director",
    "character": "Character Architect",
    "script": "Screenwriter",
    "product": "Product Stylist",
}

HERMES_BIN = "python3"
FORGE_HERMES_LAUNCHER = str(Path(__file__).parent.parent / "hermes_engine" / "hermes")
FORGE_HERMES_HOME = str(Path(__file__).parent.parent / "hermes_home")


class HermesProfileChatRequest(BaseModel):
    message: str
    profile: str = "live"


@app.post("/api/hermes/profile/chat")
async def api_hermes_profile_chat(req: HermesProfileChatRequest):
    profile = req.profile if req.profile in HERMES_PROFILES else "live"
    if not os.path.exists(FORGE_HERMES_LAUNCHER):
        raise HTTPException(status_code=503, detail="Hermes engine not found")
    try:
        skills_list = []
        if profile == 'live': skills_list = ['forge-nps-evolution-plan', 'cinematic_consistency_protocol']
        elif profile == 'character': skills_list = ['character-dna-standardization']
        elif profile == 'script': skills_list = ['narrative-beat-synthesis']
        elif profile == 'product': skills_list = ['material-physics-engine']
        
        cmd_args = [HERMES_BIN, FORGE_HERMES_LAUNCHER, "-p", profile]
        if skills_list:
            cmd_args.extend(["--skills", ",".join(skills_list)])
        cmd_args.extend(["chat", "-Q", "-q", req.message])

        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "HERMES_HOME": FORGE_HERMES_HOME, "HERMES_QUIET": "1", "NO_COLOR": "1"},
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=504, detail="Hermes response timed out")
        output = stdout.decode("utf-8", errors="replace").strip()
        if not output and stderr:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise HTTPException(status_code=500, detail=f"Hermes error: {err[:300]}")
        return {"profile": profile, "role": HERMES_PROFILES[profile], "response": output}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/hermes/profiles")
async def api_hermes_profiles():
    return [{"id": k, "role": v} for k, v in HERMES_PROFILES.items()]


# --- Hermes Live Chat (Streaming) ---

class HermesChatRequest(BaseModel):
    message: str = "Hello"
    profile: str = "live"


@app.post("/api/hermes/chat")
async def api_hermes_chat_stream(req: HermesChatRequest):
    """Stream Hermes chat response using Server-Sent Events (SSE)."""
    from fastapi.responses import StreamingResponse
    import json as _json

    async def event_generator():
        try:
            from core.bridge.nous_hermes_bridge import NousHermesBridge

            hermes_brain = NousHermesBridge()
            if not hermes_brain.is_available:
                yield _json.dumps({"error": "Hermes LM Studio endpoint unavailable"}) + "\n"
                return
            response = await hermes_brain.chat([
                {"role": "user", "content": req.message}
            ])
            chunk_size = 20
            for i in range(0, len(response), chunk_size):
                chunk = response[i:i + chunk_size]
                yield _json.dumps({"token": chunk}) + "\n"
                await asyncio.sleep(0.02)
            yield _json.dumps({"done": True}) + "\n"

        except Exception as e:
            yield _json.dumps({"error": str(e)}) + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/products")
async def api_get_products():
    """Compatibility endpoint: products now live as Asset Vault packages."""
    packages = _list_asset_vault_packages()
    return {"status": "ok", "products": [pkg for pkg in packages if pkg.get("element_type") == "product"], "packages": packages}


@app.get("/api/asset-vault/packages")
async def api_asset_vault_packages():
    return {"status": "ok", "packages": _list_asset_vault_packages()}


@app.get("/api/asset-vault/packages/{package_id}")
async def api_asset_vault_get_package(package_id: str):
    package = _asset_vault_package_by_id(package_id)
    if not package:
        raise HTTPException(status_code=404, detail=f"Asset Vault package not found: {package_id}")
    return {"status": "ok", "package": package}


@app.post("/api/asset-vault/packages")
async def api_asset_vault_create_package(req: AssetVaultPackageRequest):
    packages = _list_asset_vault_packages()
    package = _normalize_asset_vault_package(_asset_vault_request_payload(req))
    if any(pkg.get("id") == package["id"] for pkg in packages):
        raise HTTPException(status_code=409, detail=f"Asset Vault package already exists: {package['id']}")
    packages.append(package)
    _write_asset_vault_packages(packages)
    return {"status": "ok", "package": package}


@app.put("/api/asset-vault/packages/{package_id}")
async def api_asset_vault_update_package(package_id: str, req: AssetVaultPackageRequest):
    packages = _list_asset_vault_packages()
    pid = _asset_slug(package_id)
    for index, existing in enumerate(packages):
        if existing.get("id") != pid:
            continue
        updated = _normalize_asset_vault_package(_asset_vault_request_payload(req, existing))
        packages[index] = updated
        _write_asset_vault_packages(packages)
        return {"status": "ok", "package": updated}
    raise HTTPException(status_code=404, detail=f"Asset Vault package not found: {package_id}")


@app.delete("/api/asset-vault/packages/{package_id}")
async def api_asset_vault_delete_package(package_id: str):
    packages = _list_asset_vault_packages()
    pid = _asset_slug(package_id)
    remaining = [pkg for pkg in packages if pkg.get("id") != pid]
    if len(remaining) == len(packages):
        raise HTTPException(status_code=404, detail=f"Asset Vault package not found: {package_id}")
    _write_asset_vault_packages(remaining)
    return {"status": "ok", "deleted": pid}


@app.post("/api/asset-vault/packages/{package_id}/duplicate")
async def api_asset_vault_duplicate_package(package_id: str):
    packages = _list_asset_vault_packages()
    original = _asset_vault_package_by_id(package_id)
    if not original:
        raise HTTPException(status_code=404, detail=f"Asset Vault package not found: {package_id}")
    clone = dict(original)
    clone.pop("characters", None)
    base_name = f"{original.get('name') or 'Package'} Copy"
    clone["name"] = base_name
    clone["id"] = _asset_slug(base_name)
    suffix = 2
    existing_ids = {pkg.get("id") for pkg in packages}
    while clone["id"] in existing_ids:
        clone["name"] = f"{base_name} {suffix}"
        clone["id"] = _asset_slug(clone["name"])
        suffix += 1
    clone["created_at"] = _now_iso()
    clone["updated_at"] = clone["created_at"]
    normalized = _normalize_asset_vault_package(clone)
    packages.append(normalized)
    _write_asset_vault_packages(packages)
    return {"status": "ok", "package": normalized}


@app.post("/api/asset-vault/packages/{package_id}/references/upload")
async def api_asset_vault_upload_reference(
    package_id: str,
    file: UploadFile = File(...),
    asset_type: str = Form("reference"),
    name: str = Form(""),
    prompt: str = Form(""),
):
    packages = _list_asset_vault_packages()
    pid = _asset_slug(package_id)
    upload_name = _asset_slug(Path(file.filename or "asset").stem)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".ttf", ".otf", ".woff", ".woff2", ".pdf"}:
        suffix = ".bin"
    out_dir = MEDIA_ROOT / "asset_vault" / pid
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{upload_name}_{uuid.uuid4().hex[:8]}{suffix}"
    with out_path.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    ref = {
        "id": _asset_slug(f"{asset_type}_{upload_name}_{uuid.uuid4().hex[:6]}"),
        "type": str(asset_type or "reference").strip().lower() or "reference",
        "name": _short_text(name or Path(file.filename or "Asset").stem, 90),
        "url": _media_url_for_path(out_path),
        "prompt": _short_text(prompt or "", 360),
        "notes": "",
    }
    for pkg in packages:
        if pkg.get("id") == pid:
            refs = _normalize_vault_references(pkg.get("references"))
            refs.append(ref)
            pkg["references"] = refs
            pkg["updated_at"] = _now_iso()
            normalized = [_normalize_asset_vault_package(item) for item in packages]
            _write_asset_vault_packages(normalized)
            return {
                "status": "ok",
                "reference": ref,
                "package": next(item for item in normalized if item.get("id") == pid),
            }
    try:
        out_path.unlink(missing_ok=True)
    except Exception:
        pass
    raise HTTPException(status_code=404, detail=f"Asset Vault package not found: {package_id}")


@app.post("/api/asset-vault/packages/{package_id}/characters/{char_id}")
async def api_asset_vault_add_character(package_id: str, char_id: str, req: Optional[AssetVaultCharacterLinkRequest] = None):
    packages = _list_asset_vault_packages()
    pid = _asset_slug(package_id)
    cid = _character_slug(char_id)
    if cid not in _CHARACTERS_STORE:
        raise HTTPException(status_code=404, detail=f"Character not found: {char_id}")
    for pkg in packages:
        if pkg.get("id") == pid:
            refs = _normalize_vault_character_refs(pkg)
            role = (req.role if req else "reference") or "reference"
            notes = (req.notes if req else "") or ""
            found = False
            for ref in refs:
                if ref.get("id") == cid:
                    ref["role"] = _short_text(role, 48)
                    ref["notes"] = _short_text(notes, 240)
                    found = True
                    break
            if not found:
                refs.append({"id": cid, "role": _short_text(role, 48), "notes": _short_text(notes, 240)})
            pkg["character_refs"] = refs
            pkg["character_ids"] = [ref["id"] for ref in refs]
            pkg["updated_at"] = _now_iso()
            normalized = [_normalize_asset_vault_package(item) for item in packages]
            _write_asset_vault_packages(normalized)
            return {"status": "ok", "package": next(item for item in normalized if item.get("id") == pid)}
    raise HTTPException(status_code=404, detail=f"Asset Vault package not found: {package_id}")


@app.delete("/api/asset-vault/packages/{package_id}/characters/{char_id}")
async def api_asset_vault_remove_character(package_id: str, char_id: str):
    packages = _list_asset_vault_packages()
    pid = _asset_slug(package_id)
    cid = _character_slug(char_id)
    for pkg in packages:
        if pkg.get("id") == pid:
            refs = [ref for ref in _normalize_vault_character_refs(pkg) if ref.get("id") != cid]
            pkg["character_refs"] = refs
            pkg["character_ids"] = [ref["id"] for ref in refs]
            pkg["updated_at"] = _now_iso()
            normalized = [_normalize_asset_vault_package(item) for item in packages]
            _write_asset_vault_packages(normalized)
            return {"status": "ok", "package": next(item for item in normalized if item.get("id") == pid)}
    raise HTTPException(status_code=404, detail=f"Asset Vault package not found: {package_id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000)
