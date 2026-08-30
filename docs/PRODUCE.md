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

H3 is not sent to a 3090. If both 3090s are down, Flux boards may use Spark. Video graphs never fail over to a 3090.

Produce model menus (also `GET /api/produce/models`):

| Lane | Default | Also in the repo |
| --- | --- | --- |
| Boards · 3090s | Flux 2 | Flux Turbo, Klein 9B, Z-Image, ERNIE, character sheet |
| Takes · Spark | MiniMax H3 | LTX 2.3, LTX NVFP4, Wan 2.2 |

Drop any open-weight Comfy API graph in `workflows/` and it appears as a custom option. Video stays on Spark. Stills stay on the 3090s.

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
| `takes/` | Previous takes (bin) |
| `queue.json` | GPU work Hermes (or the UI) appended |
| `edit.json` | Timeline `{shot_id, clip, muted}` |
| `cut.mp4` | Assembled film |
| `cut.srt` | Captions from shot purpose/visual |
| `comments.json` | Shot notes |
| `STATUS.md` | Honest one-liner |

## Queue

GET snapshot **never** submits Comfy jobs. Append to `queue.json` or POST `/api/produce/<job>/queue`. Actions: `render_board`, `render_take`, `range_retake`, `assemble`.

If Spark or a 3090 is down, items stay `waiting_for_host`. **Run queue** when the boxes are up. Comfy presets in `workflows/` are called with the shot prompt.

## UI

- Shot strip: board, approve, take, retake. Inspector: first/last, shot prompt, camera, duration, mode, seed, take bin, notes.
- Identity: job drop zone plus a reusable elements library (character / location / voice) plus **score**.
- Timeline: reorder, mute, **Trim** (local ffmpeg in/out), range **Retake** (Spark).
- Project bar: rename, continuity grade, add shot, duplicate, **Export**.
- Sample briefs, ⌘K command palette, keyboard B/T/A.
- **Export** sheet: aspect (16:9 / 9:16 / 1:1 / 2.39), fade, title card, mix score. Assemble also writes `cut.srt`.
- **Handoff zip** next to Assemble cut.
- Queue panel with a rough ETA. Color pass optional.
- Coach chip: next honest step (boards → takes → assemble → export).
- Cut player + version history. Review chips and take compare in the inspector.
- Enhance prompt (local cinematic rewrite). Grab still from the take playhead.
- Script peek and a prompt-overlap scorecard. LLM light is reachable, not just configured.
- Export transition: hard cut or crossfade.
- Review notes queue for the matching Hermes profile (`@video` / `@storyboard` / `@story`). The bot sheet prefills; Send includes the job brief. Identity pack + `audio_manifest.json` travel with the handoff zip.

## API (selected)

- `POST /api/produce/start` `{prompt, produce_mode, stills_model, video_model, title, aspect}`
- `GET /api/produce/models`
- `GET /api/produce/samples`
- `GET` / `POST /api/produce/elements`
- `GET /api/produce/{job}`
- `POST /api/produce/{job}/render-board` / `render-take` / `range-retake`
- `POST /api/produce/{job}/queue` / `queue/plan` / `queue/run`
- `POST` / `DELETE /api/produce/{job}/shots` / `shots/{shot_id}`
- `PUT /api/produce/{job}/shots/{shot_id}`
- `POST /api/produce/{job}/upload`
- `PUT /api/produce/{job}/options` `{color_pass, stills_model, video_model, title, aspect, fade_sec}`
- `POST /api/produce/{job}/assemble`
- `POST /api/produce/{job}/comments` / `duplicate` / `rename` / `captions`
- `POST /api/produce/{job}/review` / `ab` / `enhance` / `grab-still` / `cuts/restore`
- `GET /api/produce/{job}/export`
- `POST /api/produce/{job}/takes/restore`

## Workflows

H3 graphs: `20` T2VA, `21` I2VA, `22` FL2VA, `23` R2VA. LTX and Wan are selectable Spark lanes. Drop your own Comfy API graph in `workflows/` — it shows up as a custom model. Produce injects the shot prompt.

Prompt skill: `hermes_home/skills/h3-prompt-writing`.
