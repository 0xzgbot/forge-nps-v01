# Forge NPS — Promo Video Production Kit

> **The Pipeline That Promotes Itself**
>
> This kit contains everything needed to produce a 90-second promo video for
> Forge NPS using NousResearch's newly released creative skills:
> TouchDesigner-MCP, p5js, ComfyUI v5, and AudioCraft.
>
> The video demonstrates Forge NPS creating its own marketing — a meta-narrative
> that has genuinely no competition at the hackathon.

---

## 🎬 What's In This Kit

```
promo_video_kit/
├── touchdesigner/
│   └── build_memory_graph.py      # Builds TD network via MCP + GLSL shader
├── p5js/
│   ├── transition_data_to_light.html       # Particles → "FORGE" text
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

## ✅ YOUR SETUP CHECKLIST (Things You Need To Do)

These are the **prerequisites on your machine** that I cannot set up remotely.
Check them off as you go:

### Required Software

- [ ] **TouchDesigner** installed (Non-Commercial is FREE)
  - Download: https://derivative.ca/download
  - Non-Commercial caps resolution at 1280×1280 — we use 1280×720, so you're fine

- [ ] **twozero MCP plugin** installed in TouchDesigner
  ```bash
  bash "${HERMES_HOME:-$HOME/.hermes}/skills/creative/touchdesigner-mcp/scripts/setup.sh"
  ```
  Then drag `~/Downloads/twozero.tox` into TD and enable MCP.

- [ ] **ffmpeg** installed
  ```bash
  brew install ffmpeg
  ```

- [ ] **p5.js export capability** — just a modern browser + Node.js for headless:
  ```bash
  # For headless frame capture (optional but recommended)
  npm install -g puppeteer  # or use the bundled scripts/export-frames.js
  ```

- [ ] **AudioCraft** or access to music generation (optional — can use royalty-free music instead)

### Required Data

- [ ] **Forge NPS events.jsonl** exists and has data:
  ```bash
  ls ~/Desktop/forge_nps_v01/data/hermes_memory/episodic/events.jsonl
  ```
  If empty, the TD script generates demo events automatically.

- [ ] **Dashboard recording** — YOU need to screen-record the Forge NPS dashboard
  running a campaign (use QuickTime Player or OBS).

- [ ] **ComfyUI is running** and accessible for hero frame generation.

---

## 🚀 Production Workflow (Step by Step)

### Phase 1: TouchDesigner Memory Graph (30–45 min)

This creates the **"living brain"** visualization — the biggest wow factor.

```bash
cd ~/Desktop/forge_nps_v01/promo_video_kit/touchdesigner
python3 build_memory_graph.py
```

**What happens:**
- Reads your `events.jsonl`
- Creates a TD network with GLSL shader, feedback trails, bloom, glow
- Outputs `/tmp/forge_memory_visualizer.toe`

**Then you do:**
1. Open TouchDesigner
2. File → Open → `/tmp/forge_memory_visualizer.toe`
3. (Optional but recommended) Add an **Audio File In CHOP** and wire it:
   ```
   AudioFileIn CHOP → AudioSpectrum CHOP → Math CHOP (gain=10)
   → CHOP to TOP → connect to `memory_graph` second input
   ```
4. Press **F1** to enter Perform Mode
5. Click the `recorder` TOP, set **Record** to ON
6. Let it run for 30–60 seconds
7. Set **Record** to OFF
8. Video saved to: `/tmp/forge_memory_graph_output.mov`

> 💡 **Pro tip:** Use your AudioCraft-generated soundtrack as the audio input.
> The visuals will pulse to the beat.

---

### Phase 2: p5js Transitions (20–30 min)

These are the **visual glue** between scenes.

#### Transition 1: "Data to Light"
```bash
# Open in browser
open ~/Desktop/forge_nps_v01/promo_video_kit/p5js/transition_data_to_light.html

# Press 'R' to start animation
# Press 'S' to save a PNG still
```

For video export (headless):
```bash
cd ~/Desktop/forge_nps_v01/promo_video_kit/p5js
node scripts/export-frames.js transition_data_to_light.html --frames 360
ffmpeg -framerate 30 -i frame_%06d.png -c:v prores -profile:v 3 transition1.mov
```

#### Transition 2: "The Audit Gate"
```bash
open transition_audit_gate.html
# Press 'R' to run
```

#### Transition 3: "Memory Consolidation"
```bash
open transition_memory_consolidation.html
# Press 'R' to run
```

> 💡 **Quick path:** If headless rendering is too much trouble, just screen-record
> each transition playing in the browser. 5 seconds of each is enough.

---

### Phase 3: ComfyUI Hero Frames (15–30 min)

Generate 6–7 stunning hero images using your existing ComfyUI setup.

The prompts are in:
```
~/Desktop/forge_nps_v01/promo_video_kit/comfyui/hero_frame_prompts.json
```

**Quick method:** Use your existing `batch_flux2_turbo_hackathon.py` script and
inject these prompts. Or run one at a time through the Forge NPS dashboard.

**Recommended workflow:**
1. Load `wf_flux2_turbo_api` in your dashboard
2. Copy-paste each prompt from the JSON
3. Render at 1280×720
4. Save to `promo_video_kit/assets/`

---

### Phase 4: Soundtrack (10–20 min, or skip)

Generate a custom soundtrack using AudioCraft, or use a royalty-free track.

See:
```
~/Desktop/forge_nps_v01/promo_video_kit/audiocraft/soundtrack_prompts.md
```

**Alternative:** Use a track from https://freemusicarchive.org or Epidemic Sound.
Cyberpunk ambient / synthwave genres work best.

---

### Phase 5: Dashboard Recording (10 min)

**You must do this.** Record yourself:
1. Opening Forge NPS dashboard
2. Entering a brief
3. Clicking **Run Campaign**
4. Showing the event stream
5. Opening a shot lightbox

Use **QuickTime Player** → File → New Screen Recording.
Record 10–15 seconds. Save to `promo_video_kit/assets/dashboard.mov`.

---

### Phase 6: Assembly (5 min)

```bash
cd ~/Desktop/forge_nps_v01/promo_video_kit/scripts
chmod +x assemble_promo.sh
./assemble_promo.sh
```

This produces:
```
/tmp/forge_nps_promo_final.mov
```

Review it. If good, convert to MP4 for sharing:
```bash
ffmpeg -i /tmp/forge_nps_promo_final.mov \
  -c:v libx264 -crf 18 -preset slow \
  -c:a aac -b:a 192k \
  ~/Desktop/forge_nps_promo_final.mp4
