"""Domain router: video — handlers live in cinesmith_dashboard; this module only mounts them."""

from __future__ import annotations

from fastapi import APIRouter


def build_video_router():
    """Build router after cinesmith_dashboard handlers are defined."""
    from dashboard import cinesmith_dashboard as d

    router = APIRouter(tags=['video'])
    router.add_api_route('/api/visual-audit', d.visual_audit, methods=["POST"], response_model=d.VisualAuditResponse)
    router.add_api_route('/api/video/workflows', d.api_video_workflows, methods=["GET"])
    router.add_api_route('/api/local-spark-media/styles', d.api_local_spark_media_styles, methods=["GET"])
    router.add_api_route('/api/local-spark-media/motions', d.api_local_spark_media_motions, methods=["GET"])
    router.add_api_route('/api/local-spark-media/generate-image', d.api_local_spark_media_generate_image, methods=["POST"])
    router.add_api_route('/api/local-spark-media/generate-video', d.api_local_spark_media_generate_video, methods=["POST"])
    router.add_api_route('/api/local-spark-media/jobs/{job_set_id}', d.api_local_spark_media_job_status, methods=["GET"])
    router.add_api_route('/api/local-spark-media/characters', d.api_local_spark_media_create_character, methods=["POST"])
    router.add_api_route('/api/local-spark-media/characters', d.api_local_spark_media_list_characters, methods=["GET"])
    router.add_api_route('/api/local-spark-media/characters/{reference_id}', d.api_local_spark_media_get_character, methods=["GET"])
    router.add_api_route('/api/local-spark-media/characters/{reference_id}', d.api_local_spark_media_delete_character, methods=["DELETE"])
    router.add_api_route('/api/video/process', d.api_video_process, methods=["POST"])
    router.add_api_route('/api/video/process-text', d.api_video_process_text, methods=["POST"])
    router.add_api_route('/api/video/sync-jobs', d.api_video_sync_jobs, methods=["POST"])
    router.add_api_route('/api/video/generate-prompts', d.api_video_generate_prompts, methods=["POST"])
    return router
