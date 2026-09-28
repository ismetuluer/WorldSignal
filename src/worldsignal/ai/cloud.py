"""Cloud AI services as an alternative to Ollama: Google Gemini, OpenAI-compatible services (OpenAI, OpenRouter,
Groq, Mistral, DeepSeek, LM Studio …) and Anthropic Claude.

Each client offers what the AI worker uses from :class:`~worldsignal.ai.ollama.OllamaClient`: ``chat_json``
(JSON answer constrained by a schema), ``version`` and ``loaded_models`` (a cloud service has no local GPU to
share), plus ``list_models`` for the settings. Errors are raised as :class:`OllamaError` with the same codes, and
two of their own the worker treats as "service unavailable": ``bad_key`` (401/403) and ``rate_limited`` (429).

The user chose the service and entered their own key; what is sent is the text the AI works on (see README →
"Bulut yapay zekâ"). The key comes from :mod:`worldsignal.apikeys` and is never logged.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from .ollama import ChatResult, OllamaError

GENERATE_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
QUICK_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
PROVIDERS = ("gemini", "openai", "anthropic")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
OPENAI_URL = "https://api.openai.com/v1"
ANTHROPIC_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"


def _error_for(resp: httpx.Response) -> OllamaError:
    detail = resp.text[:300]
    if resp.status_code in (401, 403) or (resp.status_code == 400 and "API_KEY_INVALID" in resp.text):
        return OllamaError("bad_key", detail)  # Gemini answers a wrong key with 400 API_KEY_INVALID
    if resp.status_code == 404:
        return OllamaError("model_missing", detail)
    if resp.status_code == 429:
        return OllamaError("rate_limited", detail)
    return OllamaError(f"http_{resp.status_code}", detail)


def _parse_object(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):  # some services wrap JSON in a code fence despite being asked not to
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise OllamaError("bad_response", raw[:300]) from exc
    if not isinstance(data, dict):
        raise OllamaError("bad_response", raw[:300])
    return data


class _CloudClient:
    name = "cloud"

    def __init__(self, key: str, base_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    async def _call(self, method: str, url: str, timeout: httpx.Timeout, **kwargs: Any) -> Any:
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport) as client:
                resp = await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise OllamaError("timeout", type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise OllamaError("unreachable", type(exc).__name__) from exc
        if resp.status_code >= 400:
            raise _error_for(resp)
        try:
            return resp.json()
        except ValueError as exc:
            raise OllamaError("bad_response", resp.text[:300]) from exc

    async def version(self) -> str:
        return self.name  # no network call: the worker asks this every few seconds when idle

    async def loaded_models(self) -> list[dict[str, Any]]:
        return []  # nothing of ours occupies the local graphics card

    @staticmethod
    def _result(data: dict[str, Any], raw: str, started: float, prompt_tokens: int, output_tokens: int) -> ChatResult:
        elapsed = (time.perf_counter() - started) * 1000
        return ChatResult(data=data, raw=raw, total_ms=elapsed, load_ms=0.0, prompt_tokens=prompt_tokens,
                          output_tokens=output_tokens, eval_ms=elapsed)


# -- Google Gemini ---------------------------------------------------------------------------------------
def gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Gemini's responseSchema is an OpenAPI subset with upper-case type names."""
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key == "type":
            out["type"] = str(value).upper()
        elif key == "properties":
            out["properties"] = {k: gemini_schema(v) for k, v in value.items()}
        elif key == "items":
            out["items"] = gemini_schema(value)
        elif key in ("required", "enum"):
            out[key] = list(value)
    if out.get("type") == "OBJECT" and "properties" in out:
        out["propertyOrdering"] = list(out["properties"])
    return out


