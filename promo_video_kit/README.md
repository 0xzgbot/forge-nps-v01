# Cinesmith — Promo Video Production Kit

> **The Pipeline That Promotes Itself**
>
> This kit contains everything needed to produce a 90-second promo video for
> Cinesmith using NousResearch's newly released creative skills:
> TouchDesigner-MCP, p5js, ComfyUI v5, and AudioCraft.
>
> The video demonstrates Cinesmith creating its own marketing — a meta-narrative
> that has genuinely no competition at the hackathon.

---

## 🎬 What's In This Kit

```
promo_video_kit/
├── touchdesigner/
│   ├── build_memory_graph_v2.py        # Enhanced living memory graph
│   ├── build_pipeline_flow.py          # 5-model orbital pipeline
│   ├── build_audit_gate.py             # Dramatic PASS/FAIL portal
│   ├── build_command_center.py         # HUD dashboard visualization
│   ├── build_provenance_web.py         # 3D retry lineage web
│   ├── assemble_all_td.py              # Build all scenes at once
│   └── build_memory_graph.py           # Original (legacy)
├── p5js/
│   ├── transition_data_to_light.html       # Particles → "CINESMITH" text
│   ├── transition_audit_gate.html          # PASS/FAIL/RETRY kinetic type
│   └── transition_memory_consolidation.html # Nodes → logo formation
├── comfyui/
│   └── hero_frame_prompts.json    # 7 optimized prompts for hero frames
├── audiocraft/
│   └── soundtrack_prompts.md      # Music generation prompts per scene
├── scripts/
│   └── assemble_promo.sh          # ffmpeg assembly script
└── README.md                      # This file
```

---

## ✅ YOUR SETUP CHECKLIST

### Required Software

- [ ] **TouchDesigner** installed (Non-Commercial is FREE)
  - Download: https://derivative.ca/download
  - Non-Commercial caps resolution at 1280×1280 — we use 1280×720

- [ ] **twozero MCP plugin** installed in TouchDesigner
  ```bash
  # Cinesmith: prefer repo-local hermes_home (never assume ~/.hermes)
bash "${HERMES_HOME:-$(cd "$(dirname "$0")/.." && pwd)/hermes_home}/skills/creative/touchdesigner-mcp/scripts/setup.sh"
  ```
  Then drag `~/Downloads/twozero.tox` into TD and enable MCP.

- [ ] **ffmpeg** installed
  ```bash
  brew install ffmpeg
  ```

- [ ] **p5.js export capability** — modern browser + optional Node.js:
  ```bash
  npm install -g puppeteer
  ```

- [ ] **AudioCraft** or royalty-free music alternative

### Required Data

- [ ] **Cinesmith events.jsonl** exists:
  ```bash
  ls ~/Desktop/cinesmith_v01/data/hermes_memory/episodic/events.jsonl
  ```
  If empty, scripts generate demo events automatically.

- [ ] **Dashboard recording** — screen-record the Cinesmith dashboard
  running a campaign (QuickTime Player or OBS).

- [ ] **ComfyUI is running** and accessible for hero frame generation.

---

## 🚀 Production Workflow

### Phase 1: Build All TouchDesigner Scenes (45–60 min)

Build all 5 scenes with one command:

```bash
cd ~/Desktop/cinesmith_v01/promo_video_kit/touchdesigner
python3 assemble_all_td.py
```

Then record each scene (15–30 seconds each):

```bash
# 1. Memory Graph V2
open /tmp/cinesmith_memory_graph_v2.toe
# F1 → click recorder TOP → Record ON → 20s → Record OFF

# 2. Pipeline Flow
open /tmp/cinesmith_pipeline_flow.toe
# F1 → click recorder TOP → Record ON → 15s → Record OFF

# 3. Audit Gate
open /tmp/cinesmith_audit_gate.toe
# F1 → click recorder TOP → Record ON → 15s → Record OFF

# 4. Command Center
open /tmp/cinesmith_command_center.toe
# F1 → click recorder TOP → Record ON → 15s → Record OFF

# 5. Provenance Web
open /tmp/cinesmith_provenance_web.toe
# F1 → click recorder TOP → Record ON → 15s → Record OFF
```

