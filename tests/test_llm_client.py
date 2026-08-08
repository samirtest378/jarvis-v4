from __future__ import annotations

import pytest

import config
import llm_client


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  sk-test  ", "sk-test"),
        ('"sk-test"', "sk-test"),
        ("Bearer sk-test", "sk-test"),
        ("bearer 'sk-test'", "sk-test"),
        ("Authorization: Bearer sk-test", "sk-test"),
        ("export ANTHROPIC_API_KEY='sk-test'", "sk-test"),
        ('QWEN_API_KEY="sk-test"', "sk-test"),
        ("sk-test==", "sk-test=="),
        ("first\nsecond", ""),
        (None, ""),
    ],
)
def test_api_key_normalization_handles_common_paste_formats(raw, expected):
    assert llm_client.normalize_api_key(raw) == expected


def test_base_url_requires_https_except_loopback():
    assert llm_client.normalize_base_url("http://127.0.0.1:1234/v1/") == "http://127.0.0.1:1234/v1"
    assert llm_client.normalize_base_url("https://api.example.com/v1") == "https://api.example.com/v1"
    with pytest.raises(ValueError, match="must use HTTPS"):
        llm_client.normalize_base_url("http://api.example.com/v1")
    with pytest.raises(ValueError, match="credentials"):
        llm_client.normalize_base_url("https://user:secret@example.com/v1")


def test_chat_completions_url_accepts_base_or_full_endpoint():
    assert (
        llm_client.chat_completions_url("https://api.example.com/v1")
        == "https://api.example.com/v1/chat/completions"
    )
    endpoint = "https://api.example.com/v1/chat/completions"
    assert llm_client.chat_completions_url(endpoint) == endpoint


def test_provider_http_error_keeps_status_without_credentials():
    error = llm_client.ProviderHTTPError("qwen", 401, "invalid key")

    assert error.status_code == 401
    assert error.provider == "qwen"
    assert "401" in str(error)


