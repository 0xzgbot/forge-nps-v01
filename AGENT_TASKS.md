# Agent Task List — Forge NPS

> **Updated:** 2026-04-24  
> **Deadline:** May 3, 2026  
> **Status:** Bugs fixed. Pipeline integration in progress.

---

## ✅ COMPLETED

| Task | What | Status |
|---|---|---|
| Path migration | Removed spaces, fixed hardcoded paths | ✅ Done |
| Spark IP update | All hosts updated to `100.112.87.8` | ✅ Done |
| Critical bugs fixed | forge_engine.py imports, kimi_bridge hardcoded path, remediation skill_registry type, IndexError in harness, image lightbox missing | ✅ Done |
| Flask→FastAPI | Removed Flask Blueprint from `memory_api.py` | ✅ Done |
| Test suite | 65/65 passing | ✅ Done |
| LM Studio integration | LMStudioClient, auto-detect models, Settings UI | ✅ Done |
| Hermes WebSocket | `/ws/hermes` streaming 7 event types | ✅ Done |
| Teach Mode backend | `POST /api/hermes/teach` — controlled learning demo | ✅ Done |
| Spark Monitor | `/api/spark/state` + `/ws/spark` | ✅ Done |
| Consistency Scorer | PIL histogram correlation, 0-100 | ✅ Done |
| Export Brain | `GET /api/hermes/export` | ✅ Done |
| Settings wired | `data/config.json` persistence + restart | ✅ Done |
| LM Studio test button | Auto-detects loaded models | ✅ Done |
| Image lightbox | `openImageLightbox()` added to app.js | ✅ Done |
| README rewritten | Full hackathon pitch with real architecture | ✅ Done |
| NEXT_STEPS updated | Realistic timeline to May 3 | ✅ Done |

---

## 🔴 IN PROGRESS / REMAINING

### Core Pipeline Integration

| # | Task | File | Priority |
|---|------|------|----------|
| 1 | Create `NousHermesBridge` | `core/bridge/nous_hermes_bridge.py` | 🔴 Critical |
| 2 | Implement `VisualAgent.generate()` | `agents/visual/visual_agent.py` | 🔴 Critical |
| 3 | Add `audit_image()` (Kimi-VL) | `core/bridge/kimi_bridge.py` | 🔴 Critical |
| 4 | Update `ContinuityAuditor` to use Kimi-VL | `agents/auditor/continuity_auditor.py` | 🔴 Critical |
| 5 | Wire Hermes-3 into `dispatch_shots()` | `core/hermes/hermes_agent.py:129` | 🔴 Critical |
| 6 | Wire Hermes-3 into remediation tier 2 | `core/feedback/remediation_loop.py` | 🔴 Critical |
| 7 | Update orchestrator — instantiate both bridges | `core/orchestrator/forge_orchestrator.py` | 🔴 Critical |
| 8 | Add `NOUS_HERMES_MODEL` to config | `.env` + `data/config.json` | 🟡 High |

### Dashboard

| # | Task | File | Priority |
|---|------|------|----------|
| 9 | Hermes Live CLI (input + send) | `app.js` + `forge_dashboard.py` | 🟡 High |
| 10 | Add Character modal + API endpoint | `app.js` + `forge_dashboard.py` | 🟡 High |
| 11 | Tag pipeline events with model names | `app.js` | 🟡 High |
| 12 | Wire existing renders to home screen | `app.js` | 🟢 Medium |

### Demo Day

| # | Task | When |
|---|------|------|
| 13 | End-to-end pipeline test (full run with real Hermes-3) | Day 5-6 |
| 14 | Record 60-second demo video | Day 7-8 |
| 15 | Final test run (all 65 tests) | Day 9 |
| 16 | Package and submit | May 3 |

---

## Notes

- **Hermes-3 model**: Running on LM Studio at `100.74.164.1:1234`. Current chat model is `gemma-4-26b-a4b-it` — need to swap to Hermes-3 model or add `NOUS_HERMES_MODEL` as separate config field
- **ComfyUI hosts**: Primary `100.112.87.8:8188`, secondary `100.112.87.8:8189` (same Spark box)
- **Workflow files**: `hermes_z_image_turbo_api.json` at `/Users/zgbot/workflows/` — proven working (generated 180 Sienna renders)
- **Kimi-VL**: Model `moonshotai/Kimi-VL-A3B-Instruct` already in env. API key working. Just needs `audit_image()` method added
- **Character anchor**: `elara_vance.jpg` exists in `data/character_banks/anchors/`. Use as Kimi-VL reference image for demo
