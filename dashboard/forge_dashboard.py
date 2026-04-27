import json
import uuid
import time
from datetime import datetime
from typing import AsyncGenerator, List, Dict, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, UploadFile, Form
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
)
from .api.prompt_builder import load_banks, build_recipe, generate_random_recipe
from .api.spark_monitor import monitor as spark_monitor

STATIC_DIR = Path(__file__).parent / "static"

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

@app.post("/api/renders/audit-batch")
async def api_renders_audit_batch():
    """Performs a batch visual audit using local LM Studio Gemma 4 model."""
    repo_root = Path(__file__).parent.parent
    sienna_dir = repo_root / "dashboard" / "static" / "renders" / "sienna"
    anchor_path = repo_root / "data" / "character_banks" / "anchors" / "elara_vance.jpg"
    
    lmstudio_host = os.getenv("LMSTUDIO_HOST", "http://localhost:1234")
    vision_model = os.getenv("LMSTUDIO_VISION_MODEL", "gemma-4-26b-a4b-it")

    if not sienna_dir.exists():
        raise HTTPException(status_code=404, detail="Sienna renders directory not found.")
    if not anchor_path.exists():
        raise HTTPException(status_code=404, detail="Character anchor image not found.")

    async def audit_generator() -> AsyncGenerator[str, None]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # 1. Pre-encode Anchor
            with Image.open(anchor_path) as img:
                if img.mode != 'RGB': img = img.convert('RGB')
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                anchor_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            render_files = sorted([f for f in sienna_dir.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg")])
            
            for render_file in render_files:
                try:
                    # 2. Encode Render (with resizing)
                    with Image.open(render_file) as img:
                        if img.mode != 'RGB': img = img.convert('RGB')
                        if img.width > 1024 or img.height > 1024:
                            img.thumbnail((640, 640))
                        buffered = io.BytesIO()
                        img.save(buffered, format="JPEG")
                        render_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

                    # 3. Construct Prompt
                    prompt_text = (
                        "Compare the two images provided. Image 1 is a character render. "
                        "Image 2 is the official character reference for Elara Vance. "
                        "Elara has platinum crop hair, amber/gold eyes, a charcoal flight jacket with copper piping on seams, "
                        "and an ember-glow forearm tattoo. "
                        "Does Image 1 maintain high visual consistency with Image 2? "
                        "Respond ONLY with a JSON object in this format: "
                        '{"is_consistent": boolean, "confidence": float (0.0-1.0), "issues": ["issue1", "issue2"]}'
                    )

                    # 4. Call LM Studio
                    payload = {
                        "model": vision_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt_text},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{render_b64}"}},
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{anchor_b64}"}}
                                ]
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": 150
                    }

                    resp = await client.post(f"{lmstudio_host}/v1/chat/completions", json=payload)
                    if resp.status_code != 200:
                        raise Exception(f"LM Studio error: {resp.text}")

                    raw_content = resp.json()['choices'][0]['message']['content']
                    clean_json_str = re.sub(r'^```json\s*|```$', '', raw_content.strip(), flags=re.MULTILINE)
                    verdict = json.loads(clean_json_str)

                    # 5. Process Results
                    confidence = float(verdict.get("confidence", 0.0))
                    score = int(confidence * 100)
                    status = "PASS" if confidence >= 0.75 else "FAIL"
                    issues = verdict.get("issues", [])

                    # 6. Persistence (Sidecar)
                    sidecar_path = render_file.with_suffix(render_file.suffix + ".json")
                    sidecar_data = {
                        "score": score,
                        "status": status,
                        "issues": issues,
                        "confidence": confidence,
                        "timestamp": datetime.now().isoformat(),
                        "prompt": f"Sienna Nomad — {render_file.stem}" 
                    }
                    with open(sidecar_path, "w", encoding="utf-8") as sf:
                        json.dump(sidecar_data, sf, indent=2)

                    # 7. Stream result back
                    yield json.dumps({
                        "filename": render_file.name,
                        "status": status,
                        "score": score,
                        "error": None
                    }) + "\n"

                except Exception as e:
                    yield json.dumps({
                        "filename": render_file.name,
                        "error": str(e)
                    }) + "\n"

    return StreamingResponse(audit_generator(), media_type="application/x-ndjson")

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
    """Alias for /api/memory/stats — used by home view."""
    return get_memory_stats()

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

