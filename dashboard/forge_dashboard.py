import json
import uuid
import time
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, UploadFile, Form, Request
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
from PIL import Image
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
from pydantic import BaseModel

from .memory_api import (
    get_memory_stats,
    get_event_timeline,
    get_graph_data,
    search_memory,
    get_memory_health,
)
from .api.prompt_builder import load_banks, build_recipe, generate_random_recipe
from .api.spark_monitor import monitor as spark_monitor
from core.dispatch.comfy_client import ComfyUIClient
from core.affiliate.local_higgsfield import LocalHiggsfieldAdapter
from core.hermes.pipeline import HermesCampaignService, CampaignRequest, HermesAuditService, HermesVideoService
from core.hermes.pipeline.director_service import KimiDirectorService
from core.hermes.platform_skills import (
    carousel_caption_text,
    detect_platform_skill,
    generate_hook_ideas,
)

STATIC_DIR = Path(__file__).parent / "static"
REPO_ROOT = Path(__file__).parent.parent.resolve()
MEDIA_ROOT = Path(os.getenv("FORGE_MEDIA_ROOT", "~/Desktop/FORGE_NPS_MEDIA"))
MEDIA_IMAGES = MEDIA_ROOT / "images"
MEDIA_IMAGES.mkdir(parents=True, exist_ok=True)
MEDIA_VIDEOS = MEDIA_ROOT / "videos"
MEDIA_VIDEOS.mkdir(parents=True, exist_ok=True)
MEDIA_IDENTITY_ASSETS = MEDIA_ROOT / "identity_assets"
MEDIA_IDENTITY_ASSETS.mkdir(parents=True, exist_ok=True)
MEDIA_IDENTITY_TEMPLATES = MEDIA_ROOT / "identity_templates"
MEDIA_IDENTITY_TEMPLATES.mkdir(parents=True, exist_ok=True)
NEXUS_DB = REPO_ROOT / ".forge-nexus" / "forge.db"

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
    if value.endswith("/v1"):
        value = value[:-3].rstrip("/")
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
    return urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


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
    output_dir = MEDIA_IMAGES / campaign_id
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

        outputs = entry.get("outputs", {}) if isinstance(entry.get("outputs"), dict) else {}
        output_filenames: List[str] = []
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
                    filename = str(item.get("filename", "") or "")
                    if filename:
                        output_filenames.append(filename)
        if not output_filenames:
            continue
        inspected += 1

        image_names = [
            name for name in output_filenames
            if Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
        if not image_names:
            continue
        output_dir = MEDIA_IMAGES / campaign_id
        existing = [output_dir / Path(name).name for name in image_names]
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
                    "label": project_dir.name.replace("_", " ").title() + " — Brand Bible",
                    "path": str(bible.relative_to(repo_root)),
                    "type": "brand_bible",
                })

    return scripts


@app.post("/api/script/reparse")
async def api_script_reparse(req: ReparseRequest = None):
    """Re-read shot list from a script file. Accepts optional path relative to repo root.
    Uses Kimi to extract shots from brand bibles when available, falls back to regex."""
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
Given a brand bible or creative brief, extract individual shots as a JSON array.

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
    """Send brand bible to Kimi for shot extraction."""
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

    user_prompt = f"""Extract a complete shot list from the following creative brief/brand bible.

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
                    "dialogue": "",
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
                    "dialogue": "",
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


async def _request_script_package(req: ScriptDevelopRequest) -> Dict[str, Any]:
    director = KimiDirectorService()
    if not director.api_key:
        return _fallback_script_package(req)

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
                        "dialogue": "string",
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
    system_prompt = (
        "You are Hermes Script Architect for FORGE NPS. Return only valid JSON. "
        "Your job is not to make isolated pretty shots; produce a locked script package "
        "that can be converted into scene-by-scene coverage for a cohesive movie edit."
    )
    user_prompt = (
        f"title: {title}\n"
        f"runtime_seconds: {runtime}\n"
        f"target_scenes: {scene_count}\n"
        f"tone: {(req.tone or 'unspecified').strip()}\n"
        f"brief:\n{(req.brief or '').strip()}\n\n"
        "Write a structured screenplay package. Every scene must include concrete beats, "
        "continuity locks, emotional turns, edit pacing, audio strategy, and transitions. "
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
        "response_format": {"type": "json_object"},
        "max_tokens": 12000,
    }
    timeout_sec = max(float(os.getenv("FORGE_KIMI_TIMEOUT_SEC", "120")), 180.0)
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        resp = await client.post(
            director.endpoint,
            headers={"Authorization": f"Bearer {director.api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"http_error status={resp.status_code} error={resp.text[:500]}")
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        package = _extract_json_response(content)
        package["source"] = "director_api"
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
    """Explicitly parse a brand bible with Kimi to extract shots.
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


