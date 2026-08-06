"""Domain router: legacy — handlers live in cinesmith_dashboard; this module only mounts them."""

from __future__ import annotations

from fastapi import APIRouter


def build_legacy_router():
    """Build router after cinesmith_dashboard handlers are defined."""
    from dashboard import cinesmith_dashboard as d

    router = APIRouter(tags=['legacy'])
    router.add_api_route('/api/session/{session_id}', d.get_session, methods=["GET"])
    router.add_api_route('/api/skills', d.get_skills, methods=["GET"])
    router.add_api_route('/api/reasoning/{shot_id}', d.get_reasoning, methods=["GET"])
    router.add_api_route('/api/submit-recipe', d.api_submit_recipe, methods=["POST"])
    router.add_api_route('/api/inject-prompt', d.api_inject_prompt, methods=["POST"])
    router.add_api_route('/api/render/audit', d.api_render_audit, methods=["POST"])
    router.add_api_route('/api/render', d.api_render, methods=["POST"])
    return router
