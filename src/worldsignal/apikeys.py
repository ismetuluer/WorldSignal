"""API keys of cloud AI services, encrypted for the Windows user (DPAPI) in ``secrets.json`` of the data folder.

Keys are never stored in the database (its backups are plain copies) and never sent back to the UI; the UI only
learns whether a key is set. DPAPI ties the encryption to this Windows account: copying the file to another user
or computer makes it unreadable, which is the point.
"""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

PROVIDERS = ("gemini", "openai", "anthropic")
# Other secrets kept the same way: the browser extension's pairing key (fulltext/bridge.py).
NAMES = PROVIDERS + ("extension",)
_ENTROPY = b"WorldSignal API keys"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _dpapi(data: bytes, protect: bool) -> bytes:
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    out = _Blob()
    source, entropy = _blob(data), _blob(_ENTROPY)
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 0x01, ctypes.byref(out))  # UI_FORBIDDEN
    if not ok:
        raise OSError(ctypes.get_last_error() or "DPAPI failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def dpapi_protect(data: bytes) -> bytes:
    return _dpapi(data, True)


def dpapi_unprotect(data: bytes) -> bytes:
    return _dpapi(data, False)


class SecretStore:
    def __init__(self, path: Path, protect: Callable[[bytes], bytes] | None = None,
                 unprotect: Callable[[bytes], bytes] | None = None) -> None:
        self.path = path
        if protect is None or unprotect is None:
            if sys.platform != "win32":
                raise RuntimeError("API keys can only be stored on Windows")
            protect, unprotect = dpapi_protect, dpapi_unprotect
        self._protect = protect
        self._unprotect = unprotect

    def _read(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {k: v for k, v in data.items() if k in NAMES and isinstance(v, str)}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.exception("API key file unreadable: %s", self.path)
            return {}

    def _write(self, data: dict[str, str]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic: a crash leaves the old file or the new one

    def get(self, provider: str) -> str | None:
        stored = self._read().get(provider)
        if not stored:
            return None
        try:
            return self._unprotect(base64.b64decode(stored)).decode("utf-8")
        except (OSError, ValueError):
            log.warning("API key for %s cannot be decrypted (another Windows user or computer?)", provider)
            return None

    def set(self, provider: str, key: str) -> None:
        if provider not in NAMES:
            raise KeyError(provider)
        data = self._read()
        data[provider] = base64.b64encode(self._protect(key.encode("utf-8"))).decode("ascii")
        self._write(data)

    def delete(self, provider: str) -> None:
        data = self._read()
        if data.pop(provider, None) is not None:
            self._write(data)

    def status(self) -> dict[str, bool]:
        return {p: self.get(p) is not None for p in PROVIDERS}
