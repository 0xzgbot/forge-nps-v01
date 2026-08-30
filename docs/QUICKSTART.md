# Produce in four minutes

Home is **`/`**. Soft white, one prompt, four lights. Hermes directs. Dual 3090s paint boards. Spark MiniMax H3 shoots. ffmpeg cuts. **`/studio`** is the old campaign app.

You do not need the GPUs on to learn the desk. Queue items wait. This page is the desk, not a second product.

## 1. Launch

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
./scripts/launch_cinesmith.sh --package
# http://127.0.0.1:7000
```

Hermes stays in repo `hermes_home/`. Isolation is not optional.

## 2. Connect

Top right: **Connect**. Four fields, four lights in the header.

| Light | Field | What it is |
| --- | --- | --- |
| Spark | Spark (H3 video) | MiniMax H3 only. Never stills by default. |
| 3090A | 3090 A (stills) | Flux / Z-Image boards |
| 3090B | 3090 B (stills) | Second board GPU, optional |
| LLM | Language model | Any OpenAI-compatible endpoint |

Green means `/system_stats` answered. Grey means configured but down. Video graphs never go to a 3090. Boards do not require Spark.

## 3. Pick models, Scout or Shoot, then Produce

Home has two menus:

- **Boards · 3090s** — Flux 2 (default), Flux Turbo, Klein 9B, Z-Image, ERNIE, or any stills graph you drop in `workflows/`.
- **Takes · Spark** — MiniMax H3 (default, stereo), LTX 2.3, Wan 2.2, or any video graph you drop in `workflows/`.

Wan 2.2 is I2V only. Scout on Wan will board first.

Type a short film. Pick a mode. Press **Produce**. Sample chips under the prompt fill a brief. ⌘K opens commands.

- **Shoot** — 3090 boards, you approve, then Spark. First+last (`fl2va`) when a shot has an end still.
- **Scout** — text-to-video when the family has T2V (H3 / LTX). No stills.

Hermes writes `story.md`, `script.md`, and `shots.json` into `data/produce/<job>/`. GPU work goes in `queue.json`. If Spark or a 3090 is off, items stay **waiting_for_host**. Press **Run queue** when the boxes are up.

Your Comfy presets in `workflows/` are called with the shot prompt. You do not edit the graph.

## 4. Boards, takes, cut

Once shots exist, the project bar shows title, runtime, and a continuity grade (locks, not beauty).

1. Click a board → inspector (first/last frames, H3 prompt, duration, mode, seed, notes).
2. Drop face/location stills, optional voice, and a **score** wav (filename containing music / bed / score) under **Identity**.
3. **Queue boards / takes** plans GPU work. **Run queue** submits it (only when you mean it). Add or delete shots without waiting on Hermes.
4. Timeline: reorder, mute (H3 stereo stays on unmuted clips), range retake (in/out seconds).
5. **Export** — 16:9 / 9:16 / 1:1 / 2.39, fade, title card, mix score. **Assemble cut** writes `cut.mp4` plus `cut.srt`. **Handoff zip** packs the job.

Crew chips (Producer, Story, Video, …) open a bot sheet. They talk through Hermes. They are not a JSON stage machine.

Keyboard: **⌘K** command palette · **B** board · **T** take · **A** assemble · **⌘↵** Produce.

The LLM light is green only when the language model answers. Grey means the URL is saved but the box is down. After a cut exists, the desk plays it and keeps older assembles under **cuts/**.

## Do not

- Do not send H3 to a 3090.
- Do not paint boards with H3.
- Do not point Hermes at `~/.hermes`.
- Do not commit `data/config.json` or `data/produce/`.

Full reference: [PRODUCE.md](PRODUCE.md).
