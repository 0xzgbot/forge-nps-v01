# Forge NPS — Neural Production Studio

An autonomous AI filmmaking pipeline. Feed it an idea or a script, and it generates a world bible, shot list, and production-ready images — while learning from its own mistakes.

## What it does

1. **Direct** — Kimi K2.5 reads your script + lore bible and generates a structured shot list
2. **Dispatch** — Hermes routes each shot to ComfyUI (FLUX / Z-Image) for image generation
3. **Audit** — The Continuity Auditor checks every shot against the world bible for consistency errors
4. **Repair** — If something fails (wrong color, bad anatomy, lore contradiction), the Remediation Loop fixes it automatically
5. **Learn** — Hermes records every outcome. After a session, it consolidates episodes into durable semantic rules so the same mistake never happens twice

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.template .env
# Edit .env and set:
#   KIMI_API_KEY=your_real_key_here
#   COMFYUI_PRIMARY=http://your-comfyui-ip:8188

# 3. Run the mock demo (no API keys needed)
python3 demo.py --mock

# 4. Run the memory-learning showcase
python3 demo.py --memory-demo

# 5. Run with injected failure to see remediation live
python3 demo.py --mock --mock-failure

# 6. Run with real APIs (requires keys + ComfyUI)
python3 demo.py --script scripts/demo/pilot_script.md

# 7. Launch the live dashboard
python3 demo.py --mock --dashboard
```

## Project structure

```
core/
  bridge/           # KimiBridge (NIM), ConfigManager
  dispatch/         # ComfyUI payload validator + dispatcher
  feedback/         # RemediationLoop (3-tier self-healing)
  hermes/           # HermesAgent + episodic/semantic memory
  orchestrator/     # ForgeOrchestrator (pipeline coordinator)
  state/            # SessionManager (JSON session persistence)
agents/
  auditor/          # ContinuityAuditor (lore-consistency QA)
  visual/           # VisualAgent (ComfyUI generation client)
dashboard/          # FastAPI live dashboard
scripts/demo/       # Demo script + pilot content
data/
  lore_bible/       # World bible markdown
  hermes_memory/    # Episodic + semantic memory stores
```

## Hackathon MVP scope

- ✅ Idea → World Bible → Script → 2–4 shots
- ✅ Kimi K2.5 for narrative direction
- ✅ Hermes orchestration + skill registry + memory
- ✅ ComfyUI for image generation (FLUX / Z-Image)
- ✅ Continuity Auditor for text-level QA
- ✅ Feedback loop: max 3 iterations
- ✅ Live dashboard showing shot progress + reasoning traces
- ✅ `--mock` mode for demo without API keys

**Post-hackathon only:** audio agent, video pipeline (LTX), Cosmos vision, vector DB, FP4 quantization, Mac app wrapper, full website.

## Requirements

- Python 3.11+
- `httpx`, `numpy`, `pydantic`
- Optional: Ollama for local embedding fallback
- Optional: Running ComfyUI instance for real generation
