"""Domain router: script — handlers live in cinesmith_dashboard; this module only mounts them."""

from __future__ import annotations

from fastapi import APIRouter


def build_script_router():
    """Build router after cinesmith_dashboard handlers are defined (avoids circular import)."""
    from dashboard import cinesmith_dashboard as d

    router = APIRouter(tags=['script'])
    router.add_api_route('/api/scripts', d.api_list_scripts, methods=["GET"])
    router.add_api_route('/api/script/reparse', d.api_script_reparse, methods=["POST"])
    router.add_api_route('/api/director/generate', d.api_director_generate, methods=["POST"])
    router.add_api_route('/api/script/develop', d.api_script_develop, methods=["POST"])
    router.add_api_route('/api/script/projects', d.api_script_projects, methods=["GET"])
    router.add_api_route('/api/script/projects/{script_id}', d.api_script_project, methods=["GET"])
    router.add_api_route('/api/script/projects/save', d.api_script_project_save, methods=["POST"])
    router.add_api_route('/api/script/series', d.api_script_series_list, methods=["GET"])
    router.add_api_route('/api/script/series/new-episode', d.api_script_series_new_episode, methods=["POST"])
    router.add_api_route('/api/script/pipeline/start', d.api_script_pipeline_start, methods=["POST"])
    router.add_api_route('/api/script/pipeline/jobs/{job_id}', d.api_script_pipeline_job, methods=["GET"])
    router.add_api_route('/api/script/storyboard', d.api_script_storyboard, methods=["POST"])
    router.add_api_route('/api/script/storyboard/image-models', d.api_script_storyboard_image_models, methods=["GET"])
    router.add_api_route('/api/script/storyboard/provider-health', d.api_script_storyboard_provider_health, methods=["GET"])
    router.add_api_route('/api/script/storyboard/render-image', d.api_script_storyboard_render_image, methods=["POST"])
    router.add_api_route('/api/script/storyboard/assemble', d.api_script_storyboard_assemble, methods=["POST"])
    router.add_api_route('/api/script/storyboard/export-video-shots', d.api_script_storyboard_export_video_shots, methods=["POST"])
    router.add_api_route('/api/script/parse-with-kimi', d.api_parse_with_kimi, methods=["POST"])
    router.add_api_route('/api/script/load-shots', d.api_load_shots, methods=["POST"])
    router.add_api_route('/api/script/add-shot', d.api_script_add_shot, methods=["POST"])
    router.add_api_route('/api/script/update-shot', d.api_script_update_shot, methods=["POST"])
    return router
