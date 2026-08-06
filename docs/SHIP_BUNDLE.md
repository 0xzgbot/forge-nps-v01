# Ship Bundle Notes (B6)

Slim **Desktop + Spark** distribution: dashboard + Python core + workflows + repo `hermes_home` skeleton — **without** Hermes engine front-end bulk or user secrets.

Primary exclude list: [`scripts/cinesmith_ship_excludes.txt`](../scripts/cinesmith_ship_excludes.txt).

Product walkthrough: [DESKTOP_SPARK_PACKAGE.md](DESKTOP_SPARK_PACKAGE.md).

---

## What recipients need in the zip

| Include | Why |
| --- | --- |
| `dashboard/`, `core/`, `pipelines/`, `agents/` | App + API |
| `workflows/*.json` | Spark/Comfy graphs (Flux2, LTX, …) |
| `requirements.txt`, `scripts/launch_cinesmith.sh`, `scripts/preflight_desktop_spark.py` | Install + launch |
| `hermes_engine/` **Python** sources (no `node_modules` / `ui-tui` / `web`) | Vendored Hermes CLI path |
| `hermes_home/` skeleton (SOUL, skills as needed) | Isolated Hermes home — strip secrets |
| `docs/DESKTOP_SPARK_PACKAGE.md`, `.env.template`, `data/config.example.json` | First-run guidance |
| `marketing/` assets optional | Demo/marketing only |

## What to exclude

| Exclude | Why |
| --- | --- |
| `hermes_engine/node_modules` | Huge; not needed for dashboard path |
| `hermes_engine/ui-tui`, `hermes_engine/web` | Upstream UIs / build trees |
| `.venv`, `__pycache__` | Rebuild with `pip install -r requirements.txt` |
| `data/sessions` dumps, large reports/renders | Ephemeral / private |
| `.env`, real `data/config.json` keys | **User secrets** |
| `hermes_home` auth DBs, session logs, tokens | **User secrets** |
| Full `media/` or sibling `CINESMITH_MEDIA` | Large binaries; recreate empty layout |

---

## Example: create a slim zip (macOS/Linux)

From the **parent** of the repo (adjust names):

```bash
cd /path/to/parent
rsync -a --exclude-from=cinesmith_v01/scripts/cinesmith_ship_excludes.txt \
  cinesmith_v01/ cinesmith_ship/
# Scrub any leftover secrets
rm -f cinesmith_ship/.env cinesmith_ship/data/config.json
zip -r cinesmith_desktop_spark.zip cinesmith_ship
```

Or with `tar`:

```bash
tar -czf cinesmith_desktop_spark.tgz \
  --exclude-from=cinesmith_v01/scripts/cinesmith_ship_excludes.txt \
  -C /path/to/parent cinesmith_v01
```

> Note: `tar --exclude-from` patterns are matched against member names; prefer `rsync` + zip for predictable strip of nested `node_modules`.

---

## Recipient checklist

1. Unzip → `python3 -m venv .venv` → `pip install -r requirements.txt`  
2. `cp .env.template .env` → set Spark URL + optional Director key  
3. `python3 scripts/preflight_desktop_spark.py`  
4. `./scripts/launch_cinesmith.sh --package`  
5. Open printed URL → Settings → Test connections  

Target: **understand + first generate within ~15 minutes** with Spark online.

---

## Status

Roadmap item **B6** (slim publish bundle / ship notes): exclude list + this doc + Desktop package guide. Automated CI packaging is optional follow-up.
