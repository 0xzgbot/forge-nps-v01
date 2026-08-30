# Desktop + Spark Package Guide

Ship bar: a creator with a Mac or PC and a Spark (ComfyUI) box on the LAN can **install, launch, and understand requirements in about 15 minutes**.

This guide is the product-facing entry for that layout. Deeper agent/ops detail lives in [INSTALLATION_AGENT_GUIDE.md](INSTALLATION_AGENT_GUIDE.md). Bundle contents and zip excludes are in [SHIP_BUNDLE.md](SHIP_BUNDLE.md).

---

## What you need

| Piece | Required? | Notes |
| --- | --- | --- |
| **Desktop** (macOS or Windows/Linux) | Yes | Runs the Cinesmith dashboard (FastAPI + static UI). |
| **Python 3.11+** | Yes | `python3 --version`. Create a venv and `pip install -r requirements.txt`. |
| **Spark / ComfyUI on LAN** | Yes for images & video | `COMFYUI_PRIMARY` = Spark (H3). Optional `COMFYUI_STILLS_A` / `COMFYUI_STILLS_B` = 3090s. |
| **Second Comfy (3090s)** | Recommended for Shoot | Boards stay off Spark. |
| **Director API key** (Kimi / NVIDIA / Nous / etc.) | Optional* | Cloud planning & critique. Or use local Director mode. |
| **LM Studio** (local OpenAI-compatible API) | Optional | Hermes chat / local Director. Default `http://localhost:1234`. |

\*Without a Director key **and** without LM Studio, you can still open the UI and explore settings; planning/generation that needs a model will fail until one path is configured.

Core workflows expected under `workflows/`:

- Flux2 text-to-image (`01_flux2_text_to_image.json`) for 3090 boards
- MiniMax H3 T2VA / I2VA / FL2VA / R2VA (`20_`–`23_minimax_h3_*.json`)
- LTX 2.3 image-to-video as a draft fallback (`04_ltx2.3_image_to_video` aliases)

---

## One-command launch

From the repo root (after venv + deps):

```bash
./scripts/launch_cinesmith.sh
```

**Package / production mode** (no uvicorn `--reload`, clearer banner):

```bash
./scripts/launch_cinesmith.sh --package
# or
CINESMITH_PACKAGE_MODE=1 ./scripts/launch_cinesmith.sh
```

The launcher:

1. Optionally runs preflight (`CINESMITH_SKIP_PREFLIGHT=1` to skip)
2. Forces `HERMES_HOME` to repo `hermes_home/` (unless `CINESMITH_ALLOW_GLOBAL_HERMES=1`)
3. Sets media root to sibling `CINESMITH_MEDIA` or `./media`
4. Re-asserts isolation after sourcing `.env`
5. Prints the dashboard URL (default `http://127.0.0.1:7000`) — Produce home. Legacy studio is `/studio`.

First-time setup:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.template .env       # then edit keys / Spark URL
./scripts/launch_cinesmith.sh --package
```

---

## Isolation guarantee

Cinesmith **never** silently uses your global Hermes install.

| Setting | Behavior |
| --- | --- |
| Default | `HERMES_HOME=<repo>/hermes_home` |
| Escape hatch | `CINESMITH_ALLOW_GLOBAL_HERMES=1` only if you intentionally want `~/.hermes` |
| Launcher | Re-asserts isolation **after** `.env` so a mistaken `HERMES_HOME` cannot stick |

All Cinesmith-scoped Hermes CLI/profile runs use the vendored `hermes_engine/` launcher with the repo home. Your personal `~/.hermes` stays untouched.

---

## Media root

Resolved by `core.cinesmith_env.default_media_root()`:

1. `CINESMITH_MEDIA_ROOT` if set  
2. Sibling folder `../CINESMITH_MEDIA` if it exists  
3. Otherwise `<repo>/media` (created with `images/`, `videos/`, `imports/`, …)

Optional sibling layout (keeps large renders out of the git tree):

```text
parent/
  cinesmith_v01/          # this repo
  CINESMITH_MEDIA/        # images, videos, imports, exports…
