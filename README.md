# Forge — The AI Studio That Remembers

**Brief it like a creative director. Get back an entire campaign.**

Forge generates complete creative projects — social media campaigns, short films, product photography series, TV spots — and **remembers everything it learns**. Your 50th render is better than your first, not because you got better at prompting, but because your AI partner got better at remembering.

> 🏆 **Hermes Agent Creative Hackathon** · @NousResearch × @Kimi_Moonshot · May 3, 2026  
> Hermes-3 (Nous Research) · Kimi K2.6 · Kimi-VL · FLUX2 · Z-Image Turbo · LTX 2.3

---

## The Problem Every Creative Faces

Generate 24 Instagram posts. Half of them have the wrong hair color. Your product loses its signature detail on render 17. You fix it manually. Next batch — same error, back again.

**AI can make one beautiful thing. It can't remember what beautiful looks like.**

---

## The Solution: Two AI Brains, One Creative Pipeline

Forge runs two specialized models in a continuous creative loop:

### 🧠 Hermes-3 (Nous Research — Local, Always On)
The creative worker. Runs on LM Studio — private, fast, no API costs. Hermes-3:
- **Writes every shot prompt** from director schemas, shot briefs, and its own memory
- **Reads its past failures** before each dispatch: *"Last time I shot Sienna at dusk the lighting was wrong — adjusting now"*
- **Diagnoses failures** when a render doesn't pass visual QA, cross-referencing memory
- **Streams its inner monologue** to the Hermes Live panel in real time — judges watch the AI think

### 🎬 Kimi (API — Precise, Expensive, Used Sparingly)
The executive layer. Three distinct roles:

| Model | Role | When Called |
|-------|------|-------------|
| **Kimi K2.6** | Creative Director — synthesizes world bible into shot list | Once per campaign |
| **Kimi-VL** | Visual Auditor — **actually looks at rendered images**, compares to character references | Per render |
| **Kimi K2-Instruct** | Fixer — full prompt rewrite when Hermes can't repair a failure | Tier-3 fallback |

### 🖥️ ComfyUI on the Spark (DGX GPU Cluster)
All rendering happens on dedicated GPU hardware. Z-Image Turbo for speed. FLUX2 Dev for final quality. LTX 2.3 for video.

---

## What Makes This Different

**Kimi-VL actually looks at the images.**

Every rendered PNG gets sent to Kimi-VL alongside the character reference sheets. Kimi-VL compares them pixel-by-pixel and returns: *"Eye color mismatch — rendered brown, expected emerald. Confidence: 94%."*

No other pipeline does this. Text-based consistency checking guesses. Vision-language model auditing *sees*.

**Hermes-3 learns from every failure.**

After Kimi-VL flags an issue, Hermes-3 reads the finding, queries its episodic memory for similar past failures, and writes a corrected prompt — automatically. That correction gets recorded. Next session, Hermes starts knowing what it learned.

**Memory compounds across sessions.**

Hermes runs a "dream process" after each session: the Consolidator scans every episode, detects patterns, and distills them into durable semantic rules. *"For Sienna shots with warm lighting, always specify iris color explicitly."* That rule lives in semantic memory and gets injected into every future prompt that matches.

---

## Live Demo Arc (60 seconds)

1. **0:00** — Dashboard opens. Home shows campaign renders + Hermes Live streaming
2. **0:10** — Click "Run Campaign." Kimi K2.6 synthesizes world bible → shot list (API call + model name visible)
3. **0:20** — Hermes Live streams Hermes-3 inner monologue writing Shot 001 prompt (local, instant)
4. **0:30** — Spark renders. Image appears in panel
5. **0:40** — Kimi-VL fires: `👁 Eye color mismatch — found brown, expected emerald. Confidence: 91%`
6. **0:50** — Hermes-3: `🧠 Memory recall: this happened before. Injecting iris descriptor. Rewriting...`
7. **0:55** — Corrected render passes audit. Memory panel shows new learned rule born
8. **1:00** — Memory graph updates with new edge connecting failure → fix → insight

---

## Teach Mode — Watch Hermes Learn Live

The fastest way to see the pipeline in action: run a controlled failure cycle.

```bash
curl -X POST http://localhost:7000/api/hermes/teach \
  -H "Content-Type: application/json" \
  -d '{"concept":"Sienna Nomad product shot","error_type":"strip_hair_color"}'
```

Response includes: before/after prompts, fix applied, confidence scores, and the new semantic insight born — all in one request. No setup. Works without GPU.

---

## Dashboard — 8 Tabs, All Live

| Tab | What's There |
|-----|-------------|
| **Home** | Hermes Live CLI (chat with Hermes-3 directly) + campaign queue + event stream |
| **Characters** | Add characters via modal (name + description + anchor image upload) · DNA display |
| **Script** | Shot list with expandable prompts and audit history |
| **Products** | Generation banks (angle, lighting, material, context) |
| **Renders** | Live Spark queue monitor + real image/video gallery with lightbox |
| **Memory** | Interactive Cytoscape graph · Timeline · Insights · Consolidation trigger |
| **Models** | Local ↔ API toggle · LM Studio model auto-detect · NIM health check |
| **Settings** | Runtime config editor · ComfyUI host management · Brain export |