@pytest.mark.parametrize(
    ("provider", "base_url", "model", "research_model", "key_env"),
    [
        ("openai", "https://api.openai.com/v1", "gpt-5.4-nano", "gpt-5.4-nano", "OPENAI_API_KEY"),
        ("kimi", "https://api.moonshot.ai/v1", "kimi-k2.6", "kimi-k3", "MOONSHOT_API_KEY"),
        ("qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen3.7-plus", "qwen3.7-max", "DASHSCOPE_API_KEY"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-3.6-flash", "gemini-3.1-pro-preview", "GEMINI_API_KEY"),
        ("grok", "https://api.x.ai/v1", "grok-4.3", "grok-4.3", "XAI_API_KEY"),
    ],
)
def test_managed_provider_defaults(provider, base_url, model, research_model, key_env):
    assert provider in config.SUPPORTED_LLM_PROVIDERS
    defaults = config.PROVIDER_DEFAULTS[provider]
    assert defaults["base_url"] == base_url
    assert defaults["model"] == model
    assert defaults["research_model"] == research_model
    assert defaults["key_env"] == key_env


def test_ollama_is_a_keyless_local_provider():
    defaults = config.PROVIDER_DEFAULTS["ollama"]
    assert defaults["base_url"] == "http://127.0.0.1:11434/v1"
    assert defaults["model"] == "qwen3.5:9b"
    client = llm_client.create_llm_client(
        provider="ollama",
        api_key="",
        base_url=defaults["base_url"],
    )
    assert isinstance(client, llm_client.OpenAICompatibleClient)
    assert client.endpoint == "http://127.0.0.1:11434/v1/chat/completions"


def test_missing_or_invalid_provider_defaults_to_openai_cloud():
    assert config.normalize_llm_provider(None) == "openai"
    assert config.normalize_llm_provider("") == "openai"
    assert config.normalize_llm_provider("not-a-provider") == "openai"


def test_local_system_prompt_stays_small_and_action_safe():
    import server

    prompt = server.LOCAL_JARVIS_SYSTEM_PROMPT.format(
        current_time="Wednesday at 10:00 AM",
        user_name="Tester",
    )
    assert len(prompt) < 1600
    assert "Never emit an action tag for normal conversation" in prompt
    assert "Never claim" in prompt
    assert "exactly two conversation languages: German and English" in prompt
    assert "Never reply in any third language" in prompt


@pytest.mark.parametrize("provider", ["openai", "kimi", "qwen", "gemini", "grok"])
def test_managed_openai_compatible_providers_require_a_key(provider):
    client = llm_client.create_llm_client(
        provider=provider,
        api_key="",
        base_url=config.PROVIDER_DEFAULTS[provider]["base_url"],
    )
    assert client is None


@pytest.mark.parametrize("provider", ["openai", "gemini", "grok"])
def test_new_providers_use_the_shared_safe_adapter(provider):
    client = llm_client.create_llm_client(
        provider=provider,
        api_key="test-key",
        base_url=config.PROVIDER_DEFAULTS[provider]["base_url"],
    )
    assert isinstance(client, llm_client.OpenAICompatibleClient)
    assert client.endpoint.endswith("/chat/completions")


@pytest.mark.asyncio
async def test_qwen_adapter_translates_anthropic_style_messages(monkeypatch):
    captured = {}

    class FakeResponse:
        is_error = False

        def json(self):
            return {
                "choices": [{"message": {"content": "Systems ready, sir."}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            }

    class FakeClient:
        def __init__(self, **options):
            captured["options"] = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="qwen",
        api_key="not-a-real-secret",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )

    response = await client.messages.create(
        model="qwen3.7-plus",
        max_tokens=32,
        system="You are JARVIS v4.",
        messages=[{"role": "user", "content": "Status?"}],
    )

    assert captured["url"].endswith("/compatible-mode/v1/chat/completions")
    assert captured["headers"]["Authorization"] == "Bearer not-a-real-secret"
    assert captured["payload"]["messages"][0] == {
        "role": "system",
        "content": "You are JARVIS v4.",
    }
    assert captured["payload"]["enable_thinking"] is False
    assert response.content[0].text == "Systems ready, sir."
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 4


@pytest.mark.asyncio
async def test_compatible_adapter_reuses_one_keepalive_client(monkeypatch):
    instances = []

    class FakeResponse:
        is_error = False

        def json(self):
            return {"choices": [{"message": {"content": "Ready"}}], "usage": {}}

    class FakeClient:
        def __init__(self, **options):
            self.options = options
            self.calls = 0
            self.closed = False
            instances.append(self)

        async def post(self, _url, **_kwargs):
            self.calls += 1
            return FakeResponse()

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="custom",
        api_key="",
        base_url="http://127.0.0.1:1234/v1",
    )
    for prompt in ("First", "Second"):
        await client.messages.create(
            model="local-model",
            max_tokens=8,
            messages=[{"role": "user", "content": prompt}],
        )

    assert len(instances) == 1
    assert instances[0].calls == 2
    assert instances[0].options["limits"].max_keepalive_connections == 5
    await client.aclose()
    assert instances[0].closed is True


@pytest.mark.asyncio
async def test_kimi_adapter_disables_slow_reasoning_for_voice_chat(monkeypatch):
    captured = {}

    class FakeResponse:
        is_error = False

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}], "usage": {}}

    class FakeClient:
        def __init__(self, **_options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, headers, json):
            captured.update(headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="kimi",
        api_key="test",
        base_url="https://api.moonshot.ai/v1",
    )
    await client.messages.create(
        model="kimi-k2.6",
        max_tokens=8,
        messages=[{"role": "user", "content": "OK?"}],
    )

    assert captured["payload"]["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_openai_adapter_uses_current_completion_budget_and_role_effort(monkeypatch):
    captured = {}

    class FakeResponse:
        is_error = False

        def json(self):
            return {"choices": [{"message": {"content": "Ready"}}], "usage": {}}

    class FakeClient:
        def __init__(self, **_options):
            pass

        async def post(self, _url, *, headers, json):
            captured.update(headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )
    await client.messages.create(
        model="gpt-5.6-terra",
        max_tokens=64,
        messages=[{"role": "user", "content": "Status?"}],
    )

    assert captured["payload"]["max_completion_tokens"] == 64
    assert "max_tokens" not in captured["payload"]
    assert captured["payload"]["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_openai_cost_first_default_model_uses_fast_provider_defaults(monkeypatch):
    """The measured 5.4 Nano default is faster than optional control hints."""
    captured = {}

    class FakeResponse:
        is_error = False

        def json(self):
            return {"choices": [{"message": {"content": "Ready"}}], "usage": {}}

    class FakeClient:
        def __init__(self, **_options):
            pass

        async def post(self, _url, *, headers, json):
            captured.update(headers=headers, payload=json)
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )
    await client.messages.create(
        model=config.PROVIDER_DEFAULTS["openai"]["model"],
        max_tokens=64,
        messages=[{"role": "user", "content": "Status?"}],
    )

    assert captured["payload"]["max_completion_tokens"] == 64
    assert "reasoning_effort" not in captured["payload"]
    assert "verbosity" not in captured["payload"]


@pytest.mark.asyncio
async def test_openai_retries_without_optional_reasoning_when_model_rejects_it(monkeypatch):
    payloads = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self.is_error = status_code >= 400
            self._payload = payload
            self.text = ""

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **_options):
            self.responses = [
                FakeResponse(400, {"error": {"message": "Unsupported reasoning_effort"}}),
                FakeResponse(200, {"choices": [{"message": {"content": "Ready"}}], "usage": {}}),
                FakeResponse(200, {"choices": [{"message": {"content": "Still ready"}}], "usage": {}}),
            ]

        async def post(self, _url, *, headers, json):
            payloads.append(dict(json))
            return self.responses.pop(0)

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )
    model = "gpt-5.6-terra"

    first = await client.messages.create(
        model=model,
        max_tokens=32,
        messages=[{"role": "user", "content": "Status?"}],
    )
    second = await client.messages.create(
        model=model,
        max_tokens=32,
        messages=[{"role": "user", "content": "Again?"}],
    )

    assert first.content[0].text == "Ready"
    assert second.content[0].text == "Still ready"
    assert payloads[0]["reasoning_effort"] == "low"
    assert "reasoning_effort" not in payloads[1]
    assert "reasoning_effort" not in payloads[2]
    assert payloads[2]["verbosity"] == "low"


