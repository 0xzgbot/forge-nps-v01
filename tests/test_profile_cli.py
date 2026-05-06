import os
from unittest.mock import patch

from core.hermes.pipeline.profile_cli import HermesProfileCLI


def test_normalize_openai_base_url_preserves_explicit_vllm_port():
    got = HermesProfileCLI._normalize_openai_base_url("http://dgx-spark.local:8000")
    assert got == "http://dgx-spark.local:8000/v1"


def test_normalize_openai_base_url_strips_chat_completions():
    got = HermesProfileCLI._normalize_openai_base_url("http://localhost:8000/v1/chat/completions")
    assert got == "http://localhost:8000/v1"


def test_normalize_openai_base_url_adds_lmstudio_default_port_only_when_requested():
    got = HermesProfileCLI._normalize_openai_base_url("http://localhost", default_port="1234")
    assert got == "http://localhost:1234/v1"


def test_runtime_prefers_explicit_profile_base_url_for_vllm():
    with patch.dict(
        os.environ,
        {
            "FORGE_PROFILE_MODEL": "gemma4-31b-mtp",
            "FORGE_PROFILE_BASE_URL": "http://3090-box:8000/v1",
            "OPENAI_BASE_URL": "",
            "LMSTUDIO_PORT": "1234",
        },
        clear=False,
    ):
        _args, env, debug = HermesProfileCLI()._runtime_args_and_env()
    assert debug["model"] == "gemma4-31b-mtp"
    assert debug["base_source"] == "FORGE_PROFILE_BASE_URL"
    assert debug["base_url"] == "http://3090-box:8000/v1"
    assert env["OPENAI_BASE_URL"] == "http://3090-box:8000/v1"
