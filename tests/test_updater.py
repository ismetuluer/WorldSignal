"""Program updates from GitHub releases (updater.py), with a fake GitHub and real folders."""

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import httpx
import pytest

from worldsignal import updater as upd
from worldsignal.updater import UpdateError, Updater, apply_update, clean_leftovers, parse_version

REPO = "someone/WorldSignal"
API = "https://api.example"


def program_zip(version: str, *, top: str = "WorldSignal", extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{top}/WorldSignal.exe", f"program {version}")
        zf.writestr(f"{top}/version.txt", version)
        zf.writestr(f"{top}/_internal/worldsignal/ui/index.html", "<html>")
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


class FakeGitHub:
    def __init__(self, version: str = "0.9.0", *, package: bytes | None = None, checksum: str | None = None,
                 status: int = 200, with_sha: bool = True) -> None:
        self.version = version
        self.package = package if package is not None else program_zip(version)
        self.checksum = checksum or hashlib.sha256(self.package).hexdigest()
        self.status = status
        self.with_sha = with_sha
        self.requests: list[str] = []

    def release(self) -> dict:
        name = f"WorldSignal-{self.version}-windows.zip"
        assets = [{"name": name, "size": len(self.package), "browser_download_url": f"https://dl.example/{name}"}]
        if self.with_sha:
            assets.append({"name": f"{name}.sha256", "browser_download_url": f"https://dl.example/{name}.sha256"})
        return {"tag_name": f"v{self.version}", "body": "- Yenilik: spor kaynakları", "html_url": "https://gh/rel",
                "published_at": "2026-09-28T10:00:00Z", "assets": assets}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(str(request.url))
        if request.url.host == "api.example":
            assert request.url.path == f"/repos/{REPO}/releases/latest"
            if self.status != 200:
                return httpx.Response(self.status, text="API rate limit exceeded")
            return httpx.Response(200, json=self.release())
        if request.url.path.endswith(".sha256"):
            return httpx.Response(200, text=f"{self.checksum}  WorldSignal-{self.version}-windows.zip\n")
        return httpx.Response(200, content=self.package)


@pytest.fixture
def install(tmp_path: Path) -> Path:
    folder = tmp_path / "Programs" / "WorldSignal"
    (folder / "_internal").mkdir(parents=True)
    (folder / "WorldSignal.exe").write_text("program 0.8.0")
    (folder / "version.txt").write_text("0.8.0")
    return folder


def make(settings, tmp_path, install, github: FakeGitHub, current: str = "0.8.0") -> Updater:
    return Updater(settings, tmp_path / "data", install_dir=install, current=current,
                   transport=httpx.MockTransport(github), api_base=API, repo=REPO)


def test_versions_compare_as_numbers():
    assert parse_version("v0.10.0") > parse_version("0.9.9")
    assert parse_version("0.8.0") == (0, 8, 0)
    assert parse_version("latest") is None


def test_new_release_is_found_downloaded_verified_and_unpacked(settings, tmp_path, install):
    github = FakeGitHub("0.9.0")
    u = make(settings, tmp_path, install, github)
    latest = u.check()
    assert latest["version"] == "0.9.0" and latest["notes"].startswith("- Yenilik")
    assert u.status()["state"] == "available" and u.status()["unsupported"] is None
    exe = u.download()
    assert exe.read_text() == "program 0.9.0"
    assert u.status()["state"] == "ready" and u.status()["progress"] == 1.0
    assert not list((tmp_path / "data" / "updates" / "0.9.0").glob("package.*"))  # the zip itself is not kept
    # A second check (e.g. next start) finds the download already in place.
    u2 = make(settings, tmp_path, install, github)
    u2.check()
    assert u2.status()["state"] == "ready"


def test_same_or_older_release_is_up_to_date(settings, tmp_path, install):
    u = make(settings, tmp_path, install, FakeGitHub("0.8.0"))
    assert u.check() is None and u.status()["state"] == "up_to_date"
    u = make(settings, tmp_path, install, FakeGitHub("0.7.9"))
    assert u.check() is None and u.status()["state"] == "up_to_date"


@pytest.mark.parametrize(("github", "code"), [
    (FakeGitHub(status=404), "no_release"),
    (FakeGitHub(status=403), "rate_limited"),
])
def test_github_problems_are_named(settings, tmp_path, install, github, code):
    u = make(settings, tmp_path, install, github)
    assert u.check() is None
    assert u.status()["state"] == "error" and u.status()["error"] == code


def test_offline_is_not_a_crash(settings, tmp_path, install):
    def down(request):
        raise httpx.ConnectError("no network")

    u = Updater(settings, tmp_path / "data", install_dir=install, current="0.8.0",
                transport=httpx.MockTransport(down), api_base=API, repo=REPO)
    assert u.check() is None and u.status()["error"] == "offline"


def test_corrupt_download_is_refused(settings, tmp_path, install):
    u = make(settings, tmp_path, install, FakeGitHub("0.9.0", checksum="0" * 64))
    u.check()
    with pytest.raises(UpdateError) as err:
        u.download()
    assert err.value.code == "checksum_mismatch" and u.status()["state"] == "error"
    assert not (tmp_path / "data" / "updates" / "0.9.0" / "staging").exists()


def test_release_without_checksum_is_not_downloaded(settings, tmp_path, install):
    u = make(settings, tmp_path, install, FakeGitHub("0.9.0", with_sha=False))
    u.check()
    with pytest.raises(UpdateError) as err:
        u.download()
    assert err.value.code == "no_checksum"


def test_package_that_writes_outside_its_folder_is_refused(settings, tmp_path, install):
    evil = program_zip("0.9.0", extra={"../../evil.txt": b"x"})
    u = make(settings, tmp_path, install, FakeGitHub("0.9.0", package=evil))
    u.check()
    with pytest.raises(UpdateError) as err:
        u.download()
    assert err.value.code == "bad_package"
    assert not (tmp_path / "evil.txt").exists()


def test_package_with_wrong_version_is_refused(settings, tmp_path, install):
    u = make(settings, tmp_path, install, FakeGitHub("0.9.0", package=program_zip("0.8.5")))
    u.check()
    with pytest.raises(UpdateError) as err:
        u.download()
    assert err.value.code == "bad_package"


def test_auto_download_follows_the_setting(settings, tmp_path, install):
    github = FakeGitHub("0.9.0")
    settings.set("update.auto_download", False)
    u = make(settings, tmp_path, install, github)
    u.check_and_download()
    assert u.status()["state"] == "available"
    settings.set("update.auto_download", True)
    u.check_and_download()
    assert u.status()["state"] == "ready"


def test_copies_that_cannot_update_themselves_say_why(settings, tmp_path, install, monkeypatch):
    assert Updater(settings, tmp_path, install_dir=None).unsupported_reason() == "dev"
    monkeypatch.setattr(upd, "is_network_path", lambda p: True)
    assert make(settings, tmp_path, install, FakeGitHub()).unsupported_reason() == "network"
    monkeypatch.setattr(upd, "is_network_path", lambda p: False)
    monkeypatch.setattr(upd, "_writable", lambda p: p != install)
    u = make(settings, tmp_path, install, FakeGitHub())
    assert u.unsupported_reason() == "readonly"
    u.check()
    u.download()  # downloading is fine; applying is not
    with pytest.raises(UpdateError) as err:
        u.apply(lambda: None)
    assert err.value.code == "unsupported_readonly"


def test_apply_starts_the_new_program_and_quits(settings, tmp_path, install, monkeypatch):
    started = []
    monkeypatch.setattr(upd.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    quits = []
    u = make(settings, tmp_path, install, FakeGitHub("0.9.0"))
    with pytest.raises(UpdateError):
        u.apply(lambda: quits.append(1))  # nothing downloaded yet
    u.check()
    exe = u.download()
    u.apply(lambda: quits.append(1))
    assert started == [[str(exe), f"--apply-update={install}", f"--after-pid={os.getpid()}"]] and quits == [1]


# -- the replacement step (runs in the new program) ------------------------------------------------------
def staged(tmp_path: Path, version: str = "0.9.0") -> Path:
    folder = tmp_path / "data" / "updates" / version
    src = folder / "staging" / "WorldSignal"
    (src / "_internal").mkdir(parents=True)
    (src / "WorldSignal.exe").write_text(f"program {version}")
    (src / "version.txt").write_text(version)
    (folder / "release.json").write_text(json.dumps({"notes": "- Yenilik"}), encoding="utf-8")
    return src


def test_apply_update_replaces_the_program_and_records_it(tmp_path, install):
    (install / "_internal" / "old_only.dll").write_text("x")
    src = staged(tmp_path)
    waited = []
    assert apply_update(install, src, tmp_path / "data", wait=lambda: waited.append(1))
    assert waited == [1]
    assert (install / "WorldSignal.exe").read_text() == "program 0.9.0"
    assert not (install / "_internal" / "old_only.dll").exists()  # a clean copy, no stale files
    result = json.loads((tmp_path / "data" / "update-result.json").read_text(encoding="utf-8"))
    assert result == {**result, "ok": True, "from": "0.8.0", "to": "0.9.0", "notes": "- Yenilik"}
    # The next start of the new program clears the leftovers.
    clean_leftovers(install, tmp_path / "data" / "updates", "0.9.0")
    assert not install.with_name("WorldSignal.old").exists()
    assert not (tmp_path / "data" / "updates" / "0.9.0").exists()


def test_failed_copy_puts_the_old_program_back(tmp_path, install, monkeypatch):
    src = staged(tmp_path)

    def broken(a, b):
        Path(b).mkdir()
        (Path(b) / "half.txt").write_text("x")
        raise OSError("disk full")

    monkeypatch.setattr(upd.shutil, "copytree", broken)
    assert not apply_update(install, src, tmp_path / "data", wait=lambda: None)
    assert (install / "WorldSignal.exe").read_text() == "program 0.8.0" and not (install / "half.txt").exists()
    assert json.loads((tmp_path / "data" / "update-result.json").read_text())["error"] == "copy_failed"


def test_folder_in_use_is_left_alone(tmp_path, install, monkeypatch):
    src = staged(tmp_path)
    monkeypatch.setattr(upd.time, "sleep", lambda s: None)

    def locked(self, target):
        raise PermissionError("in use")

    monkeypatch.setattr(Path, "rename", locked)
    assert not apply_update(install, src, tmp_path / "data", wait=lambda: None)
    monkeypatch.undo()
    assert (install / "WorldSignal.exe").read_text() == "program 0.8.0"
    assert json.loads((tmp_path / "data" / "update-result.json").read_text())["error"] == "in_use"


def test_apply_refuses_nonsense(tmp_path, install):
    assert not apply_update(tmp_path / "nowhere", staged(tmp_path), tmp_path / "data", wait=lambda: None)
    assert not apply_update(install, install, tmp_path / "data", wait=lambda: None)


def test_newer_downloads_survive_the_cleanup(tmp_path):
    updates = tmp_path / "updates"
    for v in ("0.8.0", "0.9.0", "junk"):
        (updates / v).mkdir(parents=True)
    clean_leftovers(None, updates, "0.8.5")
    assert [p.name for p in updates.iterdir()] == ["0.9.0"]


def test_update_api(tmp_path, install, monkeypatch):
    from fastapi.testclient import TestClient

    from worldsignal.api.app import create_app
    from worldsignal.bootstrap import build_context
    from worldsignal.paths import DataPaths

    paths = DataPaths(tmp_path / "apidata").ensure()
    ctx = build_context(paths, "tok", None, run_collector=False)
    github = FakeGitHub("0.9.0")
    ctx.updater = Updater(ctx.settings, paths.root, install_dir=install, current="0.8.0",
                          transport=httpx.MockTransport(github), api_base=API, repo=REPO)
    started = []
    monkeypatch.setattr(upd.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    h = {"X-WorldSignal-Token": "tok"}
    with TestClient(create_app(ctx)) as client:
        assert client.get("/api/update", headers=h).json()["state"] == "idle"
        assert client.post("/api/update/check", headers=h).json()["latest"]["version"] == "0.9.0"
        assert client.post("/api/update/download", headers=h).json()["state"] == "ready"
        r = client.post("/api/update/apply", headers=h)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "update_needs_window"  # no window in tests
        quits = []
        ctx.quit = lambda: quits.append(1)
        assert client.post("/api/update/apply", headers=h).json() == {"ok": True}
        assert quits == [1] and started
        assert client.patch("/api/settings", headers=h, json={"update.auto_check": False}).status_code == 200
