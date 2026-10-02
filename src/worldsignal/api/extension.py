"""HTTP side of the browser extension (fulltext/bridge.py).

``/api/ext/*`` is called by the extension with the pairing key in ``X-WorldSignal-Extension``; requests from web pages
(an ``http(s)://`` Origin) or for another host (DNS rebinding) are refused even with the key. ``/api/extension`` (the
program's own UI, session token) shows and renews the pairing code. The code is never logged, and neither is a lease
received from the network: a malformed one must not be able to break a response or a log line.

``/api/ext/hello`` needs no key, but proves that this program holds it and which port it listens on: it answers a
random nonce from the extension with ``HMAC-SHA256(key, "worldsignal-hello:" + port + ":" + nonce)``. The extension
checks the proof against the port it asked and sends its key only to a port that proved itself, so another local
program listening on one of the extension's ports learns nothing, even if it relays the question to the real program
(the answer then names the real program's port, not its own). A local process that can read the user's memory or files
is out of scope.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, field_validator

from .. import __version__
from ..fulltext.bridge import EXTENSION_ERRORS, UnknownLease

if TYPE_CHECKING:
    from .app import AppContext

EXTENSION_PORTS = range(47821, 47831)
KEY_NAME = "extension"
MAX_HTML = 8_000_000
MAX_LEASE = 100
MAX_URL = 2000
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
NONCE_PATTERN = r"^[A-Za-z0-9_-]{16,64}$"
HELLO_PREFIX = "worldsignal-hello:"


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": ""})


class ResultBody(BaseModel):
    # Sizes are checked in the route, not by the model: a validation error echoes the input back, which for an 8 MB
    # page is wasteful and for a lone surrogate in valid JSON cannot be encoded.
    lease: str
    html: str | None = None
    final_url: str | None = None
    error: str | None = None
    status: int | None = None  # the page's HTTP status as the browser saw it; anything but 100-599 is ignored

    @field_validator("status", mode="before")
    @classmethod
    def _plausible_status(cls, value: Any) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
            return value
        return None


def pairing_code(ctx: AppContext, renew: bool = False) -> str:
    if ctx.keys is None:
        raise _error(503, "unavailable")
    code = None if renew else ctx.keys.get(KEY_NAME)
    if not code:
        code = secrets.token_urlsafe(32)
        ctx.keys.set(KEY_NAME, code)
    return code


def hello_proof(key: str, port: int, nonce: str) -> str:
    """What the program answers to the extension's nonce: base64url (no padding) of HMAC-SHA256 over the port it
    listens on and the nonce."""
    message = f"{HELLO_PREFIX}{port}:{nonce}".encode("ascii")
    digest = hmac.new(key.encode("utf-8"), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _host_port(request: Request) -> int | None:
    """The port named in the Host header (only used while the bound port is not known yet)."""
    host = request.headers.get("host") or ""
    _, sep, port = host.rpartition(":")
    return int(port) if sep and port.isdigit() and 0 < int(port) < 65536 else None


def _same_key(given: str, key: str) -> bool:
    """Constant-time comparison as bytes: a non-ASCII or malformed header is simply not the key."""
    return hmac.compare_digest(given.encode("utf-8", "surrogatepass"), key.encode("utf-8"))


def extension_routers(ctx: AppContext, require_token: Any) -> tuple[APIRouter, APIRouter, APIRouter]:
    def local_only(request: Request) -> None:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        origin = request.headers.get("origin") or ""
        if host not in LOCAL_HOSTS or origin.startswith(("http://", "https://")):
            raise _error(403, "forbidden")

    def from_extension(request: Request, x_worldsignal_extension: Annotated[str | None, Header()] = None) -> None:
        local_only(request)
        key = ctx.keys.get(KEY_NAME) if ctx.keys is not None else None
        if not key or not x_worldsignal_extension or not _same_key(x_worldsignal_extension, key):
            raise _error(401, "not_paired")

    def bridge():
        if ctx.bridge is None:
            raise _error(503, "unavailable")
        return ctx.bridge

    open_ = APIRouter(prefix="/api/ext", dependencies=[Depends(local_only)])
    keyed = APIRouter(prefix="/api/ext", dependencies=[Depends(from_extension)])
    ui = APIRouter(prefix="/api/extension", dependencies=[Depends(require_token)])

    @open_.get("/hello")
    def hello(request: Request, nonce: Annotated[str, Query(pattern=NONCE_PATTERN)]) -> dict[str, str | None]:
        key = ctx.keys.get(KEY_NAME) if ctx.keys is not None else None
        # The port this program is bound to (set before the server starts); the Host header only as a fallback.
        port = ctx.port or _host_port(request)
        proof = hello_proof(key, port, nonce) if key and port else None
        return {"app": "worldsignal", "version": __version__, "proof": proof}

    @keyed.post("/next")
    def next_job() -> dict[str, Any]:
        return bridge().next()

    @keyed.post("/result")
    def result(body: ResultBody) -> dict[str, Any]:
        if len(body.lease) > MAX_LEASE:
            raise _error(409, "unknown_lease")
        if (body.html is not None and len(body.html) > MAX_HTML) or (
                body.final_url is not None and len(body.final_url) > MAX_URL):
            # The page was read but cannot be accepted: close the lease (the attempt counts) instead of letting it
            # hold up the queue until it runs out, and tell the extension.
            try:
                bridge().reject(body.lease, "too_large")
            except UnknownLease:
                pass
            raise _error(422, "too_large")
        if body.error is not None and body.error not in EXTENSION_ERRORS:
            raise _error(422, "bad_error")
        try:
            return bridge().result(body.lease, html=body.html, final_url=body.final_url, error=body.error,
                                   status=body.status)
        except UnknownLease:
            raise _error(409, "unknown_lease") from None

    @keyed.get("/status")
    def ext_status() -> dict[str, Any]:
        return bridge().status()

    @ui.get("")
    def info() -> dict[str, Any]:
        return {"code": pairing_code(ctx), "port": ctx.port, "fixed_port": ctx.port in EXTENSION_PORTS,
                "status": bridge().status()}

    @ui.post("/code")
    def renew() -> dict[str, str]:
        return {"code": pairing_code(ctx, renew=True)}

    return open_, keyed, ui
