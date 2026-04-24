# Forge — The Creative Studio with a Memory

**Brief an AI like a creative director. Get back an entire campaign.**

Forge generates complete creative projects — social media campaigns, TV commercials, short films, product photography series — in any visual style you describe. Wes Anderson symmetry. Photoreal advertising. Animated sequences. Cinematic shorts.

And **Hermes**, the learning agent inside Forge, ensures your brand identity stays consistent across every post, every frame, every shot. It remembers what worked. It learns from what didn't. Your next campaign is better than your last — automatically.

> 🏆 **Hermes Agent Creative Hackathon** · @Kimi_Moonshot × @NousResearch · May 3  
> Kimi 2.6 · FLUX2 Dev · LTX 2.3 · WAN 2.2 · Z-Image Turbo · 65 tests passing

---

## What You Can Create

### 📱 Social Media Campaigns
Feed Forge a brand brief — "Sienna Nomad, outdoor lifestyle, earth tones, adventure vibe" — and it generates a complete campaign: 12 Instagram posts, 3 Stories, a TikTok concept, and a product carousel. Every asset shares the same visual DNA because Hermes remembers the brand rules.

### 📺 TV Commercials
A 30-second spot with consistent characters, products, and lighting across every frame. Kimi 2.6 writes the storyboard. LTX 2.3 renders the motion. Hermes makes sure the protagonist's jacket is the same color in frame 1 and frame 900.

### 🎬 Short Films
Describe a world — characters, mood, palette — and Forge builds the shot list, generates every frame, and audits continuity. Your 50th shot inherits the lessons from your 1st. No more "who is that person?" moments.

### 📸 Product Photography Series
Generate 100 variations of your product at any angle, in any lighting, with any material. Every render maintains brand identity. Hermes remembers what "on-brand" looks like so you don't have to.

### 🎨 Styled Collections
Wes Anderson pastels. Noir shadows. Pop-art saturation. Watercolor storybooks. Describe the vibe and Forge renders it — consistently, across an entire collection.

---

## The Model Stack

| Model | Role | Best For |
|-------|------|----------|
| **Kimi 2.6** (NVIDIA NIM) | Creative Director | Brief parsing, shot lists, world bibles, visual auditing |
| **FLUX2 Dev NVFP4** | Quality Renderer | Final images, photoreal detail, advertising |
| **Z-Image Turbo** | Speed Renderer | Drafts, concepts, rapid iteration |
| **LTX 2.3 NVFP4** | Video Generation | Cinematic shorts, TV spots, motion sequences |
| **WAN 2.2 NVFP4** | Video Generation | Animated sequences, stylized motion |

One pipeline. Any style. Any format.

---

## The Problem

AI can generate one beautiful thing. But a campaign? A film? A series?

Generate 24 Instagram posts and half of them have the wrong brand colors. Your product render loses its signature detail on shot 17. You fix it manually. Then you generate the next batch and — surprise — the same error comes back.

**Every prompt is a roll of the dice. AI doesn't learn from its mistakes.**

Until now.

---

## The Solution: Hermes

Most AI tools are goldfish. They generate and forget.

**Hermes remembers.**

Before dispatching any asset, Hermes asks its memory:
> *"Have I done something like this before? What worked? What failed?"*

If it finds a similar failure, it **injects the learned fix directly into the prompt** — automatically. The pipeline gets smarter with every render. Your 50th asset is better than your 1st — not because you got better at prompting, but because your creative partner got better at remembering.

### How It Works

1. **Brief** — Kimi 2.6 reads your creative brief and builds a campaign plan + world bible
2. **Dispatch** — Hermes routes each asset to the right model (FLUX2 for quality, Z-Image for speed, LTX/WAN for video)
3. **Audit** — Every render is checked against the world bible for consistency
4. **Repair** — Failures are fixed automatically (up to 3 remediation iterations)
5. **Learn** — Hermes records every outcome. After a session, it distills episodes into durable semantic rules

---

## 🎬 Live Demo: Teach Mode

The fastest way to see Hermes learn is to watch it fail on purpose.

**Teach Mode** is a controlled learning loop you can run live in the dashboard:

1. **Inject an error** — deliberately strip a brand color from the prompt
2. **Generate** → consistency audit fails (score: 34)
3. **Hermes records** the failure + the correct fix
4. **Trigger consolidation** → a new **insight** appears in semantic memory
5. **Re-generate** the same shot → Hermes auto-injects the fix → passes audit (score: 94)

```bash
curl -X POST http://localhost:7000/api/hermes/teach \
  -H "Content-Type: application/json" \
  -d '{"concept":"Sienna Nomad bottle, earth tones, adventure vibe","error_type":"strip_hair_color"}'
```