class VideoProcessRequest(BaseModel):
    shot_ids: List[str]
    duration: int = 4
    fps: int = 24
    workflow_id: str = "02_ltx2.3_T2V_I2V_distilled"
    prompt: str = ""
    platform_mode: str = "auto"
    min_audit_score: float = 0.85
    min_audit_confidence: float = 0.70
    require_audit_pass: bool = True
    allow_failed_override: bool = False


class VideoGeneratePromptsRequest(BaseModel):
    shot_ids: List[str]
    duration: int = 4
    fps: int = 24
    campaign_id: str = ""
    workflow_id: str = "04_ltx2.3_image_to_video"
    platform_mode: str = "auto"


class LocalHiggsfieldImageRequest(BaseModel):
    prompt: str
    width_and_height: str = "1696x960"
    enhance_prompt: bool = True
    quality: str = "720p"
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


def _workflow_file_for_id(workflow_id: str) -> Optional[Path]:
    candidates = [
        REPO_ROOT / "workflows" / f"{workflow_id}.json",
        REPO_ROOT / "workflows" / f"{workflow_id}_api.json",
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
    )


@app.post("/api/local-higgsfield/generate-video")
async def api_local_higgsfield_generate_video(req: LocalHiggsfieldVideoRequest):
    if not (req.input_image_url or "").strip():
        raise HTTPException(status_code=400, detail="input_image_url is required")
    if not (req.prompt or "").strip():
        raise HTTPException(status_code=400, detail="prompt is required")
    motions = [m.model_dump() for m in req.motions]
    adapter = _make_local_higgsfield_adapter()
    return await adapter.generate_video_dop(
        input_image_url=req.input_image_url,
        prompt=req.prompt,
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
    service = HermesVideoService(
        media_videos=MEDIA_VIDEOS,
        active_campaign_getter=lambda: _ACTIVE_CAMPAIGN,
        find_shot=_find_shot,
        resolve_image_path=_resolve_image_path,
        workflow_file_for_id=_workflow_file_for_id,
    )
    workflow_id = (req.workflow_id or "").strip()
    result = await service.process(
        shot_ids=[str(x) for x in req.shot_ids],
        workflow_id=workflow_id,
        duration=int(req.duration or 0),
        fps=int(req.fps or 0),
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
    return result


@app.post("/api/video/generate-prompts")
async def api_video_generate_prompts(req: VideoGeneratePromptsRequest):
    """Stream LTX video prompt generation via Vision analysis + Hermes prompt profiles."""
    from fastapi.responses import StreamingResponse
    import asyncio

    shot_ids = [str(x) for x in req.shot_ids]
    duration = int(req.duration or 4)
    fps = int(req.fps or 24)
    workflow_id = (req.workflow_id or "04_ltx2.3_image_to_video").strip()
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
    "hands_ok",
    "limbs_ok",
    "face_ok",
    "reflection_ok",
    "vehicle_geometry_ok",
    "text_artifacts_ok",
    "prompt_adherence_ok",
]
_AUDIT_CRITICAL_CHECKS = {"hands_ok", "limbs_ok", "reflection_ok", "vehicle_geometry_ok"}
_AUDIT_CHECK_WEIGHTS = {
    "hands_ok": 3.0,
    "limbs_ok": 3.0,
    "face_ok": 2.0,
    "reflection_ok": 3.0,
    "vehicle_geometry_ok": 3.0,
    "text_artifacts_ok": 1.0,
    "prompt_adherence_ok": 2.0,
}
_AUDIT_KEYWORD_TO_CHECK = {
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


def _apply_keyword_fails(checks: Dict[str, bool], issues: List[str], feedback: str) -> Dict[str, bool]:
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


def _aggregate_audit_results(pass_a: Dict[str, Any], pass_b: Dict[str, Any]) -> Dict[str, Any]:
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

    checks = _apply_keyword_fails(checks, issues + noncritical + critical, feedback)
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
            "\"checks\":{\"hands_ok\":true,\"limbs_ok\":true,\"face_ok\":true,\"reflection_ok\":true,"
            "\"vehicle_geometry_ok\":true,\"text_artifacts_ok\":true,\"prompt_adherence_ok\":true},"
            "\"critical_failures\":[],\"noncritical_issues\":[],\"issues\":[],\"feedback\":\"short\"}. "
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
        result = _aggregate_audit_results(audit_pass, {})
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
    director_selected = director_api2 if director_active == "api2" and director_api2 else director_api1
    visual_selected = visual_api2 if visual_active == "api2" and visual_api2 else visual_api1
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
            "workflow_file": "",
        },
    }


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
    }
    for k, v in (updates or {}).items():
        mapped[key_map.get(k, k)] = v
    current_cfg = get_raw_config()
    for secret_key in ["NOUS_API_KEY", "KIMI_API_KEY", "OPENROUTER_API_KEY"]:
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
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(endpoint, headers=headers, json=payload)
        if r.status_code >= 400:
            return {"status": "error", "error": f"http {r.status_code}: {r.text[:200]}", "endpoint": endpoint, "model": model}
        return {"status": "ok", "latency_ms": int((time.time() - t0) * 1000), "endpoint": endpoint, "model": model}
    except Exception as e:
        reason = str(e).strip() or e.__class__.__name__
        return {"status": "error", "error": reason, "endpoint": endpoint, "model": model}


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
    image_b64 = ""
    mime_type = "image/png"
    for root in [MEDIA_IMAGES, MEDIA_ROOT / "imports", MEDIA_ROOT / "legacy"]:
        try:
            candidate = next(
                f for f in sorted(root.rglob("*"))
                if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            )
            image_b64 = base64.b64encode(candidate.read_bytes()).decode("utf-8")
            mime_type = _image_mime_type(str(candidate))
            break
        except StopIteration:
            continue
        except Exception:
            continue
    if not image_b64:
        image_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
        )
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
    active = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_ACTIVE", "api1") or "api1").strip().lower()
    api1 = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API1", "") or cfg.get("NIM_ENDPOINT", "") or "").strip()
    api2 = str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API2", "") or "").strip()
    endpoint = api2 if active == "api2" and api2 else api1
    api_key = str(cfg.get("KIMI_API_KEY", "") or "").strip()
    model = str(cfg.get("KIMI_INSTRUCT_MODEL", "") or "").strip()
    if endpoint.startswith("https://") and not api_key:
        return {"status": "error", "error": "missing api key"}
    return await _test_chat_completion(endpoint, api_key, model)


