# Forge — Hermes Agent Creative Hackathon Submission
**Date:** May 3, 2026  
**Event:** Hermes Agent Creative Hackathon · @Kimi_Moonshot × @NousResearch  
**Category:** Creative AI Production Pipeline

---

## 🎯 The Pitch

**Brief an AI like a creative director. Get back an entire campaign.**

Forge generates complete creative projects — social media campaigns, TV commercials, short films, product photography series — in any visual style. And **Hermes**, the learning agent inside Forge, ensures your brand identity stays consistent across every post, every frame, every shot.

Most AI tools are goldfish. They generate and forget. **Forge remembers.**

---

## 🎨 The Model Stack

| Model | Role | Best For |
|-------|------|----------|
| **Kimi 2.6** (NVIDIA NIM) | Creative Director | Brief parsing, campaign plans, shot lists, visual auditing |
| **FLUX2 Dev NVFP4** | Quality Renderer | Final images, photoreal detail, advertising |
| **Z-Image Turbo** | Speed Renderer | Drafts, concepts, rapid iteration |
| **LTX 2.3 NVFP4** | Video Generation | TV spots, cinematic shorts, motion sequences |
| **WAN 2.2 NVFP4** | Video Generation | Animated sequences, stylized motion |

One pipeline. Any style. Any format.

---

## 🧠 The Secret Sauce: Hermes

Before dispatching any asset, Hermes asks its memory:
> *"Have I done something like this before? What worked? What failed?"*

If it finds a similar failure, it **injects the learned fix directly into the prompt** — automatically. The pipeline gets smarter with every render.

**Your 50th asset is better than your 1st. Not because you got better at prompting. Because your creative partner got better at remembering.**

### Memory Architecture

| Layer | What It Does |
|-------|-------------|
| **Episodic Memory** | Immutable log of every attempt, failure, and fix (212+ events) |
| **Semantic Memory** | Durable rules distilled from patterns — with confidence scores |
| **Consolidator** | The "dream" process that turns raw experience into actionable knowledge |

---

## 🎬 Teach Mode — The Killer Demo

The fastest way to see Hermes learn is to watch it fail on purpose.

1. **Inject an error** — deliberately strip a brand color from the prompt
2. **Generate** → consistency audit fails (score: 34)
3. **Hermes records** the failure + the correct fix
4. **Trigger consolidation** → a new **insight** appears in semantic memory
5. **Re-generate** the same shot → Hermes auto-injects the fix → passes audit (score: 94)

You can show a judge the exact moment an AI learns something. In 30 seconds.

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

## 🏗️ Architecture at a Glance

```
Creative Brief
    ↓
Kimi 2.6 (NIM) → Campaign Plan + Shot List + World Bible
    ↓
HermesAgent (queries memory → augments prompt)
    ↓
ArchitectRouter (selects renderer: FLUX2 / Z-Image / LTX / WAN)
    ↓
ComfyDispatcher → Spark (localhost:8188)
    ↓
ContinuityAuditor (checks consistency against bible)
    ↓
RemediationLoop (fixes failures, 3 iterations max)
    ↓
Hermes records outcome → Consolidator → Semantic insight
```

---

## 🧪 Test Coverage

```bash
$ python -m pytest
============================= 65 passed in 54s =============================
```

Core modules tested: bridge, dispatch, memory, consistency, prompts, skills, templates, script parser, orchestrator, payload validator, dashboard API.

---

## 🚀 Recommended Demo Flow for Judges

1. **Start the dashboard** — `python -m dashboard.forge_dashboard`
2. **Show Models tab** — toggle to API, show Kimi 2.6 / NVIDIA NIM selected
3. **Generate a campaign** — type a brief, watch Kimi build the plan
4. **Run Teach Mode** — POST to `/api/hermes/teach`. Show before/after + new insight born
5. **Explore Memory** — Cytoscape graph of events, outcomes, learned rules
6. **Export Brain** — Settings → Export → show JSON with episodic + semantic data
7. **Run tests** — `python -m pytest` → 65 green dots

---

## 📋 Submission Checklist

- [ ] Demo video recorded (60–90s, with voiceover)
- [ ] Kimi 2.6 usage clearly visible in at least one scene
- [ ] Teach Mode sequence included
- [ ] Cross-format output shown (image + video + social)
- [ ] Tweet drafted with @NousResearch and @Kimi_Moonshot tags
- [ ] Tweet posted
- [ ] Link dropped in Discord `#creative-hackathon-submissions`
- [ ] Tests pass
- [ ] Dashboard launches cleanly

---

## 📋 Post-Hackathon Roadmap

- Vector database backend for semantic memory (Chroma / Qdrant)
- Video pipeline integration (LTX, Cosmos)
- FP4 quantization for local inference
- Mac app wrapper
- Full web deployment

---

**Forge — The Creative Studio with a Memory.**
