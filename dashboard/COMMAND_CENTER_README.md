# Forge NPS — Command Center Dashboard

FastAPI dashboard for the Forge NPS pipeline. Port 7000. Obsidian Studio UI.

---

## Start

```bash
cd <forge_nps_v01>
KIMI_API_KEY="nvapi-..." python3 forge_dashboard.py
```

Env vars loaded from `.env` in dashboard dir, then parent dir. `KIMI_API_KEY` is normally read from repo `.env`; the value in `data/config.json` may be masked.

On startup:
1. Loads `data/config.json`
2. Queries LM Studio `/v1/models` — auto-detects loaded model, no hardcoding
3. Initializes `NousHermesBridge`, `KimiBridge`, `ComfyUIClient`
4. Emits `lmstudio_detected` / `lmstudio_offline` WebSocket event

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve index.html |
| POST | `/api/hermes/chat` | Stream Hermes chat response (SSE) |
| POST | `/api/hermes/run-campaign` | Full pipeline: brief → shots → renders (NDJSON stream) |
| POST | `/api/render` | Single-shot render: prompt → ComfyUI → save → audit → memory |
| POST | `/api/hermes/inject-prompt` | Inject prompt into ComfyUI workflow node |
| GET | `/api/renders` | List all renders (scans campaigns/ recursively) |
| GET | `/api/characters` | List characters from `data/character_banks/anchors/` |
| POST | `/api/characters` | Add character — saves anchor image + appends to world bible |
| POST | `/api/config/save` | Persist config changes to `data/config.json` |
| GET | `/api/stats` | RAM usage, shot count, event log size |
| GET | `/api/events` | Recent event log entries |
| GET | `/api/shots` | Shots in current session |

---

## Campaign Stream Events (NDJSON)

`POST /api/hermes/run-campaign` streams newline-delimited JSON:

```
{"type": "kimi",   "text": "Generating shot list..."}
{"type": "kimi",   "text": "Shot list ready: 6 shots"}
{"type": "hermes", "text": "Writing prompt for SHOT_001...", "shot_id": "SHOT_001"}
{"type": "hermes", "text": "SHOT_001: cinematic prompt...", "shot_id": "SHOT_001", "prompt": "..."}
{"type": "spark",  "text": "Dispatching SHOT_001...", "shot_id": "SHOT_001", "status": "dispatched"}
{"type": "spark",  "text": "SHOT_001 queued", "shot_id": "SHOT_001", "status": "queued", "prompt_id": "..."}
{"type": "render_complete", "src": "/campaigns/abc123_car/shot001.png", "shot_id": "SHOT_001"}
{"type": "kimi_vl_audit",  "score": 0.91, "passed": true, "feedback": "...", "shot_id": "SHOT_001"}
{"type": "memory_written", "concept": "...", "event_id": "...", "score": 0.91}
{"type": "error",  "text": "..."}
{"type": "done",   "shots": [...]}
```

WebSocket events (model status, render_complete, audit results):
```
lmstudio_detected   — {model_id: "qwen3.6-35b-a3b"}
lmstudio_offline    — {}
render_complete     — {files, campaign, prompt_preview}
kimi_vl_audit       — {score, passed, feedback, issues}
memory_written      — {concept, event_id, score, passed, feedback}
remediation_retry   — {shot_id, attempt, rewrite_reason}
```

---

## Run Campaign Request

```json
POST /api/hermes/run-campaign
{
  "brief": "car commercial golden hour",
  "shot_count": 6,
  "bible_path": "data/lore_bible/world_bible.md"
}
```

Length → shot count mapping: `15s=3, 30s=6, 60s=12, 90s=18`

---

## Single Render Request

```json
POST /api/render
{
  "prompt": "cinematic wide shot, golden hour...",
  "shot_id": "SHOT_001",
  "seed": 42,
  "campaign": "my_campaign",
  "audit": true
}
```

Response:
```json
{
  "status": "complete",
  "prompt_id": "abc-123",
  "output_filename": "shot001.png",
  "saved_count": 1,
  "campaign_dir": "data/campaigns/my_campaign/"
}
```

---

## Add Character Request

```
POST /api/characters
Content-Type: multipart/form-data

name=Sienna Nomad
description=Wanderer with silver eyes, weathered leather jacket, dark braided hair
anchor_image=<file upload>
```

Saves anchor to `data/character_banks/anchors/sienna_nomad.jpg`.
Appends to `data/lore_bible/world_bible.md`.

---

## File Layout

```
dashboard/
├── forge_dashboard.py       # FastAPI app — all endpoints + WebSocket
├── static/
│   ├── js/
│   │   ├── app.js           # All UI logic, WebSocket handlers, view rendering
│   │   ├── data.js          # STATUS_BADGE map, static data
│   │   └── components.css   # Chip styles, length selector, badges
│   └── renders/sienna/      # Legacy static renders (also served)
├── templates/
│   └── index.html           # Single-page shell
└── README.md
```

---

## ComfyUI Workflow Injection

Workflow loaded from `workflows/spark_image_z_image_turbo.json`.

- **Node 6** (`CLIPTextEncode`) — `inputs.text` = Hermes-generated prompt
- **Node 9** (`KSampler`) — `inputs.seed` = random int (or user-provided)

Renders saved to `data/campaigns/{campaign_id}/` and served at `/campaigns/{campaign}/{filename}`.

---

## Dependencies

```
fastapi
uvicorn
python-multipart
httpx
```

Core bridges loaded from this repository (`forge_nps_v01/core`).