_data_renders_dir = Path(__file__).parent.parent / "data" / "renders"
if _data_renders_dir.exists():
    app.mount("/renders", StaticFiles(directory=str(_data_renders_dir)), name="data-renders")

# Serve campaigns folder for render outputs
_campaigns_dir = Path(__file__).parent.parent / "data" / "campaigns"
_campaigns_dir.mkdir(parents=True, exist_ok=True)
app.mount("/campaigns", StaticFiles(directory=str(_campaigns_dir)), name="campaigns")

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")



class ClearQueueRequest(BaseModel):
    comfy_url: str # e.g., http://localhost:8188

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


class UpdateShotRequest(BaseModel):
    shot_id: str
    prompt: str

class ReparseRequest(BaseModel):
    path: str = ""


@app.get("/api/shots")
async def api_get_shots():
    return _SHOTS_STORE


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


@app.post("/api/shots/dispatch-all")
async def api_shots_dispatch_all():
    from core.dispatch.comfy_client import ComfyUIClient
    client = ComfyUIClient("http://localhost:8188")
    dispatched = []
    errors = []
    for shot in _SHOTS_STORE:
        if shot["status"] in ("ready", "queued"):
            try:
                workflow = {"prompt": shot["prompt"], "seed": shot["seed"]}
                prompt_id = await client.submit_prompt(workflow)
                if prompt_id:
                    shot["status"] = "dispatched"
                    dispatched.append(shot["id"])
                else:
                    errors.append(shot["id"])
            except Exception as e:
                errors.append(f"{shot['id']}: {e}")
    return {"dispatched": dispatched, "errors": errors}


@app.post("/api/shots/dispatch")
async def api_shots_dispatch(req: ShotDispatchRequest):
    """Dispatches a specific shot prompt to Spark (ComfyUI)."""
    from core.dispatch.comfy_client import ComfyUIClient
    # Use the default primary URL from config if not provided, 
    # but here we'll assume it's configured in the client.
    client = ComfyUIClient("http://localhost:8188") 
    
    # We mimic the api_submit_recipe logic for a single shot
    workflow = {"prompt": req.prompt, "seed": req.seed} # Minimal mock workflow
    # Note: Real implementation would load a specific 'shot' workflow template.
    
    try:
        prompt_id = await client.submit_prompt(workflow)
        if prompt_id:
            spark_monitor.add_job(req.recipe if hasattr(req, 'recipe') else {"prompt": req.prompt}, 
                                 prompt_id, f"SHOT_{req.shot_id}")
            return {"status": "dispatched", "prompt_id": prompt_id}
        else:
            raise HTTPException(status_code=502, detail="ComfyUI submission failed.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/submit-recipe")