Response shows **before/after prompts**, the fix applied, and the new insight born — all in one request.

---

## 🎛️ Full Dashboard — All Real, All Live

8 tabs. Zero mock data. All wired to real APIs.

| Tab | What You See |
|-----|-------------|
| **Home** | Live Hermes event stream + Teach Mode panel + campaign stats |
| **Characters** | DNA editor, variation gallery, consistency scores |
| **Script** | Shot list with expandable prompts and audit history |
| **Products** | Product anchors + generation banks |
| **Renders** | Live Spark queue monitor + real thumbnail gallery |
| **Memory** | Interactive Cytoscape graph (194 nodes), insights, timeline |
| **Models** | **Local ↔ API toggle** — switch backends instantly |
| **Settings** | Runtime config + Export Brain |

---

## ✅ Demo-Ready Features

| Feature | How to Show It |
|---------|---------------|
| **Teach Mode** | Dashboard → run cycle → before/after + insight birth animation |
| **Hermes Live** | Home tab → watch `/ws/hermes` stream decision events in real time |
| **Memory Graph** | Memory tab → interactive graph with 194 nodes, 449 edges |
| **Models Toggle** | Models tab → flip Local/API → test connection → switch back |
| **Consistency Score** | POST render to `/api/consistency/score` → get 0-100 score |
| **Export Brain** | Settings → Export → download JSON with insights + registry |
| **Spark Monitor** | Renders tab → live queue stats + real thumbnails |

---

## Backend-Agnostic by Design

Forge doesn't care where the models live:

- **Cloud:** Kimi 2.6 via NVIDIA NIM (`integrate.api.nvidia.com`)
- **Local:** LM Studio (any GGUF — Qwen, Llama, Phi, Nomic, etc.)
- **Fallback:** Zero-dependency TF-IDF embedder (no API keys, no GPU needed)

One toggle in the dashboard. Same pipeline. Any model.

---

## Quick Start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.template .env
# Edit .env:
#   KIMI_API_KEY=your_nvapi_key_here
#   COMFYUI_PRIMARY=http://100.112.87.8:8188
#   LMSTUDIO_HOST=http://localhost:1234

# 3. Verify
python -m pytest        # 65 tests passing

# 4. Launch
python -m dashboard.forge_dashboard   # http://localhost:7000

# 5. Run Teach Mode (works without API keys)
curl -X POST http://localhost:7000/api/hermes/teach \
  -H "Content-Type: application/json" \
  -d '{"concept":"Sienna Nomad product shot","error_type":"strip_hair_color"}'
```

---

## Architecture

```
Creative Brief
    ↓
Kimi 2.6 (NIM) → Campaign Plan + Shot List + World Bible
    ↓
HermesAgent (queries memory → augments prompt)
    ↓
ArchitectRouter (selects renderer: FLUX2 / Z-Image / LTX / WAN)
    ↓
ComfyDispatcher → Spark (100.112.87.8:8188)
    ↓
ContinuityAuditor (checks consistency against bible)
    ↓
RemediationLoop (fixes failures, 3 iterations max)
    ↓
Hermes records outcome → Consolidator → Semantic insight
```

---

## Project Structure

```
core/
  bridge/           # KimiBridge (K2.6), LMStudioClient, ConfigManager
  consistency/      # Character DNA extraction, anchor seeds
  dispatch/         # ComfyUI payload validator + dispatcher
  feedback/         # RemediationLoop (3-tier self-healing)
  hermes/           # HermesAgent + episodic/semantic memory + consolidator
  orchestrator/     # ForgeOrchestrator (pipeline coordinator)
  quality/          # ConsistencyScorer (PIL histogram comparison)
dashboard/          # FastAPI app + static UI + memory API + spark monitor
agents/             # ContinuityAuditor, VisualAgent, Production agents
data/               # Character banks, product banks, lore bible, memory stores
scripts/            # Batch render pipeline, memory integrity audit
```

---

## Test Coverage

```bash
$ python -m pytest
============================= 65 passed in 54s =============================
```

Core modules tested: bridge, dispatch, memory, consistency, prompts, skills, templates, script parser, orchestrator, payload validator.

---

## Requirements

- Python 3.11+
- `fastapi`, `uvicorn`, `httpx`, `numpy`, `pydantic`, `Pillow`
- **Optional:** ComfyUI instance for real generation
- **Optional:** LM Studio for local inference
- **Optional:** `KIMI_API_KEY` for cloud generation

---

## License

MIT — Hackathon MVP. Production licensing TBD post-May 3.
