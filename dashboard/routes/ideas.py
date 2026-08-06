"""Domain router: ideas — handlers live in cinesmith_dashboard; this module only mounts them."""

from __future__ import annotations

from fastapi import APIRouter


def build_ideas_router():
    """Build router after cinesmith_dashboard handlers are defined."""
    from dashboard import cinesmith_dashboard as d

    router = APIRouter(tags=['ideas'])
    router.add_api_route('/api/ideas/board', d.api_get_idea_board, methods=["GET"])
    router.add_api_route('/api/ideas/cards', d.api_create_idea_card, methods=["POST"])
    router.add_api_route('/api/ideas/cards/{card_id}', d.api_update_idea_card, methods=["PATCH"])
    router.add_api_route('/api/ideas/cards/{card_id}', d.api_delete_idea_card, methods=["DELETE"])
    router.add_api_route('/api/ideas/hooks', d.api_generate_hook_ideas, methods=["POST"])
    return router