---

## Architecture

```
Creative Brief
    ↓
Kimi K2.6 (NIM) ────────────────────── Director Schema + Shot List
    ↓
Hermes-3 (LM Studio, local) ─────────── Writes each shot prompt
  ↑ queries episodic + semantic memory
    ↓
ComfyUI / Spark (localhost) ──────── Renders PNG
    ↓
Kimi-VL (NIM) ───────────────────────── Visual audit: render vs reference image
    ↓ fails
Hermes-3 (tier 2) ───────────────────── Diagnoses from memory → corrected prompt
    ↓ still fails
Kimi K2-Instruct (tier 3) ───────────── Full prompt rewrite
    ↓
HermesAgent.record_outcome() ────────── Logs to episodic memory
    ↓
MemoryConsolidator ───────────────────── Distills episodes → semantic rules
```

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.template .env
# Set:
#   KIMI_API_KEY=your_nvapi_key
#   COMFYUI_PRIMARY=http://your-spark:8188
#   LMSTUDIO_HOST=http://localhost:1234
#   NOUS_HERMES_MODEL=Hermes-3-Llama-3.2-3B

# 3. Verify
python -m pytest        # 65 tests passing

# 4. Launch
python -m dashboard.forge_dashboard   # http://localhost:7000

# 5. Teach Mode (works without GPU)
curl -X POST http://localhost:7000/api/hermes/teach \
  -H "Content-Type: application/json" \
  -d '{"concept":"Sienna Nomad product shot","error_type":"strip_hair_color"}'
```

---

## Project Structure

```
core/
  bridge/         KimiBridge (K2.6 + VL + Instruct), NousHermesBridge, LMStudioClient, ConfigManager
  consistency/    Character DNA extraction, anchor seeds, Redux workflow injection
  dispatch/       ComfyUI payload validator + multi-host dispatcher + remediation harness
  feedback/       RemediationLoop (3-tier: skill registry → Hermes-3 → Kimi rewrite)
  hermes/         HermesAgent + EpisodicMemory + SemanticMemory + MemoryConsolidator
  orchestrator/   ForgeOrchestrator — master pipeline coordinator
agents/
  auditor/        ContinuityAuditor (text + Kimi-VL visual modes)
  visual/         VisualAgent — ComfyUI workflow dispatch + image generation
  production/     CopywriterAgent, EditorAgent (campaign copy + post-production notes)
dashboard/
  forge_dashboard.py    FastAPI app — all API routes + WebSocket streams
  memory_api.py         Memory data layer (events, insights, graph)
  static/               Neo-Veridia UI — dark/light mode, JetBrains Mono, neon accents
data/
  character_banks/      Anchor images + quality constants + variation banks
  hermes_memory/        episodic/events.jsonl + semantic/insights.json (live, grows each run)
  projects/             Brand bibles, world bibles for sample campaigns
workflows/              hermes_z_image_turbo_api.json, flux2_turbo.json, ltx_2_3.json
```

---

## Test Coverage

```bash
$ python -m pytest
============================= 65 passed =============================
```

Core modules tested: bridge, dispatch, memory (episodic + semantic + consolidator), consistency engine, prompts, skills, templates, script parser, orchestrator, payload validator.

---

## Model Stack

| Model | Provider | Role |
|-------|----------|------|
| **Hermes-3-Llama-3.2-3B** | Nous Research (LM Studio local) | Prompt writing, failure diagnosis, Hermes Live chat |
| **moonshotai/kimi-k2.6** | Kimi via NVIDIA NIM | Director schema generation (1M context) |
| **moonshotai/Kimi-VL-A3B-Instruct** | Kimi via NVIDIA NIM | Visual consistency auditing on rendered images |
| **moonshotai/kimi-k2-instruct** | Kimi via NVIDIA NIM | Tier-3 prompt rewrite (last resort) |
| **Z-Image Turbo** | ComfyUI / Spark | Fast image generation (8 steps, res_multistep) |
| **FLUX2 Dev** | ComfyUI / Spark | Quality image generation |
| **LTX 2.3** | ComfyUI / Spark | Video generation (I2V + T2V) |

---

## Why It Wins Both Tracks

**Main Track** (Creativity + Usefulness + Presentation):
- Cross-format consistency through visual memory — not just text rules
- Demonstrable learning arc: watch a failure, a fix, and a new rule born
- Real use case: brand managers, indie filmmakers, social media studios

**Kimi Track** (Creative use of Kimi models):
- Kimi K2.6 model name visible in director schema API call
- Kimi-VL actually analyzing rendered images — unique among hackathon entries
- Kimi K2-instruct as precision fixer — clean role separation

---

## Requirements

- Python 3.11+
- `fastapi`, `uvicorn`, `httpx`, `numpy`, `pydantic`, `Pillow`
- LM Studio running Hermes-3 (local, any machine)
- NVIDIA NIM API key (`KIMI_API_KEY`) for cloud Kimi models
- ComfyUI instance for GPU rendering (optional — Teach Mode works without it)

---

## License

MIT — Hackathon MVP. Built in 9 days for the Hermes Agent Creative Hackathon.
