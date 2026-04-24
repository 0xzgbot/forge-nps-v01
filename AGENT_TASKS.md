# Agent Task List — Forge NPS v0.1

> **Updated:** 2026-04-23
> **Deadline:** May 3
> **Status:** Backend complete. UI in progress.

---

## ✅ COMPLETED BY KIMI (Backend / Integration)

| Task | What | Status |
|---|---|---|
| Path migration | Renamed folder (removed space), fixed ~45 hardcoded paths | ✅ Done |
| Spark IP update | Old IP `localhost` → `localhost` in 14 files | ✅ Done |
| Critical bugs | Fixed Pydantic API misuse, missing `validate()`, remediation signature mismatch | ✅ Done |
| Flask→FastAPI | Removed Flask Blueprint from `memory_api.py` | ✅ Done |
| Encoding fixes | Added `encoding='utf-8'` to 21 `open()` calls | ✅ Done |
| Test suite | Fixed async decorators, broken paths, wrong extensions → **65/65 passing** | ✅ Done |
| LM Studio migration | Replaced Ollama with LM Studio (embedder + chat client + env) | ✅ Done |
| Models page | New dashboard tab with Local/API toggle, test connection, dropdowns | ✅ Done |
| Hermes WebSocket | `/ws/hermes` streams 7 event types from instrumented `HermesAgent` | ✅ Done |
| Teach Mode | `POST /api/hermes/teach` — controlled learning demo backend | ✅ Done |
| Prompt Builder wired | `GET /api/banks`, `POST /api/build-recipe`, `POST /api/submit-recipe` | ✅ Done |
| Spark Monitor API | `GET /api/spark/state`, `/ws/spark`, auto-start on boot | ✅ Done |
| Consistency Scorer | `POST /api/consistency/score` — PIL histogram correlation, 0-100 | ✅ Done |
| Export Brain | `GET /api/hermes/export` — JSON skill pack download | ✅ Done |
| Settings wired | Live config editor with `data/config.json` persistence + restart button | ✅ Done |

---

## 🐧 LOCAL AGENT (Spark / Linux Box) — Remaining Tasks

| # | Task | Priority | Notes |
|---|------|----------|-------|
| 1 | Keep ComfyUI alive | 🔴 Critical | Monitor `/system_stats`, restart if deadlocked |
| 2 | Install LM Studio on Spark | 🟡 Medium | Only if user wants LM Studio on Spark instead of Mac |
| 3 | Load embedding model | 🟡 Medium | `nomic-embed-text-v1.5` or similar |
| 4 | Load chat model | 🟡 Medium | `qwen2.5-3b-instruct` or similar |
| 5 | Expose LM Studio to network | 🟡 Medium | Bind to `0.0.0.0:1234` |
| 6 | `spark_health_daemon.py` | 🟢 Low | Poll ComfyUI + LM Studio, write `/opt/forge/status.json` |
| 7 | FLUX2 Redux model | 🟢 Low | `flux1-redux-dev.safetensors` in `models/style_models/` |
| 8 | Demo workspace | 🟢 Low | `input/elara_vance.jpg`, pre-load LoRAs |

---

## 🎨 CLAUDE CODE (Frontend / UI) — Remaining Tasks

| # | Task | Priority | Backend API Ready? |
|---|------|----------|-------------------|
| 1 | Hermes Live Panel | 🔴 Critical | ✅ `/ws/hermes` streaming |
| 2 | Teach Mode UI | 🔴 Critical | ✅ `POST /api/hermes/teach` |
| 3 | Spark Monitor Widget | 🟡 High | ✅ `/api/spark/state` + `/ws/spark` |
| 4 | Render Gallery (real images) | 🟡 High | ✅ `POST /api/consistency/score` |
| 5 | Insight Birth Animation | 🟡 Medium | ✅ Memory graph API |
| 6 | Export Brain Button | 🟢 Low | ✅ `GET /api/hermes/export` |
| 7 | Empty states & polish | 🟢 Low | — |

---

## 📝 DOCUMENTATION — Remaining Tasks

| # | Task | Status | Owner |
|---|------|--------|-------|
| 1 | README.md | ✅ Updated by Kimi | Done |
| 2 | docs/FEATURE_PLAN.md | ✅ Updated | Done |
| 3 | docs/WORKLOAD_SPLIT.md | ✅ Updated | Done |
| 4 | docs/DESIGN_BRIEF.md | ✅ Updated (Models tab added) | Done |
| 5 | docs/DEMO_SCRIPT.md | ✅ Updated (Teach Mode narrative) | Done |
| 6 | docs/PITCH_DECK.md | ✅ Updated | Done |
| 7 | SUBMISSION_MAY_03/README.md | ✅ Updated | Done |
| 8 | SUBMISSION_MAY_03/SUBMISSION_SUMMARY.md | ✅ Updated | Done |
| 9 | AGENT_TASKS.md | ✅ Updated (this file) | Done |
| 10 | NEXT_STEPS.md | ⬜ Needs rewrite | Kimi |

---

## 🎬 DEMO DAY PREP (May 3)

| # | Task | Owner | When |
|---|------|-------|------|
| 1 | Record 90-second teach mode demo | User | Day 8 |
| 2 | Record dashboard walkthrough | User | Day 8 |
| 3 | Capture screenshots for submission | User | Day 8 |
| 4 | Final test run (all 65 tests) | Kimi | Day 9 |
| 5 | Package & submit | User | Day 9 |

---

## Notes

- **FluxRedux wiring**: Node exists in workflow but not connected. Prompt-based consistency is working well (validated with test renders). Lower priority.
- **ComfyUI failover**: Secondary host (`:8189`) on same machine. Multi-host failover implemented but not critical for demo.
- **Resolution**: Current renders are 1920×1088. For faster iteration, 1024×1024 or 1280×720.
- **LM Studio location**: Configurable via Settings UI. Can be localhost, Spark, or a separate GPU box.
