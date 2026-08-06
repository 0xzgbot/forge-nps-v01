# Dashboard router layout

`dashboard/cinesmith_dashboard.py` still holds **handler implementations** and shared state
(`MEDIA_ROOT`, `_SHOTS_STORE`, helpers). HTTP mounting is split into domain routers under
`dashboard/routes/`.

## Why this shape

- Avoids a risky big-bang move of 400+ tightly coupled helpers
- Gives OpenAPI tags and clear ownership per domain
- Keeps tests that import `dashboard.cinesmith_dashboard` symbols working
- New product features live as self-contained routers (`product.py`)

## Registration order

1. Create `app = FastAPI()`
2. `register_exception_handlers(app)` + `register_extra_routes(app)` → product
3. Define all handler functions on `cinesmith_dashboard`
4. `register_domain_routers(app)` at **end of module** (lazy import of handlers)

## Domain modules

| Module | Tag | Responsibility |
| --- | --- | --- |
| `routes/product.py` | product | Create hub, export, scorecard, wizard, suggestions, cost-meter (G5), failure-auto-consolidate (J4) |
| `routes/system.py` | system | config, readiness, models, spark tests, restart |
| `routes/campaigns.py` | campaigns | shots, campaigns, identity assets, comfy recover |
| `routes/script.py` | script | Script Studio projects, pipeline, storyboard |
| `routes/hermes.py` | hermes | run-campaign, chat, audit, platform |
| `routes/characters.py` | characters | character CRUD, DNA, sheets, anchors |
| `routes/assets.py` | assets | Asset Vault, banks, products |
| `routes/memory.py` | memory | memory + nexus + failure-auto (J4) |
| `routes/video.py` | video | video process, local spark media, visual audit |
| `routes/ideas.py` | ideas | idea board + hooks |
| `routes/legacy.py` | legacy | 410 disabled / old session routes |

## Still on `app` directly

- `GET /` (dashboard HTML)
- WebSockets: `/ws/{session_id}`, `/ws/spark`, `/ws/hermes`
- Static mounts (`/static`, `/media-assets`, …)

## Next step (optional)

Move handler bodies from `cinesmith_dashboard.py` into `dashboard/services/*` once a domain
is stable, keeping the router `add_api_route` map as the public surface.