@app.post("/api/test/director")
async def api_test_director_post(req: KimiTestRequest):
    cfg = get_raw_config()
    endpoint = (req.endpoint or str(cfg.get("KIMI_DIRECTOR_ENDPOINT_API1", "") or cfg.get("NIM_ENDPOINT", "") or "")).strip()
    api_key = (req.api_key or str(cfg.get("KIMI_API_KEY", "") or "")).strip()
    model = (req.model or str(cfg.get("KIMI_INSTRUCT_MODEL", "") or "")).strip()
    if endpoint.startswith("https://") and not api_key:
        return {"status": "error", "error": "missing api key"}
    return await _test_chat_completion(endpoint, api_key, model)


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
    if endpoint.startswith("https://") and not api_key:
        return {"status": "error", "error": "missing api key"}
    return await _test_vision_completion(endpoint, api_key, model)


@app.get("/api/test/lmstudio")
async def api_test_lmstudio(host: str = "", port: int = 0):
    base = _normalize_lmstudio_base_url(host, port)
    url = f"{base}/v1/models"
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url)
        if r.status_code >= 400:
            return {"status": "error", "error": f"http {r.status_code}: {r.text[:200]}", "models": []}
        data = r.json()
        models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
        return {"status": "ok", "models": models, "latency_ms": int((time.time() - t0) * 1000), "message": f"{len(models)} model(s)"}
    except Exception as e:
        return {"status": "error", "error": str(e), "models": []}


