from core.bridge.llm_endpoint import normalize_openai_base, resolve_llm_endpoint


def test_normalize_strips_chat_completions():
    assert normalize_openai_base("http://localhost:1234/v1/chat/completions") == "http://localhost:1234/v1"


def test_resolve_prefers_canonical_llm_keys(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:8000/v1")
    monkeypatch.setenv("LLM_MODEL", "local-hermes")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_INSTRUCT_MODEL", raising=False)
    endpoint = resolve_llm_endpoint({})
    assert endpoint.source == "llm"
    assert endpoint.model == "local-hermes"
    assert endpoint.chat_url.endswith("/chat/completions")
    assert endpoint.ready


def test_resolve_does_not_require_kimi(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-4.1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    for key in ("KIMI_API_KEY", "KIMI_INSTRUCT_MODEL", "NIM_ENDPOINT", "NOUS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    endpoint = resolve_llm_endpoint({})
    assert endpoint.source == "llm"
    assert "kimi" not in endpoint.model.lower()
