"""The extension API: pairing, the key, Host/Origin checks, the job loop."""

import base64
import hashlib
import hmac
from datetime import UTC, datetime

from test_api import H, client, ctx  # noqa: F401  (fixtures)
from test_fulltext import article_page

HOST = {"host": "127.0.0.1:47821"}
NONCE = "n0nce-ABCdef_123456"


def pair(client):
    code = client.get("/api/extension", headers=H).json()["code"]
    return {**HOST, "X-WorldSignal-Extension": code}


def queue_browser_job(ctx):
    from test_api import add_articles
    add_articles(ctx)
    beta = next(s for s in ctx.sources.list_sources() if s["slug"] == "beta")
    ctx.sources.update_source(beta["id"], {"fulltext_mode": "browser"})
    ctx.settings.set_many({"fulltext.browser_night_rest": False})
    article_id = ctx.db.conn.execute("SELECT id FROM articles ORDER BY id LIMIT 1").fetchone()[0]
    ctx.fulltext.request(article_id)
    return article_id


def test_hello_needs_no_key_but_everything_else_does(client):
    assert client.get(f"/api/ext/hello?nonce={NONCE}", headers=HOST).json()["app"] == "worldsignal"
    assert client.post("/api/ext/next", headers=HOST).status_code == 401
    assert client.post("/api/ext/next", headers={**HOST, "X-WorldSignal-Extension": "wrong"}).status_code == 401


def expected_proof(key: str, port: int, nonce: str) -> str:
    """The extension's side, written independently: HMAC-SHA256 over "worldsignal-hello:<port>:<nonce>", base64url."""
    mac = hmac.new(key.encode(), f"worldsignal-hello:{port}:{nonce}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")


def test_hello_proves_the_program_holds_the_key_without_revealing_it(client):
    code = client.get("/api/extension", headers=H).json()["code"]
    r = client.get(f"/api/ext/hello?nonce={NONCE}", headers=HOST)
    # The test server's port is unknown (ctx.port 0): the Host header's port is signed.
    assert r.status_code == 200 and r.json()["proof"] == expected_proof(code, 47821, NONCE)
    assert code not in r.text
    other = client.get("/api/ext/hello?nonce=another-nonce-0123456789", headers=HOST).json()["proof"]
    assert other == expected_proof(code, 47821, "another-nonce-0123456789") and other != r.json()["proof"]
    renewed = client.post("/api/extension/code", headers=H).json()["code"]
    assert client.get(f"/api/ext/hello?nonce={NONCE}", headers=HOST).json()["proof"] == expected_proof(renewed, 47821, NONCE)


def test_hello_signs_the_port_the_program_listens_on_not_the_one_asked(client, ctx):
    """A program on 47821 relaying the question to World Signal on 47822 gets a proof for 47822: useless on 47821."""
    code = client.get("/api/extension", headers=H).json()["code"]
    ctx.port = 47822
    relayed = client.get(f"/api/ext/hello?nonce={NONCE}", headers={"host": "127.0.0.1:47821"}).json()["proof"]
    assert relayed == expected_proof(code, 47822, NONCE)
    assert relayed != expected_proof(code, 47821, NONCE)


def test_hello_has_no_proof_without_a_known_port(client, ctx):
    client.get("/api/extension", headers=H)
    assert client.get(f"/api/ext/hello?nonce={NONCE}", headers={"host": "127.0.0.1"}).json()["proof"] is None


def test_hello_proof_known_vector():
    from worldsignal.api.extension import hello_proof

    # The same vectors are checked against WebCrypto in frontend/src/test/extension.test.ts.
    assert hello_proof("k", 47821, "0123456789abcdef") == "rdSBGxEAtL9JkzpscnOm4YrFJY4-AWA6ZUk1EtgwHR4"
    assert hello_proof("k", 47822, "0123456789abcdef") == "pgxJtxNdNVZgfjaZwU_6Yt2l3QZJTXGZQOzYCfzB1hU"
    assert hello_proof("k", 47821, "0123456789abcdef") == expected_proof("k", 47821, "0123456789abcdef")


def test_hello_has_no_proof_before_a_key_exists(client, ctx):
    assert ctx.keys.get("extension") is None
    assert client.get(f"/api/ext/hello?nonce={NONCE}", headers=HOST).json()["proof"] is None


