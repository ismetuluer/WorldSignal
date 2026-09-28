"""Program updates from GitHub releases.

Every release on GitHub carries ``WorldSignal-<version>-windows.zip`` (the program folder, top folder
``WorldSignal``) and ``WorldSignal-<version>-windows.zip.sha256``. The updater:

1. asks GitHub for the latest release (at start-up, then every few hours; ``update.auto_check``);
2. downloads the zip into ``<data>\\updates\\<version>``, checks the SHA-256 and unpacks it;
3. on the user's word, starts the *new* program with ``--apply-update=<program folder>`` and quits.
   The new program waits for the old process to end, moves the old folder aside
   (``<folder>.old``), copies itself into place, starts the updated program and ends. If anything fails the
   old folder is put back. The updated program deletes the leftovers on its next start.

User data lives in the data folder, never in the program folder, so an update does not touch it; the
database migrates itself (with a copy made first) as on any start.
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .db import utc_now_iso
from .repo.settings import SettingsRepository

log = logging.getLogger(__name__)

# The public repository the releases come from.
UPDATE_REPO = "ismetuluer/WorldSignal"
# Tests and the end-to-end check point this at a local server.
API_BASE = os.environ.get("WORLDSIGNAL_UPDATE_API", "https://api.github.com")
FIRST_CHECK_DELAY = 90.0
CHECK_INTERVAL = timedelta(hours=6)
ASSET = re.compile(r"^WorldSignal-(\d+\.\d+\.\d+)-windows\.zip$")
MAX_DOWNLOAD = 600 * 1024 * 1024
RESULT_FILE = "update-result.json"
DRIVE_REMOTE = 4


def parse_version(text: str) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_network_path(path: Path) -> bool:
    text = str(path)
    if text.startswith("\\\\"):
        return True
    drive = os.path.splitdrive(text)[0]
    return os.name == "nt" and bool(drive) and ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == DRIVE_REMOTE


def _writable(folder: Path) -> bool:
    try:
        fd, name = tempfile.mkstemp(prefix=".ws-write-test-", dir=folder)
        os.close(fd)
        os.unlink(name)
        return True
    except OSError:
        return False


def program_dir() -> Path | None:
    """The folder of the packaged program; None when running from source."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None