> 💡 **Pro tip:** Add an **Audio File In CHOP** → **AudioSpectrum CHOP** → **Math CHOP** (gain=10)
> → **CHOP to TOP** → connect to each scene's audio_input for audio-reactive visuals.

---

### Phase 2: p5js Transitions (20–30 min)

```bash
# Transition 1: "Data to Light"
open ~/Desktop/cinesmith_v01/promo_video_kit/p5js/transition_data_to_light.html
# Press 'R' to start, 'S' to save stills

# Transition 2: "The Audit Gate"
open transition_audit_gate.html

# Transition 3: "Memory Consolidation"
open transition_memory_consolidation.html
```

For video export (headless):
```bash
cd ~/Desktop/cinesmith_v01/promo_video_kit/p5js
node scripts/export-frames.js transition_data_to_light.html --frames 360
ffmpeg -framerate 30 -i frame_%06d.png -c:v prores -profile:v 3 transition1.mov
```

> 💡 **Quick path:** Screen-record each transition in the browser. 5 seconds each is enough.

---

### Phase 3: ComfyUI Hero Frames (15–30 min)

Generate 6–7 stunning hero images using your existing ComfyUI setup.

```bash
# Load wf_flux2_turbo_api in your dashboard
# Copy-paste each prompt from hero_frame_prompts.json
# Render at 1280×720
# Save to promo_video_kit/assets/
```

---

### Phase 4: Soundtrack (10–20 min, or skip)

Generate a custom soundtrack using AudioCraft, or use royalty-free music.

See: `audiocraft/soundtrack_prompts.md`

**Alternative:** Cyberpunk ambient / synthwave from freemusicarchive.org or Epidemic Sound.

---

### Phase 5: Dashboard Recording (10 min)

Record yourself:
1. Opening Cinesmith dashboard
2. Entering a brief
3. Clicking **Run Campaign**
4. Showing the event stream
5. Opening a shot lightbox

Save to `promo_video_kit/assets/dashboard.mov`.

---

### Phase 6: Assembly (5 min)

```bash
cd ~/Desktop/cinesmith_v01/promo_video_kit/scripts
chmod +x assemble_promo.sh
./assemble_promo.sh
```

Output: `/tmp/cinesmith_promo_final.mov`

Convert to MP4 for sharing:
```bash
ffmpeg -i /tmp/cinesmith_promo_final.mov \
  -c:v libx264 -crf 18 -preset slow \
  -c:a aac -b:a 192k \
  ~/Desktop/cinesmith_promo_final.mp4
```

---

## 🎯 The 90-Second Structure

| Time | Scene | Source | Duration |
|------|-------|--------|----------|
| 0:00–0:05 | Opening title: "Every pixel has an origin" | Generated by script | 5s |
| 0:05–0:15 | Dashboard: brief → Run Campaign → event stream | Screen recording | 10s |
| 0:15–0:25 | **Pipeline Flow** — 5 roles in orbital motion | TouchDesigner | 10s |
| 0:25–0:30 | p5js Transition: Data to Light | Browser | 5s |
| 0:30–0:40 | **Command Center** — HUD dashboard visualization | TouchDesigner | 10s |
| 0:40–0:50 | Hero frames: Director, Engineer, Renderer | ComfyUI renders | 10s |
| 0:50–0:55 | p5js Transition: The Audit Gate | Browser | 5s |
| 0:55–1:05 | **Audit Gate** — PASS/FAIL portal with particles | TouchDesigner | 10s |
| 1:05–1:15 | Hero frames: Gate, Memory, Output + provenance | ComfyUI + dashboard | 10s |
| 1:15–1:25 | **Provenance Web** — retry lineage in 3D | TouchDesigner | 10s |
| 1:25–1:35 | **Memory Graph V2** — living brain visualization | TouchDesigner | 10s |
| 1:35–1:40 | p5js Transition: Memory Consolidation | Browser | 5s |
| 1:40–1:45 | Closing title: "Cinesmith. Every shot, accounted for." | Generated by script | 5s |

---

