"""Domain router: system — handlers live in cinesmith_dashboard; this module only mounts them."""

from __future__ import annotations

from fastapi import APIRouter


def build_system_router():
    """Build router after cinesmith_dashboard handlers are defined (avoids circular import)."""
    from dashboard import cinesmith_dashboard as d

    router = APIRouter(tags=['system'])
    router.add_api_route('/api/system/readiness', d.api_system_readiness, methods=["GET"])
    router.add_api_route('/api/stats', d.api_stats, methods=["GET"])
    router.add_api_route('/api/queue/clear', d.api_queue_clear, methods=["POST"])
    router.add_api_route('/api/models/status', d.models_status, methods=["GET"])
    router.add_api_route('/api/models/mode', d.set_model_mode, methods=["POST"])
    router.add_api_route('/api/models/test-local', d.test_local_models, methods=["GET"])
    router.add_api_route('/api/models/test-api', d.test_api_models, methods=["GET"])
    router.add_api_route('/api/spark/test', d.api_spark_test, methods=["GET"])
    router.add_api_route('/api/test/comfyui', d.api_test_comfyui, methods=["POST"])
    router.add_api_route('/api/spark/state', d.api_spark_state, methods=["GET"])
    router.add_api_route('/api/config', d.api_config, methods=["GET"])
    router.add_api_route('/api/lora/presets', d.api_lora_presets, methods=["GET"])
    router.add_api_route('/api/config', d.api_config_update, methods=["POST"])
    router.add_api_route('/api/config/save', d.api_config_save, methods=["POST"])
    router.add_api_route('/api/config/effective', d.api_config_effective, methods=["GET"])
    router.add_api_route('/api/test/nous', d.api_test_nous, methods=["POST"])
    router.add_api_route('/api/test/director', d.api_test_director, methods=["GET"])
    router.add_api_route('/api/test/director', d.api_test_director_post, methods=["POST"])
    router.add_api_route('/api/test/director-self-check', d.api_test_director_self_check, methods=["GET"])
    router.add_api_route('/api/test/director-self-check', d.api_test_director_self_check_post, methods=["POST"])
    router.add_api_route('/api/test/vision', d.api_test_vision, methods=["GET"])
    router.add_api_route('/api/test/vision', d.api_test_vision_post, methods=["POST"])
    router.add_api_route('/api/test/lmstudio', d.api_test_lmstudio, methods=["GET"])
    router.add_api_route('/api/lmstudio/status', d.api_lmstudio_status, methods=["GET"])
    router.add_api_route('/api/lmstudio/load', d.api_lmstudio_load, methods=["POST"])
    router.add_api_route('/api/test/nim', d.api_test_nim, methods=["GET"])
    router.add_api_route('/api/restart', d.api_restart, methods=["POST"])
    router.add_api_route('/api/spark/stats', d.api_spark_stats, methods=["GET"])
    return router