@app.get("/api/lmstudio/status")
async def api_lmstudio_status(host: str = "", port: int = 0):
    base = _normalize_lmstudio_base_url(host, port)
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            loaded_resp = await client.get(f"{base}/v1/models")
            available_resp = await client.get(f"{base}/api/v1/models")
        if loaded_resp.status_code >= 400:
            return {"status": "error", "error": f"http {loaded_resp.status_code}: {loaded_resp.text[:200]}", "base_url": base}
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
            "loaded_models": loaded,
            "available_models": available,
            "loaded_count": len(loaded),
            "available_count": len(available),
            "hermes_usable": bool(loaded),
            "vision_usable": bool(loaded),
            "latency_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "base_url": base}


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
                cid = c.get("id", c.get("name", "")).lower().replace(" ", "_")
                if cid and cid not in _CHARACTERS_STORE:
                    _CHARACTERS_STORE[cid] = c
        except Exception:
            pass

    # Scan anchors dir for images, link them to existing characters or create stubs
    for img in CHARACTERS_ANCHORS_DIR.glob("*"):
        if img.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        # Derive character id from filename: e.g. "elara_vance.jpg" -> "elara"
        stem = img.stem.lower()
        parts = re.split(r'[_\s-]+', stem)
        cid = parts[0] if parts else stem
        anchor_url = f"/api/characters/anchor/{stem}"
        if cid in _CHARACTERS_STORE:
            _CHARACTERS_STORE[cid]["anchor_url"] = anchor_url
        elif cid:
            _CHARACTERS_STORE[cid] = {
                "id": cid,
                "name": stem.replace("_", " ").title(),
                "role": "Character",
                "accent": "cyan",
                "score": 0,
                "anchor_url": anchor_url,
                "anchor_prompt": "",
                "dna": {}
            }


def _persist_character(char_id: str, char_data: Dict[str, Any]) -> None:
    """Persist a character to a JSON file in character_banks."""
    out_path = CHARACTER_BANKS_DIR / f"char_{char_id}.json"
    with open(out_path, "w") as f:
        json.dump(char_data, f, indent=2)


_scan_character_files()


@app.get("/api/characters")
async def api_get_characters():
    """Return the full character list from the store."""
    return list(_CHARACTERS_STORE.values())


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
    char = _CHARACTERS_STORE.get(char_id)
    if not char:
        raise HTTPException(status_code=404, detail=f"Character '{char_id}' not found")
    return char


class SaveDNARequest(BaseModel):
    id: str
    dna: Dict[str, Any]


@app.post("/api/characters/save-dna")
async def api_save_character_dna(req: SaveDNARequest):
    """Persist updated character DNA to disk."""
    cid = req.id.lower().replace(" ", "_")
    if cid in _CHARACTERS_STORE:
        _CHARACTERS_STORE[cid]["dna"] = req.dna
        _persist_character(cid, _CHARACTERS_STORE[cid])
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
        _CHARACTERS_STORE[cid] = new_char
        _persist_character(cid, new_char)
        return {"status": "created", "message": f"Character {cid} created with DNA"}


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
    cid = (req.name or result.get("name", "unknown")).lower().replace(" ", "_")
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
    _CHARACTERS_STORE[cid] = char_entry
    _persist_character(cid, char_entry)
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
    host = (
        os.getenv("COMFYUI_PRIMARY", "")
        or str(cfg.get("COMFYUI_PRIMARY", ""))
        or str((cfg.get("comfyui", {}) if isinstance(cfg.get("comfyui"), dict) else {}).get("primary", ""))
        or ""
    ).strip().rstrip("/")
    if host and not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


