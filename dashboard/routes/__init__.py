"""Extra modular FastAPI routers registered onto the main dashboard app."""

from __future__ import annotations

from fastapi import FastAPI

from dashboard.routes.product import router as product_router
from dashboard.routes.system import build_system_router
from dashboard.routes.campaigns import build_campaigns_router
from dashboard.routes.script import build_script_router
from dashboard.routes.hermes import build_hermes_router
from dashboard.routes.characters import build_characters_router
from dashboard.routes.assets import build_assets_router
from dashboard.routes.memory import build_memory_router
from dashboard.routes.video import build_video_router
from dashboard.routes.ideas import build_ideas_router
from dashboard.routes.legacy import build_legacy_router


def register_extra_routes(app: FastAPI) -> None:
    """Mount product routes early (self-contained)."""
    app.include_router(product_router, tags=["product"])


def register_domain_routers(app: FastAPI) -> None:
    """Mount domain routers after cinesmith_dashboard handlers exist."""
    app.include_router(build_system_router())
    app.include_router(build_campaigns_router())
    app.include_router(build_script_router())
    app.include_router(build_hermes_router())
    app.include_router(build_characters_router())
    app.include_router(build_assets_router())
    app.include_router(build_memory_router())
    app.include_router(build_video_router())
    app.include_router(build_ideas_router())
    app.include_router(build_legacy_router())
