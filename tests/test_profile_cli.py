import os
from pathlib import Path
from unittest.mock import patch

from core.cinesmith_env import cinesmith_hermes_home
from core.hermes.pipeline.profile_cli import HermesProfileCLI


def test_normalize_openai_base_url_preserves_explicit_custom_port():
    got = HermesProfileCLI._normalize_openai_base_url("http://dgx-spark.local:8000")
    assert got == "http://dgx-spark.local:8000/v1"


def test_normalize_openai_base_url_strips_chat_completions():
    got = HermesProfileCLI._normalize_openai_base_url("http://localhost:8000/v1/chat/completions")
    assert got == "http://localhost:8000/v1"


def test_normalize_openai_base_url_adds_lmstudio_default_port_only_when_requested():
    got = HermesProfileCLI._normalize_openai_base_url("http://localhost", default_port="1234")
    assert got == "http://localhost:1234/v1"


def test_runtime_prefers_explicit_profile_base_url_for_custom_endpoint():
    with patch.dict(
        os.environ,
        {
            "CINESMITH_PROFILE_MODEL": "custom-kimi-compatible-model",
            "CINESMITH_PROFILE_BASE_URL": "http://3090-box:8000/v1",
            "OPENAI_BASE_URL": "",
            "LMSTUDIO_PORT": "1234",
            "HERMES_HOME": str(Path.home() / ".hermes"),
            "CINESMITH_ALLOW_GLOBAL_HERMES": "",
        },
        clear=False,
    ):
        _args, env, debug = HermesProfileCLI()._runtime_args_and_env()
    assert debug["model"] == "custom-kimi-compatible-model"
    assert debug["base_source"] == "CINESMITH_PROFILE_BASE_URL"
    assert debug["base_url"] == "http://3090-box:8000/v1"
    assert env["OPENAI_BASE_URL"] == "http://3090-box:8000/v1"
    # Isolation: never inherit caller's ~/.hermes for profile CLI subprocess env
    assert Path(env["HERMES_HOME"]).resolve() == cinesmith_hermes_home().resolve()
    assert debug["hermes_home"] == env["HERMES_HOME"]
