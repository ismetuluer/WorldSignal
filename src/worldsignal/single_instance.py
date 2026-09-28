"""Ensure only one World Signal runs per user.

The first instance holds an OS-level lock on ``instance.lock`` for its whole
lifetime and writes its port and token to ``instance.json``. A second
instance fails to take the lock, asks the first one to show its window and
exits. The OS releases the lock automatically if the process crashes, so a
stale lock file never blocks start-up.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import IO

import httpx

log = logging.getLogger(__name__)


class InstanceLock:
    def __init__(self, lock_path: Path, info_path: Path) -> None:
        self.lock_path = lock_path
        self.info_path = info_path
        self._fh: IO[bytes] | None = None

    def acquire(self) -> bool:
        fh = open(self.lock_path, "a+b")  # noqa: SIM115 - kept open for the lifetime of the lock
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def publish(self, port: int, token: str) -> None:
        tmp = self.info_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"port": port, "token": token, "pid": os.getpid()}), encoding="utf-8")
        os.replace(tmp, self.info_path)

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            self.info_path.unlink(missing_ok=True)
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            log.debug("Releasing instance lock failed", exc_info=True)
        finally:
            self._fh.close()
            self._fh = None


def activate_running_instance(info_path: Path) -> bool:
    """Ask the already running instance to bring its window to front."""
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        resp = httpx.post(
            f"http://127.0.0.1:{int(info['port'])}/api/app/show",
            headers={"X-WorldSignal-Token": info["token"]},
            timeout=5,
        )
        return resp.status_code == 200
    except (OSError, ValueError, KeyError, httpx.HTTPError):
        log.warning("Could not reach the running instance", exc_info=True)
        return False