def test_hello_refuses_a_bad_nonce(client):
    for bad in ("", "short", "x" * 65, "has spaces in it ok?", "ğüşiöç-ğüşiöç-ğüşiöç", "a/b+c=d0123456789"):
        assert client.get("/api/ext/hello", headers=HOST, params={"nonce": bad}).status_code == 422, bad
    assert client.get("/api/ext/hello", headers=HOST).status_code == 422
    assert client.get("/api/ext/hello", headers=HOST, params={"nonce": "a" * 64}).status_code == 200
    assert client.get("/api/ext/hello", headers=HOST, params={"nonce": "a" * 16}).status_code == 200


def test_the_code_is_stable_until_renewed(client):
    first = client.get("/api/extension", headers=H).json()["code"]
    assert client.get("/api/extension", headers=H).json()["code"] == first and len(first) >= 40
    renewed = client.post("/api/extension/code", headers=H).json()["code"]
    assert renewed != first
    assert client.post("/api/ext/next", headers={**HOST, "X-WorldSignal-Extension": first}).status_code == 401


def test_web_pages_cannot_use_the_extension_api(client):
    keyed = pair(client)
    assert client.post("/api/ext/next", headers={**keyed, "origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/ext/next", headers={**keyed, "host": "evil.example"}).status_code == 403
    ok = client.post("/api/ext/next", headers={**keyed, "origin": "chrome-extension://abcdefghijklmnop"})
    assert ok.status_code == 200


def test_a_job_round_trip(client, ctx):
    article_id = queue_browser_job(ctx)
    keyed = pair(client)
    job = client.post("/api/ext/next", headers=keyed).json()
    assert job["article_id"] == article_id
    done = client.post("/api/ext/result", headers=keyed,
                       json={"lease": job["lease"], "final_url": job["url"], "html": article_page()}).json()
    assert done["status"] == "done" and ctx.fulltext.get(article_id)["method"] == "extension"
    assert client.get("/api/extension", headers=H).json()["status"]["read_today"] == 1


def test_the_pages_http_status_is_used(client, ctx):
    article_id = queue_browser_job(ctx)
    keyed = pair(client)
    job = client.post("/api/ext/next", headers=keyed).json()
    r = client.post("/api/ext/result", headers=keyed,
                    json={"lease": job["lease"], "final_url": job["url"], "html": "<p>Forbidden</p>", "status": 403})
    assert r.json() == {"status": "failed", "error": "http_403"}
    assert ctx.fulltext.get(article_id)["error_code"] == "http_403"
    source_id = ctx.db.conn.execute("SELECT source_id FROM articles WHERE id = ?", (article_id,)).fetchone()[0]
    assert source_id in [p["id"] for p in ctx.fulltext.paused_sources(datetime.now(UTC))]


def test_an_implausible_status_is_ignored(client, ctx):
    article_id = queue_browser_job(ctx)
    keyed = pair(client)
    for bad in (99, 600, -1, "403", True, 403.5, None):
        ctx.db.conn.execute("DELETE FROM article_fulltext")  # forget the previous round (and the site's pace)
        ctx.db.conn.commit()
        ctx.fulltext.request(article_id)
        job = client.post("/api/ext/next", headers=keyed).json()
        assert job.get("lease"), bad
        r = client.post("/api/ext/result", headers=keyed,
                        json={"lease": job["lease"], "final_url": job["url"], "html": article_page(), "status": bad})
        assert r.status_code == 200 and r.json()["status"] == "done", bad
        assert ctx.fulltext.get(article_id)["status"] == "done"


def test_resume_and_test_end_the_extensions_rest_for_the_site(client, ctx):
    article_id = queue_browser_job(ctx)
    source_id = ctx.db.conn.execute("SELECT source_id FROM articles WHERE id = ?", (article_id,)).fetchone()[0]
    keyed = pair(client)
    job = client.post("/api/ext/next", headers=keyed).json()
    for route in (f"/api/fulltext/sources/{source_id}/resume", f"/api/fulltext/sites/{source_id}/test"):
        assert job.get("lease"), route
        client.post("/api/ext/result", headers=keyed, json={"lease": job["lease"], "error": "tab_closed"})
        assert client.post("/api/ext/next", headers=keyed).json()["reason"] == "cooldown"
        assert client.post(route, headers=H).status_code == 200
        job = client.post("/api/ext/next", headers=keyed).json()
    assert job.get("lease")


def test_unknown_lease_is_rejected(client, ctx):
    queue_browser_job(ctx)
    keyed = pair(client)
    r = client.post("/api/ext/result", headers=keyed, json={"lease": "from-a-previous-run", "html": "<p>x</p>"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "unknown_lease"


def test_result_validation(client, ctx):
    queue_browser_job(ctx)
    keyed = pair(client)
    job = client.post("/api/ext/next", headers=keyed).json()
    assert client.post("/api/ext/result", headers=keyed, json={"lease": job["lease"], "error": "boom"}).status_code == 422
    huge = "x" * (8_000_001)
    assert client.post("/api/ext/result", headers=keyed, json={"lease": job["lease"], "html": huge}).status_code == 422


def test_a_page_too_large_is_refused_and_closes_the_lease(client, ctx):
    article_id = queue_browser_job(ctx)
    keyed = pair(client)
    job = client.post("/api/ext/next", headers=keyed).json()
    r = client.post("/api/ext/result", headers=keyed, json={"lease": job["lease"], "html": "x" * 8_000_001})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_large"
    ft = ctx.fulltext.get(article_id)
    assert ft["attempts"] == 1 and ft["error_code"] == "too_large"
    assert client.post("/api/ext/next", headers=keyed).json()["reason"] != "busy"  # the queue is not held up
    again = client.post("/api/ext/result", headers=keyed, json={"lease": job["lease"], "html": article_page()})
    assert again.status_code == 409
    assert client.post("/api/ext/result", headers=keyed, json={"lease": job["lease"], "error": "too_large"}).status_code == 422


def test_a_malformed_key_or_lease_is_refused_not_a_server_error(client, ctx):
    queue_browser_job(ctx)
    keyed = pair(client)
    assert client.post("/api/ext/next", headers={**HOST, "X-WorldSignal-Extension": "ключ".encode()}).status_code == 401  # raw UTF-8 bytes
    client.post("/api/ext/next", headers=keyed)  # a lease is held now
    body = '{"lease": "\\ud800", "html": "<p>x</p>"}'  # a lone surrogate is valid JSON
    r = client.post("/api/ext/result", headers={**keyed, "content-type": "application/json"}, content=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "unknown_lease"
    long_lease = client.post("/api/ext/result", headers=keyed, json={"lease": "x" * 101, "html": "<p>x</p>"})
    assert long_lease.status_code == 409
    too_long = client.post("/api/ext/result", headers=keyed, json={"lease": "x", "final_url": "u" * 2001})
    assert too_long.status_code == 422


def test_the_pairing_code_never_appears_in_settings_or_the_key_status(client):
    code = client.get("/api/extension", headers=H).json()["code"]
    assert code not in client.get("/api/settings", headers=H).text
    assert code not in client.get("/api/ai/keys", headers=H).text


def test_the_ui_endpoints_need_the_session_token(client):
    assert client.get("/api/extension").status_code == 401
    assert client.post("/api/extension/code").status_code == 401
    info = client.get("/api/extension", headers=H).json()
    assert info["port"] == 0 and info["fixed_port"] is False and info["status"]["connected"] is False


def test_sign_in_opens_the_users_own_browser_in_extension_mode(client, ctx, monkeypatch):
    from pathlib import Path

    from worldsignal.api import app as app_module
    from worldsignal.fulltext.fetch import BrowserInfo

    opened = []
    monkeypatch.setattr(app_module, "browser_for", lambda p: BrowserInfo("Brave", Path("brave.exe"), Path("p")))
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda args, **k: opened.append(args))
    monkeypatch.setattr(app_module, "open_login_window", lambda *a: opened.append("own-profile"))
    ctx.settings.set("fulltext.enabled", True)
    assert client.post("/api/fulltext/login", headers=H, json={"url": "https://www.wsj.com/"}).status_code == 200
    assert opened == [["brave.exe", "https://www.wsj.com/"]]


def test_sign_in_opens_the_programs_own_profile_when_the_extension_lives_there(client, ctx, monkeypatch):
    from pathlib import Path

    from worldsignal.api import app as app_module
    from worldsignal.fulltext.fetch import BrowserInfo

    opened = []
    monkeypatch.setattr(app_module, "browser_for", lambda p: BrowserInfo("Brave", Path("brave.exe"), Path("p")))
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda args, **k: opened.append(args))
    monkeypatch.setattr(app_module, "open_login_window", lambda *a: opened.append(("own-profile", a[2])))
    ctx.settings.set("extension.profile", "own")
    assert client.post("/api/fulltext/login", headers=H, json={"url": "https://www.wsj.com/"}).status_code == 200
    assert opened == [("own-profile", "https://www.wsj.com/")]
    opened.clear()
    assert client.post("/api/extension/profile/open", headers=H).json() == {"status": "opened"}
    assert opened == [("own-profile", "chrome://extensions")]  # the page where the extension is loaded, once


def test_status_tells_whether_the_extension_reads_and_is_connected(client, ctx):
    block = client.get("/api/status", headers=H).json()["extension"]
    assert block["active"] is True and block["connected"] is False and block["warn"] is False  # just started: no warning
    ctx.settings.set("fulltext.enabled", False)
    assert client.get("/api/status", headers=H).json()["extension"]["active"] is False


def test_status_has_no_extension_block_without_a_bridge(client, ctx):
    ctx.bridge = None
    assert client.get("/api/status", headers=H).json()["extension"] is None


def test_open_extension_dir(client, monkeypatch, tmp_path):
    from worldsignal.api import app as app_module

    opened = []
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda args, **k: opened.append(args))
    monkeypatch.setattr(app_module, "extension_dir", lambda: tmp_path)
    assert client.post("/api/app/open-extension-dir", headers=H).json() == {"ok": True}
    assert opened == [["explorer", str(tmp_path)]]
    monkeypatch.setattr(app_module, "extension_dir", lambda: None)
    r = client.post("/api/app/open-extension-dir", headers=H)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "no_extension_dir"
    assert client.post("/api/app/open-extension-dir").status_code == 401


def test_extension_dir_is_next_to_the_program_or_in_the_repository(monkeypatch, tmp_path):
    import sys

    from worldsignal import paths

    found = paths.extension_dir()
    assert found is not None and (found / "manifest.json").is_file()
    program = tmp_path / "WorldSignal"
    program.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(program / "WorldSignal.exe"))
    assert paths.extension_dir() is None
    (program / "extension").mkdir()
    assert paths.extension_dir() == program / "extension"


