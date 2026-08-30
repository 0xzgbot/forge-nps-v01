# Produce — prompt to cut

`/` is Cinesmith Produce. Hermes is the director. Dual 3090s paint boards. Spark MiniMax H3 shoots motion with native stereo. ffmpeg builds the cut.

`/studio` is the older Images / Videos / Stories campaign app. It stays labeled **Legacy studio**.

## Hardware

| Host | Config key | Job |
| --- | --- | --- |
| Spark | `COMFYUI_PRIMARY` | MiniMax H3 video (never stills by default) |
| 3090 A | `COMFYUI_STILLS_A` or `COMFYUI_SECONDARY` | Flux / Z-Image boards |
| 3090 B | `COMFYUI_STILLS_B` | Parallel boards |
| LLM | `LLM_BASE_URL` / Settings | Any OpenAI-compatible model |

H3 is not sent to a 3090. If both 3090s are down, Flux boards may use Spark. H3 never fails over to a 3090.

## Scout vs Shoot

- **Scout** — H3 text-to-video (`t2va`). No boards.
- **Shoot** — 3090 stills, then H3. `fl2va` when a shot has an end still, else `i2va`. `r2va` when identity refs exist.

## Job directory

`data/produce/<job_id>/`

| File | Meaning |
| --- | --- |
| `prompt.md` `story.md` `script.md` | Narrative |
| `shots.json` | Shot objects |
| `boards/` | 3090 stills |
| `clips/` | H3 takes |
| `identity/` | Face / location / voice refs |
| `queue.json` | GPU work Hermes (or the UI) appended |
| `edit.json` | Timeline `{shot_id, clip, muted}` |
| `cut.mp4` | Assembled film |
| `STATUS.md` | Honest one-liner |

## Queue

GET snapshot **never** submits Comfy jobs. Append to `queue.json` or POST `/api/produce/<job>/queue`. Actions: `render_board`, `render_take`, `range_retake`, `assemble`.

If Spark or a 3090 is down, items stay `waiting_for_host`. **Run queue** when the boxes are up. Comfy presets in `workflows/` are called with the shot prompt.

## UI

- Shot strip: board, approve, take, retake. Click a shot for the inspector (first/last frames, H3 prompt, duration, mode, audio playback).
- Identity strip: face/location stills and a voice file for R2VA.
- Timeline: reorder, mute (keeps H3 stereo on unmuted clips), range retake (in/out seconds → extract frames → FL2VA → stitch the rest of the original).
- Color pass: mild continuity grade on `cut.mp4` after concat.
- Queue panel with a rough ETA.

## API (selected)

- `POST /api/produce/start` `{prompt, produce_mode}`
- `GET /api/produce/{job}`
- `POST /api/produce/{job}/render-board` / `render-take` / `range-retake`
- `POST /api/produce/{job}/queue` / `queue/plan` / `queue/run`
- `PUT /api/produce/{job}/shots/{shot_id}`
- `POST /api/produce/{job}/upload` (multipart `kind`: identity, still, end_still, voice, guide)
- `PUT /api/produce/{job}/options` `{color_pass}`
- `POST /api/produce/{job}/assemble`

## Workflows

H3 graphs: `20` T2VA, `21` I2VA, `22` FL2VA, `23` R2VA under `workflows/`. LTX 2.3 remains a draft lane. Drop your own Comfy presets in `workflows/` — Produce injects the prompt.

Prompt skill: `hermes_home/skills/h3-prompt-writing`.
