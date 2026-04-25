---
name: sienna-nomad-i2v-anchor-generator
description: Generates I2V anchor image prompts from existing video prompts for the Sienna Nomad project. Each video prompt requires a corresponding static first-frame image to be rendered before LTX 2.3 image-to-video generation can begin.
---

# Sienna Nomad — I2V Anchor Image Prompt Generator

## Purpose

LTX 2.3 is image-to-video. Every `Prompt_NN_Video_XX.md` file needs a corresponding **anchor image** — the static first frame that LTX uses as its i2v seed. This skill generates those anchor prompts and their JSON payloads.

**Render order is mandatory:**
1. ALL `_ANCHOR.json` payloads → rendered first via z-image
2. Resulting images → stored as `Prompt_NN_Video_XX_ANCHOR.png`
3. Only THEN: LTX 2.3 video generation with each anchor image as i2v input

---

## Naming Convention

| File | Purpose |
|---|---|
| `Prompt_NN_Video_XX.md` | LTX video motion prompt (source) |
| `Prompt_NN_Video_XX_ANCHOR.md` | Static first-frame image prompt (derived) |
| `JSON_PAYLOADS/Prompt_NN_Video_XX_ANCHOR.json` | z-image payload for the anchor |
| `Prompt_NN_Video_XX_ANCHOR.png` | Rendered anchor image (output) |

The `_ANCHOR` suffix is the only difference in name. This makes the pairing unambiguous.

---

## Trigger Conditions

- When asked to "create anchor prompts for [episode]"
- When asked to "set up i2v for [episode]"  
- When new video prompts are added to any episode folder
- Before any LTX 2.3 video generation run for any episode that lacks anchor images

---

## Step-by-Step Workflow

### Step 1 — Find All Video Prompts

```python
import os, glob

episode_dir = "~/Desktop/Sienna_Nomad_Project/04_Prompt_Library/EP{NN}_{Name}/"
video_prompts = sorted(glob.glob(os.path.join(episode_dir, "Prompt_*_Video_*.md")))
# e.g. ['Prompt_01_Video_01.md', 'Prompt_01_Video_02.md', 'Prompt_01_Video_03.md']
```

Skip any file that already has a corresponding `_ANCHOR.md` to avoid overwriting.

### Step 2 — Extract First-Frame Information from Video Prompt

Read the video prompt and extract these fields for the anchor:

```
From the video prompt, take:
- EXPOSURE time window (same)
- CORE SUBJECT (identical — same character, same scene)
- LIGHTING/ENVIRONMENT (identical — same lighting state)
- ATMOSPHERE (identical)
- TEXTURE/MATERIALITY (identical)
- OPTICAL/CAMERAS (take lens and format, remove motion-specific notes)

Convert FLUX_DIR_COMMAND:
- REMOVE: camera_motion (there is no motion in a still frame)
- KEEP: lighting tags
- KEEP: lens tags
- KEEP: texture tags
- ADD: composition tags describing the STARTING FRAME position

For camera position in the anchor:
- The anchor shows the OPENING POSITION of the camera before any movement begins
- Example: if video says "slow lateral pan starting from the left ridge" →
  anchor shows the left ridge, camera stationary, before the pan starts
- If video has a drone shot descending → anchor shows the HIGH starting altitude
- If video has a push-in → anchor shows the wide starting distance
```

### Step 3 — Write the Anchor Prompt File

Format for `Prompt_NN_Video_XX_ANCHOR.md`:

```markdown
# Prompt_NN_Video_XX_ANCHOR

[TYPE: I2V_ANCHOR | EXPOSURE: {same as video} | LINKED_VIDEO: Prompt_NN_Video_XX.md]

**ANCHOR ROLE:** Static first-frame image. This image is rendered by z-image and used as the i2v seed for `Prompt_NN_Video_XX.md`. Must be rendered BEFORE the video generation run.

**CINEMATIC CONTEXT:**
{Describe the opening frame — what the camera sees at the exact moment before any motion begins. Write as a still photograph, not a motion description.}

**VISUAL BLUEPRINT:**
- **CORE SUBJECT:** {Identical to video prompt — full Sienna + Aura description}
- **LIGHTING/ENVIRONMENT:** {Identical to video prompt}
- **ATMOSPHERE:** {Identical to video prompt}
- **TEXTURE/MATERIALITY:** {Identical to video prompt}
- **OPTICAL/CAMERAS:** {Lens, format, aperture — same as video. Remove motion notes.}
- **COMPOSITION:** {Opening frame composition — rule of thirds, subject placement, framing}

**FLUX_DIR_COMMAND:**
[composition: {opening_frame_composition}]
[lighting: {same lighting tags from video}]
[lens: {same lens tags from video}]
[texture: {same texture tags from video}]
```

