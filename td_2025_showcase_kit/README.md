# Forge NPS — TouchDesigner 2025 Showcase Kit
## "The Living Pipeline"

> A next-generation visual experience built exclusively for **TouchDesigner 2025+**, showcasing POPs (Point Operators), 3D textures, Layer Mix compositing, Render Simple TOP, and GPU-accelerated particle systems — all telling the Forge NPS creation story.

---

## 🚀 What's New Here

Unlike the previous kits (SOP-based particles, pure GLSL), this kit leverages **every major TD 2025 feature**:

| Feature | How We Use It |
|---------|--------------|
| **POPs** | Millions of GPU particles for data streams, orbital nodes, volumetric clouds |
| **3D Textures** | Volumetric fog, god rays, and depth-based effects in Scene 3 |
| **Render Simple TOP** | Direct POP rendering without Geometry/Camera/Light COMPs |
| **Layer Mix TOP** | Per-layer glow, color grading, and composite operations |
| **Force POP** | Radial, spiral, and planar forces for particle choreography |
| **Instance POP** | Crystalline memory structures with unique images per instance |
| **Geo Text COMP** | Face-camera labels that always read correctly |
| **Color Space Workflows** | Proper ACES/linear handling throughout the pipeline |

---

## 🎬 The 90-Second Experience

| Time | Scene | TD 2025 Stars |
|------|-------|---------------|
| 0:00–0:10 | **Genesis** — Brief appears, particles condense, hero image materializes | `noisePOP`, `forcePOP` (attractor), `renderSimpleTOP` |
| 0:10–0:25 | **The Five Minds** — 5 orbital agents, millions of data packets stream between | `noisePOP`, `forcePOP` (orbital), `instancePOP`, `layerMixTOP` |
| 0:25–0:40 | **Inside the Forge** — Volumetric 3D space, ComfyUI images float, god rays | `noiseTOP` (3D), `renderSimpleTOP`, volumetric compositing |
| 0:40–0:55 | **The Audit Gate** — Dimensional portal, particles flash green/red, loop back | `forcePOP` (radial/planar), feedback trails, `convertPOP` |
| 0:55–1:10 | **Memory Palace** — Infinite hall of crystals, each holding a campaign | `instancePOP`, `geoTextCOMP`, `pointFileInPOP` |
| 1:10–1:30 | **The Output** — Convergence explosion, final video emerges on particle screen | `forcePOP` (explosive), `moviefileinTOP`, `layerMixTOP` |

---

## ✅ Setup

### Required
- **TouchDesigner 2025.31550+** (Official build, Oct 2025 or later)
- **twozero MCP plugin** (for `build_master.py` method)
- **ffmpeg** (for final assembly)
- **ComfyUI-generated media** placed in `assets/` (see `comfy_prompts/`)

### ComfyUI Media Checklist
Generate these with your Forge NPS pipeline and place in `assets/`:

```
assets/
├── hero_genesis.png          # Cinematic wide shot, golden hour
├── portrait_kimi.png         # Cyberpunk director, neon cyan
├── portrait_hermes.png       # Purple-lit engineer, holographic UI
├── portrait_spark.png        # Orange-glowing renderer, GPU core
├── portrait_vision.png       # Green-eyed auditor, scanning beam
├── portrait_memory.png       # Gold-memory archivist, crystalline
├── forge_interior_01.png     # Futuristic render farm interior
├── forge_interior_02.png     # Server cathedral, light beams
├── forge_interior_03.png     # Abstract data landscape
├── audit_pass.png            # Green glowing "PASS" typography
├── audit_fail.png            # Red glitch "FAIL" typography
├── memory_crystal_01.png     # Past campaign still, framed in glass
├── memory_crystal_02.png     # Another campaign, different palette
├── memory_crystal_03.png     # Third campaign, emotional beat
├── final_output_video.mov    # 5s cinematic reveal, your best shot
└── forge_logo_white.png      # Forge NPS logo, transparent PNG
```

See `comfy_prompts/shot_prompts.json` for exact prompts to feed into Forge NPS.

---

## 🏗️ Build Methods

### Method 1: MCP (Recommended)
```bash
cd ~/Desktop/forge_nps_v01/td_2025_showcase_kit
python3 build_master.py
```
Then open each scene `.toe` and record.

### Method 2: Textport (No MCP)
Open TouchDesigner, open Textport (Alt+T), run:
```python
exec(open("/Users/zgbot/Desktop/forge_nps_v01/td_2025_showcase_kit/build_master_textport.py").read())
```

---

## 🎥 Recording Workflow

### Per-Scene Recording
Each scene saves as its own `.toe`. Open, press F1, hit Record on the Movie File Out TOP.

| Scene | Duration | Resolution | Codec |
|-------|----------|------------|-------|
| Genesis | 10s | 1920×1080 | ProRes 422 |
| Five Minds | 15s | 1920×1080 | ProRes 422 |
| Inside Forge | 15s | 1920×1080 | ProRes 422 |
| Audit Gate | 15s | 1920×1080 | ProRes 422 |
| Memory Palace | 15s | 1920×1080 | ProRes 422 |
| Output | 20s | 1920×1080 | ProRes 422 |

### Assembly
```bash
cd ~/Desktop/forge_nps_v01/td_2025_showcase_kit
python3 assemble_final.py
```
Output: `~/Desktop/FORGE_NPS_MEDIA/forge_2025_showcase_final.mp4`

---

## 🔥 Why This Looks Better Than V1

| V1 (Pre-2025) | V2 (This Kit) |
|---------------|---------------|
| SOP particles (~10k max) | POP particles (millions, GPU) |
| GLSL-only orbital math | Force POP orbital motion |
| Standard 2D compositing | 3D texture volumetrics |
| Single blur bloom | Layer Mix per-layer glow |
| Geometry COMP + Camera + Light required | Render Simple TOP, direct POP render |
| Static image planes | Instance POP with per-point images |

---

## 🆘 Troubleshooting

### "POP operator not found"
You need TouchDesigner **2025.31550+**. Check Help → About.

### "Render Simple TOP is black"
Ensure your POP has valid `P` (position) attributes. Check the POP node viewer (right-click → Display Attribute Colors).

### "ComfyUI images not loading"
Set `FORGE_MEDIA_ROOT` env var, or edit the `moviefileinTOP` / `constantTOP` paths in each scene script.

### Color looks wrong
TD 2025 has per-project color space. The kit assumes **Linear** working space. Check Preferences → Color Space.

---

**Questions?** Check the Troubleshooting section or ask.

**Now go make something that looks impossible.** 🚀