class GeminiClient(_CloudClient):
    name = "gemini"

    def __init__(self, key: str, base_url: str = GEMINI_URL, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(key, base_url, transport)

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.key}

    async def list_models(self) -> list[str]:
        data = await self._call("GET", f"{self.base_url}/models", QUICK_TIMEOUT, headers=self._headers(),
                                params={"pageSize": 200})
        return sorted(m["name"].removeprefix("models/") for m in data.get("models", [])
                      if "generateContent" in (m.get("supportedGenerationMethods") or []))

    async def chat_json(self, model: str, system: str, user: str, schema: dict[str, Any], *,
                        temperature: float = 0.2, num_predict: int = 1024, **_: Any) -> ChatResult:
        started = time.perf_counter()
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": num_predict,
                                 "responseMimeType": "application/json", "responseSchema": gemini_schema(schema)},
        }
        data = await self._call("POST", f"{self.base_url}/models/{model}:generateContent", GENERATE_TIMEOUT,
                                headers=self._headers(), json=body)
        try:
            raw = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError) as exc:
            raise OllamaError("bad_response", json.dumps(data)[:300]) from exc
        usage = data.get("usageMetadata") or {}
        return self._result(_parse_object(raw), raw, started, int(usage.get("promptTokenCount") or 0),
                            int(usage.get("candidatesTokenCount") or 0))


# -- OpenAI and compatible services ----------------------------------------------------------------------------
class OpenAIClient(_CloudClient):
    name = "openai"

    def __init__(self, key: str, base_url: str = OPENAI_URL, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(key, base_url or OPENAI_URL, transport)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}"} if self.key else {}

    async def list_models(self) -> list[str]:
        data = await self._call("GET", f"{self.base_url}/models", QUICK_TIMEOUT, headers=self._headers())
        return sorted(m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id"))

    async def chat_json(self, model: str, system: str, user: str, schema: dict[str, Any], *,
                        temperature: float = 0.2, num_predict: int = 1024, **_: Any) -> ChatResult:
        started = time.perf_counter()
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": num_predict,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
        }
        url = f"{self.base_url}/chat/completions"
        try:
            data = await self._call("POST", url, GENERATE_TIMEOUT, headers=self._headers(), json=body)
        except OllamaError as exc:
            if exc.code != "http_400":
                raise
            # Some compatible services know only plain JSON mode; the prompt already describes every field.
            body["response_format"] = {"type": "json_object"}
            data = await self._call("POST", url, GENERATE_TIMEOUT, headers=self._headers(), json=body)
        try:
            raw = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise OllamaError("bad_response", json.dumps(data)[:300]) from exc
        usage = data.get("usage") or {}
        return self._result(_parse_object(raw), raw, started, int(usage.get("prompt_tokens") or 0),
                            int(usage.get("completion_tokens") or 0))


# -- Anthropic Claude -------------------------------------------------------------------------------------------
class AnthropicClient(_CloudClient):
    name = "anthropic"

    def __init__(self, key: str, base_url: str = ANTHROPIC_URL, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(key, base_url, transport)

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.key, "anthropic-version": ANTHROPIC_VERSION}

    async def list_models(self) -> list[str]:
        data = await self._call("GET", f"{self.base_url}/models", QUICK_TIMEOUT, headers=self._headers(),
                                params={"limit": 100})
        return sorted(m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id"))

    async def chat_json(self, model: str, system: str, user: str, schema: dict[str, Any], *,
                        temperature: float = 0.2, num_predict: int = 1024, **_: Any) -> ChatResult:
        """The answer comes as the input of a forced tool call, which the API checks against the schema."""
        started = time.perf_counter()
        body = {
            "model": model,
            "max_tokens": num_predict,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [{"name": "answer", "description": "Return the result.", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": "answer"},
        }
        data = await self._call("POST", f"{self.base_url}/messages", GENERATE_TIMEOUT, headers=self._headers(), json=body)
        block = next((b for b in data.get("content", []) if b.get("type") == "tool_use"), None)
        if block is None or not isinstance(block.get("input"), dict):
            raise OllamaError("bad_response", json.dumps(data)[:300])
        usage = data.get("usage") or {}
        return self._result(block["input"], json.dumps(block["input"], ensure_ascii=False), started,
                            int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0))


def make_client(provider: str, key: str, base_url: str = "",
                transport: httpx.AsyncBaseTransport | None = None) -> _CloudClient:
    if provider == "gemini":
        return GeminiClient(key, transport=transport)
    if provider == "openai":
        return OpenAIClient(key, base_url or OPENAI_URL, transport=transport)
    if provider == "anthropic":
        return AnthropicClient(key, transport=transport)
    raise KeyError(provider)