def test_sign_in_in_extension_mode_refuses_a_stored_homepage_that_is_not_a_web_page(client, ctx, monkeypatch):
    from pathlib import Path

    from worldsignal.api import app as app_module
    from worldsignal.fulltext.fetch import BrowserInfo

    opened = []
    monkeypatch.setattr(app_module, "browser_for", lambda p: BrowserInfo("Brave", Path("brave.exe"), Path("p")))
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda args, **k: opened.append(args))
    ctx.settings.set("fulltext.enabled", True)
    source = ctx.sources.list_sources()[0]
    for bad in ("file:///C:/Windows/System32/calc.exe", "--utility-sub-type=x", "javascript:alert(1)", "ftp://x.example/"):
        ctx.db.conn.execute("UPDATE sources SET homepage = ? WHERE id = ?", (bad, source["id"]))
        ctx.db.conn.commit()
        r = client.post("/api/fulltext/login", headers=H, json={"source_id": source["id"]})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "bad_url", bad
    assert opened == []
    ctx.db.conn.execute("UPDATE sources SET homepage = 'https://www.wsj.com/' WHERE id = ?", (source["id"],))
    ctx.db.conn.commit()
    assert client.post("/api/fulltext/login", headers=H, json={"source_id": source["id"]}).status_code == 200
    assert opened == [["brave.exe", "https://www.wsj.com/"]]
    opened.clear()
    assert client.post("/api/fulltext/login", headers=H, json={}).status_code == 200  # about:blank
    assert opened == [["brave.exe", "about:blank"]]


def test_the_extension_reports_its_version_and_an_old_copy_is_flagged(client, ctx):
    from worldsignal.fulltext.bridge import EXTENSION_VERSION as __version__
    keyed = pair(client)
    assert client.get("/api/extension", headers=H).json()["status"]["outdated"] is False  # never seen: no warning
    client.post("/api/ext/next", headers=keyed)  # an old copy says nothing
    s = client.get("/api/extension", headers=H).json()["status"]
    assert s["version"] is None and s["outdated"] is True
    client.post("/api/ext/next", headers={**keyed, "X-WorldSignal-Extension-Version": __version__})
    s = client.get("/api/extension", headers=H).json()["status"]
    assert s["version"] == __version__ and s["outdated"] is False
    client.post("/api/ext/next", headers={**keyed, "X-WorldSignal-Extension-Version": "<script>"})
    assert client.get("/api/extension", headers=H).json()["status"]["version"] is None  # junk is not echoed
