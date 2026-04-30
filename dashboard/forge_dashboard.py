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
from pathlib import Path
import httpx
from PIL import Image
import io

# ... (existing imports from top of file)
from core.bridge.kimi_vl_client import KimiVLClient
from core.bridge.lmstudio_client import LMStudioClient
from core.bridge.config_manager import ConfigManager
from core.hermes.memory.episodic_memory import EpisodicMemory
from core.hermes.memory.semantic_memory import SemanticMemory
from core.skills.skill_registry import SkillRegistry
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
from core.hermes.pipeline import HermesCampaignService, CampaignRequest, HermesAuditService

STATIC_DIR = Path(__file__).parent / "static"
REPO_ROOT = Path(__file__).parent.parent.resolve()
MEDIA_ROOT = Path(os.getenv("FORGE_MEDIA_ROOT", "/Users/zgbot/Desktop/FORGE_NPS_MEDIA"))
MEDIA_IMAGES = MEDIA_ROOT / "images"
MEDIA_IMAGES.mkdir(parents=True, exist_ok=True)

app = FastAPI()

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

# Mock Data Storage (In-memory for demo)
sessions_db = {}
skills_registry = [
    {"name": "Visual Generation", "status": "ready"},
    {"name": "Continuity Auditing", "status": "active"},
    {"name": "Script Synthesis", "status": "ready"},
    {"name": "Lore Consistency", "status": "idle"}
]

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
    return sessions_db.get(session_id, {"status": "not_found"})

@app.get("/api/skills")
async def get_skills():
    return skills_registry

@app.get("/api/reasoning/{shot_id}")
async def get_reasoning(shot_id: str):
    return {
        "shot_id": shot_id,
        "content": f"Reasoning for shot {shot_id}: Analyzing visual consistency with lore bible..."
    }

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
        "chat_sessions": len(sessions_db),
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
    # In a real implementation, this would call client.cancel_all() or similar
    # For now, we simulate the interaction with the backend logic
    try:
        # Assuming client has a method to clear queue via /queue DELETE (as per user prompt)
        # If not implemented, we'll mock it for now but follow the architecture.
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

    # Fallback mock data if no renders on disk
    if not results:
        results = [
            {"src": "/static/renders/placeholder.png", "prompt": "Elara Vance portrait, cyberpunk neon glow", "score": 92, "status": "PASS"},
            {"src": "/static/renders/placeholder.png", "prompt": "Concept art: neon alleyway, rain reflections", "score": 87, "status": "PASS"},
            {"src": "/static/renders/placeholder.png", "prompt": "Character turnaround sheet — Elara", "score": 95, "status": "PASS"},
            {"src": "/static/renders/placeholder.png", "prompt": "Orin workshop interior, forge glow", "score": 78, "status": "PASS"},
            {"src": "/static/renders/placeholder.png", "prompt": "Vex-09 drone patrol, night city", "score": 88, "status": "PASS"},
            {"src": "/static/renders/placeholder.png", "prompt": "Elara without hair color (injected error)", "score": 34, "status": "FAIL"},
        ]
    return results

# --- WebSocket ---

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await manager.connect(websocket, session_id)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "START_MOCK":
                asyncio.create_task(run_mock_stream(session_id))
    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)

# --- Mock Stream Generator ---

async def run_mock_stream(session_id: str):
    """Simulates Kimi and Hermes thinking."""
    events = [
        {"type": "SHOT_STARTED", "payload": {"shot_id": "SHOT_001", "name": "The Neon Ghost"}},
        {"type": "KIMI_THINKING", "payload": {"text": "Analyzing character visual consistency..."}},
        {"type": "HERMES_ACTION", "payload": {"action": "checking_lore_bible", "target": "Elara Vance"}},
        {"type": "REASONING_UPDATE", "payload": {"shot_id": "SHOT_001", "content": "Visuals match Elara's signature aesthetic."}},
        {"type": "AUTONOMY_SCORE", "payload": {"score": 85, "trend": "up"}},
        {"type": "SKILL_USED", "payload": {"skill": "Continuity Auditing", "result": "SUCCESS"}},
    ]
    
    for event in events:
        await asyncio.sleep(2)
        await manager.broadcast(event, session_id)