## 🔥 TouchDesigner Scenes Reference

### Scene 1: Memory Graph V2
- **File:** `build_memory_graph_v2.py`
- **What:** Enhanced living memory graph with perlin noise drift, multi-layer feedback trails, RGB-separated bloom, film grain, and chromatic aberration
- **Colors:** Cyan (attempt), Green (success), Red (fail), Purple (insight), White (remediation)
- **Record:** 20 seconds

### Scene 2: Pipeline Flow
- **File:** `build_pipeline_flow.py`
- **What:** 5 orbital nodes (KIMI → HERMES → SPARK → VISION → MEMORY) with particle streams flowing between them, holographic rings, and rotating arcs
- **Record:** 15 seconds

### Scene 3: Audit Gate
- **File:** `build_audit_gate.py`
- **What:** Dramatic sci-fi portal with rotating hexagons, scan-line sweep, data packets entering from left, green PASS burst with particle explosion, red FAIL burst with glitch distortion
- **Record:** 15 seconds

### Scene 4: Command Center
- **File:** `build_command_center.py`
- **What:** Futuristic HUD with floating data panels, matrix rain event stream, progress rings, waveform visualization, and corner brackets
- **Record:** 15 seconds

### Scene 5: Provenance Web
- **File:** `build_provenance_web.py`
- **What:** 3D retry lineage visualization with parent/child shot nodes, bezier connection curves, data packet travel animation, and audit score rings
- **Record:** 15 seconds

---

## 🆘 Troubleshooting

### TouchDesigner MCP not responding
```bash
nc -z 127.0.0.1 40404 && echo "READY" || echo "NOT RUNNING"
```
If not running:
1. Open TouchDesigner
2. Drag `twozero.tox` into the network
3. Click the twozero icon → Settings → MCP → "Auto Start MCP" → Yes

### p5js transitions won't export frames
Screen-record them in the browser. QuickTime Player works fine.

### ffmpeg not found
```bash
brew install ffmpeg
```

### ComfyUI prompts too long
Trim to the first sentence of each prompt.

### The whole thing feels overwhelming
**Minimum viable promo:**
1. Record 10 seconds of dashboard
2. Run `build_pipeline_flow.py` and record 15 seconds
3. Run `build_audit_gate.py` and record 10 seconds
4. Assemble with the script
5. Add any music
6. Done — 30 seconds that's still better than 90% of entries.

---

## 📁 Asset Organization

```
promo_video_kit/
├── assets/
│   ├── dashboard.mov                  # YOUR screen recording
│   ├── td_memory_graph_v2.mov         # TouchDesigner
│   ├── td_pipeline_flow.mov           # TouchDesigner
│   ├── td_audit_gate.mov              # TouchDesigner
│   ├── td_command_center.mov          # TouchDesigner
│   ├── td_provenance_web.mov          # TouchDesigner
│   ├── transition1.mov                # p5js Data to Light
│   ├── transition2.mov                # p5js Audit Gate
│   ├── transition3.mov                # p5js Memory Consolidation
│   ├── hero_director.png              # ComfyUI render
│   ├── hero_engineer.png              # ComfyUI render
│   ├── hero_renderer.png              # ComfyUI render
│   ├── hero_gate.png                  # ComfyUI render
│   ├── hero_memory.png                # ComfyUI render
│   ├── hero_output.png                # ComfyUI render
│   └── soundtrack.wav                 # AudioCraft or royalty-free
```

Then update the paths in `scripts/assemble_promo.sh` and run it.

---

## 🏆 Final Submission Checklist

- [ ] Promo video exported as MP4 (`cinesmith_promo_final.mp4`)
- [ ] Video is 60–90 seconds
- [ ] Video shows the 5 model roles (Kimi, Hermes, Spark, Vision, Memory)
- [ ] Video includes at least one TouchDesigner visual
- [ ] Video includes provenance concept (retry lineage, audit scores)
- [ ] Writeup mentions TouchDesigner-MCP and p5js skills
- [ ] Tweet/writeup frames it as "the pipeline that promotes itself"

---

**Questions?** Just ask.

**Now go make something incredible.** 🚀