```

Or leave unset and use `./media` inside the package.

---

## First 15 minutes walkthrough

1. **Launch** — `./scripts/launch_cinesmith.sh --package` → open the printed URL.  
2. **Settings** — set `COMFYUI_PRIMARY` to your Spark host; set Director key **or** enable local Director + LM Studio.  
3. **Test connections** — use Test buttons (ComfyUI/Spark, Director, LM Studio as applicable). Watch the readiness strip chips (Spark / Director / Hermes / Media).  
4. **Agency brief** — on **Images** (or Script Studio), paste a short production brief.  
5. **Images** — run **Generate Images** for a small still batch (Flux2 path). Confirm thumbs appear in the gallery.  
6. **Stories** — open Script Studio: brief → package/storyboard path; frames need Spark online.  
7. **Videos** — send a start frame through LTX I2V (Videos tab or Script Studio Videos step).

If Spark is offline you can still configure Settings and draft script packages; image/video render chips will stay yellow/red until ComfyUI answers.

---

## Spark offline recovery

When the readiness strip shows **Spark offline**, Hermes can still plan, draft stories, and write memory — but **renders wait** until Spark is reachable.

Readiness is also available as `GET /api/system/readiness`.

| Chip / check | Meaning | Fix |
| --- | --- | --- |
| **Spark** red/unreachable | ComfyUI not answering `COMFYUI_PRIMARY` (e.g. `/system_stats`) | Start ComfyUI on the Spark box; open firewall; use LAN IP + port in Settings; re-Test. |
| **Director** / no API key | Cloud planning key missing | Set `KIMI_API_KEY` (or provider key in `.env` / Settings) **or** turn on local Director with LM Studio. |
| **LM Studio** yellow | Optional local model API down | Start LM Studio server; load chat model; Test & Detect Models. |
| **Hermes** / isolation fail | Process pointed at global `~/.hermes` or missing `hermes_home` | Relaunch with `./scripts/launch_cinesmith.sh`; do not set global Hermes unless you mean it. |
| **Media** fail | Media root missing or not writable | Create sibling `CINESMITH_MEDIA` or allow `./media`; set `CINESMITH_MEDIA_ROOT` if custom. |
| Overall **partial** | Core OK but Spark down | UI works; queue renders after Spark is up. |
| Overall **ready** | Isolation + media + Spark OK | Generate Images / video paths unblocked. |

### Recovery checklist

1. **Check `COMFYUI_PRIMARY`** in Settings → confirm ComfyUI Primary origin (example `http://127.0.0.1:8188`).  
2. **Open Spark UI** in a browser at that same origin; confirm models load.  
3. **Re-test connections** via readiness Refresh / Test Render Workers.  
4. **Relaunch** with `scripts/launch_cinesmith.sh` if isolation env drifted.

Preflight without starting the server:

```bash
python3 scripts/preflight_desktop_spark.py
```

Spark down is a **WARN** (exit 0) so you can still package-test the desktop; missing Python deps or isolation are **FAIL** (exit 1).

---

## What is NOT included

A Desktop + Spark ship bundle intentionally omits heavy or secret material. See [SHIP_BUNDLE.md](SHIP_BUNDLE.md) and `scripts/cinesmith_ship_excludes.txt`.

Not shipped (or stripped before zip):

- `hermes_engine/node_modules`, `hermes_engine/ui-tui`, `hermes_engine/web` bulk trees  
- Local `.venv`, `__pycache__`, large session dumps under `data/sessions`  
- User secrets: `.env`, real keys in `data/config.json`, tokens in `hermes_home`  
- Machine-only media blobs (use `CINESMITH_MEDIA` / `./media` outside the zip when possible)

Recipients install Python deps themselves (`pip install -r requirements.txt`). Hermes engine JS bulk is not required for the dashboard + Spark image/video path.

---

## Verification

**Preflight** (no server required):

```bash
python3 scripts/preflight_desktop_spark.py
# expect PASS / WARN lines; exit 0 if no hard FAILs
```

**Syntax / shell sanity** (maintainers):

```bash
python3 -m py_compile scripts/preflight_desktop_spark.py
bash -n scripts/launch_cinesmith.sh
```

**Smoke suite** (dashboard must be running):

```bash
./scripts/launch_cinesmith.sh --package
# other terminal:
python3 scripts/smoke_cinesmith.py --base-url http://127.0.0.1:7000
```

Live Spark renders (optional, queue time):

```bash
python3 scripts/smoke_cinesmith.py --base-url http://127.0.0.1:7000 --live-script
python3 scripts/smoke_cinesmith.py --base-url http://127.0.0.1:7000 --live-campaign
```

---

## Related docs

- [INSTALLATION_AGENT_GUIDE.md](INSTALLATION_AGENT_GUIDE.md) — full agent restore checklist  
- [SHIP_BUNDLE.md](SHIP_BUNDLE.md) — zip excludes and slim publish notes  
- [STABILITY_CHECKLIST.md](STABILITY_CHECKLIST.md) — ops stability  
- [POLISH_ROADMAP.md](POLISH_ROADMAP.md) — polish status (B6 ship bundle)
- [PRODUCT_VISION.md](PRODUCT_VISION.md) — Hermes-first agency model