**Key rules for the anchor prompt:**
- NO `camera_motion` tag — it is a still image
- NO motion language in CINEMATIC CONTEXT ("the camera drifts", "sweeps", "pans" — remove these)
- The COMPOSITION tag must describe the exact opening frame position
- Character anchors (Sienna + Aura descriptions) must be identical to the source video prompt
- The EXPOSURE time window must match exactly — this is how LTX knows the lighting state

### Step 4 — Determine Resolution from the Video Prompt

**The anchor image MUST match the video output resolution.** LTX 2.3 conditions on the anchor — a resolution mismatch causes stretching/cropping on the first frame.

Derive resolution from the CINEMATIC CONTEXT and OPTICAL/CAMERAS fields:

| Signal in video prompt | Resolution | Width × Height |
|---|---|---|
| Drone / wide / establishing / landscape / 24mm–35mm | Landscape 16:9 | 1024 × 576 |
| Portrait / close-up / intimate / vertical / 85mm+ | Portrait 9:16 | 576 × 1024 |
| Unclear | Default landscape | 1024 × 576 |

Record the chosen resolution in the `_ANCHOR.md` file under a `RENDER_SPEC` line:
```
[RENDER_SPEC: 1024×576 | MODEL: z-image | LINKED_VIDEO: Prompt_NN_Video_XX.md]
```

### Step 5 — Generate the JSON Payload

The anchor JSON uses **`hermes_z_image_api.json`** from `~/workflows/`. Read it via MCP `read_workflow`, then inject.

**Inject the anchor prompt text** by tracing from KSampler positive input to find the CLIPTextEncode node ID, then set `payload["prompt"][pos_node_id]["inputs"]["text"]`.

**Set resolution** by updating the `EmptySD3LatentImage` node's `widgets_values` to the dimensions derived in Step 4:
- Landscape: `[1024, 576, 1]`
- Portrait: `[576, 1024, 1]`

**Set filename_prefix** in the `SaveImage` node's `widgets_values` to:
```
Prompt_NN_Video_XX_ANCHOR
```

**Save as:** `JSON_PAYLOADS/Prompt_NN_Video_XX_ANCHOR.json`

### Step 5 — Confirm Output and Report

After generating all anchors for an episode, report:

```
EP{NN}_{Name} — Anchor Generation Complete

Created {N} anchor pairs:
  Prompt_{NN}_Video_01 → Prompt_{NN}_Video_01_ANCHOR.md + .json  ✓
  Prompt_{NN}_Video_02 → Prompt_{NN}_Video_02_ANCHOR.md + .json  ✓
  Prompt_{NN}_Video_03 → Prompt_{NN}_Video_03_ANCHOR.md + .json  ✓

RENDER ORDER FOR THIS EPISODE:
  PHASE 1 (image generation): Submit all _ANCHOR.json payloads to z-image
  PHASE 2 (video generation): After all anchor PNGs are confirmed rendered,
                               submit LTX video prompts with anchor images as i2v input

Anchor PNG expected output location: ComfyUI output folder → named Prompt_{NN}_Video_XX_ANCHOR_XXXXX.png
```

---

## Pitfalls

**Do NOT create anchor prompts for Photo prompts** — only `_Video_XX.md` files get anchors. Photo prompts are standalone.

**Do NOT use the video prompt text directly as the anchor text.** The camera_motion and motion language must be removed. A video prompt fed into z-image will produce a blurry, motion-artifact image.

**Maintain character anchor consistency.** The Sienna + Aura description in the anchor must be word-for-word identical to the source video prompt. Any drift here creates visual inconsistency when LTX animates from the anchor.

**The EXPOSURE time must match exactly.** LTX conditions on lighting state from the anchor image. If anchor says 04:30 and video says 05:00, the lighting will fight the anchor.

**Anchor resolution must match video dimensions.** Use 1024×576 for landscape shots, 576×1024 for portrait. Never use square (1024×1024) — LTX will stretch it. Derive from the video prompt's CINEMATIC CONTEXT (see Step 4 table).

---

## Gold Standard Example

⚠️ **Every anchor file MUST look like this. No N/A values. No placeholder text. Every field fully written.**

The completed gold standard anchor is at:
`~/Desktop/Sienna_Nomad_Project/04_Prompt_Library/EP01_Dawn_Ritual/Prompt_01_Video_01_ANCHOR.md`

Read that file before generating any anchor. Use it as the template for every other anchor you write.

**What the gold standard does:**
- Pulls ALL detail from the source video prompt — lighting, atmosphere, texture, lens, character description
- Writes a full paragraph CINEMATIC CONTEXT describing the frozen opening frame
- Every VISUAL BLUEPRINT field is fully written — never N/A, never placeholder
- FLUX_DIR_COMMAND has composition tags describing the static frame position (not motion)
- Character description matches source exactly: "Sienna (30s, sun-kissed skin, freckles, Golden-Rust hair with blonde highlights) and Aura (Sleek, muscular Vizsla with a Golden-Rust coat)"

**What killed the previous batch:**
Every anchor was written with `N/A` for all fields. z-image had nothing to work with and generated generic studio shots. The model cannot invent content — you must provide it everything.