async def api_submit_recipe(req: SubmitRecipeRequest):
    """Submit a recipe to ComfyUI via Spark Monitor."""
    from core.dispatch.comfy_client import ComfyUIClient
    import json as _json

    workflow_path = Path(__file__).parent.parent / "workflows" / req.workflow_name
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow not found: {req.workflow_name}")

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = _json.load(f)

    # Simple prompt injection into CLIPTextEncode nodes
    prompt_text = req.recipe.get("prompt", "")
    prompt_block = workflow.get("prompt", workflow)
    for node_id, node in prompt_block.items():
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
            text = node.get("inputs", {}).get("text", "")
            negative_markers = ["blurry,", "low quality,", "distorted,", "worst quality,",
                                "deformed", "bad anatomy", "extra fingers", "watermark"]
            is_negative = len(text) < 200 and sum(1 for m in negative_markers if m in text.lower()) >= 2
            if not is_negative:
                prompt_block[node_id]["inputs"]["text"] = prompt_text

    # Inject seed
    seed = req.recipe.get("seed", 42)
    for node_id, node in prompt_block.items():
        if isinstance(node, dict):
            ct = node.get("class_type", "")
            if ct in ("KSampler", "SamplerCustom", "SamplerCustomAdvanced"):
                if "seed" in node.get("inputs", {}):
                    prompt_block[node_id]["inputs"]["seed"] = seed
            if ct in ("RandomNoise", "FluxNoise"):
                if "noise_seed" in node.get("inputs", {}):
                    prompt_block[node_id]["inputs"]["noise_seed"] = seed
            if ct == "SaveImage":
                prompt_block[node_id]["inputs"]["filename_prefix"] = req.recipe.get("filename", "FORGE")

    # Submit via ComfyUI client
    client = ComfyUIClient("http://localhost:8188")
    prompt_id = await client.submit_prompt(workflow)

    if prompt_id:
        spark_monitor.add_job(req.recipe, prompt_id, req.recipe.get("filename", "job"))
        return {"status": "queued", "prompt_id": prompt_id, "recipe": req.recipe}
    else:
        raise HTTPException(status_code=502, detail="ComfyUI submission failed")


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
    """
    Wire Hermes prompt -> ComfyUI workflow node injection before dispatch.
    Loads the named workflow, injects the prompt into the specified node,
    injects seed into sampler nodes, then submits to ComfyUI.
    """
    from core.dispatch.comfy_client import ComfyUIClient
    import json as _json

    workflow_path = Path(__file__).parent.parent / "workflows" / req.workflow_name
    if not workflow_path.exists():
        workflow_path = Path(__file__).parent.parent / "workflows" / (req.workflow_name + ".json")
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow not found: {req.workflow_name}")

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = _json.load(f)

    prompt_block = workflow.get("prompt", workflow)

    # Inject prompt into the target node (default "6")
    target = str(req.node_id)
    if target in prompt_block:
        node = prompt_block[target]
        if isinstance(node, dict):
            node["inputs"]["text"] = req.prompt
            print(f"[FORGE] Injected prompt into node {target}: {req.prompt[:80]}...")
    else:
        # Fallback: inject into first CLIPTextEncode that isn't negative
        for nid, node in prompt_block.items():
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
                text = node.get("inputs", {}).get("text", "")
                neg_markers = ["blurry,", "low quality,", "worst quality", "deformed"]
                if sum(1 for m in neg_markers if m in text.lower()) < 2:
                    node["inputs"]["text"] = req.prompt
                    print(f"[FORGE] Injected prompt into fallback node {nid}")
                    break

    # Inject seed into sampler nodes
    for nid, node in prompt_block.items():
        if isinstance(node, dict):
            ct = node.get("class_type", "")
            if ct in ("KSampler", "SamplerCustom", "SamplerCustomAdvanced"):
                if "seed" in node.get("inputs", {}):
                    prompt_block[nid]["inputs"]["seed"] = req.seed
            if ct in ("RandomNoise", "FluxNoise"):
                if "noise_seed" in node.get("inputs", {}):
                    prompt_block[nid]["inputs"]["noise_seed"] = req.seed
            if ct == "SaveImage":
                prompt_block[nid]["inputs"]["filename_prefix"] = req.filename

    # Submit to ComfyUI
    client = ComfyUIClient(req.comfy_url)
    prompt_id = await client.submit_prompt(workflow)

    if prompt_id:
        spark_monitor.add_job({"prompt": req.prompt, "seed": req.seed}, prompt_id, req.filename)
        await emit_hermes_event("prompt_injected", {
            "node_id": req.node_id,
            "prompt_id": prompt_id,
            "filename": req.filename,
            "prompt_preview": req.prompt[:100],
        })
        return {"status": "queued", "prompt_id": prompt_id, "node_id": req.node_id}
    else:
        raise HTTPException(status_code=502, detail="ComfyUI submission failed")


class RenderRequest(BaseModel):
    """Full render pipeline: inject prompt, submit, poll, download, save."""
    prompt: str = ""
    node_id: str = "6"
    workflow_name: str = "default.json"
    comfy_url: str = "http://localhost:8188"
    campaign: str = "default"
    filename: str = "FORGE"
    seed: int = 42
    poll_timeout: int = 300
    audit: bool = True  # Run Kimi-VL audit after render


class AuditRenderRequest(BaseModel):
    """Audit a specific render with Kimi-VL."""
    image_path: str = ""
    prompt: str = ""
    campaign: str = "default"


