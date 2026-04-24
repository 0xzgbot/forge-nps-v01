# FORGE NPS — Next Steps (Post-Backend Completion)

**Date:** 2026-04-23  
**Deadline:** May 3 (~9 days)  
**Status:** Backend is complete. 65 tests passing. UI is the remaining work.

---

## ✅ What's Done (Don't Touch)

- All backend APIs built and tested (65/65 passing)
- Hermes WebSocket streaming live decision events
- Teach Mode backend — controlled learning loop
- Prompt Builder → ComfyUI submission fully wired
- Spark Monitor with live queue progress
- Consistency Scorer (PIL histogram, 0-100)
- LM Studio integration (replaces Ollama)
- Models page with Local/API toggle
- Settings page with live config editor + restart
- Export Brain endpoint
- All documentation updated

---

## 🔥 Critical Path to Demo Day

### Days 1-2: Claude Code — Core UI
1. **Hermes Live Panel** — Subscribe to `/ws/hermes`, render event cards with icons
2. **Teach Mode UI** — Toggle, error dropdown, "Run Teach Cycle" button, before/after split view
3. **Spark Monitor Widget** — Poll `/api/spark/state` every 2s, show queue depth + progress

### Days 3-4: Claude Code — Gallery + Polish
4. **Render Gallery** — Real `<img>` thumbnails from `data/seed_outputs/`, score badges
5. **Insight Birth Animation** — "Consolidate Now" button → animated graph update
6. **Export Brain Button** — Settings → triggers `GET /api/hermes/export` download

### Days 5-6: Integration & Testing
7. End-to-end test: Build recipe → Submit → Monitor progress → Score output → Teach Mode → Export brain
8. Fix any UI bugs, empty states, responsive issues

### Days 7-8: Demo Recording
9. Record 90-second teach mode narrative
10. Record dashboard walkthrough
11. Capture screenshots for submission

### Days 9-10: Buffer & Submit
12. Final test run
13. Package and submit

---

## 🎯 Demo-Day Success Criteria

1. Judge opens dashboard → clicks "Teach Mode" → watches Hermes learn in 60 seconds
2. Live WebSocket shows Hermes thinking before every shot
3. 5 real renders in gallery with consistency scores
4. Memory graph shows ≥1 insight connected to source events
5. "Export Brain" button downloads a JSON file
6. All 65 tests still pass

---

## 🚫 Post-Hackathon Only (May 4+)

- LTX 2.3 video pipeline
- 120-photo batch renders
- Cosmos vision integration
- VIME vector database
- FP4 quantization
- Mac app wrapper
- Full website build
- Audio agent / voice pipeline

---

## Quick Commands

```bash
# Run tests
python -m pytest

# Launch dashboard
python -m dashboard.forge_dashboard

# Teach mode demo
curl -X POST http://localhost:7000/api/hermes/teach \
  -H "Content-Type: application/json" \
  -d '{"concept":"Elara Vance portrait, neon glow","error_type":"strip_hair_color"}'

# Consistency score
curl -X POST http://localhost:7000/api/consistency/score \
  -H "Content-Type: application/json" \
  -d '{"render_path":"data/seed_outputs/VAR_000.png"}'

# Export brain
curl http://localhost:7000/api/hermes/export > hermes_brain.json
```