@app.post("/api/characters/spark-render")
async def api_character_spark_render(req: CharacterSparkRenderRequest):
    safe_name = re.sub(r'[^a-z0-9]+', '_', req.name.lower().strip()).strip('_')
    if not safe_name:
        raise HTTPException(status_code=400, detail="Character name is required")
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")

    requested_type = (req.render_type or "character").strip().lower()
    if requested_type == "anchor":
        requested_type = "character"
    if requested_type not in {"character", "sheet", "variation"}:
        raise HTTPException(status_code=400, detail="render_type must be character, sheet, or variation")
    storage_type = "anchor" if requested_type == "character" else requested_type

    host = _character_host_from_config()
    if not host:
        raise HTTPException(status_code=400, detail="COMFYUI_PRIMARY is not configured. Turn on Spark or set the ComfyUI primary host in Settings.")

    workflow_path = _default_character_workflow_path(req.workflow_id)
    if not workflow_path:
        raise HTTPException(status_code=404, detail="No text-to-image workflow file found for character rendering")

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

    char = _CHARACTERS_STORE.get(safe_name, {
        "id": safe_name,
        "name": req.name.strip(),
        "role": (req.role or "Character").strip() or "Character",
        "accent": "cyan",
        "score": 0,
        "anchor_url": "",
        "anchor_prompt": "",
        "dna": {},
    })
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
        "created_at": _now_iso(),
    })
    if req.save_character:
        _CHARACTERS_STORE[safe_name] = char
        _persist_character(safe_name, char)

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
    }


@app.post("/api/characters/render")
async def api_render_character(req: RenderCharacterRequest):
    from core.dispatch.comfy_client import ComfyUIClient
    import json as _json

    workflow_path = Path("~/workflows/hermes_z_image_turbo_api.json")
    if not workflow_path.exists():
        workflow_path = Path(__file__).parent.parent / "workflows" / "z_image_turbo_api.json"
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail="No ComfyUI workflow file found")

    with open(workflow_path, "r") as f:
        workflow = _json.load(f)

    seed = req.seed or random.randint(1, 999_999_999)
    safe_name = re.sub(r'[^a-z0-9]+', '_', req.name.lower()).strip('_')
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
                prompt_block[node_id]["inputs"]["text"] = req.prompt
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
    return {"status": "complete", "anchor_url": f"/api/characters/anchor/{safe_name}", "prompt_id": prompt_id}


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
    anchor_image: UploadFile | None = Form(None),
):
    """Create a new character with an optional drag-drop character image."""
    import uuid as _uuid

    safe_name = re.sub(r'[^a-z0-9]+', '_', name.lower().strip()).strip('_')
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid character name")

    if safe_name in _CHARACTERS_STORE:
        raise HTTPException(status_code=409, detail=f"Character '{safe_name}' already exists")

    # Assign accent color from palette
    accents = ["cyan", "magenta", "amber", "green"]
    existing_accents = {c.get("accent") for c in _CHARACTERS_STORE.values()}
    accent = next((a for a in accents if a not in existing_accents), "cyan")

    # Save character image if provided
    anchor_url = ""
    if anchor_image and anchor_image.filename:
        raw_name = re.sub(r'[^a-z0-9]+', '_', Path(anchor_image.filename).stem.lower()).strip('_')
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

    # Build character record
    char_data = {
        "id": safe_name,
        "name": name.strip().upper(),
        "role": description[:60] if description else "Character",
        "description": description,
        "accent": accent,
        "score": 0,
        "anchor_url": anchor_url,
        "anchor_prompt": f"Portrait of {name.strip()}, {description or ''}",
        "dna": {},
    }

    # Persist to character_banks/char_{id}.json
    _CHARACTERS_STORE[safe_name] = char_data
    _persist_character(safe_name, char_data)

    # Append to world bible
    world_bible_path = Path(__file__).parent.parent / "data" / "lore_bible" / "world_bible.md"
    try:
        if world_bible_path.exists():
            wb_text = world_bible_path.read_text(encoding="utf-8")
        else:
            wb_text = ""

        char_section = (
            f"\n## KEY CHARACTER: {name.strip().upper()}\n"
            f"- **Role:** {description or 'Character'}\n"
            f"- **Character Image:** `{Path(final_name).stem}`\n\n"
        )
        if not world_bible_path.exists():
            world_bible_path.parent.mkdir(parents=True, exist_ok=True)
            wb_text = "# WORLD BIBLE: CHARACTER ROSTER\n\n" + char_section
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

    return {"status": "created", "character": char_data}


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
    """Return configured products. No synthetic product data is generated."""
    return {"status": "ok", "products": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000)