async def audit_render_with_kimi_vl(image_path: str, prompt: str = "", campaign: str = "default"):
    """
    Run Kimi-VL audit on a rendered image.
    Returns audit result dict with score, passed, feedback.
    """
    from pydantic import BaseModel, Field
    from core.bridge.kimi_vl_client import KimiVLClient

    class AuditResult(BaseModel):
        score: int = Field(0, description="Quality score 0-100")
        passed: bool = Field(True, description="Whether the render passed quality checks")
        feedback: str = Field("", description="Human-readable feedback")
        issues: list = Field(default_factory=list, description="List of detected issues")

    system_prompt = (
        "You are a visual quality auditor for AI-generated images. "
        "Evaluate the image for: composition, lighting, character consistency, "
        "artifact detection, prompt adherence, and overall cinematic quality. "
        "Be strict but fair. Score 0-100."
    )

    user_prompt = (
        f"Audit this rendered image. "
        f"Original prompt: {prompt[:200] if prompt else 'N/A'} "
        f"Campaign: {campaign}. "
        "Return a JSON object with score (0-100), passed (boolean), "
        "feedback (string), and issues (array of strings)."
    )

    try:
        client = KimiVLClient()
        result = await client.analyze_visuals(
            image_path=image_path,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=AuditResult,
            task_description=f"Audit render for campaign {campaign}"
        )
        print(f"[FORGE] [KIMI-VL] Audit result: score={result.get('score', 'N/A')}, passed={result.get('passed', 'N/A')}")
        return result
    except Exception as e:
        print(f"[FORGE] [KIMI-VL] Audit failed: {e}")
        return {
            "score": 0,
            "passed": False,
            "feedback": f"Audit failed: {str(e)}",
            "issues": [str(e)],
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
        "event_type": "audit_outcome",
        "session_id": campaign,
        "shot_id": Path(image_path).stem if image_path else "",
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
    """Audit a specific render with Kimi-VL and stream result."""
    result = await audit_render_with_kimi_vl(req.image_path, req.prompt, req.campaign)
    # Stream [KIMI-VL] result via WebSocket
    await emit_hermes_event("kimi_vl_audit", {
        "image_path": req.image_path,
        "campaign": req.campaign,
        "score": result.get("score", 0),
        "passed": result.get("passed", False),
        "feedback": result.get("feedback", ""),
        "issues": result.get("issues", []),
    })
    # Write to memory
    mem = await write_audit_to_memory(result, req.image_path, req.prompt, req.campaign)
    return {"audit": result, "memory": mem}


@app.post("/api/render")
async def api_render(req: RenderRequest):
    """
    Full render pipeline:
    1. Load workflow, inject prompt into node (default "6")
    2. Submit to ComfyUI
    3. Poll for completion
    4. Download PNG
    5. Save to data/campaigns/{campaign}/
    6. Emit render_complete event with image path
    """
    from core.dispatch.comfy_client import ComfyUIClient
    import json as _json

    # --- Step 1: Load workflow & inject prompt ---
    workflow_path = Path(__file__).parent.parent / "workflows" / req.workflow_name
    if not workflow_path.exists():
        workflow_path = Path(__file__).parent.parent / "workflows" / (req.workflow_name + ".json")
    if not workflow_path.exists():
        raise HTTPException(status_code=404, detail=f"Workflow not found: {req.workflow_name}")

    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = _json.load(f)

    prompt_block = workflow.get("prompt", workflow)

    # Inject prompt into target node
    target = str(req.node_id)
    if target in prompt_block:
        node = prompt_block[target]
        if isinstance(node, dict):
            node["inputs"]["text"] = req.prompt
    else:
        # Fallback: first non-negative CLIPTextEncode
        for nid, node in prompt_block.items():
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode":
                text = node.get("inputs", {}).get("text", "")
                neg_markers = ["blurry,", "low quality,", "worst quality", "deformed"]
                if sum(1 for m in neg_markers if m in text.lower()) < 2:
                    node["inputs"]["text"] = req.prompt
                    break

    # Inject seed + filename
    import random
    actual_seed = req.seed if req.seed else random.randint(100000, 999999)
    for nid, node in prompt_block.items():
        if isinstance(node, dict):
            ct = node.get("class_type", "")
            if ct in ("KSampler", "SamplerCustom", "SamplerCustomAdvanced"):
                if "seed" in node.get("inputs", {}):
                    prompt_block[nid]["inputs"]["seed"] = actual_seed
            if ct in ("RandomNoise", "FluxNoise"):
                if "noise_seed" in node.get("inputs", {}):
                    prompt_block[nid]["inputs"]["noise_seed"] = actual_seed
            if ct == "SaveImage":
                prompt_block[nid]["inputs"]["filename_prefix"] = req.filename

    # --- Step 2: Submit to ComfyUI ---
    client = ComfyUIClient(req.comfy_url)
    prompt_id = await client.submit_prompt(workflow)
    if not prompt_id:
        raise HTTPException(status_code=502, detail="ComfyUI submission failed")

    print(f"[FORGE] Submitted render {prompt_id} for campaign '{req.campaign}'")
    spark_monitor.add_job({"prompt": req.prompt, "seed": actual_seed}, prompt_id, req.filename)

    # --- Step 3: Poll for completion ---
    filename_on_server = await client.poll_job(prompt_id, timeout_sec=req.poll_timeout)
    if not filename_on_server:
        await emit_hermes_event("render_failed", {"prompt_id": prompt_id, "reason": "poll_timeout"})
        raise HTTPException(status_code=504, detail="Render timed out")

    # --- Step 4: Download outputs ---
    repo_root = Path(__file__).parent.parent
    campaigns_dir = repo_root / "data" / "campaigns" / req.campaign
    campaigns_dir.mkdir(parents=True, exist_ok=True)

    saved = await client.download_outputs(prompt_id, str(campaigns_dir))

    # --- Step 5: Emit render_complete event ---
    if saved:
        # Use relative path from repo root for the frontend
        rel_paths = [str(Path(p).relative_to(repo_root)) for p in saved]
        await emit_hermes_event("render_complete", {
            "prompt_id": prompt_id,
            "campaign": req.campaign,
            "files": saved,
            "relative_files": rel_paths,
            "filename": filename_on_server,
            "prompt_preview": req.prompt[:100],
        })
        print(f"[FORGE] Render complete: {saved}")

        # --- Step 6: Kimi-VL audit (if enabled) ---
        audit_result = None
        memory_event = None
        if req.audit and saved:
            print(f"[FORGE] Running Kimi-VL audit on {saved[0]}")
            audit_result = await audit_render_with_kimi_vl(
                saved[0], req.prompt, req.campaign
            )
            await emit_hermes_event("kimi_vl_audit", {
                "image_path": saved[0],
                "campaign": req.campaign,
                "score": audit_result.get("score", 0),
                "passed": audit_result.get("passed", False),
                "feedback": audit_result.get("feedback", ""),
                "issues": audit_result.get("issues", []),
            })
            # --- Step 7: Write to memory ---
            memory_event = await write_audit_to_memory(
                audit_result, saved[0], req.prompt, req.campaign
            )

            # --- Step 8: Remediation loop (if audit failed) ---
            max_retries = getattr(req, 'max_retries', 2)
            retry_count = 0
            current_prompt = req.prompt
            current_saved = saved

            while (not audit_result.get("passed", False) or
                   audit_result.get("score", 0) < getattr(req, 'audit_threshold', 0.6)) and \
                  retry_count < max_retries:
                retry_count += 1
                print(f"[FORGE] Audit failed (score={audit_result.get('score', 0)}), "
                      f"remediating (attempt {retry_count}/{max_retries})")

                # Get rewrite reason from audit feedback
                rewrite_reason = audit_result.get("feedback", "Audit failed")
                issues = audit_result.get("issues", [])
                if issues:
                    rewrite_reason += " | Issues: " + "; ".join(issues[:3])

                # Emit [RETRY] event
                await emit_hermes_event("remediation_retry", {
                    "retry_number": retry_count,
                    "max_retries": max_retries,
                    "original_score": audit_result.get("score", 0),
                    "rewrite_reason": rewrite_reason,
                    "original_prompt": current_prompt[:100],
                    "campaign": req.campaign,
                })

                # Call Hermes to analyze failure and generate corrected prompt
                corrected_prompt = None
                try:
                    from core.bridge.nous_hermes_bridge import NousHermesBridge
                    hermes_brain = NousHermesBridge()
                    if hermes_brain.is_available:
                        diagnosis = await hermes_brain.analyze_failure(
                            visual_audit_result=audit_result,
                            original_prompt=current_prompt,
                        )
                        if diagnosis and isinstance(diagnosis, dict):
                            corrected_prompt = diagnosis.get("fix_prompt", "")
                            root_cause = diagnosis.get("root_cause", "Unknown")
                            print(f"[FORGE] Hermes diagnosis: {root_cause}")
                            print(f"[FORGE] Corrected prompt: {corrected_prompt[:100]}...")
                except Exception as e:
                    print(f"[FORGE] Hermes analysis failed: {e}")

                # Fallback: if Hermes couldn't generate a fix, use audit feedback
                if not corrected_prompt:
                    corrected_prompt = current_prompt + " | FIX: " + rewrite_reason
                    print(f"[FORGE] Using fallback prompt with audit feedback")

                # Re-render with corrected prompt
                try:
                    # Re-submit with corrected prompt
                    re_client = ComfyUIClient(req.comfy_url)
                    re_workflow = await client.load_workflow(req.workflow)
                    re_workflow = await client.inject_prompt(re_workflow, corrected_prompt, req.target_node)
                    re_prompt_id = await re_client.submit_prompt(re_workflow)
                    if not re_prompt_id:
                        raise HTTPException(status_code=502, detail="ComfyUI re-submission failed")

                    print(f"[FORGE] Submitted retry render {re_prompt_id}")
                    spark_monitor.add_job(
                        {"prompt": corrected_prompt, "seed": actual_seed, "retry": retry_count},
                        re_prompt_id, req.filename + f"_retry{retry_count}"
                    )

                    # Poll for completion
                    re_filename = await re_client.poll_job(re_prompt_id, timeout_sec=req.poll_timeout)
                    if not re_filename:
                        await emit_hermes_event("render_failed", {
                            "prompt_id": re_prompt_id, "reason": "poll_timeout_retry"
                        })
                        raise HTTPException(status_code=504, detail="Retry render timed out")

                    # Download retry outputs
                    retry_dir = campaigns_dir / f"retry_{retry_count}"
                    retry_dir.mkdir(parents=True, exist_ok=True)
                    retry_saved = await re_client.download_outputs(re_prompt_id, str(retry_dir))

                    if retry_saved:
                        current_saved = retry_saved
                        current_prompt = corrected_prompt
                        rel_retry_paths = [str(Path(p).relative_to(repo_root)) for p in retry_saved]
                        await emit_hermes_event("render_complete", {
                            "prompt_id": re_prompt_id,
                            "campaign": req.campaign,
                            "files": retry_saved,
                            "relative_files": rel_retry_paths,
                            "filename": re_filename,
                            "prompt_preview": corrected_prompt[:100],
                            "retry": retry_count,
                        })
                        print(f"[FORGE] Retry render complete: {retry_saved}")

                        # Re-audit the retry render
                        audit_result = await audit_render_with_kimi_vl(
                            retry_saved[0], corrected_prompt, req.campaign
                        )
                        await emit_hermes_event("kimi_vl_audit", {
                            "image_path": retry_saved[0],
                            "campaign": req.campaign,
                            "score": audit_result.get("score", 0),
                            "passed": audit_result.get("passed", False),
                            "feedback": audit_result.get("feedback", ""),
                            "issues": audit_result.get("issues", []),
                            "retry": retry_count,
                        })

                        # Write retry audit to memory
                        memory_event = await write_audit_to_memory(
                            audit_result, retry_saved[0], corrected_prompt, req.campaign
                        )
                    else:
                        break
                except HTTPException:
                    raise
                except Exception as e:
                    print(f"[FORGE] Retry render failed: {e}")
                    break

            # Emit final remediation status
            final_passed = audit_result.get("passed", False) if audit_result else False
            final_score = audit_result.get("score", 0) if audit_result else 0
            await emit_hermes_event("remediation_complete", {
                "campaign": req.campaign,
                "final_score": final_score,
                "final_passed": final_passed,
                "retries_used": retry_count,
                "max_retries": max_retries,
                "resolved": final_passed and final_score >= getattr(req, 'audit_threshold', 0.6),
            })

        return {
            "status": "complete",
            "prompt_id": prompt_id,
            "campaign": req.campaign,
            "files": saved,
            "relative_files": rel_paths,
            "audit": audit_result,
            "memory": memory_event,
        }
    else:
        await emit_hermes_event("render_failed", {"prompt_id": prompt_id, "reason": "no_outputs"})
        raise HTTPException(status_code=502, detail="No outputs found after render")


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
    """Return current configuration (merged .env + JSON overrides). API key is masked."""
    from core.bridge.runtime_config import get_config
    return get_config()


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
    data: Dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        return self.data.get(key)


@app.post("/api/config/save")
async def api_config_save(req: FlatConfigUpdateRequest):
    """Save individual config fields directly to data/config.json."""
    from core.bridge.runtime_config import set_config, apply_to_environment
    updated = set_config(dict(req.data))
    apply_to_environment()
    return {"status": "saved", "config": updated}


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
    host = os.getenv("COMFYUI_PRIMARY", "http://localhost:8188").rstrip("/")
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

    client = ComfyUIClient("http://localhost:8188")
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
