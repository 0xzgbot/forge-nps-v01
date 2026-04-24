# FORGE NPS — Next Steps to Demo Day

**Date:** 2026-04-24  
**Deadline:** May 3 (~9 days)  
**Status:** Architecture reviewed. Core bugs fixed. Pipeline integration in progress.

---

## ✅ What's Solid (Don't Touch)

- 65/65 tests passing
- Hermes WebSocket streaming (`/ws/hermes`) live and instrumented
- Teach Mode backend — controlled learning demo fully wired
- Spark Monitor — live queue via `/ws/spark` + REST fallback
- Memory system — episodic JSONL + semantic JSON + Cytoscape graph
- Settings page — runtime config editor with `data/config.json` persistence
- Consistency Scorer — PIL histogram, 0-100 score
- Export Brain — `GET /api/hermes/export` downloads full JSON skill pack
- LM Studio integration — auto-detect loaded models, health check in Settings

---

## 🔥 What Must Get Built Before May 3

### Priority 1 — The Pipeline Core (blocks demo)
1. **`core/bridge/nous_hermes_bridge.py`** — Hermes-3 LM Studio wrapper
   - `generate_shot_prompt()`, `analyze_failure()`, `chat()` methods
   - Wraps existing `LMStudioClient`
2. **`VisualAgent.generate()`** — implement the missing method
   - Uses existing `_build_kernel_payload()` + `submit_to_comfy()`
   - Loads `hermes_z_image_turbo_api.json` from `/Users/zgbot/workflows/`
3. **Kimi-VL `audit_image()`** — add to `core/bridge/kimi_bridge.py`
   - Base64 encode rendered PNG + character ref → Kimi-VL → audit result
4. **Wire `HermesAgent.dispatch_shots()` line 129** — call Hermes-3 for prompts
5. **Wire remediation tier 2** — Kimi-VL finding → Hermes-3 diagnosis → corrected prompt

### Priority 2 — Dashboard (for demo visuals)
6. **Hermes Live CLI** — input + Send button → `POST /api/hermes/chat` → real Hermes-3 response
7. **"Add Character" modal** — name + description + anchor image upload → saves to disk + reloads engine
8. **Pipeline events tagged** — `[HERMES-3 🧠]` `[KIMI-VL 👁]` `[KIMI K2 ✍]` in Hermes Live panel

### Priority 3 — Demo content
9. **Wire Sienna renders to home screen** — show real existing images from `data/outputs/`
10. **Record 60-second demo video** — follow script in `docs/DEMO_SCRIPT.md`

---

## 🎯 Demo-Day Success Criteria

1. Click "Run Campaign" → Kimi K2.6 model name visible in output → shot list generated
2. Hermes Live panel streams Hermes-3 writing prompts in real time (local, instant)
3. Spark receives real ComfyUI job (check queue at 100.112.87.8:8188)
4. Kimi-VL audit result appears in panel: model name visible + visual finding
5. Hermes-3 corrects and re-dispatches — corrected render passes
6. Memory graph shows new learned rule after session
7. Hermes Live panel: type a message → get real Hermes-3 response
8. All 65 tests still pass

---

## 🚫 Skip Until May 4

- LTX 2.3 video pipeline
- Product anchor upload system
- Script file parser / shot editor
- Project creation UI
- Cosmos vision integration

---

## Quick Commands

```bash
# Run tests
python -m pytest

# Launch dashboard
python -m dashboard.forge_dashboard   # http://localhost:7000

# Teach mode demo
curl -X POST http://localhost:7000/api/hermes/teach \
  -H "Content-Type: application/json" \
  -d '{"concept":"Sienna product shot, earth tones","error_type":"strip_hair_color"}'

# Check Hermes-3 via LM Studio
curl http://100.74.164.1:1234/v1/models

# Check Spark
curl http://100.112.87.8:8188/system_stats

# Consistency score
curl -X POST http://localhost:7000/api/consistency/score \
  -H "Content-Type: application/json" \
  -d '{"render_path":"data/seed_outputs/VAR_000.png"}'
```
