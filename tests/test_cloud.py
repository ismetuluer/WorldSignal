"""Cloud AI services (ai/cloud.py), encrypted API keys (apikeys.py) and the worker running on a cloud service."""

import asyncio
import json
import sys

import httpx
import pytest

from worldsignal.ai.cloud import AnthropicClient, GeminiClient, OpenAIClient, gemini_schema
from worldsignal.ai.enrich import EnrichTask
from worldsignal.ai.ollama import OllamaError
from worldsignal.apikeys import SecretStore
from test_api import client, ctx  # noqa: F401  (the API fixtures)

SCHEMA = EnrichTask(("tr", "en"), ("nato",)).schema
ANSWER = {"title_tr": "Başlık", "summary_tr": "Özet.", "title_en": "Title", "summary_en": "Summary.",
          "category": "politics", "countries": ["IQ"], "mentions_turkey": False, "topics": []}


def run(coro):
    return asyncio.run(coro)


class Recorder:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    def body(self, n: int = -1) -> dict:
        return json.loads(self.requests[n].content)


# -- Gemini -----------------------------------------------------------------------------------------------
def test_gemini_sends_a_json_schema_and_reads_the_answer():
    rec = Recorder(httpx.Response(200, json={
        "candidates": [{"content": {"parts": [{"text": json.dumps(ANSWER)}]}}],
        "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 60},
    }))
    result = run(GeminiClient("k-123", transport=rec.transport).chat_json("gemini-x", "system text", "user text", SCHEMA,
                                                                          num_predict=700))
    assert result.data == ANSWER and result.output_tokens == 60
    req = rec.requests[0]
    assert req.url.path.endswith("/models/gemini-x:generateContent") and req.headers["x-goog-api-key"] == "k-123"
    assert "k-123" not in str(req.url)  # the key travels in a header, not in the address (logs, proxies)
    body = rec.body()
    assert body["systemInstruction"]["parts"][0]["text"] == "system text"
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json" and config["maxOutputTokens"] == 700
    assert config["responseSchema"]["type"] == "OBJECT"
    assert config["responseSchema"]["properties"]["topics"] == {"type": "ARRAY", "items": {"type": "STRING", "enum": ["nato"]}}


def test_gemini_schema_keeps_field_order_and_required():
    out = gemini_schema(SCHEMA)
    assert out["propertyOrdering"][:2] == ["title_tr", "summary_tr"] and out["required"] == SCHEMA["required"]


@pytest.mark.parametrize(("response", "code"), [
    (httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}), "bad_key"),
    (httpx.Response(403, json={"error": {}}), "bad_key"),
    (httpx.Response(404, json={"error": {}}), "model_missing"),
    (httpx.Response(429, json={"error": {}}), "rate_limited"),
    (httpx.Response(500, text="oops"), "http_500"),
    (httpx.Response(200, json={"candidates": []}), "bad_response"),
    (httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}), "bad_response"),
])
def test_gemini_errors(response, code):
    with pytest.raises(OllamaError) as err:
        run(GeminiClient("k", transport=Recorder(response).transport).chat_json("m", "s", "u", SCHEMA))
    assert err.value.code == code


