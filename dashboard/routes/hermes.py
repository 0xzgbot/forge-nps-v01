"""Domain router: hermes — handlers live in cinesmith_dashboard; this module only mounts them."""

from __future__ import annotations

from fastapi import APIRouter


def build_hermes_router():
    """Build router after cinesmith_dashboard handlers are defined."""
    from dashboard import cinesmith_dashboard as d

    router = APIRouter(tags=['hermes'])
    router.add_api_route('/api/hermes/cancel', d.api_hermes_cancel, methods=["POST"])
    router.add_api_route('/api/platform/detect', d.api_platform_detect, methods=["POST"])
    router.add_api_route('/api/hermes/run-campaign', d.api_hermes_run_campaign, methods=["POST"])
    router.add_api_route('/api/audit/reprocess', d.api_audit_reprocess, methods=["POST"])
    router.add_api_route('/api/audit/remediate', d.api_audit_remediate, methods=["POST"])
    router.add_api_route('/api/hermes/teach', d.api_hermes_teach, methods=["POST"])
    router.add_api_route('/api/hermes/export', d.api_hermes_export, methods=["GET"])
    router.add_api_route('/api/consistency/score', d.api_consistency_score, methods=["POST"])
    router.add_api_route('/api/hermes/generate-character', d.api_generate_character, methods=["POST"])
    router.add_api_route('/api/hermes/profile/chat', d.api_hermes_profile_chat, methods=["POST"])
    router.add_api_route('/api/hermes/profiles', d.api_hermes_profiles, methods=["GET"])
    router.add_api_route('/api/hermes/chat', d.api_hermes_chat_stream, methods=["POST"])
    return router
