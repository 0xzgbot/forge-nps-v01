# Forge Cinema Kit — Hackathon Edition v2
## "The Infinite Studio"

A completely different creative direction from the first video. This one tells the story of **scale** — what happens when a single creative idea multiplies through AI into an entire media empire.

---

## Creative Direction

**Vibe:** Dark cinematic control room meets generative art installation. Think *Blade Runner 2049* UI crossed with *Everything Everywhere All At Once* rapid-fire montage energy.

**Color Palette:**
- Deep void blacks (`#050505`)
- Forge dashboard purple (`#7c3aed`)
- Neon cyan pipeline (`#00f0ff`)
- Warm gold for the "human touch" moments (`#ffb700`)
- Social media hot pink (`#ff006e`)

**Audio Suggestion:** 
- 0-20s: Ambient, almost silent with sub-bass pulses
- 20-50s: Driving techno/industrial beat (160-170 BPM)
- 50-75s: Epic cinematic orchestral + synth hybrid

---

## Scene Breakdown

### Scene 1: "The Spark" (0-8s)
A single text prompt materializes from noise. Characters don't type — they **condense** out of particle dust. The prompt then ignites, burning away to reveal the first generated image emerging from white-hot center.

**TD Technique:** Noise CHOP → Text TOP with dynamic text, Particle SOP with attractor forces, Feedback TOP for the "burn" transition.

### Scene 2: "Mitosis" (8-18s)
That single image divides. One becomes four, four becomes sixteen. Each new image morphs into a different shot type — wide establishing, close-up, aerial, handheld POV. The camera pulls back through a 3D grid of floating frames.

**TD Technique:** Replicator COMP with instanced geometry, GLSL MAT for morphing textures, Camera COMP with animated path.

### Scene 3: "The Forge" (18-32s)
We enter the pipeline. Abstract data visualization — shots flow as glowing orbs through a network of processing nodes. Each node is labeled with Forge agent names: **Image Analyst**, **Duration Planner**, **Prompt Engineer**, **ComfyUI**. Orbs change color as they pass through stages.

**TD Technique:** Geometry COMP with instanced spheres, CHOP-based animation curves for flow, Trail SOP for particle trails, Text TOP labels.

### Scene 4: "Social Velocity" (32-48s)
Smash cut to chaos. TikTok/Instagram/Reels UI frames fly past the camera like a hyperspace tunnel. Each frame holds generated content. Fake metrics (views, likes, shares) explode upward. The color palette shifts to vibrant social neons.

**TD Technique:** Fast Camera COMP movement through instanced plane geometry, Text TOP with animated numbers, Over TOP for UI chrome, Blur TOP for motion streaks.

### Scene 5: "The Theater" (48-62s)
The chaos resolves into perfect stillness. We're in a darkened movie theater, looking over the audience's shoulders at a massive curved screen. The screen shows a cinematic trailer — dramatic music, epic shots, title cards. Camera slowly pushes forward, through the screen, into the movie world.

**TD Technique:** 3D theater environment (simple geo), Render TOP for screen content, Camera COMP push-in, Fog MAT for atmospheric depth.

### Scene 6: "Infinite Studio" (62-75s)
The movie world IS the studio. We realize the "audience" is actually an infinite hall of monitors, each showing a different campaign in progress. Pull back to reveal the Forge NPS logo at the center of a neural-network-like structure. Tagline appears.

**TD Technique:** Recursive instancing, Feedback TOP for infinite zoom effect, elegant typography with kerning animation.

---

## Quick Start

1. **Generate source images** using the ComfyUI prompts in `comfy_prompts/`
2. **Open TouchDesigner** and run the builder script in the textport:
   ```python
   exec(open("path/to/hackathon_cinema_kit/td_scripts/build_master_network.py").read())
   ```
3. **Replace placeholders** in `/project1/scene_X/media` with your generated images
4. **Set Render TOP resolution** to your target output (1920×1080 or 3840×2160)
5. **Hit Render** or record via Movie File Out TOP

---

## Output Specs
- **Resolution:** 1920×1080 (or 4K if GPU permits)
- **Frame Rate:** 30fps
- **Duration:** ~75 seconds
- **Codec:** H.264 or ProRes 422 for editing

---

## File Structure
```
hackathon_cinema_kit/
├── README.md                          # This file
├── td_scripts/
│   ├── build_master_network.py        # One-click TD network builder
│   ├── scene_spark.py                 # Scene 1 operators
│   ├── scene_mitosis.py               # Scene 2 operators
│   ├── scene_forge.py                 # Scene 3 operators
│   ├── scene_social.py                # Scene 4 operators
│   ├── scene_theater.py               # Scene 5 operators
│   └── scene_infinite.py              # Scene 6 operators
├── comfy_prompts/
│   ├── spark_images.json              # Prompts for Scene 1 source images
│   ├── social_mockups.json            # Prompts for social content frames
│   └── theater_trailer.json           # Prompts for cinematic trailer shots
├── assets/
│   ├── forge_logo_white.png           # Placeholder for logo
│   └── ui_chrome/                     # UI frame overlays (generated or drawn)
└── ffmpeg_scripts/
    └── assemble_with_music.sh         # Post-production assembly script
```