# --- Startup & Mounts ---

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/external-renders", StaticFiles(directory=str(MEDIA_IMAGES)), name="external-renders")

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



class ClearQueueRequest(BaseModel):
    comfy_url: str # e.g., http://100.74.164.1:8188

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


# --- In-memory shots store (seeded with demo data) ---
_SHOTS_STORE: List[Dict[str, Any]] = [
    {"id": "SHOT_001", "n": 1, "chars": ["Elara"], "status": "ready",
     "prompt": "Elara Vance, emerald iris, auburn hair lit by amber forge glow, 3/4 portrait, shallow DOF",
     "seed": 849271},
    {"id": "SHOT_002", "n": 2, "chars": ["Elara", "Orin"], "status": "ready",
     "prompt": "Elara and Orin in mechanist workshop, blue-steel tools, rim lighting, cinematic wide",
     "seed": 849272},
    {"id": "SHOT_003", "n": 3, "chars": ["Vex-09"], "status": "queued",
     "prompt": "Vex-09 drone, neon city patrol, rain-slicked streets, lens flare, extreme low angle",
     "seed": 849273},
    {"id": "SHOT_004", "n": 4, "chars": ["Elara"], "status": "queued",
     "prompt": "Elara reading schematics, overexposed window behind, moody contrast, close-up hands",
     "seed": 849274},
]
_CAMPAIGNS: Dict[str, Dict[str, Any]] = {}
_ACTIVE_CAMPAIGN: Optional[str] = None
_CANCEL_CAMPAIGN = False


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _find_shot(shot_id: str) -> Optional[Dict[str, Any]]:
    for s in _SHOTS_STORE:
        if s.get("id") == shot_id:
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

class ReparseRequest(BaseModel):
    path: str = ""

class RenameCampaignRequest(BaseModel):
    old_campaign_id: str
    new_campaign_name: str


@app.get("/api/shots")
async def api_get_shots():
    return {
        "shots": _SHOTS_STORE,
        "count": len(_SHOTS_STORE),
        "active_campaign_id": _ACTIVE_CAMPAIGN,
    }


