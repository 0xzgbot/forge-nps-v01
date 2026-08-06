"""Domain router: campaigns — handlers live in cinesmith_dashboard; this module only mounts them."""

from __future__ import annotations

from fastapi import APIRouter


def build_campaigns_router():
    """Build router after cinesmith_dashboard handlers are defined (avoids circular import)."""
    from dashboard import cinesmith_dashboard as d

    router = APIRouter(tags=['campaigns'])
    router.add_api_route('/api/renders/audit-batch', d.api_renders_audit_batch, methods=["POST"])
    router.add_api_route('/api/renders', d.api_renders, methods=["GET"])
    router.add_api_route('/api/shots', d.api_get_shots, methods=["GET"])
    router.add_api_route('/api/shots/reindex-storage', d.api_reindex_shots_from_storage, methods=["POST"])
    router.add_api_route('/api/comfy/recover-prompt', d.api_recover_comfy_prompt, methods=["POST"])
    router.add_api_route('/api/comfy/recover-history', d.api_recover_comfy_history, methods=["POST"])
    router.add_api_route('/api/comfy/recover-queue', d.api_recover_comfy_queue, methods=["POST"])
    router.add_api_route('/api/campaigns', d.api_get_campaigns, methods=["GET"])
    router.add_api_route('/api/campaigns/{campaign_id}/agent-exchanges', d.api_get_campaign_agent_exchanges, methods=["GET"])
    router.add_api_route('/api/campaigns/rename', d.api_rename_campaign, methods=["POST"])
    router.add_api_route('/api/campaigns/{campaign_id}', d.api_delete_campaign, methods=["DELETE"])
    router.add_api_route('/api/campaigns/delete', d.api_delete_campaign_body, methods=["POST"])
    router.add_api_route('/api/campaigns/{campaign_id}/identity', d.api_get_campaign_identity, methods=["GET"])
    router.add_api_route('/api/campaigns/identity', d.api_set_campaign_identity, methods=["POST"])
    router.add_api_route('/api/campaigns/{campaign_id}/assets', d.api_get_campaign_assets, methods=["GET"])
    router.add_api_route('/api/campaigns/{campaign_id}/assets/upload', d.api_upload_campaign_asset, methods=["POST"])
    router.add_api_route('/api/campaigns/{campaign_id}/assets/{asset_id}', d.api_update_campaign_asset, methods=["POST"])
    router.add_api_route('/api/campaigns/{campaign_id}/identity/clone/{source_campaign_id}', d.api_clone_campaign_identity, methods=["POST"])
    router.add_api_route('/api/campaigns/{campaign_id}/assets/auto-select', d.api_auto_select_identity_assets, methods=["POST"])
    router.add_api_route('/api/shots/{shot_id}', d.api_update_script_shot_description, methods=["PATCH"])
    router.add_api_route('/api/director/shots/{shot_id}', d.api_delete_script_director_shot, methods=["DELETE"])
    router.add_api_route('/api/export/carousel', d.api_export_carousel, methods=["POST"])
    router.add_api_route('/api/import/sienna-batch', d.api_import_sienna_batch, methods=["POST"])
    router.add_api_route('/api/shots/dispatch-all', d.api_shots_dispatch_all, methods=["POST"])
    router.add_api_route('/api/shots/dispatch', d.api_shots_dispatch, methods=["POST"])
    return router
