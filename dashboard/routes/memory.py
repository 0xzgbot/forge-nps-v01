"""Domain router: memory — handlers live in cinesmith_dashboard; this module only mounts them."""

from __future__ import annotations

from fastapi import APIRouter


def build_memory_router():
    """Build router after cinesmith_dashboard handlers are defined."""
    from dashboard import cinesmith_dashboard as d

    router = APIRouter(tags=['memory'])
    router.add_api_route('/memory', d.get_memory_page, methods=["GET"])
    router.add_api_route('/api/memory/stats', d.api_memory_stats, methods=["GET"])
    router.add_api_route('/api/memory/timeline', d.api_memory_timeline, methods=["GET"])
    router.add_api_route('/api/memory/insights', d.api_memory_insights, methods=["GET"])
    router.add_api_route('/api/memory/graph', d.api_memory_graph, methods=["GET"])
    router.add_api_route('/api/memory/search', d.api_memory_search, methods=["GET"])
    router.add_api_route('/api/memory/health', d.api_memory_health, methods=["GET"])
    router.add_api_route('/api/nexus/query', d.api_nexus_query, methods=["POST"])
    router.add_api_route('/api/nexus/impact', d.api_nexus_impact, methods=["POST"])
    router.add_api_route('/api/memory/consolidate', d.api_memory_consolidate, methods=["POST"])
    router.add_api_route('/api/memory/failure-auto', d.api_memory_failure_auto_status, methods=["GET"])
    router.add_api_route('/api/memory/failure-auto', d.api_memory_failure_auto_run, methods=["POST"])
    return router