class UpdateError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class Updater:
    def __init__(
        self,
        settings: SettingsRepository,
        data_root: Path,
        *,
        install_dir: Path | None = None,
        current: str = __version__,
        transport: httpx.BaseTransport | None = None,
        api_base: str = API_BASE,
        repo: str = UPDATE_REPO,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.settings = settings
        self.updates_dir = data_root / "updates"
        self.result_file = data_root / RESULT_FILE
        self.install_dir = install_dir if install_dir is not None else program_dir()
        self.current = current
        self.transport = transport
        self.api_base = api_base.rstrip("/")
        self.repo = repo
        self.clock = clock
        self._state: dict[str, Any] = {
            "state": "idle", "latest": None, "progress": None, "error": None, "checked_at": None,
        }
        self._staged: Path | None = None
        self._busy = False
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.last_update = self._read_result()

    # -- state --------------------------------------------------------------------------------
    def unsupported_reason(self) -> str | None:
        """Why this copy cannot update itself (the user then downloads the new zip by hand)."""
        if self.install_dir is None:
            return "dev"
        if is_network_path(self.install_dir):
            return "network"
        if not (_writable(self.install_dir) and _writable(self.install_dir.parent)):
            return "readonly"
        return None

    def status(self) -> dict[str, Any]:
        return {
            **self._state,
            "current": self.current,
            "unsupported": self.unsupported_reason(),
            "releases_url": f"https://github.com/{self.repo}/releases",
            "last_update": self.last_update,
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self.transport, timeout=httpx.Timeout(30, read=60), follow_redirects=True,
            headers={"User-Agent": f"WorldSignal/{self.current}", "Accept": "application/vnd.github+json"},
        )

    # -- check ----------------------------------------------------------------------------------
    def check(self) -> dict[str, Any] | None:
        """Ask GitHub for the latest release. Returns it when it is newer than this program."""
        self._state.update(state="checking", error=None)
        try:
            with self._client() as client:
                r = client.get(f"{self.api_base}/repos/{self.repo}/releases/latest")
            if r.status_code == 404:
                raise UpdateError("no_release")
            if r.status_code in (403, 429):
                raise UpdateError("rate_limited", r.text[:200])
            if r.status_code != 200:
                raise UpdateError("http_error", str(r.status_code))
            release = r.json()
        except httpx.HTTPError as exc:
            self._fail(UpdateError("offline", str(exc)))
            return None
        except (UpdateError, ValueError) as exc:
            self._fail(exc if isinstance(exc, UpdateError) else UpdateError("bad_answer", str(exc)))
            return None
        self._state["checked_at"] = utc_now_iso(self.clock())
        latest = self._describe(release)
        if latest is None or parse_version(latest["version"]) <= parse_version(self.current):  # type: ignore[operator]
            self._state.update(state="up_to_date", latest=latest)
            return None
        self._state.update(state="available", latest=latest)
        staged = self._staged_exe(latest["version"])
        if staged is not None:
            self._staged = staged
            self._state["state"] = "ready"
        return latest

    def _describe(self, release: dict[str, Any]) -> dict[str, Any] | None:
        assets = {a.get("name"): a for a in release.get("assets", [])}
        for name, asset in assets.items():
            m = ASSET.match(name or "")
            if not m:
                continue
            checksum = assets.get(f"{name}.sha256")
            return {
                "version": m.group(1),
                "tag": release.get("tag_name"),
                "notes": (release.get("body") or "").strip()[:20000],
                "published_at": release.get("published_at"),
                "page": release.get("html_url"),
                "size": asset.get("size"),
                "zip_url": asset.get("browser_download_url"),
                "sha_url": checksum.get("browser_download_url") if checksum else None,
            }
        return None

    # -- download -----------------------------------------------------------------------------
    def download(self) -> Path:
        latest = self._state.get("latest")
        if not latest or self._state["state"] not in ("available", "ready", "error"):
            raise UpdateError("nothing_to_download")
        if not latest.get("sha_url"):
            raise UpdateError("no_checksum")
        version = latest["version"]
        folder = self.updates_dir / version
        self._state.update(state="downloading", progress=0.0, error=None)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            package = folder / "package.zip"
            with self._client() as client:
                expected = client.get(latest["sha_url"]).raise_for_status().text.split()[0].strip().lower()
                digest = hashlib.sha256()
                done = 0
                partial = package.with_suffix(".partial")
                with client.stream("GET", latest["zip_url"]) as resp, partial.open("wb") as out:
                    resp.raise_for_status()
                    total = int(resp.headers.get("content-length") or latest.get("size") or 0)
                    for chunk in resp.iter_bytes(1024 * 256):
                        done += len(chunk)
                        if done > MAX_DOWNLOAD:
                            raise UpdateError("too_large")
                        digest.update(chunk)
                        out.write(chunk)
                        if total:
                            self._state["progress"] = round(done / total, 3)
            if digest.hexdigest() != expected:
                partial.unlink(missing_ok=True)
                raise UpdateError("checksum_mismatch")
            os.replace(partial, package)
            staging = folder / "staging"
            shutil.rmtree(staging, ignore_errors=True)
            with zipfile.ZipFile(package) as zf:
                for member in zf.namelist():  # nothing may land outside the staging folder
                    if member.startswith(("/", "\\")) or ".." in Path(member).parts:
                        raise UpdateError("bad_package", member)
                zf.extractall(staging)
            package.unlink(missing_ok=True)
            (folder / "release.json").write_text(json.dumps(latest, ensure_ascii=False), encoding="utf-8")
            (staging / ".complete").write_text(version, encoding="utf-8")
            exe = self._staged_exe(version)
            if exe is None:
                raise UpdateError("bad_package", "program or version file missing")
        except UpdateError as exc:
            self._fail(exc)
            raise
        except (httpx.HTTPError, OSError, zipfile.BadZipFile) as exc:
            err = UpdateError("download_failed", str(exc))
            self._fail(err)
            raise err from exc
        self._staged = exe
        self._state.update(state="ready", progress=1.0)
        log.info("Update %s downloaded and verified: %s", version, exe)
        return exe

    def _staged_exe(self, version: str) -> Path | None:
        staging = self.updates_dir / version / "staging"
        exe = staging / "WorldSignal" / "WorldSignal.exe"
        stamp = staging / "WorldSignal" / "version.txt"
        try:
            ok = (staging / ".complete").is_file() and exe.is_file() and stamp.read_text(encoding="utf-8").strip() == version
        except OSError:
            ok = False
        return exe if ok else None

    # -- apply --------------------------------------------------------------------------------
    def apply(self, quit_app: Callable[[], None]) -> None:
        """Start the new program to replace this one, then quit."""
        reason = self.unsupported_reason()
        if reason:
            raise UpdateError(f"unsupported_{reason}")
        if self._state["state"] != "ready" or self._staged is None:
            raise UpdateError("not_ready")
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        cmd = [str(self._staged), f"--apply-update={self.install_dir}", f"--after-pid={os.getpid()}"]
        log.info("Applying update: %s", cmd)
        subprocess.Popen(cmd, close_fds=True, creationflags=flags)  # noqa: S603 - our own verified program
        self._state["state"] = "applying"
        quit_app()

    def _fail(self, exc: UpdateError) -> None:
        log.warning("Update: %s", exc)
        self._state.update(state="error", error=exc.code, progress=None)

    def _read_result(self) -> dict[str, Any] | None:
        try:
            return json.loads(self.result_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def dismiss_result(self) -> None:
        self.result_file.unlink(missing_ok=True)
        self.last_update = None

    # -- background ---------------------------------------------------------------------------------
    def check_and_download(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            latest = self.check()
            if latest and self._state["state"] == "available" and self.unsupported_reason() is None \
                    and self.settings.get_preferences()["update.auto_download"]:
                try:
                    self.download()
                except UpdateError:
                    pass  # state says why; the next round or the button tries again
        finally:
            self._busy = False

    def wake(self) -> None:
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        await asyncio.to_thread(clean_leftovers, self.install_dir, self.updates_dir, self.current)
        try:
            await asyncio.wait_for(self._wake.wait(), FIRST_CHECK_DELAY)
        except TimeoutError:
            pass
        while True:
            self._wake.clear()
            if self.settings.get_preferences()["update.auto_check"]:
                try:
                    await asyncio.to_thread(self.check_and_download)
                except Exception:
                    log.exception("Update check failed")
            try:
                await asyncio.wait_for(self._wake.wait(), CHECK_INTERVAL.total_seconds())
            except TimeoutError:
                pass


# -- runs in the new program, before anything else ----------------------------------------------------------
def _retry(action: Callable[[], Any], attempts: int = 40) -> Any:
    for i in range(attempts):
        try:
            return action()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.5)
    return None


def apply_update(install_dir: Path, source_dir: Path, data_root: Path, wait: Callable[[], None]) -> bool:
    """Replace ``install_dir`` with ``source_dir``. True on success; on failure the old folder is back."""
    wait()
    old = install_dir.with_name(f"{install_dir.name}.old")
    result: dict[str, Any] = {"at": utc_now_iso(), "to": _version_of(source_dir), "from": _version_of(install_dir)}
    try:
        notes = json.loads((source_dir.parent.parent / "release.json").read_text(encoding="utf-8")).get("notes")
    except (OSError, ValueError):
        notes = None
    if not (install_dir / "WorldSignal.exe").is_file() or install_dir.resolve() == source_dir.resolve():
        log.error("Refusing to update %s from %s", install_dir, source_dir)
        return False
    shutil.rmtree(old, ignore_errors=True)
    try:
        _retry(lambda: install_dir.rename(old))
    except OSError as exc:
        log.error("Update: the program folder is in use: %s", exc)
        _write_result(data_root, {**result, "ok": False, "error": "in_use"})
        return False
    try:
        shutil.copytree(source_dir, install_dir)
    except OSError as exc:
        log.error("Update: copying failed, putting the old program back: %s", exc)
        shutil.rmtree(install_dir, ignore_errors=True)
        _retry(lambda: old.rename(install_dir))
        _write_result(data_root, {**result, "ok": False, "error": "copy_failed"})
        return False
    _write_result(data_root, {**result, "ok": True, "notes": notes})
    log.info("Updated %s from %s to %s", install_dir, result["from"], result["to"])
    return True


def _version_of(folder: Path) -> str | None:
    try:
        return (folder / "version.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _write_result(data_root: Path, result: dict[str, Any]) -> None:
    try:
        tmp = data_root / f"{RESULT_FILE}.tmp"
        tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, data_root / RESULT_FILE)
    except OSError:
        log.exception("Could not record the update result")


def clean_leftovers(install_dir: Path | None, updates_dir: Path, current: str) -> None:
    """Remove the previous program folder and downloads that are not newer than this program."""
    if install_dir is not None:
        shutil.rmtree(install_dir.with_name(f"{install_dir.name}.old"), ignore_errors=True)
    if not updates_dir.is_dir():
        return
    mine = parse_version(current)
    for folder in updates_dir.iterdir():
        version = parse_version(folder.name)
        if version is None or mine is None or version <= mine:
            shutil.rmtree(folder, ignore_errors=True)