@app.post("/api/shots/reindex-storage")
async def api_reindex_shots_from_storage():
    """
    Rehydrate shot records from on-disk render folders so historical campaigns
    appear again in Dashboard/Video after server restarts or store drift.
    """
    roots = [
        ("external", MEDIA_IMAGES, "/external-renders", "campaign"),
        ("campaigns", REPO_ROOT / "data" / "campaigns", "/campaigns", "campaign"),
        ("renders_campaigns", REPO_ROOT / "data" / "renders" / "campaigns", "/renders/campaigns", "campaign"),
    ]

    image_exts = {".png", ".jpg", ".jpeg", ".webp"}
    rebuilt: List[Dict[str, Any]] = []
    seen_ids = set()

    def _guess_campaign_and_shot(stem: str, rel_parts: List[str]) -> tuple[str, str]:
        campaign = ""
        shot = ""
        if rel_parts:
            campaign = rel_parts[0]
        # Common id pattern: <campaign>__SHOT_001__workflow
        if "__SHOT_" in stem:
            parts = stem.split("__")
            if not campaign and parts:
                campaign = parts[0]
            for p in parts:
                if p.startswith("SHOT_"):
                    shot = p
                    break
        if not campaign:
            campaign = "legacy"
        if not shot:
            shot = stem[:40]
        return campaign, shot

    for mount_name, root, url_prefix, source in roots:
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in image_exts:
                continue
            stem = f.stem
            rel = f.relative_to(root)
            rel_parts = list(rel.parts[:-1])
            campaign_id, shot_id = _guess_campaign_and_shot(stem, rel_parts)
            record_id = stem
            if record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            image_url = f"{url_prefix}/{rel.as_posix()}" if mount_name != "external" else f"{url_prefix}/{rel.as_posix()}"
            rebuilt.append({
                "id": record_id,
                "campaign_id": campaign_id,
                "shot_id": shot_id,
                "sequence": 0,
                "workflow_id": "reindexed_media",
                "status": "complete",
                "state": "rendered",
                "seed": None,
                "prompt": f"Reindexed media: {stem}",
                "compiled_prompt": f"Reindexed media: {stem}",
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
                "image_path": str(f),
                "image_url": image_url,
                "created_at": _now_iso(),
            })

    # Preserve any existing non-media script shots, but prioritize media records.
    non_media = [s for s in _SHOTS_STORE if not s.get("image_url")]
    _SHOTS_STORE.clear()
    _SHOTS_STORE.extend(rebuilt + non_media)

    return {
        "status": "ok",
        "reindexed": len(rebuilt),
        "preserved_non_media": len(non_media),
        "count": len(_SHOTS_STORE),
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
        shot_count = len(matching)
        meta = _CAMPAIGNS.get(cid, {}) if isinstance(_CAMPAIGNS.get(cid, {}), dict) else {}
        inferred_brief = str(meta.get("brief", "") or "")
        if not inferred_brief:
            for s in matching:
                b = str(s.get("campaign_brief", "") or "").strip()
                if b:
                    inferred_brief = b
                    break
        if not inferred_brief:
            inferred_brief = _brief_from_campaign_manifest(cid)
        if not inferred_brief:
            # Last-resort for older campaigns: humanize campaign id slug.
            inferred_brief = _humanize_campaign_id(cid)
        campaigns.append({
            "campaign_id": cid,
            "shot_count": shot_count,
            "active": cid == _ACTIVE_CAMPAIGN,
            "brief": inferred_brief,
            "started_at": str(meta.get("started_at", "") or ""),
        })

    return {
        "campaigns": campaigns,
        "count": len(campaigns),
        "active_campaign_id": _ACTIVE_CAMPAIGN,
    }


def _safe_campaign_name(raw: str) -> str:
    # Keep this filesystem-safe and UI-friendly.
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", (raw or "").strip())
    name = re.sub(r"_+", "_", name).strip("._-")
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


def _humanize_campaign_id(cid: str) -> str:
    if not cid:
        return ""
    base = cid
    if "__" in cid:
        left, right = cid.rsplit("__", 1)
        if re.fullmatch(r"[a-f0-9]{6,12}", right):
            base = left
    return base.replace("__", " ").replace("_", " ").strip()


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


class ReAuditRequest(BaseModel):
    shot_ids: List[str]


class RemediateRequest(BaseModel):
    shot_ids: List[str]
    max_retries: int = 1


class ImportBatchRequest(BaseModel):
    report_path: str


def _workflow_file_for_id(workflow_id: str) -> Optional[Path]:
    candidates = [
        REPO_ROOT / "workflows" / f"{workflow_id}.json",
        REPO_ROOT / "workflows" / f"{workflow_id}_api.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


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
    c2 = MEDIA_IMAGES / Path(image_url).name
    if c2.exists():
        return c2
    return None


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


@app.post("/api/hermes/cancel")
async def api_hermes_cancel():
    global _CANCEL_CAMPAIGN
    _CANCEL_CAMPAIGN = True
    return {"status": "ok", "cancelled": True}


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
        )
        payload = CampaignRequest(
            brief=req.brief,
            bible_path=req.bible_path,
            length=req.length,
            workflow_ids=req.workflow_ids,
        )
        async for event in service.stream_campaign(payload):
            yield json.dumps(event) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")


@app.post("/api/audit/reprocess")
async def api_audit_reprocess(req: ReAuditRequest):
    service = _make_audit_service()
    return await service.reprocess(req.shot_ids)


@app.post("/api/audit/remediate")
async def api_audit_remediate(req: RemediateRequest):
    service = _make_audit_service()
    return await service.remediate(req.shot_ids, max_retries=req.max_retries)


@app.post("/api/import/sienna-batch")
async def api_import_sienna_batch(req: ImportBatchRequest):
    report_path = Path(req.report_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {report_path}")
    if report_path.is_dir():
        files = sorted([p for p in report_path.rglob("*") if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])
    elif report_path.suffix.lower() in {".json"}:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            files = []
            for item in report.get("images", []):
                p = Path(item) if Path(item).is_absolute() else report_path.parent / item
                if p.exists():
                    files.append(p)
        except Exception:
            files = []
    else:
        files = [report_path]

    imported = 0
    updated_existing = 0
    for f in files:
        stem = f.stem
        shot_id = f"sienna_{stem}"
        existing = _find_shot(shot_id)
        shot_payload = {
            "id": shot_id,
            "campaign_id": "import",
            "shot_id": shot_id,
            "sequence": 0,
            "workflow_id": "imported_media",
            "status": "rendered",
            "state": "rendered",
            "seed": None,
            "prompt": f"Imported media: {stem}",
            "compiled_prompt": f"Imported media: {stem}",
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
            "image_path": str(f),
            "image_url": f"/external-renders/{f.name}",
            "created_at": _now_iso(),
        }
        if existing:
            existing.update(shot_payload)
            updated_existing += 1
        else:
            _SHOTS_STORE.append(shot_payload)
            imported += 1

    _record_pipeline_event(
        "import_completed",
        campaign_id="import",
        source="import",
        extra={"imported": imported, "updated_existing": updated_existing, "report_path": str(report_path)},
    )
    return {"status": "ok", "imported": imported, "updated_existing": updated_existing, "report": str(report_path)}


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
    comfy_url: str = "http://100.74.164.1:8188"
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
    comfy_url: str = "http://100.74.164.1:8188"
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
    for check_key, keywords in _AUDIT_KEYWORD_TO_CHECK.items():
        if any(k in merged_text for k in keywords):
            checks[check_key] = False
    return checks


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


async def _run_audit_pass(
    client: Any,
    image_path: str,
    system_prompt: str,
    user_prompt: str,
    task_description: str,
) -> Dict[str, Any]:
    result = await client.analyze_visuals(
        image_path=image_path,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=FullImageAuditSchema,
        task_description=task_description,
    )
    if not isinstance(result, dict):
        return {}
    return result


async def audit_render_with_kimi_vl(image_path: str, prompt: str = "", campaign: str = "default"):
    """
    Run Kimi-VL audit on a rendered image.
    Returns audit result dict with score, passed, feedback.
    """
    from core.bridge.kimi_vl_client import KimiVLClient

    try:
        client = KimiVLClient()
        cinematic_system_prompt = (
            "You are an image quality auditor. "
            "Score cinematic composition, lighting quality, prompt adherence, and visible artifacts."
        )
        cinematic_user_prompt = (
            f"Audit this full image for campaign '{campaign}'. "
            f"Original prompt excerpt: {prompt[:240] if prompt else 'N/A'}. "
            "Return JSON with keys: overall_score (0-100), model_passed (bool), confidence (0-1), "
            "checks object with booleans for hands_ok, limbs_ok, face_ok, reflection_ok, vehicle_geometry_ok, "
            "text_artifacts_ok, prompt_adherence_ok, plus critical_failures (array), noncritical_issues (array), "
            "feedback (string), issues (array)."
        )

        forensic_system_prompt = (
            "You are a forensic visual consistency auditor. "
            "Be strict on anatomy, reflections, and physical plausibility."
        )
        forensic_user_prompt = (
            f"Inspect this full image for hard failures. Campaign '{campaign}'. "
            "Explicitly verify: "
            "1) human hand/finger count and structure, "
            "2) extra or impossible limbs, "
            "3) mirror/window reflection consistency with scene geometry, "
            "4) vehicle body/wheel/door geometry consistency, "
            "5) deformed faces, "
            "6) text/watermark artifacts. "
            "Return JSON in the same schema as requested in the other pass."
        )

        pass_a = await _run_audit_pass(
            client=client,
            image_path=image_path,
            system_prompt=cinematic_system_prompt,
            user_prompt=cinematic_user_prompt,
            task_description=f"Cinematic audit for {campaign}",
        )
        pass_b = await _run_audit_pass(
            client=client,
            image_path=image_path,
            system_prompt=forensic_system_prompt,
            user_prompt=forensic_user_prompt,
            task_description=f"Forensic audit for {campaign}",
        )
        result = _aggregate_audit_results(pass_a, pass_b)
        print(
            "[FORGE] [KIMI-VL] Audit result: "
            f"backend_score={result.get('score', 'N/A')}, "
            f"final_passed={result.get('passed', 'N/A')}, "
            f"model_passed={result.get('model_passed', 'N/A')}"
        )
        return result
    except Exception as e:
        print(f"[FORGE] [KIMI-VL] Audit failed: {e}")
        return {
            "score": 0,
            "passed": False,
            "feedback": f"Audit failed: {str(e)}",
            "issues": [str(e)],
            "overall_score": 0,
            "model_score": 0,
            "checks_score": 0,
            "confidence": 0,
            "model_passed": False,
            "final_passed": False,
            "checks": {k: False for k in _AUDIT_CHECK_KEYS},
            "critical_failures": ["audit_execution_failure"],
            "noncritical_issues": [],
            "audit_decision_reasons": ["audit_execution_failure"],
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
    concept: str = "Elara Vance portrait, cyberpunk neon glow"
    error_type: str = "strip_hair_color"  # strip_hair_color | wrong_lighting | remove_anchor


@app.post("/api/hermes/teach")
async def api_hermes_teach(req: TeachModeRequest):
    """
    Run a controlled teach cycle:
    1. Inject deliberate error
    2. Generate (simulated if Spark down)
    3. Record failure + fix
    4. Trigger consolidation
    5. Return before/after trace
    """
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
    # Auto-detect LM Studio model at startup
    from core.bridge.lmstudio_client import LMStudioClient
    local = LMStudioClient()
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
        print("[FORGE] LM Studio not reachable at startup")
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
    lm_model = str(cfg.get("LMSTUDIO_CHAT_MODEL", "") or "")
    vision_model = str(cfg.get("KIMI_VISUAL_MODEL", "") or os.getenv("LMSTUDIO_VISION_MODEL", ""))
    return {
        "backend_mode": "remote" if endpoint.startswith("http") else "local",
        "kimi": {
            "api_key_set": bool(kimi_key),
            "endpoint": endpoint,
        },
        "models": {
            "director_kimi": {"model_name": str(cfg.get("KIMI_INSTRUCT_MODEL", "moonshotai/kimi-k2")), "endpoint": endpoint},
            "kimi_vl": {"model_name": vision_model, "endpoint": endpoint},
            "hermes_3": {
                "host": lm_host,
                "port": 1234 if lm_host else "",
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
        "kimi.api_key": "KIMI_API_KEY",
        "kimi.endpoint": "NIM_ENDPOINT",
        "models.director_kimi.model_name": "KIMI_INSTRUCT_MODEL",
        "models.director_kimi.endpoint": "NIM_ENDPOINT",
        "models.kimi_vl.model_name": "KIMI_VISUAL_MODEL",
        "models.kimi_vl.endpoint": "NIM_ENDPOINT",
        "models.hermes_3.host": "LMSTUDIO_HOST",
        "models.hermes_3.model_name": "LMSTUDIO_CHAT_MODEL",
        "comfyui.primary": "COMFYUI_PRIMARY",
        "comfyui.secondary": "COMFYUI_SECONDARY",
        "spark.primary": "COMFYUI_PRIMARY",
        "spark.secondary": "COMFYUI_SECONDARY",
    }
    for k, v in (updates or {}).items():
        mapped[key_map.get(k, k)] = v
    updated = set_config(mapped)
    apply_to_environment()
    return {"status": "success", "saved": list(mapped.keys()), "config": updated}


class KimiTestRequest(BaseModel):
    api_key: str
    endpoint: str


@app.post("/api/test/kimi")
async def api_test_kimi(req: KimiTestRequest):
    endpoint = (req.endpoint or "").strip().rstrip("/")
    if endpoint and not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/chat/completions"
    payload = {
        "model": os.getenv("KIMI_INSTRUCT_MODEL", "moonshotai/kimi-k2"),
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 8,
    }
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {req.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        if r.status_code >= 400:
            return {"status": "error", "error": f"http {r.status_code}: {r.text[:200]}"}
        latency_ms = int((time.time() - t0) * 1000)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/test/lmstudio")
async def api_test_lmstudio(host: str = "http://127.0.0.1", port: int = 1234):
    base = (host or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1"
    if not base.startswith("http://") and not base.startswith("https://"):
        base = "http://" + base
    url = f"{base}:{int(port)}/v1/models"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url)
        if r.status_code >= 400:
            return {"status": "error", "error": f"http {r.status_code}: {r.text[:200]}", "models": []}
        data = r.json()
        models = [m.get("id") for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
        return {"status": "ok", "models": models}
    except Exception as e:
        return {"status": "error", "error": str(e), "models": []}


@app.get("/api/test/nim")
async def api_test_nim():
    cm = ConfigManager()
    endpoint = (cm.get("NIM_ENDPOINT", "") or cm.get_nim_endpoint() or "").strip().rstrip("/")
    if endpoint and not endpoint.endswith("/chat/completions"):
        endpoint = endpoint + "/chat/completions"
    api_key = cm.get_kimi_api_key()
    if not endpoint:
        return {"status": "error", "error": "missing endpoint"}
    if not api_key:
        return {"status": "error", "error": "missing api key"}
    payload = {
        "model": cm.get("KIMI_INSTRUCT_MODEL", "moonshotai/kimi-k2"),
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
        return {"status": "ok", "latency_ms": int((time.time() - t0) * 1000), "endpoint": endpoint}
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
    host = (os.getenv("COMFYUI_PRIMARY", "") or str(cfg.get("COMFYUI_PRIMARY", "")) or "http://100.112.87.8:8188").rstrip("/")
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

# Seed with Elara Vance (the only character with a real anchor image)
_CHARACTERS_STORE["elara"] = {
    "id": "elara",
    "name": "ELARA",
    "role": "Pilot · Protagonist",
    "accent": "cyan",
    "score": 94,
    "anchor_url": "/api/characters/anchor/elara_vance",
    "anchor_prompt": "Portrait of ELARA, female pilot protagonist, platinum crop hair with undercut left side and singed tips, pale amber reflective eyes, lean athletic build, charcoal flight jacket over graphite undersuit with copper piping along seams, ember-glow tattoo on left forearm, softbox studio lighting, neutral dark background, highly detailed, cinematic, 8k",
    "dna": {
        "hair": "Platinum crop, undercut left side, singed tips from the Hollow",
        "eyes": "Pale amber, reflective — pupils dilate in low-light",
        "build": "Lean, 5'8\", defined shoulders from high-g maneuvers",
        "clothing": "Charcoal flight jacket over graphite undersuit, copper piping along seams",
        "signature": "Left forearm: ember-glow tattoo — a spiralling sigil, always visible",
        "palette": ["#C4A57A", "#2A2E35", "#E9A74B"]
    }
}


def _scan_character_files() -> None:
    """Scan character_banks for JSON character files and anchor images, merge into store."""
    # Load character JSON files (skip demo_* files)
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

    client = ComfyUIClient("http://100.112.87.8:8188")
    prompt_id = await client.submit_prompt(workflow)
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
    raise HTTPException(status_code=404, detail=f"No anchor image for '{name}'")


class NewCharacterRequest(BaseModel):
    name: str
    description: Optional[str] = ""


@app.post("/api/characters")
async def api_create_character(
    name: str = Form(...),
    description: str = Form(""),
    anchor_image: UploadFile | None = Form(None),
):
    """Create a new character with an optional drag-drop anchor image."""
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

    # Save anchor image if provided
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
            f"- **Anchor Image:** `{Path(final_name).stem}`\n\n"
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

    profile = req.profile if req.profile in HERMES_PROFILES else "live"

    async def event_generator():
        try:
            # Emit initial event
            yield f"data: {_json.dumps({'type': 'chat_start', 'profile': profile})}\n\n"

            # Try NousHermesBridge first (faster, local model)
            try:
                from core.bridge.nous_hermes_bridge import NousHermesBridge
                hermes_brain = NousHermesBridge()
                if hermes_brain.is_available:
                    response = await hermes_brain.chat([
                        {"role": "user", "content": req.message}
                    ])
                    # Stream in chunks for visual effect
                    chunk_size = 20
                    for i in range(0, len(response), chunk_size):
                        chunk = response[i:i + chunk_size]
                        yield f"data: {_json.dumps({'type': 'chat_chunk', 'content': chunk})}\n\n"
                        await asyncio.sleep(0.02)  # Small delay for visual streaming
                    yield f"data: {_json.dumps({'type': 'chat_complete', 'full_response': response})}\n\n"
                    return
            except Exception as e:
                print(f"[FORGE] NousHermesBridge chat failed, falling back to CLI: {e}")

            # Fallback: use Hermes CLI launcher
            if not os.path.exists(FORGE_HERMES_LAUNCHER):
                yield f"data: {_json.dumps({'type': 'chat_error', 'error': 'Hermes engine not found'})}\n\n"
                return

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
                output = stdout.decode("utf-8", errors="replace").strip()
                if not output and stderr:
                    err = stderr.decode("utf-8", errors="replace").strip()
                    yield f"data: {_json.dumps({'type': 'chat_error', 'error': err[:300]})}\n\n"
                    return
                # Stream the output in chunks
                chunk_size = 20
                for i in range(0, len(output), chunk_size):
                    chunk = output[i:i + chunk_size]
                    yield f"data: {_json.dumps({'type': 'chat_chunk', 'content': chunk})}\n\n"
                    await asyncio.sleep(0.02)
                yield f"data: {_json.dumps({'type': 'chat_complete', 'full_response': output})}\n\n"
            except asyncio.TimeoutError:
                proc.kill()
                yield f"data: {_json.dumps({'type': 'chat_error', 'error': 'Hermes response timed out'})}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'type': 'chat_error', 'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000)


@app.get("/api/products")
async def api_get_products():
    """Returns the list of products for the Products tab."""
    # In a real production setup, this would fetch from a database or file.
    # For now, we return the data defined in data.js via a mock/static approach 
    # since the backend doesn't directly share JS files.
    return {
        "products": [
            {
                "id": "emberdrive_mk2",
                "name": "Emberdrive Mk-II",
                "description": "High-performance propulsion module designed for deep-space maneuvers and rapid atmospheric entry.",
                "anchor_prompt": "Studio product photography of Emberdrive Mk-II, sleek obsidian chassis with glowing amber heat sinks, internal turbine components visible through semi-transparent casing, macro lens detail, dramatic rim lighting, dark technical background, 8k"
            }
        ]
    }