```

---

## 🎯 The 90-Second Structure

| Time | Scene | Source |
|------|-------|--------|
| 0:00–0:05 | Opening title: "Every pixel has an origin" | Generated by script |
| 0:05–0:15 | Dashboard: brief → Run Campaign → event stream | Your screen recording |
| 0:15–0:35 | TouchDesigner: living memory graph visualization | `build_memory_graph.py` output |
| 0:35–0:40 | p5js Transition: Data to Light | Browser/headless render |
| 0:40–0:50 | Hero frames: Director, Engineer, Renderer | ComfyUI renders |
| 0:50–0:55 | p5js Transition: The Audit Gate | Browser/headless render |
| 0:55–1:05 | Hero frames: Gate, Memory, Output + provenance overlay | ComfyUI + dashboard lightbox |
| 1:05–1:20 | Remediation: failed shot → retry → success | Dashboard recording + TD visual |
| 1:20–1:25 | p5js Transition: Memory Consolidation | Browser/headless render |
| 1:25–1:30 | Closing title: "Forge NPS. Every shot, accounted for." | Generated by script |

---

## 🔥 Why This Has No Competition

| Other Entries | Forge NPS Promo |
|--------------|-----------------|
| Screen recording + stock music | **Recursive pipeline** — the app creates its own promo |
| Static screenshots | **TouchDesigner real-time visuals** of the memory graph as living art |
| Generic transitions | **p5js generative particle transitions** between scenes |
| Boring voiceover | **AudioCraft-generated soundtrack** that drives the visuals |
| Talk about features | **Show provenance** — every frame has an audit trail |

You're using NousResearch features that were **literally released today** (v0.12.0,
April 30). Nobody else will have TouchDesigner-MCP + p5js + ComfyUI + their own
app in a recursive creative loop.

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
Just **screen-record them** in the browser. QuickTime Player works fine.

### ffmpeg not found
```bash
brew install ffmpeg
```

### ComfyUI prompts too long for your workflow
The prompts are optimized for Flux2. If using a different model, trim to the
first sentence of each prompt — that's usually enough.

### The whole thing feels overwhelming
**Minimum viable promo:**
1. Record 10 seconds of dashboard
2. Run the TouchDesigner script for 20 seconds
3. Assemble with the script (it auto-fills placeholders)
4. Add any music
5. Done — you have a 30-second promo that's still better than 90% of entries.

---

## 📁 Asset Organization (Recommended)

As you produce assets, organize them like this:

```
promo_video_kit/
├── assets/
│   ├── dashboard.mov              # YOUR screen recording
│   ├── td_output.mov              # TouchDesigner recording
│   ├── transition1.mov            # p5js Data to Light
│   ├── transition2.mov            # p5js Audit Gate
│   ├── transition3.mov            # p5js Memory Consolidation
│   ├── hero_director.png          # ComfyUI render
│   ├── hero_engineer.png          # ComfyUI render
│   ├── hero_renderer.png          # ComfyUI render
│   ├── hero_gate.png              # ComfyUI render
│   ├── hero_memory.png            # ComfyUI render
│   ├── hero_output.png            # ComfyUI render
│   └── soundtrack.wav             # AudioCraft or royalty-free
```

Then update the paths in `scripts/assemble_promo.sh` and run it.

---

## 🏆 Final Submission Checklist

- [ ] Promo video exported as MP4 (`forge_nps_promo_final.mp4`)
- [ ] Video is 60–90 seconds
- [ ] Video shows the 5 model roles (Kimi, Hermes, Spark, Vision, Memory)
- [ ] Video includes at least one TouchDesigner visual
- [ ] Video includes provenance concept (retry lineage, audit scores)
- [ ] Writeup mentions TouchDesigner-MCP and p5js skills (proves you used new features)
- [ ] Tweet/writeup frames it as "the pipeline that promotes itself"

---

**Questions?** While you're working on the main app, I'm here to debug any of
these components, refine prompts, or adjust the assembly. Just ask.

**Now go make something incredible.** 🚀