@pytest.mark.asyncio
async def test_openai_retries_without_optional_verbosity_and_caches_result(monkeypatch):
    payloads = []

    class FakeResponse:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self.is_error = status_code >= 400
            self._payload = payload
            self.text = ""

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, **_options):
            self.responses = [
                FakeResponse(400, {"error": {"message": "Unsupported parameter: verbosity"}}),
                FakeResponse(200, {"choices": [{"message": {"content": "Ready"}}], "usage": {}}),
                FakeResponse(200, {"choices": [{"message": {"content": "Still ready"}}], "usage": {}}),
            ]

        async def post(self, _url, *, headers, json):
            payloads.append(dict(json))
            return self.responses.pop(0)

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="openai",
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
    )
    model = "gpt-5.6-terra"

    first = await client.messages.create(
        model=model,
        max_tokens=32,
        messages=[{"role": "user", "content": "Status?"}],
    )
    second = await client.messages.create(
        model=model,
        max_tokens=32,
        messages=[{"role": "user", "content": "Again?"}],
    )

    assert first.content[0].text == "Ready"
    assert second.content[0].text == "Still ready"
    assert payloads[0]["verbosity"] == "low"
    assert "verbosity" not in payloads[1]
    assert "verbosity" not in payloads[2]
    assert payloads[2]["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_ollama_qwen_disables_hidden_reasoning_for_fast_visible_replies(monkeypatch):
    captured = {}

    class FakeResponse:
        is_error = False

        def json(self):
            return {"choices": [{"message": {"content": "JARVIS_LOCAL_OK"}}], "usage": {}}

    class FakeClient:
        def __init__(self, **_options):
            pass

        async def post(self, _url, *, headers, json):
            captured.update(headers=headers, payload=json)
            return FakeResponse()

        async def aclose(self):
            return None

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="ollama",
        api_key="",
        base_url="http://127.0.0.1:11434/v1",
    )
    response = await client.messages.create(
        model="qwen3.5:4b",
        max_tokens=32,
        messages=[{"role": "user", "content": "Status?"}],
    )

    assert captured["payload"]["reasoning_effort"] == "none"
    assert "Authorization" not in captured["headers"]
    assert response.content[0].text == "JARVIS_LOCAL_OK"


@pytest.mark.asyncio
async def test_compatible_adapter_handles_reasoning_only_response(monkeypatch):
    class FakeResponse:
        is_error = False

        def json(self):
            return {
                "choices": [{"message": {"content": None, "reasoning_content": "Ready."}}],
                "usage": {},
            }

    class FakeClient:
        def __init__(self, **_options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="custom",
        api_key='"Bearer sk-test"',
        base_url="http://127.0.0.1:1234/v1",
    )
    response = await client.messages.create(
        model="local-model",
        max_tokens=8,
        messages=[{"role": "user", "content": "Status?"}],
    )

    assert client.api_key == "sk-test"
    assert response.content[0].text == "Ready."


@pytest.mark.asyncio
async def test_compatible_adapter_redacts_key_from_provider_error(monkeypatch):
    class FakeResponse:
        is_error = True
        status_code = 401
        text = ""

        def json(self):
            return {"error": {"message": "token sk-secret was rejected"}}

    class FakeClient:
        def __init__(self, **_options):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", FakeClient)
    client = llm_client.OpenAICompatibleClient(
        provider="custom",
        api_key="sk-secret",
        base_url="http://127.0.0.1:1234/v1",
    )

    with pytest.raises(llm_client.ProviderHTTPError) as caught:
        await client.messages.create(
            model="local-model",
            max_tokens=8,
            messages=[{"role": "user", "content": "Status?"}],
        )

    assert "sk-secret" not in str(caught.value)
    assert "[redacted]" in str(caught.value)