def test_gemini_lists_only_models_that_write_text():
    rec = Recorder(httpx.Response(200, json={"models": [
        {"name": "models/gemini-b", "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/embedding-1", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-a", "supportedGenerationMethods": ["generateContent"]},
    ]}))
    assert run(GeminiClient("k", transport=rec.transport).list_models()) == ["gemini-a", "gemini-b"]


# -- OpenAI-compatible --------------------------------------------------------------------------------------
def test_openai_uses_a_json_schema_and_falls_back_to_json_mode():
    fenced = "```json\n" + json.dumps(ANSWER) + "\n```"
    rec = Recorder(
        httpx.Response(400, json={"error": {"message": "response_format json_schema not supported"}}),
        httpx.Response(200, json={"choices": [{"message": {"content": fenced}}], "usage": {"completion_tokens": 50}}),
    )
    client = OpenAIClient("sk-1", "http://lmstudio.local:1234/v1/", transport=rec.transport)
    result = run(client.chat_json("local-model", "s", "u", SCHEMA))
    assert result.data == ANSWER and result.output_tokens == 50
    assert str(rec.requests[0].url) == "http://lmstudio.local:1234/v1/chat/completions"
    assert rec.requests[0].headers["authorization"] == "Bearer sk-1"
    assert rec.body(0)["response_format"]["type"] == "json_schema" and rec.body(1)["response_format"] == {"type": "json_object"}


def test_openai_without_a_key_sends_no_authorization():
    rec = Recorder(httpx.Response(200, json={"data": [{"id": "b"}, {"id": "a"}]}))
    assert run(OpenAIClient("", "http://localhost:1234/v1", transport=rec.transport).list_models()) == ["a", "b"]
    assert "authorization" not in rec.requests[0].headers


@pytest.mark.parametrize(("status", "code"), [(401, "bad_key"), (429, "rate_limited"), (404, "model_missing")])
def test_openai_errors(status, code):
    with pytest.raises(OllamaError) as err:
        run(OpenAIClient("k", transport=Recorder(httpx.Response(status, json={})).transport).chat_json("m", "s", "u", SCHEMA))
    assert err.value.code == code


def test_network_failures_are_service_errors():
    def boom(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(OllamaError) as err:
        run(OpenAIClient("k", transport=httpx.MockTransport(boom)).chat_json("m", "s", "u", SCHEMA))
    assert err.value.code == "unreachable"


# -- Anthropic --------------------------------------------------------------------------------------------------
def test_anthropic_answers_through_a_forced_tool_call():
    rec = Recorder(httpx.Response(200, json={
        "content": [{"type": "text", "text": "Sure."}, {"type": "tool_use", "name": "answer", "input": ANSWER}],
        "usage": {"input_tokens": 300, "output_tokens": 90},
    }))
    result = run(AnthropicClient("sk-ant", transport=rec.transport).chat_json("claude-x", "sys", "user", SCHEMA,
                                                                                num_predict=900))
    assert result.data == ANSWER and result.output_tokens == 90
    req, body = rec.requests[0], rec.body()
    assert req.url.path == "/v1/messages" and req.headers["x-api-key"] == "sk-ant" and req.headers["anthropic-version"]
    assert body["tools"][0]["input_schema"] == SCHEMA and body["tool_choice"] == {"type": "tool", "name": "answer"}
    assert body["system"] == "sys" and body["max_tokens"] == 900


def test_anthropic_without_the_tool_call_is_a_bad_response():
    rec = Recorder(httpx.Response(200, json={"content": [{"type": "text", "text": "{}"}]}))
    with pytest.raises(OllamaError) as err:
        run(AnthropicClient("k", transport=rec.transport).chat_json("m", "s", "u", SCHEMA))
    assert err.value.code == "bad_response"


def test_cloud_clients_have_no_local_gpu_and_no_idle_network_calls():
    rec = Recorder()
    for client in (GeminiClient("k", transport=rec.transport), OpenAIClient("k", transport=rec.transport),
                   AnthropicClient("k", transport=rec.transport)):
        assert run(client.loaded_models()) == [] and run(client.version()) == client.name
    assert rec.requests == []


# -- API keys --------------------------------------------------------------------------------------------------
def fake_store(path):
    return SecretStore(path, protect=lambda b: bytes(x ^ 0x5A for x in b), unprotect=lambda b: bytes(x ^ 0x5A for x in b))


def test_keys_are_stored_encrypted_and_can_be_removed(tmp_path):
    store = fake_store(tmp_path / "secrets.json")
    assert store.status() == {"gemini": False, "openai": False, "anthropic": False}
    store.set("gemini", "AIza-secret")
    assert store.get("gemini") == "AIza-secret" and store.status()["gemini"]
    assert "AIza" not in (tmp_path / "secrets.json").read_text()
    store.delete("gemini")
    assert store.get("gemini") is None
    with pytest.raises(KeyError):
        store.set("other", "x")
    (tmp_path / "secrets.json").write_text("not json")  # a damaged file means "no keys", not a crash
    assert store.get("gemini") is None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_real_windows_encryption_round_trip(tmp_path):
    store = SecretStore(tmp_path / "secrets.json")
    store.set("anthropic", "sk-ant-123")
    assert store.get("anthropic") == "sk-ant-123" and "sk-ant" not in (tmp_path / "secrets.json").read_text()


# -- the worker on a cloud service ---------------------------------------------------------------------------------
class FakeCloud:
    """Stands in for a cloud client; records what the worker asks."""

    def __init__(self, answer=None, error: str | None = None) -> None:
        self.answer = answer or ANSWER
        self.error = error
        self.made: list[tuple[str, str, str]] = []
        self.calls: list[dict] = []

    def factory(self, provider, key, url):
        self.made.append((provider, key, url))
        return self

    async def version(self):
        return "fake"

    async def loaded_models(self):
        raise AssertionError("a cloud service has no local GPU to check")

    async def chat_json(self, model, system, user, schema, **kw):
        from worldsignal.ai.ollama import ChatResult

        self.calls.append({"model": model, "schema": schema, **kw})
        if self.error:
            raise OllamaError(self.error, "")
        return ChatResult(self.answer, json.dumps(self.answer), 10.0, 0.0, 1, 1, 10.0)


def cloud_worker(db, settings, fake, keys, **prefs):
    from worldsignal.ai.worker import AiWorker
    from worldsignal.repo.ai import AiRepository

    settings.set_many({"ai.provider": "gemini", "ai.gemini_model": "gemini-x", "ai.cloud_rpm": 12, "ai.depth": "full",
                       **prefs})
    return AiWorker(AiRepository(db), settings, client_factory=lambda url: pytest.fail("Ollama must not be used"),
                    keys=keys, cloud_factory=fake.factory)


def test_worker_runs_on_the_chosen_cloud_service_at_the_set_pace(db, sources, articles, settings, tmp_path):
    from test_ai import add_articles

    add_articles(db, sources, articles, n=2)
    keys = fake_store(tmp_path / "secrets.json")
    fake = FakeCloud()
    worker = cloud_worker(db, settings, fake, keys)
    assert run(worker.step()) == 30  # no key yet: waits
    assert worker.status()["state"] == "no_key" and fake.calls == []

    keys.set("gemini", "AIza-1")
    assert run(worker.step()) == pytest.approx(5.0)  # 12 requests per minute
    assert fake.made[-1] == ("gemini", "AIza-1", "https://api.openai.com/v1")
    assert fake.calls[0]["model"] == "gemini-x" and fake.calls[0]["num_predict"] == 300 + 400 * 2
    assert worker.status()["done"] == 1 and worker.status()["provider"] == "gemini"


@pytest.mark.parametrize("code", ["bad_key", "rate_limited"])
def test_a_wrong_key_or_a_full_quota_pauses_without_failing_articles(db, sources, articles, settings, tmp_path, code):
    from test_ai import add_articles
    from worldsignal.repo.ai import AiRepository

    add_articles(db, sources, articles, n=1)
    keys = fake_store(tmp_path / "secrets.json")
    keys.set("gemini", "AIza-1")
    worker = cloud_worker(db, settings, FakeCloud(error=code), keys)
    assert run(worker.step()) == 30
    assert worker.status()["state"] == code and AiRepository(db).next_job().attempts == 0


def test_a_local_openai_compatible_service_needs_no_key(db, sources, articles, settings, tmp_path):
    from test_ai import add_articles

    add_articles(db, sources, articles, n=1)
    fake = FakeCloud()
    worker = cloud_worker(db, settings, fake, fake_store(tmp_path / "secrets.json"), **{
        "ai.provider": "openai", "ai.openai_model": "local", "ai.openai_url": "http://localhost:1234/v1"})
    run(worker.step())
    assert fake.made[-1] == ("openai", "", "http://localhost:1234/v1") and worker.status()["done"] == 1


# -- API --------------------------------------------------------------------------------------------------------------
def test_key_endpoints_never_return_the_key(client, ctx, monkeypatch, tmp_path):
    from test_api import H
    from worldsignal.api import app as app_module

    ctx.keys = fake_store(tmp_path / "secrets.json")
    assert client.get("/api/ai/keys", headers=H).json() == {"gemini": False, "openai": False, "anthropic": False}
    assert client.post("/api/ai/cloud/test", headers=H, json={"provider": "gemini"}).json()["error_code"] == "no_key"
    assert client.put("/api/ai/keys/gemini", headers=H, json={"key": "short"}).status_code == 422
    assert client.put("/api/ai/keys/other", headers=H, json={"key": "AIza-long-enough"}).status_code == 422
    r = client.put("/api/ai/keys/gemini", headers=H, json={"key": "  AIza-long-enough  "})
    assert r.json()["gemini"] is True and "AIza" not in r.text
    assert ctx.keys.get("gemini") == "AIza-long-enough"
    for path in ("/api/settings", "/api/ai/keys", "/api/ai/status", "/api/status"):
        assert "AIza" not in client.get(path, headers=H).text, path

    seen = []

    class Lister:
        async def list_models(self):
            return ["gemini-a", "gemini-b"]

    monkeypatch.setattr(app_module, "make_cloud_client", lambda p, k, u: seen.append((p, k, u)) or Lister())
    test = client.post("/api/ai/cloud/test", headers=H, json={"provider": "gemini"}).json()
    assert test == {"ok": True, "error_code": None, "models": ["gemini-a", "gemini-b"]} and seen == [("gemini", "AIza-long-enough", "")]

    r = client.patch("/api/settings", headers=H, json={"ai.provider": "gemini", "ai.gemini_model": " gemini-a ", "ai.cloud_rpm": 30})
    assert r.json()["ai.gemini_model"] == "gemini-a" and r.json()["ai.cloud_rpm"] == 30
    assert client.patch("/api/settings", headers=H, json={"ai.provider": "skynet"}).status_code == 422
    assert client.patch("/api/settings", headers=H, json={"ai.cloud_rpm": 0}).status_code == 422
    assert client.delete("/api/ai/keys/gemini", headers=H).json()["gemini"] is False
