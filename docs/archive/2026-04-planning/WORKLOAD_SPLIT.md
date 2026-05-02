# Forge NPS — 3-Agent Workload Split

> **Goal:** Build the Hermes showcase demo in parallel across 3 agents.
> **Deadline:** May 3
> **Last Updated:** 2026-04-23

---

## ✅ COMPLETED BY KIMI (Backend / Integration)

**ALL TASKS DONE.** 65/65 tests passing.

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | **Hermes WebSocket Instrumentation** | ✅ DONE | `/ws/hermes` endpoint streaming 7 event types: `DISPATCH_START`, `MEMORY_QUERY`, `MEMORY_RECALL`, `PROMPT_AUGMENT`, `DISPATCH_SHOT`, `OUTCOME_RECORD`, `CONSOLIDATION_START`, `INSIGHT_BORN`. `HermesAgent` emits events via `_event_emitter` callback. Dashboard startup wires `emit_hermes_event` into the agent |
| 2 | **Teach Mode Backend** | ✅ DONE | `POST /api/hermes/teach` accepts `concept` + `error_type` (strip_hair_color / wrong_lighting / remove_anchor). Injects deliberate error, records failure + success events, triggers consolidation, returns `{before, after, fix, insight, events_recorded}` |
| 3 | **Wire Prompt Builder → ComfyUI** | ✅ DONE | `GET /api/banks` (load banks), `POST /api/build-recipe` (generate recipe from selections), `POST /api/submit-recipe` (submit to ComfyUI via `ComfyUIClient`, register with `SparkMonitor`). Prompt injection into CLIPTextEncode + seed/prefix injection working |
| 4 | **Spark Monitor API** | ✅ DONE | `GET /api/spark/state` (snapshot), `/ws/spark` (WebSocket push). Monitor starts on app startup. Polls ComfyUI queue every 2s, pushes updates |
| 5 | **Consistency Scorer** | ✅ DONE | `POST /api/consistency/score` compares render vs anchor using per-channel histogram correlation (PIL). Returns 0-100 score. Auto-logs to episodic memory. No heavy ML deps |
| 6 | **LM Studio Fallback Integration** | ✅ DONE | `LMStudioEmbedder` replaces `OllamaEmbedder` in `HybridEmbedder` chain. `LMStudioClient` in `core/bridge/` for chat completions. `.env` keys: `LMSTUDIO_HOST`, `LMSTUDIO_EMBED_MODEL`, `LMSTUDIO_CHAT_MODEL` |
| 7 | **Export Brain Endpoint** | ✅ DONE | `GET /api/hermes/export` returns JSON with all semantic insights + skill registry + episodic summary. Ready for Settings UI download button |
| 8 | **Models Page (Local vs API)** | ✅ DONE | New "Models" tab with big toggle switch, two cards (LM Studio + Kimi/NIM), test connection buttons, dropdowns populated from `/api/models/status` |
| 9 | **Settings Page (Fully Wired)** | ✅ DONE | Live config editor that loads from `.env` + `data/config.json`, saves on blur, masks API keys, includes LM Studio host field, restart server button |
| 10 | **Bug Fixes & Path Migration** | ✅ DONE | Renamed folder (removed space), fixed ~45 hardcoded paths, updated old Spark IP `100.74.164.1` → `100.112.87.8` in 14 files, fixed Flask→FastAPI conflict, fixed 3 critical runtime bugs (Pydantic, config_manager, remediation_loop), added encoding='utf-8' to 21 files, fixed test suite |
| 11 | **Documentation Update** | ✅ DONE | Updated README.md, AGENT_TASKS.md, NEXT_STEPS.md, FEATURE_PLAN.md, DESIGN_BRIEF.md, DEMO_SCRIPT.md, PITCH_DECK.md, SUBMISSION_MAY_03/* |

### Files Created / Modified by Kimi
- `core/hermes/memory/embedder.py` — LMStudioEmbedder
- `core/hermes/hermes_agent.py` — Event emission instrumentation
- `core/bridge/lmstudio_client.py` — **NEW**
- `core/bridge/runtime_config.py` — **NEW** (config persistence)
- `dashboard/forge_dashboard.py` — 15+ new endpoints, 3 WebSockets, startup wiring
- `dashboard/static/js/app.js` — Models tab + Settings tab (fully dynamic)
- `dashboard/static/css/components.css` — Toggle switch + model cards + settings
- `docs/*` — All documentation updated
- `.env` + `.env.template` — LM Studio config

---

## 🐧 Agent 1: Local Agent (Spark / Linux Box)

**Where you run:** `100.112.87.8` (GB10 GPU, 121GB VRAM)
**Your superpower:** GPU compute, ComfyUI management, LM Studio server (optional)

### Your Remaining Tasks

| # | Task | Effort | Notes |
|---|------|--------|-------|
| 1 | **Keep ComfyUI alive** | Ongoing | Monitor `/system_stats`, restart if deadlocked |
| 2 | **Restart ComfyUI** | 15 min | Currently down. Start with FLUX2 NVFP4 + Turbo LoRA |
| 3 | **Install LM Studio on Spark** | 30 min | Only if user wants LM Studio remote instead of Mac local |
| 4 | **Load models in LM Studio** | 20 min | Embedding + chat model (if running on Spark) |
| 5 | **Expose LM Studio to network** | 15 min | Bind to `0.0.0.0:1234` (if running on Spark) |
| 6 | **`spark_health_daemon.py`** | 1 hour | Poll ComfyUI + LM Studio, write `/opt/forge/status.json` |
| 7 | **FLUX2 Redux model** | 30 min | `flux1-redux-dev.safetensors` if needed |
| 8 | **Demo workspace** | 30 min | `input/elara_vance.jpg`, pre-load LoRAs |

### Deliverables
- [ ] ComfyUI stable on `100.112.87.8:8188`
- [ ] `scripts/spark_health_daemon.py` writing `/opt/forge/status.json`
- [ ] 5+ seed renders available in `data/seed_outputs/`

---

## 🎨 Agent 2: Claude Code (Frontend / UI)

**Where you run:** MacBook (local dev)
**Your superpower:** Pixel-perfect UI, CSS animations, vanilla JS architecture

### Your Remaining Tasks

| # | Task | Effort | Backend API Ready? |
|---|------|--------|-------------------|
| 1 | **Hermes Live Panel** | 4 hours | ✅ `/ws/hermes` streaming 7 event types |
| 2 | **Teach Mode UI** | 3 hours | ✅ `POST /api/hermes/teach` returns full trace |
| 3 | **Spark Monitor Widget** | 3 hours | ✅ `/api/spark/state` + `/ws/spark` |
| 4 | **Render Gallery (Real)** | 3 hours | ✅ `POST /api/consistency/score` for scoring |
| 5 | **Insight Birth Animation** | 2 hours | ✅ Memory graph API + consolidation trigger |
| 6 | **Export Brain Button** | 1 hour | ✅ `GET /api/hermes/export` |
| 7 | **Empty States & Polish** | 2 hours | — |

### Backend APIs Already Ready for You
| Endpoint | What It Returns |
|----------|----------------|
| `GET /api/banks` | All variation bank items |
| `POST /api/build-recipe` | Recipe dict from selections |
| `POST /api/submit-recipe` | Queues job on Spark, returns prompt_id |
| `GET /api/spark/state` | Queue snapshot (total, running, completed, failed) |
| `/ws/spark` | WebSocket push of job status updates |
| `/ws/hermes` | WebSocket push of Hermes decision events |
| `POST /api/hermes/teach` | Teach mode trace `{before, after, fix, insight}` |
| `GET /api/hermes/export` | Full brain export JSON |
| `POST /api/consistency/score` | 0-100 score for a render vs anchor |
| `GET /api/models/status` | Local/API mode + available models |
| `GET /api/config` | Current configuration (masked) |
| `POST /api/config` | Update configuration |
| `POST /api/restart` | Restart dashboard server |

### Design References
- `docs/DESIGN_BRIEF.md` — Full UI spec with 8 tabs (Models added)
- `/Users/zgbot/Desktop/FORGE NPS/design_handoff_forge_nps 2 UI/` — Claude Code prototype with screenshots

### Deliverables
- [ ] Hermes Live panel streaming real events from `/ws/hermes`
- [ ] Teach Mode toggle + before/after comparison
- [ ] Spark Monitor widget with live progress
- [ ] Render gallery with real images + score badges
- [ ] Insight birth animation in memory graph
- [ ] Export Brain button in Settings

---

## 🔄 Handoff Points (All Complete on Backend)

| What | Status |
|------|--------|
| `/ws/hermes` endpoint with mock events | ✅ Ready for UI testing |
| Teach Mode backend | ✅ Ready for UI toggle |
| Render gallery API | ✅ Ready for thumbnail grid |
| Spark Monitor streaming | ✅ Ready for progress widget |
| Config persistence | ✅ Ready for Settings save/load |

---

## 🏁 Success Criteria (May 3)

1. **Judge can open dashboard, click "Teach Mode," and watch Hermes learn in 60 seconds**
2. **Live WebSocket shows Hermes thinking before every shot**
3. **5 real renders in gallery with consistency scores**
4. **Memory graph shows ≥1 insight connected to source events**
5. **"Export Brain" button downloads a JSON file**
6. **All 65 tests still pass** ✅
