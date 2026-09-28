"""Minimal async client for the local Ollama HTTP API.

Only the endpoints World Signal needs: version, model list, loaded models and
JSON-constrained chat. Every failure is raised as :class:`OllamaError` with a
machine-readable ``code`` the UI translates:

* ``unreachable``   – Ollama is not running / wrong address
* ``model_missing`` – the configured model is not installed
* ``timeout``       – the model did not answer in time
* ``bad_response``  – the answer was not valid JSON for the schema
* ``http_<n>``      – any other HTTP error from Ollama
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_URL = "http://localhost:11434"
# Generation on a busy GPU can take a while, loading a large model even longer.
GENERATE_TIMEOUT = httpx.Timeout(300.0, connect=5.0)
QUICK_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


class OllamaError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class ModelInfo:
    name: str
    size_bytes: int
    parameter_size: str | None
    quantization: str | None
    family: str | None


@dataclass
class ChatResult:
    data: dict[str, Any]
    raw: str
    total_ms: float
    load_ms: float
    prompt_tokens: int
    output_tokens: int
    eval_ms: float

    @property
    def tokens_per_second(self) -> float:
        return self.output_tokens / (self.eval_ms / 1000) if self.eval_ms else 0.0


class OllamaClient:
    def __init__(self, base_url: str = DEFAULT_URL, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._transport = transport

    def _client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=self._transport)

    async def _request(self, method: str, path: str, timeout: httpx.Timeout, **kwargs: Any) -> Any:
        try:
            async with self._client(timeout) as client:
                resp = await client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise OllamaError("timeout" if timeout is GENERATE_TIMEOUT else "unreachable", repr(exc)) from exc
        except httpx.HTTPError as exc:
            raise OllamaError("unreachable", repr(exc)) from exc
        if resp.status_code == 404:
            raise OllamaError("model_missing", resp.text[:200])
        if resp.status_code >= 400:
            raise OllamaError(f"http_{resp.status_code}", resp.text[:200])
        try:
            return resp.json()
        except ValueError as exc:
            raise OllamaError("bad_response", resp.text[:200]) from exc

    async def version(self) -> str:
        data = await self._request("GET", "/api/version", QUICK_TIMEOUT)
        return str(data.get("version", ""))

    async def list_models(self) -> list[ModelInfo]:
        data = await self._request("GET", "/api/tags", QUICK_TIMEOUT)
        models = []
        for m in data.get("models", []):
            details = m.get("details") or {}
            models.append(
                ModelInfo(
                    name=m["name"],
                    size_bytes=int(m.get("size") or 0),
                    parameter_size=details.get("parameter_size"),
                    quantization=details.get("quantization_level"),
                    family=details.get("family"),
                )
            )
        return sorted(models, key=lambda x: x.name.lower())

    async def capabilities(self, model: str) -> list[str] | None:
        """What a model can do ("completion", "embedding", ...). None when this Ollama does not say."""
        data = await self._request("POST", "/api/show", QUICK_TIMEOUT, json={"model": model})
        caps = data.get("capabilities")
        return [str(c) for c in caps] if isinstance(caps, list) else None

    async def loaded_models(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/ps", QUICK_TIMEOUT)
        return list(data.get("models", []))

    async def unload(self, model: str) -> None:
        await self._request("POST", "/api/generate", GENERATE_TIMEOUT, json={"model": model, "keep_alive": 0})

    async def embed(
        self, model: str, texts: list[str], *, cpu_only: bool = True, keep_alive: str = "30m"
    ) -> list[list[float]]:
        """Embedding vectors for ``texts``.

        ``cpu_only`` keeps the embedding model off the graphics card (``num_gpu: 0``) so it
        never competes with the chat model or the user's own models for VRAM.
        """
        if not texts:
            return []
        body: dict[str, Any] = {"model": model, "input": texts, "keep_alive": keep_alive, "truncate": True}
        if cpu_only:
            body["options"] = {"num_gpu": 0}
        data = await self._request("POST", "/api/embed", GENERATE_TIMEOUT, json=body)
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise OllamaError("bad_response", f"expected {len(texts)} embeddings")
        return vectors

    async def chat_json(
        self,
        model: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        *,
        temperature: float = 0.2,
        num_ctx: int = 8192,
        num_predict: int = 1024,
        keep_alive: str = "10m",
    ) -> ChatResult:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "think": False,
            "keep_alive": keep_alive,
            # num_predict bounds the answer so a looping model cannot hold the GPU.
            "options": {"temperature": temperature, "num_ctx": num_ctx, "num_predict": num_predict},
        }
        data = await self._request("POST", "/api/chat", GENERATE_TIMEOUT, json=body)
        raw = (data.get("message") or {}).get("content", "")
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise OllamaError("bad_response", raw[:300]) from exc
        if not isinstance(parsed, dict):
            raise OllamaError("bad_response", raw[:300])
        ns = 1_000_000
        return ChatResult(
            data=parsed,
            raw=raw,
            total_ms=data.get("total_duration", 0) / ns,
            load_ms=data.get("load_duration", 0) / ns,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            output_tokens=int(data.get("eval_count") or 0),
            eval_ms=data.get("eval_duration", 0) / ns,
        )
