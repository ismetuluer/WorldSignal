# World Signal Browser Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subscription-site articles are read autonomously in the user's own Brave/Chrome by a World Signal MV3
extension; the program decides what and when, the extension only opens, reads and returns the page.

**Architecture:** The program keeps the queue and the human pace (`repo.fulltext.next_job` + `BrowserPace`). A new
`fulltext.bridge.ExtensionBridge` hands one job at a time to the extension under a 5-minute lease and records the
returned HTML through the same `fulltext.outcome.record_page` the background worker uses. The extension (plain JS, no
build) polls `/api/ext/next`, opens the page in a minimized window of the user's browser, scrolls like a reader,
posts the HTML to `/api/ext/result`. A setting `fulltext.reader` (`automation` | `extension`) decides who reads the
sources whose full-text mode is "browser"; no database migration.

**Tech Stack:** Python 3.12, FastAPI, SQLite; Chrome Manifest V3 (ES modules); React 19 + TypeScript; pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-10-01-tarayici-eklentisi-design.md`

## Global Constraints

- CAPTCHAs / robot checks are never solved; a `bot_check` page pauses the site (existing escalation), nothing else.
- No fingerprint changes, no automation flags in the user's browser; the program starts it only "normally".
- Human pace stays: `fulltext.browser_gap_min` (20), `fulltext.browser_per_day` (15), night rest 00–07, working hours.
- Full texts never go into outputs; the pairing key is never logged.
- `/api/ext/*` accepts only Host `127.0.0.1`/`localhost`, rejects web-page Origins (`http://`, `https://`), compares the
  key with `hmac.compare_digest`, HTML at most 8 MB.
- Fixed ports for the extension: 47821–47830, tried in order; otherwise a random port and a UI warning.
- Lease 5 minutes; the extension's own errors (`tab_closed`, `load_failed`, `timeout`, `script_failed`) cost no attempt.
- No fallback to the automation browser while `fulltext.reader == "extension"`.
- All UI text from `frontend/src/i18n/tr.ts` and `en.ts`; extension text from `extension/_locales/{tr,en}`.
- Version 0.14.0; CHANGELOG.md and CHANGELOG.en.md both; README.md and README.en.md both.
- Files on this machine have mixed CRLF/LF: edit with byte-aware scripts or the Edit tool, never `sed -i`; check
  `git show --shortstat` after each commit for whole-file flips.

## Review Focus

1. The user closes the reading window or the tab while a page is open → the article stays pending with its attempt
   unchanged, the next job comes after the lease (Task 3 test `test_extension_error_costs_nothing`).
2. The extension dies mid-read (browser closed) → the lease expires after 5 minutes and the article returns to the
   queue without losing an attempt (Task 3 `test_expired_lease_returns_the_job`).
3. A web page in the user's browser tries `fetch("http://127.0.0.1:47821/api/ext/next")` → refused even with a valid
   key, because of its Origin (Task 4 `test_web_pages_cannot_use_the_extension_api`).
4. The program restarts and the extension posts a result for a lease the new process never gave → 409, no crash, no
   write (Task 4 `test_unknown_lease_is_rejected`).
5. A page that is a "Subscribe to read" barrier (like the FT clip of 2026-10-01) → stored as `paywall`, site paused,
   never as text (Task 1 `test_paywall_page_is_a_failure_not_text`).

---

### Task 1: One place that records a fetched page

**Files:**
- Create: `src/worldsignal/fulltext/outcome.py`
- Modify: `src/worldsignal/fulltext/worker.py` (step: lines that call `extract`, `store_text`, `request_translation`,
  `store_failure`)
- Test: `tests/test_fulltext_outcome.py`

**Interfaces:**
- Produces: `record_page(repo: FullTextRepository, job: FullTextJob, page: Page, prefs: dict, now: datetime,
  on_translation_queued: Callable[[], None], method: str | None = None) -> Outcome`;
  `Outcome(ok: bool, code: str | None, status: str)` (`status`: done | pending | failed | blocked).

- [ ] **Step 1: Write the failing tests**

```python
"""record_page: the single path from a fetched page to the database (worker and extension)."""

from datetime import UTC, datetime

from test_fulltext import article_page, html, world  # noqa: F401  (world is a fixture)
from worldsignal.fulltext.fetch import Page
from worldsignal.fulltext.outcome import record_page

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def job_for(world, key):
    repo = world["repo"]
    repo.request(world["ids"][key])
    return repo.next_job(NOW, 99)


def test_text_is_stored_and_translation_queued_when_asked(world):
    world["settings"].set("fulltext.translate", True)
    job = job_for(world, "a2")
    woken = []
    out = record_page(world["repo"], job, Page(200, article_page(), job.url), world["settings"].get_preferences(), NOW,
                      lambda: woken.append(1), method="extension")
    ft = world["repo"].get(job.article_id)
    assert out.ok and out.status == "done" and ft["method"] == "extension" and "Hürmüz" in ft["text"]
    assert ft["translate_status"] == "pending" and woken == [1]


def test_paywall_page_is_a_failure_not_text(world):
    job = job_for(world, "a2")
    barrier = html("<p>Kısa giriş.</p><p>Subscribe to continue reading. Already a subscriber? Log in.</p>")
    out = record_page(world["repo"], job, Page(200, barrier, job.url), {}, NOW, lambda: None)
    ft = world["repo"].get(job.article_id)
    assert not out.ok and out.code == "paywall" and ft["status"] == "failed" and ft["text"] is None


def test_bot_check_blocks_and_pauses_the_site(world):
    job = job_for(world, "a2")
    check = html("<p>Just a moment...</p><p>Checking your browser before accessing.</p>")
    out = record_page(world["repo"], job, Page(403, check, job.url), {}, NOW, lambda: None)
    assert out.status == "blocked" and world["repo"].paused_sources(NOW)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_fulltext_outcome.py -q`
Expected: FAIL — `ModuleNotFoundError: worldsignal.fulltext.outcome`. (If `world`/`html` are not importable from
`test_fulltext`, check its fixture name with `Grep "def world" tests/test_fulltext.py` and import that name.)

- [ ] **Step 3: Implement `outcome.py`**

```python
"""What becomes of a fetched article page: its text, or the reason it has none (one path for the background worker
and the browser extension)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..ai.languages import effective as ai_languages
from ..repo.fulltext import FullTextJob, FullTextRepository
from .extract import extract
from .fetch import Page


@dataclass
class Outcome:
    ok: bool
    code: str | None
    status: str  # done | pending | failed | blocked


def record_page(repo: FullTextRepository, job: FullTextJob, page: Page, prefs: dict[str, Any], now: datetime,
                on_translation_queued: Callable[[], None], method: str | None = None) -> Outcome:
    """Extract the article text and store it, or store the failure (pausing the site where that is wise)."""
    result = extract(page.html, page.final_url, page.status)
    if result.ok and result.text:
        repo.store_text(job.article_id, result.text, method or job.mode, now)
        if prefs.get("fulltext.translate") and prefs.get("ai.enabled", True):
            repo.request_translation(job.article_id, ai_languages(prefs))
            on_translation_queued()
        return Outcome(True, None, "done")
    code = result.error_code or "not_article"
    return Outcome(False, code, repo.store_failure(job, code, now))
```

- [ ] **Step 4: Use it in the worker.** In `FullTextWorker.step`, replace the block from `page = await self._fetch(...)`
  to the end of the success/failure branches with:

```python
        try:
            page = await self._fetch(job, prefs, browser)
        except FetchFailed as exc:
            if exc.local:
                return await self._local_failure(job, exc, previous)
            if exc.code == "browser_failed":
                log.warning("Browser failed on %s: %s", job.url, exc.detail)
            if job.mode == "browser":
                self._browser_failures = 0  # the browser did start: only this page failed
            status = await asyncio.to_thread(self.repo.store_failure, job, exc.code, self.clock())
            self._state.update(state="ok", last_error=exc.code, current_article_id=None)
            log.warning("Full text of article %s (%s) failed: %s -> %s", job.article_id, job.source_name, exc.code, status)
            return PAUSED_SECONDS if exc.code in ("profile_in_use", "browser_failed") else random.uniform(*PACE[job.mode])
        if job.mode == "browser":
            self._browser_failures = 0
        outcome = await asyncio.to_thread(record_page, self.repo, job, page, prefs, self.clock(),
                                          self.on_translation_queued)
        if outcome.ok:
            self._state.update(state="ok", last_error=None, last_done_at=utc_now_iso(self.clock()), current_article_id=None)
            log.info("Full text of article %s (%s, %s)", job.article_id, job.source_name, job.mode)
        else:
            self._state.update(state="ok", last_error=outcome.code, current_article_id=None)
            log.warning("Full text of article %s (%s) failed: %s -> %s", job.article_id, job.source_name,
                        outcome.code, outcome.status)
        low, high = PACE[job.mode]
        return random.uniform(low, high)
```

Remove the now unused `extract` and `ai_languages` imports from `worker.py` if nothing else uses them; add
`from .outcome import record_page`.

- [ ] **Step 5: Run all full-text tests**

Run: `.venv\Scripts\python -m pytest tests/test_fulltext.py tests/test_fulltext_outcome.py -q`
Expected: all PASS (the worker's behaviour is unchanged).

- [ ] **Step 6: Commit**

```bash
git add src/worldsignal/fulltext/outcome.py src/worldsignal/fulltext/worker.py tests/test_fulltext_outcome.py
git commit -m "Full text: one path from a fetched page to the database (record_page)"
```

---

### Task 2: Settings, pairing key storage, reader split and the paid-article queue

**Files:**
- Modify: `src/worldsignal/apikeys.py` (`NAMES`, `_read`, `set`)
- Modify: `src/worldsignal/repo/settings.py` (DEFAULTS)
- Modify: `src/worldsignal/api/app.py` (`SettingsPatch`: two fields)
- Modify: `src/worldsignal/repo/fulltext.py` (`_priority` boost, `enqueue(boost=)`, `next_job(modes=)`,
  `auto_candidates(paid=)`)
- Modify: `src/worldsignal/fulltext/worker.py` (modes by reader, paid enqueue)
- Test: `tests/test_extension_queue.py`

**Interfaces:**
- Produces: setting `fulltext.reader: "automation" | "extension"` (default `"automation"`), `fulltext.launch_browser:
  bool` (default `True`); `SecretStore.get/set/delete("extension")`; `next_job(..., modes: tuple[str, ...] = ("http",
  "browser"))`; `enqueue(article_ids, reason, boost: float = 0.0)`; `auto_candidates(..., paid: bool = False) ->
  {"notebook": [...], "auto": [...], "exclusive": [...], "paid": [...]}`; constants `EXCLUSIVE_BOOST = 0.5`,
  `PAID_BOOST = -0.5` in `repo/fulltext.py`.

- [ ] **Step 1: Write the failing tests**

```python
"""Who reads which full texts, and which paid reports are queued in extension mode."""

from datetime import UTC, datetime, timedelta

from test_fulltext import make_ft_worker, run, source_of, world  # noqa: F401
from worldsignal.apikeys import SecretStore
from worldsignal.repo.fulltext import EXCLUSIVE_BOOST, PAID_BOOST


def test_the_pairing_key_is_kept_apart_from_ai_keys(tmp_path):
    store = SecretStore(tmp_path / "secrets.json", protect=lambda b: b[::-1], unprotect=lambda b: b[::-1])
    store.set("extension", "k" * 43)
    store.set("gemini", "g")
    assert store.get("extension") == "k" * 43 and "extension" not in store.status()
    store.delete("extension")
    assert store.get("extension") is None and store.get("gemini") == "g"


def test_next_job_can_be_limited_to_one_mode(world):
    repo, ids = world["repo"], world["ids"]
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    repo.request(ids["a1"])
    repo.request(ids["a2"])
    now = datetime.now(UTC)
    assert repo.next_job(now, 99, modes=("http",)).article_id == ids["a2"]
    assert repo.next_job(now, 99, modes=("browser",)).article_id == ids["a1"]


def test_extension_mode_leaves_browser_sources_to_the_extension(world, tmp_path):
    repo, ids = world["repo"], world["ids"]
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    world["settings"].set("fulltext.reader", "extension")
    repo.request(ids["a1"])
    worker = make_ft_worker(world, tmp_path)
    run(worker.step())
    assert repo.get(ids["a1"])["status"] == "pending"  # untouched: no automation browser was started
    from test_fulltext import FakeSession
    assert FakeSession.instances == []


def test_paid_exclusives_come_before_other_paid_reports(world):
    repo, ids, db = world["repo"], world["ids"], world["db"]
    sid = source_of(world, "a1")
    world["sources"].update_source(sid, {"fulltext_mode": "browser"})
    with db.transaction() as c:
        c.execute("UPDATE articles SET title = 'Exclusive: Iran talks stall' WHERE id = ?", (ids["a1"],))
    since = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    picks = repo.auto_candidates(since, 999, 2, "2026-10-01", paid=True)
    assert ids["a1"] in picks["exclusive"] and ids["a1"] not in picks["paid"]
    assert repo.auto_candidates(since, 999, 2, "2026-10-01")["exclusive"] == []  # automation mode: not asked
    repo.enqueue(picks["paid"], "auto", boost=PAID_BOOST)
    repo.enqueue(picks["exclusive"], "auto", boost=EXCLUSIVE_BOOST)
    assert repo.next_job(datetime.now(UTC), 99, modes=("browser",)).article_id == ids["a1"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_extension_queue.py -q`
Expected: FAIL (`KeyError: 'extension'`, unexpected keyword `modes`, `paid`, missing `EXCLUSIVE_BOOST`).

- [ ] **Step 3: `apikeys.py`** — add after `PROVIDERS`:

```python
# Other secrets kept the same way: the browser extension's pairing key (fulltext/bridge.py).
NAMES = PROVIDERS + ("extension",)
```

In `_read` filter with `k in NAMES`; in `set` check `provider not in NAMES`. `status()` keeps `PROVIDERS` (the AI key
screen must not list the extension).

- [ ] **Step 4: Settings** — in `repo/settings.py` DEFAULTS after `"fulltext.visible"`:

```python
    "fulltext.reader": "automation",  # automation: World Signal's own browser | extension: the user's browser (0.14)
    "fulltext.launch_browser": True,  # extension mode: start the user's browser (no window) when it is closed
```

In `api/app.py` `SettingsPatch` after `fulltext_visible`:

```python
    fulltext_reader: Literal["automation", "extension"] | None = Field(None, alias="fulltext.reader")
    fulltext_launch_browser: bool | None = Field(None, alias="fulltext.launch_browser")
```

- [ ] **Step 5: Queue** — in `repo/fulltext.py`:

```python
# Extension mode reads every paid report it has time for; exclusives first, the rest after important stories.
EXCLUSIVE_BOOST = 0.5
PAID_BOOST = -0.5
# The full-text mode actually used for a source ('off' sources are read only on the user's request).
EFFECTIVE_MODE = ("(CASE WHEN s.fulltext_mode = 'off' THEN (CASE WHEN s.paywalled THEN 'browser' ELSE 'http' END) "
                  "ELSE s.fulltext_mode END)")


def _priority(reason: str, sort_at: str, boost: float = 0.0) -> float:
    epoch = datetime.strptime(sort_at, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    return (TIERS[reason] + boost) * 1e10 + epoch
```

`enqueue(self, article_ids, reason, boost: float = 0.0)` passes `boost` to `_priority`. `next_job(..., user_only=False,
modes: tuple[str, ...] = ("http", "browser"))`: build `modes_sql = f" AND {EFFECTIVE_MODE} IN ({','.join('?' * len(modes))})"`
— the query uses named parameters, so instead add named ones:

```python
        mode_names = {f"mode{i}": m for i, m in enumerate(modes)}
        mode_sql = f" AND {EFFECTIVE_MODE} IN ({', '.join(':' + k for k in mode_names)})"
```

append `mode_sql` after `pace_sql` and `**mode_names` to the parameters; replace the inline CASE inside `pace_sql`
with `EFFECTIVE_MODE`.

`auto_candidates(self, since_iso, min_score, per_story, today, paid: bool = False)`: keep the existing body; before
`return out` add:

```python
        out["exclusive"], out["paid"] = [], []
        if paid:
            from ..flags import is_exclusive  # flags imports nothing from repo

            rows = self.db.conn.execute(
                """SELECT a.id, a.title FROM articles a JOIN sources s ON s.id = a.source_id
                   WHERE s.enabled = 1 AND s.fulltext_mode = 'browser' AND a.sort_at >= ?
                     AND NOT EXISTS (SELECT 1 FROM article_fulltext f WHERE f.article_id = a.id)
                   ORDER BY a.sort_at DESC LIMIT 300""",
                (since_iso,),
            ).fetchall()
            taken = set(out["notebook"]) | set(out["auto"])
            for r in rows:
                if r["id"] not in taken:
                    out["exclusive" if is_exclusive(r["title"]) else "paid"].append(r["id"])
```

- [ ] **Step 6: Worker** — in `FullTextWorker.step`:

```python
        reader = prefs.get("fulltext.reader", "automation")
        if not resting:
            since = utc_now_iso(now - AUTO_WINDOW)
            picks = await asyncio.to_thread(
                self.repo.auto_candidates, since, float(prefs.get("fulltext.auto_min_score", 60)),
                int(prefs.get("fulltext.auto_per_story", 2)), self.today(), reader == "extension",
            )
            for reason in ("notebook", "auto"):
                await asyncio.to_thread(self.repo.enqueue, picks[reason], reason)
            await asyncio.to_thread(self.repo.enqueue, picks["exclusive"], "auto", EXCLUSIVE_BOOST)
            await asyncio.to_thread(self.repo.enqueue, picks["paid"], "auto", PAID_BOOST)
        # In extension mode the user's browser reads the "browser" sources (fulltext/bridge.py); never this one.
        modes = ("http",) if reader == "extension" else ("http", "browser")
        job = await asyncio.to_thread(self.repo.next_job, now, int(prefs.get("fulltext.per_site_hour", 4)),
                                      self.browser_pace(prefs, now), resting, modes)
```

Import `EXCLUSIVE_BOOST, PAID_BOOST` from `..repo.fulltext`. When `reader == "extension"` and `self._session` is
open, close it (`await self.close_browser()`) at the top of the step.

- [ ] **Step 7: Run tests**

Run: `.venv\Scripts\python -m pytest tests/test_extension_queue.py tests/test_fulltext.py tests/test_api.py -q`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add src/worldsignal/apikeys.py src/worldsignal/repo/settings.py src/worldsignal/api/app.py src/worldsignal/repo/fulltext.py src/worldsignal/fulltext/worker.py tests/test_extension_queue.py
git commit -m "Full text: reader setting, pairing key storage, paid reports and exclusives queued for the extension"
```

---

### Task 3: The bridge (leases, next, result, status)

**Files:**
- Create: `src/worldsignal/fulltext/bridge.py`
- Modify: `src/worldsignal/fulltext/worker.py` (make `browser_pace` a module function `browser_pace(prefs, now,
  local_zone)`; the method calls it)
- Test: `tests/test_extension_bridge.py`

**Interfaces:**
- Consumes: `record_page`, `Outcome` (Task 1); `next_job(modes=)`, `mark_attempt`, `release_attempt` (Task 2 / 0.13.4).
- Produces: `ExtensionBridge(repo, settings, *, resting, clock=..., local_zone=None)` with
  `next() -> dict`, `result(lease: str, *, html: str | None = None, final_url: str | None = None, error: str | None =
  None) -> dict`, `status() -> dict`, `silent_for() -> timedelta | None`, attribute `on_translation_queued`;
  constants `LEASE = timedelta(minutes=5)`, `EXTENSION_ERRORS = {"tab_closed", "load_failed", "timeout",
  "script_failed"}`; `UnknownLease(Exception)`.

- [ ] **Step 1: Write the failing tests**

```python
"""The extension's side of the queue: one job at a time under a lease, results through record_page."""

from datetime import UTC, datetime, timedelta

import pytest

from test_fulltext import article_page, html, source_of, world  # noqa: F401
from worldsignal.fulltext.bridge import LEASE, ExtensionBridge, UnknownLease


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

    def __call__(self):
        return self.now


@pytest.fixture
def bridge(world):
    world["settings"].set_many({"fulltext.reader": "extension", "fulltext.browser_night_rest": False})
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    world["repo"].request(world["ids"]["a1"])
    clock = Clock()
    b = ExtensionBridge(world["repo"], world["settings"], resting=lambda: False, clock=clock)
    b.clock_ = clock
    return b


def test_a_job_is_leased_once_and_its_text_stored(bridge, world):
    job = bridge.next()
    assert job["article_id"] == world["ids"]["a1"] and job["url"].startswith("http") and job["lease"]
    assert bridge.next()["reason"] == "busy"  # one page at a time
    out = bridge.result(job["lease"], html=article_page(), final_url=job["url"])
    ft = world["repo"].get(job["article_id"])
    assert out["status"] == "done" and ft["method"] == "extension"
    assert bridge.status()["read_today"] == 1 and bridge.status()["connected"]


def test_extension_error_costs_nothing(bridge, world):
    job = bridge.next()
    assert bridge.result(job["lease"], error="tab_closed") == {"status": "pending"}
    ft = world["repo"].get(job["article_id"])
    assert ft["status"] == "pending" and ft["attempts"] == 0 and ft["attempted_at"] is None


def test_expired_lease_returns_the_job(bridge, world):
    first = bridge.next()
    bridge.clock_.now += LEASE + timedelta(seconds=1)
    second = bridge.next()
    assert second["article_id"] == first["article_id"] and second["lease"] != first["lease"]
    assert world["repo"].get(first["article_id"])["attempts"] == 0
    with pytest.raises(UnknownLease):
        bridge.result(first["lease"], html=article_page())


def test_a_robot_check_pauses_the_site_and_is_not_retried(bridge, world):
    job = bridge.next()
    page = html("<p>Just a moment...</p><p>Checking your browser before accessing.</p>")
    assert bridge.result(job["lease"], html=page, final_url=job["url"])["status"] == "blocked"
    assert bridge.next()["reason"] == "idle"  # the site is paused; nothing else is queued


def test_waits_while_off_resting_or_at_night(world):
    world["settings"].set("fulltext.reader", "automation")
    b = ExtensionBridge(world["repo"], world["settings"], resting=lambda: True)
    assert b.next()["reason"] == "disabled"
    world["settings"].set("fulltext.reader", "extension")
    assert b.next()["reason"] == "resting"
    assert b.next()["wait_seconds"] >= 60
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_extension_bridge.py -q`
Expected: FAIL — `ModuleNotFoundError: worldsignal.fulltext.bridge`.

- [ ] **Step 3: Move `browser_pace` to a module function** in `worker.py`:

```python
def browser_pace(prefs: dict[str, Any], now: datetime, local_zone: tzinfo | None = None) -> BrowserPace:
    local = now.astimezone(local_zone)
    return BrowserPace(
        gap=timedelta(minutes=int(prefs.get("fulltext.browser_gap_min", 20))),
        user_gap=USER_GAP,
        per_day=int(prefs.get("fulltext.browser_per_day", 15)),
        day_start=local.replace(hour=0, minute=0, second=0, microsecond=0),
        resting=bool(prefs.get("fulltext.browser_night_rest", True)) and local.hour in NIGHT_HOURS,
    )
```

and make the method `return browser_pace(prefs, now, self.local_zone)`.

- [ ] **Step 4: Implement `bridge.py`**

```python
"""The browser extension's side of the full-text queue (decision 2026-10-01: subscription sites are read in the user's
own browser). The program decides what and when (the same queue and human pace as the background worker); the
extension asks for one page at a time, reads it in a minimized window and posts its HTML back. A job is lent under a
lease: a result for a lost lease is refused, an expired lease returns the job to the queue without costing it an
attempt, and so do the extension's own troubles (tab closed, page did not load)."""

from __future__ import annotations

import hmac
import logging
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from ..db import utc_now_iso
from ..repo.fulltext import FullTextJob, FullTextRepository
from ..repo.settings import SettingsRepository
from .fetch import Page
from .outcome import record_page
from .worker import browser_pace

log = logging.getLogger(__name__)

LEASE = timedelta(minutes=5)
CONNECTED_WITHIN = timedelta(minutes=3)
EXTENSION_ERRORS = {"tab_closed", "load_failed", "timeout", "script_failed"}
WAIT = {"disabled": 300, "resting": 300, "busy": 30, "idle": 60}


class UnknownLease(Exception):
    pass


@dataclass
class Lease:
    id: str
    job: FullTextJob
    previous: str | None
    until: datetime


class ExtensionBridge:
    def __init__(self, repo: FullTextRepository, settings: SettingsRepository, *, resting: Callable[[], bool],
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC), local_zone: tzinfo | None = None) -> None:
        self.repo = repo
        self.settings = settings
        self.resting = resting
        self.clock = clock
        self.local_zone = local_zone
        self.on_translation_queued: Callable[[], None] = lambda: None
        self._lock = threading.Lock()
        self._lease: Lease | None = None
        self.last_seen: datetime | None = None
        self.last_error: str | None = None
        self.last_source: str | None = None
        self._day = ""
        self._read_today = 0

    def _wait(self, reason: str) -> dict[str, Any]:
        return {"wait_seconds": WAIT[reason], "reason": reason}

    def next(self) -> dict[str, Any]:
        now = self.clock()
        self.last_seen = now
        prefs = self.settings.get_preferences()
        if not prefs.get("fulltext.enabled", True) or prefs.get("fulltext.reader") != "extension":
            return self._wait("disabled")
        with self._lock:
            if self._lease is not None:
                if self._lease.until > now:
                    return self._wait("busy")
                log.info("Extension lease for article %s expired", self._lease.job.article_id)
                self.repo.release_attempt(self._lease.job.article_id, self._lease.previous)
                self._lease = None
            resting = self.resting()
            job = self.repo.next_job(now, int(prefs.get("fulltext.per_site_hour", 4)),
                                     browser_pace(prefs, now, self.local_zone), resting, ("browser",))
            if job is None:
                return self._wait("resting" if resting else "idle")
            previous = self.repo.mark_attempt(job.article_id, now)
            self._lease = Lease(secrets.token_urlsafe(16), job, previous, now + LEASE)
            return {"lease": self._lease.id, "article_id": job.article_id, "url": job.url, "source": job.source_name}

    def result(self, lease: str, *, html: str | None = None, final_url: str | None = None,
               error: str | None = None) -> dict[str, Any]:
        now = self.clock()
        self.last_seen = now
        with self._lock:
            held = self._lease
            if held is None or not hmac.compare_digest(held.id, lease):
                raise UnknownLease(lease)
            self._lease = None
        job = held.job
        self.last_source = job.source_name
        if error is not None or not html:
            self.repo.release_attempt(job.article_id, held.previous)
            self.last_error = error or "load_failed"
            log.info("Extension could not read article %s: %s", job.article_id, self.last_error)
            return {"status": "pending"}
        outcome = record_page(self.repo, job, Page(None, html, final_url or job.url), self.settings.get_preferences(),
                              now, self.on_translation_queued, method="extension")
        self.last_error = outcome.code
        day = utc_now_iso(now)[:10]
        if day != self._day:
            self._day, self._read_today = day, 0
        if outcome.ok:
            self._read_today += 1
        log.info("Extension read article %s (%s): %s", job.article_id, job.source_name, outcome.status)
        return {"status": outcome.status, "error": outcome.code}

    def silent_for(self) -> timedelta | None:
        return None if self.last_seen is None else self.clock() - self.last_seen

    def status(self) -> dict[str, Any]:
        silent = self.silent_for()
        with self._lock:
            reading = self._lease.job.source_name if self._lease else None
        return {
            "connected": silent is not None and silent <= CONNECTED_WITHIN,
            "last_seen": utc_now_iso(self.last_seen) if self.last_seen else None,
            "read_today": self._read_today if self._day == utc_now_iso(self.clock())[:10] else 0,
            "reading": reading, "last_source": self.last_source, "last_error": self.last_error,
        }
```

- [ ] **Step 5: Run tests**

Run: `.venv\Scripts\python -m pytest tests/test_extension_bridge.py tests/test_fulltext.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/worldsignal/fulltext/bridge.py src/worldsignal/fulltext/worker.py tests/test_extension_bridge.py
git commit -m "Full text: extension bridge (leased jobs, results through record_page)"
```

---

### Task 4: The extension API and pairing

**Files:**
- Create: `src/worldsignal/api/extension.py`
- Modify: `src/worldsignal/api/app.py` (`AppContext.bridge`, `AppContext.port`; include the routers; lifespan wires
  `bridge.on_translation_queued = ctx.ai_worker.wake`)
- Modify: `src/worldsignal/bootstrap.py` (build the bridge with the same `WorkHours.resting`)
- Modify: `tests/test_api.py` fixture (`keys=SecretStore(tmp_path / "s.json", protect=bytes, unprotect=bytes)`,
  `bridge=ExtensionBridge(...)`)
- Test: `tests/test_extension_api.py`

**Interfaces:**
- Consumes: `ExtensionBridge`, `UnknownLease`, `EXTENSION_ERRORS` (Task 3); `SecretStore` "extension" (Task 2).
- Produces: HTTP `GET /api/ext/hello`, `POST /api/ext/next`, `POST /api/ext/result`, `GET /api/ext/status` (header
  `X-WorldSignal-Extension`); token-protected `GET /api/extension` → `{code, port, fixed_port, status}` and
  `POST /api/extension/code` → `{code}`; constant `EXTENSION_PORTS = range(47821, 47831)` in `api/extension.py`.

- [ ] **Step 1: Write the failing tests**

```python
"""The extension API: pairing, the key, Host/Origin checks, the job loop."""

from test_api import H, client, ctx  # noqa: F401  (fixtures)
from test_fulltext import article_page

HOST = {"host": "127.0.0.1:47821"}


def pair(client):
    code = client.get("/api/extension", headers=H).json()["code"]
    return {**HOST, "X-WorldSignal-Extension": code}


def queue_browser_job(ctx):
    from test_api import add_articles
    add_articles(ctx)
    beta = next(s for s in ctx.sources.list_sources() if s["slug"] == "beta")
    ctx.sources.update_source(beta["id"], {"fulltext_mode": "browser"})
    ctx.settings.set_many({"fulltext.reader": "extension", "fulltext.browser_night_rest": False})
    article_id = ctx.db.conn.execute("SELECT id FROM articles ORDER BY id LIMIT 1").fetchone()[0]
    ctx.fulltext.request(article_id)
    return article_id


def test_hello_needs_no_key_but_everything_else_does(client):
    assert client.get("/api/ext/hello", headers=HOST).json()["app"] == "worldsignal"
    assert client.post("/api/ext/next", headers=HOST).status_code == 401
    assert client.post("/api/ext/next", headers={**HOST, "X-WorldSignal-Extension": "wrong"}).status_code == 401


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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_extension_api.py -q`
Expected: FAIL (404 on `/api/extension`, missing fixture fields).

- [ ] **Step 3: Implement `api/extension.py`**

```python
"""HTTP side of the browser extension (fulltext/bridge.py).

``/api/ext/*`` is called by the extension with the pairing key in ``X-WorldSignal-Extension``; requests from web pages
(an ``http(s)://`` Origin) or for another host (DNS rebinding) are refused even with the key. ``/api/extension`` (the
program's own UI, session token) shows and renews the pairing code. The code is never logged.
"""

from __future__ import annotations

import hmac
import secrets
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .. import __version__
from ..fulltext.bridge import EXTENSION_ERRORS, UnknownLease

if TYPE_CHECKING:
    from .app import AppContext

EXTENSION_PORTS = range(47821, 47831)
KEY_NAME = "extension"
MAX_HTML = 8_000_000
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": ""})


class ResultBody(BaseModel):
    lease: str = Field(max_length=100)
    html: str | None = Field(None, max_length=MAX_HTML)
    final_url: str | None = Field(None, max_length=2000)
    error: str | None = None


def pairing_code(ctx: AppContext, renew: bool = False) -> str:
    if ctx.keys is None:
        raise _error(503, "unavailable")
    code = None if renew else ctx.keys.get(KEY_NAME)
    if not code:
        code = secrets.token_urlsafe(32)
        ctx.keys.set(KEY_NAME, code)
    return code


def extension_routers(ctx: AppContext, require_token: Any) -> tuple[APIRouter, APIRouter, APIRouter]:
    def from_extension(request: Request, x_worldsignal_extension: Annotated[str | None, Header()] = None) -> None:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        origin = request.headers.get("origin") or ""
        if host not in LOCAL_HOSTS or origin.startswith(("http://", "https://")):
            raise _error(403, "forbidden")
        key = ctx.keys.get(KEY_NAME) if ctx.keys is not None else None
        if not key or not x_worldsignal_extension or not hmac.compare_digest(x_worldsignal_extension, key):
            raise _error(401, "not_paired")

    def bridge():
        if ctx.bridge is None:
            raise _error(503, "unavailable")
        return ctx.bridge

    open_ = APIRouter(prefix="/api/ext")
    keyed = APIRouter(prefix="/api/ext", dependencies=[Depends(from_extension)])
    ui = APIRouter(prefix="/api/extension", dependencies=[Depends(require_token)])

    @open_.get("/hello")
    def hello() -> dict[str, str]:
        return {"app": "worldsignal", "version": __version__}

    @keyed.post("/next")
    def next_job() -> dict[str, Any]:
        return bridge().next()

    @keyed.post("/result")
    def result(body: ResultBody) -> dict[str, Any]:
        if body.error is not None and body.error not in EXTENSION_ERRORS:
            raise _error(422, "bad_error")
        try:
            return bridge().result(body.lease, html=body.html, final_url=body.final_url, error=body.error)
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
```

In `create_app`, before `app.include_router(public)`:

```python
    for router in extension_routers(ctx, require_token):
        app.include_router(router)
```

`AppContext`: add `bridge: ExtensionBridge | None = None` and `port: int = 0`. In `lifespan`, add
`if ctx.bridge is not None: ctx.bridge.on_translation_queued = ctx.ai_worker.wake`. Pydantic `max_length` on `html`
gives 422 for an oversized page (FastAPI's default validation error format: tests only check the status).

In `bootstrap.build_context` create `ExtensionBridge(fulltext_repo, settings, resting=work_hours.resting)` (use the
same `WorkHours` instance the workers get) and pass `bridge=` and the existing `keys=` to `AppContext`.

In `tests/test_api.py` `ctx` fixture add:

```python
        keys=SecretStore(tmp_path / "secrets.json", protect=bytes, unprotect=bytes),
        bridge=ExtensionBridge(FullTextRepository(db), settings, resting=lambda: False),
```

with imports `from worldsignal.apikeys import SecretStore` and `from worldsignal.fulltext.bridge import ExtensionBridge`.

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python -m pytest tests/test_extension_api.py tests/test_api.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/worldsignal/api/extension.py src/worldsignal/api/app.py src/worldsignal/bootstrap.py tests/test_api.py tests/test_extension_api.py
git commit -m "API: extension endpoints with pairing key, Host and Origin checks"
```

---

### Task 5: Fixed port and starting the user's browser

**Files:**
- Modify: `src/worldsignal/__main__.py` (`ServerThread` takes a list of ports; `server_ports(...)`; `ctx.port`)
- Create: `src/worldsignal/fulltext/launcher.py`
- Modify: `src/worldsignal/fulltext/bridge.py` (`async def watch_forever(self)`), `api/app.py` lifespan (task)
- Test: `tests/test_extension_launch.py`

**Interfaces:**
- Produces: `server_ports(cli_port: int, reader: str) -> list[int]`; `ServerThread(app, ports: list[int])`;
  `launcher.is_running(exe: Path, run=subprocess.run) -> bool`; `launcher.start_hidden(exe: Path, popen=subprocess.Popen)
  -> None`; `ExtensionBridge.launch_if_needed(find_browser, is_running, start) -> bool`; `SILENT_LAUNCH =
  timedelta(minutes=10)`, `LAUNCH_EVERY = timedelta(minutes=30)`.

- [ ] **Step 1: Write the failing tests**

```python
"""The extension finds the program on a fixed port; the program starts the user's browser when it is closed."""

import socket
from datetime import timedelta
from pathlib import Path

from test_extension_bridge import Clock
from test_fulltext import world  # noqa: F401
from worldsignal.__main__ import ServerThread, server_ports
from worldsignal.fulltext.bridge import ExtensionBridge
from worldsignal.fulltext.fetch import BrowserInfo
from worldsignal.fulltext.launcher import is_running


def test_ports_in_extension_mode():
    assert server_ports(0, "automation") == [0]
    assert server_ports(0, "extension") == [*range(47821, 47831), 0]
    assert server_ports(8765, "extension") == [8765]  # development: --port wins


def test_a_taken_port_is_skipped():
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    port = taken.getsockname()[1]
    try:
        server = ServerThread(lambda scope, receive, send: None, [port, 0])
        assert server.port not in (0, port)
        server.sock.close()
    finally:
        taken.close()


def test_is_running_reads_the_task_list():
    class Done:
        def __init__(self, out):
            self.stdout = out

    assert is_running(Path("C:/x/brave.exe"), run=lambda *a, **k: Done('"brave.exe","123","Console"'))
    assert not is_running(Path("C:/x/brave.exe"), run=lambda *a, **k: Done("INFO: No tasks are running"))


def test_the_browser_is_started_only_when_needed(world):
    world["settings"].set("fulltext.reader", "extension")
    clock = Clock()
    bridge = ExtensionBridge(world["repo"], world["settings"], resting=lambda: False, clock=clock)
    brave = BrowserInfo("Brave", Path("brave.exe"), Path("profile"))
    started = []
    launch = lambda: bridge.launch_if_needed(lambda p: brave, lambda exe: False, started.append)  # noqa: E731
    assert launch() and started == [brave.executable]  # never heard from the extension: start it
    assert not launch()  # not again within half an hour
    clock.now += timedelta(minutes=31)
    bridge.last_seen = clock.now - timedelta(minutes=2)
    assert not launch()  # the extension talks: nothing to do
    world["settings"].set("fulltext.launch_browser", False)
    bridge.last_seen = None
    clock.now += timedelta(hours=1)
    assert not launch()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python -m pytest tests/test_extension_launch.py -q`
Expected: FAIL (`ImportError: server_ports`, `launcher`).

- [ ] **Step 3: `__main__.py`**

```python
EXTENSION_PORTS = range(47821, 47831)  # same as api/extension.py; the extension looks for the program there


def server_ports(cli_port: int, reader: str) -> list[int]:
    """Ports to try, in order: the one given on the command line, else (extension mode) the fixed ones, else any."""
    if cli_port:
        return [cli_port]
    return [*EXTENSION_PORTS, 0] if reader == "extension" else [0]
```

Import `EXTENSION_PORTS` from `.api.extension` instead of repeating the range. `ServerThread.__init__(self, app,
ports: list[int])`:

```python
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        for i, port in enumerate(ports):
            try:
                self.sock.bind(("127.0.0.1", port))
                break
            except OSError:
                if i == len(ports) - 1:
                    raise
                self.sock.close()
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.port = self.sock.getsockname()[1]
```

In `main`: `reader = ctx.settings.get_preferences().get("fulltext.reader", "automation")`,
`server = ServerThread(app, server_ports(args.port, reader))`, then `ctx.port = server.port` before `server.start()`.

- [ ] **Step 4: `fulltext/launcher.py`**

```python
"""Starting the user's own browser for the extension: a normal start (no automation flags), without a window, only
when it is not running. The extension then opens its own minimized reading window."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any


def is_running(exe: Path, run: Callable[..., Any] = subprocess.run) -> bool:
    out = run(["tasklist", "/FI", f"IMAGENAME eq {exe.name}", "/FO", "CSV", "/NH"],
              capture_output=True, text=True, check=False,
              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout or ""
    return exe.name.lower() in out.lower()


def start_hidden(exe: Path, popen: Callable[..., Any] = subprocess.Popen) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    popen([str(exe), "--no-startup-window"], close_fds=True, creationflags=flags)  # noqa: S603
```

- [ ] **Step 5: Bridge watch** — add to `bridge.py`:

```python
SILENT_LAUNCH = timedelta(minutes=10)
LAUNCH_EVERY = timedelta(minutes=30)
```

in `__init__`: `self._launched_at: datetime | None = None`, and:

```python
    def launch_if_needed(self, find_browser: Callable[[str], Any], is_running: Callable[[Any], bool],
                         start: Callable[[Any], None]) -> bool:
        """Extension mode, nothing heard for a while, the browser not running: start it (at most twice an hour)."""
        prefs = self.settings.get_preferences()
        now = self.clock()
        if prefs.get("fulltext.reader") != "extension" or not prefs.get("fulltext.launch_browser", True):
            return False
        silent = self.silent_for()
        if silent is not None and silent < SILENT_LAUNCH:
            return False
        if self._launched_at is not None and now - self._launched_at < LAUNCH_EVERY:
            return False
        browser = find_browser(str(prefs.get("fulltext.browser_path") or ""))
        if browser is None or is_running(browser.executable):
            return False
        self._launched_at = now
        log.info("Starting %s for the extension (no window)", browser.name)
        start(browser.executable)
        return True

    async def watch_forever(self) -> None:
        from .fetch import browser_for
        from .launcher import is_running, start_hidden

        while True:
            try:
                await asyncio.to_thread(self.launch_if_needed, browser_for, is_running, start_hidden)
            except Exception:
                log.exception("Starting the browser for the extension failed")
            await asyncio.sleep(60)
```

(`import asyncio` at the top.) In `app.py` lifespan under `if ctx.run_collector:` add
`if ctx.bridge is not None: tasks.append(asyncio.create_task(ctx.bridge.watch_forever(), name="extension-watch"))`.

- [ ] **Step 6: Run tests**

Run: `.venv\Scripts\python -m pytest tests/test_extension_launch.py tests/test_extension_bridge.py tests/test_api.py -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/worldsignal/__main__.py src/worldsignal/fulltext/launcher.py src/worldsignal/fulltext/bridge.py src/worldsignal/api/app.py tests/test_extension_launch.py
git commit -m "Extension: fixed ports 47821-47830 and starting the user's browser without a window"
```

---

### Task 6: The extension

**Files:**
- Create: `extension/manifest.json`, `extension/lib.js`, `extension/background.js`, `extension/popup.html`,
  `extension/popup.js`, `extension/_locales/tr/messages.json`, `extension/_locales/en/messages.json`
- Test: `frontend/src/test/extension.test.ts` (vitest runs from `frontend/`; the test imports `../../../extension/lib.js`)

**Interfaces:**
- Consumes: HTTP API of Task 4.
- Produces (in `lib.js`, all functions take their dependencies, so they run under vitest):
  `PORTS` (47821…47830); `findProgram(fetch) -> Promise<number | null>`; `call(fetch, port, key, path, body?) ->
  Promise<any>` (throws `Error("not_paired")` on 401); `readingPlan(random) -> {firstLook: number, steps: number[]}`
  (ms; 3–8 s first look, 4–9 scroll pauses of 2.5–7 s); `readPage(chrome, url, plan) -> Promise<{result: {html, final_url} |
  {error}}>`; `tick(deps) -> Promise<number>` (seconds until the next tick).

- [ ] **Step 1: Write the failing tests** (`frontend/src/test/extension.test.ts`)

```ts
import { describe, expect, it, vi } from "vitest";
// @ts-expect-error plain JS module outside the app
import { PORTS, call, findProgram, readPage, readingPlan, tick } from "../../../extension/lib.js";

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });

describe("the extension", () => {
  it("finds the program on the first fixed port that answers as World Signal", async () => {
    const fetch = vi.fn((url: string) =>
      url.includes(":47823/") ? json(200, { app: "worldsignal" }) : Promise.reject(new Error("refused")));
    expect(await findProgram(fetch)).toBe(47823);
    expect(PORTS[0]).toBe(47821);
    expect(await findProgram(() => Promise.reject(new Error("x")))).toBeNull();
  });

  it("sends the key and reports an unpaired extension", async () => {
    const fetch = vi.fn(() => json(401, { detail: { code: "not_paired" } }));
    await expect(call(fetch, 47821, "k", "/api/ext/next")).rejects.toThrow("not_paired");
    expect(fetch.mock.calls[0]![1].headers["X-WorldSignal-Extension"]).toBe("k");
  });

  it("reads like a person: a first look, then 4 to 9 uneven scrolls, about 20-60 seconds", () => {
    for (let seed = 0; seed < 50; seed++) {
      let x = seed / 50;
      const plan = readingPlan(() => (x = (x * 9301 + 0.49297) % 1));
      expect(plan.firstLook).toBeGreaterThanOrEqual(3000);
      expect(plan.firstLook).toBeLessThanOrEqual(8000);
      expect(plan.steps.length).toBeGreaterThanOrEqual(4);
      expect(plan.steps.length).toBeLessThanOrEqual(9);
    }
  });

  it("opens the page in its own minimized window, reads it and closes the window", async () => {
    const chrome = fakeChrome({ html: "<html>report</html>", url: "https://x.example/a" });
    const out = await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [0, 0, 0, 0] });
    expect(chrome.windows.create).toHaveBeenCalledWith(expect.objectContaining({ url: "https://x.example/a", state: "minimized", focused: false }));
    expect(out.result).toEqual({ html: "<html>report</html>", final_url: "https://x.example/a" });
    expect(chrome.windows.remove).toHaveBeenCalledWith(7);
  });

  it("closes the window even when the page could not be read", async () => {
    const chrome = fakeChrome({ closed: true });
    await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] });
    expect(chrome.windows.remove).toHaveBeenCalledWith(7);
  });

  it("says the tab was closed instead of failing", async () => {
    const chrome = fakeChrome({ closed: true });
    const out = await readPage(chrome, "https://x.example/a", { firstLook: 0, steps: [] });
    expect(out.result).toEqual({ error: "tab_closed" });
  });

  it("one tick: asks for a job, reads it, posts the result, waits as told otherwise", async () => {
    const posts: unknown[] = [];
    const deps = {
      port: async () => 47821,
      key: async () => "k",
      paused: async () => false,
      call: vi.fn(async (_p: number, _k: string, path: string, body?: unknown) => {
        if (path === "/api/ext/next") return { lease: "L", url: "https://x.example/a" };
        posts.push(body);
        return { status: "done" };
      }),
      read: async () => ({ result: { html: "<p>t</p>", final_url: "https://x.example/a" } }),
    };
    expect(await tick(deps)).toBe(5);
    expect(posts).toEqual([{ lease: "L", html: "<p>t</p>", final_url: "https://x.example/a" }]);
    deps.call = vi.fn(async () => ({ wait_seconds: 300, reason: "resting" }));
    expect(await tick(deps)).toBe(300);
    expect(await tick({ ...deps, paused: async () => true })).toBe(60);
  });
});

function fakeChrome(page: { html?: string; url?: string; closed?: boolean }) {
  return {
    windows: { create: vi.fn(async () => ({ id: 7, tabs: [{ id: 3 }] })), remove: vi.fn(async () => undefined) },
    tabs: {
      get: vi.fn(async () => (page.closed ? Promise.reject(new Error("No tab")) : { id: 3, status: "complete", url: page.url })),
    },
    scripting: {
      executeScript: vi.fn(async () => [{ result: { html: page.html, final_url: page.url } }]),
    },
  };
}
```

- [ ] **Step 2: Run to verify they fail**

Run (in `frontend/`): `npx vitest run src/test/extension.test.ts`
Expected: FAIL — cannot resolve `../../../extension/lib.js`.

- [ ] **Step 3: `extension/lib.js`**

```js
// World Signal extension: everything that can be tested without a browser. background.js wires it to chrome.*.
export const PORTS = Array.from({ length: 10 }, (_, i) => 47821 + i);
const LOAD_TIMEOUT_MS = 45000;

export async function findProgram(fetch) {
  for (const port of PORTS) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/api/ext/hello`);
      if (r.ok && (await r.json()).app === "worldsignal") return port;
    } catch {
      // not there: next port
    }
  }
  return null;
}

export async function call(fetch, port, key, path, body) {
  const r = await fetch(`http://127.0.0.1:${port}${path}`, {
    method: body === undefined && path.endsWith("/status") ? "GET" : "POST",
    headers: { "Content-Type": "application/json", "X-WorldSignal-Extension": key },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (r.status === 401) throw new Error("not_paired");
  if (!r.ok) throw new Error(`http_${r.status}`);
  return r.json();
}

const between = (random, low, high) => low + random() * (high - low);

export function readingPlan(random = Math.random) {
  const steps = Math.floor(between(random, 4, 10));
  return {
    firstLook: Math.round(between(random, 3000, 8000)),
    steps: Array.from({ length: steps }, () => Math.round(between(random, 2500, 7000))),
  };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Runs inside the article page: look, scroll down in uneven steps like a reader, then hand back the page.
function readInPage(plan) {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  return (async () => {
    await wait(plan.firstLook);
    for (const pause of plan.steps) {
      window.scrollBy(0, 250 + Math.floor(Math.random() * 450));
      await wait(pause);
    }
    return { html: document.documentElement.outerHTML, final_url: location.href };
  })();
}

async function loaded(chrome, tabId) {
  const until = Date.now() + LOAD_TIMEOUT_MS;
  while (Date.now() < until) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return true;
    await sleep(500);
  }
  return false;
}

// One page, one minimized window of its own that is closed afterwards (a service worker can be stopped by the
// browser between pages, so no window is kept for reuse: nothing is left behind).
export async function readPage(chrome, url, plan) {
  let win = null;
  try {
    win = await chrome.windows.create({ url, state: "minimized", focused: false });
    const tabId = win.tabs && win.tabs[0] ? win.tabs[0].id : null;
    if (tabId == null) return { result: { error: "load_failed" } };
    if (!(await loaded(chrome, tabId))) return { result: { error: "timeout" } };
    const [frame] = await chrome.scripting.executeScript({ target: { tabId }, func: readInPage, args: [plan] });
    if (!frame || !frame.result || !frame.result.html) return { result: { error: "script_failed" } };
    return { result: frame.result };
  } catch (e) {
    const closed = /No tab|closed|No window/i.test(String(e && e.message));
    return { result: { error: closed ? "tab_closed" : "load_failed" } };
  } finally {
    if (win && win.id != null) await chrome.windows.remove(win.id).catch(() => undefined);
  }
}

// One round: returns how many seconds to wait before the next one.
export async function tick(deps) {
  if (await deps.paused()) return 60;
  const port = await deps.port();
  const key = await deps.key();
  if (port == null || !key) return 60;
  const job = await deps.call(port, key, "/api/ext/next");
  if (!job.lease) return job.wait_seconds ?? 60;
  const { result } = await deps.read(job.url);
  await deps.call(port, key, "/api/ext/result", { lease: job.lease, ...result });
  return 5;
}
```

- [ ] **Step 4: `extension/background.js`**

```js
import { call, findProgram, readPage, readingPlan, tick } from "./lib.js";

const state = { port: null, busy: false };

async function port() {
  if (state.port != null) return state.port;
  state.port = await findProgram(fetch);
  return state.port;
}

async function settings() {
  return chrome.storage.local.get({ key: "", paused: false });
}

async function round() {
  if (state.busy) return;
  state.busy = true;
  let wait = 60;
  try {
    wait = await tick({
      port,
      key: async () => (await settings()).key,
      paused: async () => (await settings()).paused,
      call: (p, k, path, body) => call(fetch, p, k, path, body),
      read: (url) => readPage(chrome, url, readingPlan()),
    });
    await chrome.storage.local.set({ lastError: "" });
  } catch (e) {
    state.port = null; // the program may have restarted on another port
    await chrome.storage.local.set({ lastError: String(e.message || e) });
  } finally {
    state.busy = false;
  }
  chrome.alarms.create("round", { delayInMinutes: Math.max(wait, 30) / 60 });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "round") void round();
});
chrome.runtime.onStartup.addListener(() => void round());
chrome.runtime.onInstalled.addListener(() => void round());
chrome.runtime.onMessage.addListener((msg) => {
  if (msg === "round") void round();
});
```

(Chrome alarms fire at most every 30 s for unpacked extensions; `Math.max(wait, 30)` respects it. Each page gets its
own minimized window which `readPage` closes afterwards; spec §3.1's "idle window closes after 10 minutes" therefore
no longer applies — record that when editing the spec in Task 10. Also: `readPage`'s `lib.js` signature is
`readPage(chrome, url, plan) -> Promise<{result}>`, not `{windowId, result}`; the Interfaces block of this task is
corrected accordingly.)

- [ ] **Step 5: `manifest.json`, popup and messages**

```json
{
  "manifest_version": 3,
  "name": "__MSG_name__",
  "description": "__MSG_description__",
  "version": "0.14.0",
  "default_locale": "tr",
  "minimum_chrome_version": "116",
  "background": { "service_worker": "background.js", "type": "module" },
  "action": { "default_popup": "popup.html", "default_title": "World Signal" },
  "permissions": ["alarms", "tabs", "scripting", "storage"],
  "host_permissions": ["<all_urls>"]
}
```

`popup.html`:

```html
<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { font: 13px "Segoe UI", sans-serif; width: 280px; margin: 12px; }
  input { width: 100%; box-sizing: border-box; margin: 6px 0; }
  .muted { color: #6e6e73; }
</style></head>
<body>
  <strong data-msg="name"></strong>
  <p id="state" class="muted"></p>
  <label><span data-msg="codeLabel"></span><input id="code" type="password" autocomplete="off"></label>
  <button id="save" data-msg="save"></button>
  <label><input id="paused" type="checkbox"> <span data-msg="pause"></span></label>
  <p id="error" class="muted"></p>
  <script type="module" src="popup.js"></script>
</body></html>
```

`popup.js`:

```js
import { call, findProgram } from "./lib.js";

const t = (name, subs) => chrome.i18n.getMessage(name, subs);
for (const el of document.querySelectorAll("[data-msg]")) el.textContent = t(el.dataset.msg);

const { key, paused, lastError } = await chrome.storage.local.get({ key: "", paused: false, lastError: "" });
document.getElementById("paused").checked = paused;
document.getElementById("error").textContent = lastError ? t("lastError", [lastError]) : "";

async function show() {
  const state = document.getElementById("state");
  const port = await findProgram(fetch);
  if (port == null) return void (state.textContent = t("noProgram"));
  const k = (await chrome.storage.local.get({ key: "" })).key;
  if (!k) return void (state.textContent = t("notPaired"));
  try {
    const s = await call(fetch, port, k, "/api/ext/status");
    state.textContent = s.reading ? t("reading", [s.reading]) : t("connected", [String(s.read_today)]);
  } catch (e) {
    state.textContent = e.message === "not_paired" ? t("wrongCode") : t("noProgram");
  }
}

document.getElementById("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ key: document.getElementById("code").value.trim() });
  chrome.runtime.sendMessage("round");
  await show();
});
document.getElementById("paused").addEventListener("change", (e) => chrome.storage.local.set({ paused: e.target.checked }));
if (key) document.getElementById("code").placeholder = "••••••";
await show();
```

`_locales/tr/messages.json`:

```json
{
  "name": { "message": "World Signal okuyucu" },
  "description": { "message": "Abonelik sitelerindeki haberleri World Signal için sizin tarayıcınızda, insan temposunda okur." },
  "codeLabel": { "message": "Eşleşme kodu (World Signal → Ayarlar → Tam metin → Eklenti)" },
  "save": { "message": "Kaydet" },
  "pause": { "message": "Duraklat" },
  "noProgram": { "message": "World Signal bulunamadı. Program açık mı, Ayarlar'da okuyucu \"Eklenti\" mi?" },
  "notPaired": { "message": "Eşleşme kodu girilmedi." },
  "wrongCode": { "message": "Eşleşme kodu geçersiz; Ayarlar'daki kodu yeniden girin." },
  "connected": { "message": "Bağlı. Bugün okunan: $1" },
  "reading": { "message": "Okunuyor: $1" },
  "lastError": { "message": "Son hata: $1" }
}
```

`_locales/en/messages.json` with the same keys: "World Signal reader"; "Reads subscription-site reports for World
Signal in your own browser, at a person's pace."; "Pairing code (World Signal → Settings → Full text → Extension)";
"Save"; "Pause"; "World Signal not found. Is the program open, with the reader set to \"Extension\" in Settings?";
"No pairing code entered."; "The pairing code is not valid; enter the code from Settings again."; "Connected. Read
today: $1"; "Reading: $1"; "Last error: $1".

- [ ] **Step 6: Run tests**

Run (in `frontend/`): `npx vitest run src/test/extension.test.ts` then `npx vitest run`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add extension frontend/src/test/extension.test.ts
git commit -m "Extension: MV3 reader (find the program, lease loop, minimized reading window, popup)"
```

---

### Task 7: Prototype check in a real browser (risks 1 and 4 of the spec)

**Files:** none changed unless a finding requires it (then a new task is written for it before code changes).

- [ ] **Step 1:** Start the dev server (`preview_start` "worldsignal-dev"; it runs with `--port 8765`, so for this
  check start a second instance with `.venv\Scripts\python -m worldsignal --server-only --data-dir .devdata-ext
  --token dev` after setting `fulltext.reader = extension` in that data folder via `PATCH /api/settings`; it must
  bind 47821).
- [ ] **Step 2:** Load `extension/` into a test browser: Playwright's bundled Chromium with
  `--disable-extensions-except=<abs path>` and `--load-extension=<abs path>` (branded Chrome ignores these flags).
  If the bundled Chromium is not installed, ask the user before downloading it (`playwright install chromium`, ~150 MB);
  otherwise ask the user to load it in Brave (`brave://extensions` → Developer mode → Load unpacked).
- [ ] **Step 3:** Pair (paste the code from `GET /api/extension`), queue a free article from a "browser"-mode source
  (set The Guardian to `browser` in the test data folder), and confirm: a minimized window appears, the page is read
  for 20–60 s, `article_fulltext.method = 'extension'` with text.
- [ ] **Step 4:** Measure risk 1: compare `chars` of the same article read minimized vs. read by the HTTP path. If
  the minimized read is shorter by more than 20 %, change `readPage` to `state: "normal"` with `left: -32000, top:
  -32000` (off-screen) and re-measure.
- [ ] **Step 5:** Measure risk 4 (Brave only, with the user): close Brave, wait for `launch_if_needed`, confirm the
  extension's service worker runs (popup shows "Bağlı"). Record the result in CLAUDE.md §17 either way.
- [ ] **Step 6:** Report the measured results to the user in Turkish; no "tested" claim for subscription sites until the user
  has run it on their own subscriptions.

---

### Task 8: Settings UI

**Files:**
- Create: `frontend/src/pages/ExtensionSettings.tsx`
- Modify: `frontend/src/pages/FullTextSettings.tsx` (render `<ExtensionSettings />` at the top of the group; hide
  the automation-only rows — browser, profile, visible — when `fulltext.reader === "extension"`)
- Modify: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/i18n/tr.ts`, `en.ts`
- Modify: `src/worldsignal/api/app.py` (`POST /api/app/open-extension-dir`, same pattern as `open_data_dir`, opens
  `<program folder>/extension`; returns 404 `no_extension_dir` if it is missing)
- Test: `frontend/src/test/extension-settings.test.tsx`

**Interfaces:**
- Consumes: `GET /api/extension` → `ExtensionInfo { code: string; port: number; fixed_port: boolean; status:
  ExtensionStatus }`, `ExtensionStatus { connected: boolean; last_seen: string | null; read_today: number; reading:
  string | null; last_source: string | null; last_error: string | null }`; `POST /api/extension/code`.
- Produces: `api.extension()`, `api.renewExtensionCode()`, `api.openExtensionDir()`; settings
  `"fulltext.reader": "automation" | "extension"`, `"fulltext.launch_browser": boolean`.

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, api: { extension: vi.fn(), renewExtensionCode: vi.fn(), openExtensionDir: vi.fn(), updateSettings: vi.fn() } };
});

import { api } from "../api/client";
import { ExtensionSettings } from "../pages/ExtensionSettings";
import { renderWithApp } from "./fixtures";

const mocked = vi.mocked(api, true);
const INFO = { code: "abc123", port: 47821, fixed_port: true,
  status: { connected: true, last_seen: "2026-10-01T09:00:00Z", read_today: 4, reading: null, last_source: "WSJ", last_error: null } };

beforeEach(() => {
  vi.resetAllMocks();
  mocked.extension.mockResolvedValue(INFO);
});

describe("Extension settings", () => {
  it("switches the reader and shows the steps, the code and the connection", async () => {
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Bağlı · bugün 4 haber/)).toBeInTheDocument();
    expect(screen.getByText(/Paketlenmemiş öğe yükle/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Kodu kopyala" }));
    mocked.renewExtensionCode.mockResolvedValue({ code: "new" });
    await userEvent.click(screen.getByRole("button", { name: "Yeni kod" }));
    await waitFor(() => expect(mocked.renewExtensionCode).toHaveBeenCalled());
  });

  it("asks for a restart when the program is not on a fixed port", async () => {
    mocked.extension.mockResolvedValue({ ...INFO, fixed_port: false, port: 51234 });
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Programı yeniden başlatın/)).toBeInTheDocument();
  });

  it("says when the extension has not been heard from", async () => {
    mocked.extension.mockResolvedValue({ ...INFO, status: { ...INFO.status, connected: false, last_seen: null } });
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Eklenti bağlı değil/)).toBeInTheDocument();
  });
});
```

If `fixtures.tsx` has no `renderWithApp`, add it there: it wraps `ui` in `AppStateProvider` (with
`STORY_SETTINGS` merged with the given settings and `META`), `I18nProvider lang="tr"` and `ToastProvider`, the same
way `notebook.test.tsx` `wrap()` does.

- [ ] **Step 2: Run to verify it fails**

Run (in `frontend/`): `npx vitest run src/test/extension-settings.test.tsx`
Expected: FAIL — cannot resolve `../pages/ExtensionSettings`.

- [ ] **Step 3: Implement.** Types and client:

```ts
export interface ExtensionStatus { connected: boolean; last_seen: string | null; read_today: number; reading: string | null; last_source: string | null; last_error: string | null }
export interface ExtensionInfo { code: string; port: number; fixed_port: boolean; status: ExtensionStatus }
```

```ts
  extension: () => request<ExtensionInfo>("GET", "/extension"),
  renewExtensionCode: () => request<{ code: string }>("POST", "/extension/code"),
  openExtensionDir: () => request<{ ok: boolean }>("POST", "/app/open-extension-dir"),
```

`Settings` gains `"fulltext.reader": "automation" | "extension"; "fulltext.launch_browser": boolean;`.

`ExtensionSettings.tsx`:

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { ExtensionInfo } from "../api/types";
import { Segmented, Switch } from "../components/controls";
import { useToast } from "../components/Toasts";
import { useI18n } from "../i18n";
import { useAppState } from "../state";

/** Who reads the subscription sites: World Signal's own browser, or the extension in the user's browser. */
export function ExtensionSettings() {
  const { t, plural } = useI18n();
  const toast = useToast();
  const { settings, updateSettings } = useAppState();
  const reader = settings["fulltext.reader"];
  const [info, setInfo] = useState<ExtensionInfo | null>(null);

  useEffect(() => {
    if (reader !== "extension") return;
    const load = () => api.extension().then(setInfo, () => undefined);
    load();
    const timer = window.setInterval(load, 15_000);
    return () => window.clearInterval(timer);
  }, [reader]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(info?.code ?? "");
      toast.show(t("extension.copied"), "success");
    } catch {
      toast.show(t("extension.copyFailed"), "error");
    }
  };
  const renew = async () => {
    const { code } = await api.renewExtensionCode();
    setInfo((i) => (i ? { ...i, code } : i));
    toast.show(t("extension.renewed"), "success");
  };

  const s = info?.status;
  return (
    <div className="settings-row settings-row-stack">
      <div className="settings-row-text">
        <div className="settings-row-title">{t("extension.reader")}</div>
        <div className="settings-row-hint">{t("extension.readerHint")}</div>
      </div>
      <Segmented<"automation" | "extension">
        label={t("extension.reader")}
        value={reader}
        onChange={(v) => void updateSettings({ "fulltext.reader": v })}
        options={[
          { value: "extension", label: t("extension.reader.extension") },
          { value: "automation", label: t("extension.reader.automation") },
        ]}
      />
      {reader === "extension" ? (
        <>
          <ol className="extension-steps">
            <li>{t("extension.step1")} <button type="button" className="link-btn" onClick={() => void api.openExtensionDir()}>{t("extension.openDir")}</button></li>
            <li>{t("extension.step2")}</li>
            <li>{t("extension.step3")}</li>
          </ol>
          {info ? (
            <div className="inline-row">
              <code className="extension-code">{"•".repeat(12)}</code>
              <button type="button" className="btn" onClick={() => void copy()}>{t("extension.copy")}</button>
              <button type="button" className="btn" onClick={() => void renew()}>{t("extension.renew")}</button>
            </div>
          ) : null}
          {info && !info.fixed_port ? <p className="field-error">{t("extension.restart")}</p> : null}
          {s ? (
            <p className={s.connected ? "field-hint" : "field-error"}>
              {s.connected
                ? s.reading ? t("extension.reading", { source: s.reading }) : `${t("extension.connected")} · ${plural("extension.readToday", s.read_today)}`
                : t("extension.notConnected")}
            </p>
          ) : null}
          <Switch
            checked={settings["fulltext.launch_browser"]}
            label={t("extension.launch")}
            onChange={(v) => void updateSettings({ "fulltext.launch_browser": v })}
          />
        </>
      ) : null}
    </div>
  );
}
```

i18n (tr):

```ts
  "extension.reader": "Abonelik sitelerini kim okusun?",
  "extension.readerHint": "Eklenti, sitelere sizin tarayıcınızdan, kendi oturumunuzla girer; programın kendi tarayıcısını siteler daha sık reddediyor.",
  "extension.reader.extension": "Eklenti (önerilen)",
  "extension.reader.automation": "Programın tarayıcısı",
  "extension.step1": "Bir kez: Brave'de brave://extensions (Chrome'da chrome://extensions) sayfasını açın, Geliştirici modunu açın, Paketlenmemiş öğe yükle ile eklenti klasörünü seçin.",
  "extension.openDir": "Eklenti klasörünü aç",
  "extension.step2": "Eklentinin simgesine tıklayıp aşağıdaki kodu yapıştırın.",
  "extension.step3": "Abonelik sitelerine o tarayıcıda giriş yapmış olun. Gerisi kendiliğinden: tarayıcınız açıkken eklenti haberleri küçültülmüş bir pencerede, insan temposunda okur.",
  "extension.copy": "Kodu kopyala",
  "extension.copied": "Eşleşme kodu kopyalandı.",
  "extension.copyFailed": "Kod kopyalanamadı.",
  "extension.renew": "Yeni kod",
  "extension.renewed": "Yeni kod oluşturuldu; eklentiye yeniden girin.",
  "extension.restart": "Eklentinin programı bulabilmesi için Programı yeniden başlatın.",
  "extension.connected": "Bağlı",
  "extension.readToday": "bugün {n} haber",
  "extension.reading": "Okunuyor: {source}",
  "extension.notConnected": "Eklenti bağlı değil: tarayıcı kapalı, eklenti yüklenmemiş ya da duraklatılmış.",
  "extension.launch": "Tarayıcı kapalıysa pencere açmadan başlat",
```

(en): "Who reads the subscription sites?"; "The extension visits the sites from your own browser with your own
sign-in; sites refuse the program's own browser more often."; "Extension (recommended)"; "The program's browser";
"Once: open brave://extensions (chrome://extensions in Chrome), turn on Developer mode, choose Load unpacked and pick
the extension folder."; "Open the extension folder"; "Click the extension's icon and paste the code below."; "Be signed
in to your subscription sites in that browser. The rest is automatic: while your browser is open the extension reads
reports in a minimized window at a person's pace."; "Copy code"; "Pairing code copied."; "The code could not be
copied."; "New code"; "New code made; enter it in the extension again."; "Restart the program so the extension can
find it."; "Connected"; "{n} today" (plural form as the dictionary's plural keys use, see `stories.count`);
"Reading: {source}"; "Extension not connected: the browser is closed, the extension is not loaded or it is paused.";
"Start the browser without a window when it is closed".

Plural: `extension.readToday` follows the existing plural key pattern of the dictionaries (look at how
`"meeting.count"` is declared in `tr.ts` and declare `extension.readToday` the same way).

CSS in `styles/app.css`: `.extension-steps { margin: 8px 0; padding-left: 20px; display: flex; flex-direction:
column; gap: 6px; font-size: 13.5px; }` and `.extension-code { font-family: ui-monospace, Consolas, monospace; }`.

`api/app.py`:

```python
    @api.post("/app/open-extension-dir")
    def open_extension_dir() -> dict[str, bool]:
        if os.name != "nt":
            raise api_error(501, "unsupported")
        folder = extension_dir()
        if folder is None:
            raise api_error(404, "no_extension_dir")
        subprocess.Popen(["explorer", str(folder)])  # noqa: S603,S607 - fixed program, our own folder
        return {"ok": True}
```

with `extension_dir()` in `paths.py`: the `extension` folder next to the frozen executable
(`Path(sys.executable).parent / "extension"` when `getattr(sys, "frozen", False)`), else the repository's
`extension/`; `None` if it does not exist. Add an i18n error text `"error.no_extension_dir"` (tr: "Eklenti klasörü
bulunamadı; programı yeniden indirin.", en: "The extension folder was not found; download the program again.").

- [ ] **Step 3b: Sign-in and the warning outside Settings (spec §3.3).**
  - `POST /api/fulltext/login`: when `fulltext.reader == "extension"`, open the site in the user's **own** browser
    profile (sign-in happens where the extension reads): `subprocess.Popen([str(browser.executable), url])` instead of
    `make_room_for_login` + `open_login_window`. Test in `tests/test_extension_api.py`:

```python
def test_sign_in_opens_the_users_own_browser_in_extension_mode(client, ctx, monkeypatch):
    from worldsignal.api import app as app_module
    from worldsignal.fulltext.fetch import BrowserInfo
    from pathlib import Path

    opened = []
    monkeypatch.setattr(app_module, "browser_for", lambda p: BrowserInfo("Brave", Path("brave.exe"), Path("p")))
    monkeypatch.setattr(app_module.subprocess, "Popen", lambda args, **k: opened.append(args))
    monkeypatch.setattr(app_module, "open_login_window", lambda *a: opened.append("own-profile"))
    ctx.settings.set("fulltext.reader", "extension")
    assert client.post("/api/fulltext/login", headers=H, json={"url": "https://www.wsj.com/"}).status_code == 200
    assert opened == [["brave.exe", "https://www.wsj.com/"]]
```

  - `GET /api/status` gains `"extension": ctx.bridge.status() | {"active": reader == "extension"}` (or `None` without a
    bridge); `Status` type gains `extension: (ExtensionStatus & { active: boolean }) | null`. The sidebar status block
    (the component that renders `status.collector` lines — `Grep "Son tarama" frontend/src/i18n/tr.ts` to find its key,
    then the component using it) shows `t("extension.notConnected")` as a warning line when `extension.active &&
    !extension.connected`. Test in `extension-settings.test.tsx`: render the sidebar status component with such a
    status and expect the text.
  - Tray: no change (the tray shows the collector state; the sidebar line and Settings are enough — record this
    narrowing in the spec's §3.3 when committing).

- [ ] **Step 4: Run tests and type check**

Run (in `frontend/`): `npx tsc --noEmit -p .` and `npx vitest run`
Expected: no type errors; all tests PASS.

- [ ] **Step 5: Look at it** — `npm run build`, `preview_start` "worldsignal-dev", open Ayarlar → Tam metin, switch to
  "Eklenti", screenshot light and dark, and at 375 px width (no overflow).

- [ ] **Step 6: Commit**

```bash
git add frontend src/worldsignal/api/app.py src/worldsignal/paths.py
git commit -m "Settings: the extension reader (steps, pairing code, connection state)"
```

---

### Task 9: Remove the clip code

**Files:**
- Delete: `src/worldsignal/clip.py`, `tests/test_clip.py`
- Modify: `src/worldsignal/api/app.py` (import, `ClipBody`, `/clips`, `AppContext.clips`), `src/worldsignal/bootstrap.py`,
  `src/worldsignal/repo/fulltext.py` (`store_clip`), `tests/test_api.py` (fixture `clips=`), `ARCHITECTURE.md`
  (the "Sayfa ekle" entry becomes one line: removed in 0.14.0, replaced by the extension)

- [ ] **Step 1:** `Grep "clip" src tests frontend/src` and remove every use listed above. Keep
  `frontend/src/pages/SourcesPage.tsx` `manualOnly` (the "Added by hand" source still exists in databases with pages
  added in 0.13.3).
- [ ] **Step 2:** Run `.venv\Scripts\python -m pytest -q -p no:cacheprovider` → all PASS (one skip is normal).
- [ ] **Step 3: Commit**

```bash
git add -A src tests ARCHITECTURE.md
git commit -m "Remove the clip intake (the extension completes existing reports instead)"
```

---

### Task 10: Packaging, documents, version 0.14.0

**Files:**
- Modify: `tools/build.py` (copy `extension/` next to the exe), `tools/release.py` (refuse a package without
  `extension/manifest.json`)
- Modify: version in `pyproject.toml`, `src/worldsignal/__init__.py`, `frontend/package.json`,
  `frontend/package-lock.json` (2 places), `uv.lock`, `extension/manifest.json`
- Modify: `CHANGELOG.md`, `CHANGELOG.en.md`, `README.md`, `README.en.md`, `ARCHITECTURE.md`, `CLAUDE.md` §4.2 and §17

- [ ] **Step 1:** In `tools/build.py` after the `.exe.config` copy:

```python
    shutil.copytree(ROOT / "extension", APP / "extension")  # loaded unpacked into the user's browser
```

In `tools/release.py`, next to the existing `.exe.config` check, refuse when `extension/manifest.json` is missing from
the app folder, with the same message style.

- [ ] **Step 2:** Add a test in `tests/test_packaging.py` (or the existing release test file — `Grep "exe.config"
  tests`) asserting `manifest.json` version equals `worldsignal.__version__`:

```python
import json
from pathlib import Path

from worldsignal import __version__


def test_extension_version_follows_the_program():
    manifest = json.loads((Path(__file__).parents[1] / "extension" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == __version__
```

- [ ] **Step 3:** Documents: CHANGELOG 0.14.0 (TR/EN) — Added: the extension (what it does, one-time setup, what it
  never does: no robot checks solved; risk notes: sites' terms of use, browser must be open); Removed: clip intake
  code. README (TR/EN): a "Abonelik siteleri: tarayıcı eklentisi" section with the three setup steps and the limits.
  ARCHITECTURE: bridge, lease, ports, security checks, launcher. CLAUDE.md §4.2: the reader setting and the decision of
  2026-10-01; §17: status entry with what was measured in Task 7.
- [ ] **Step 4:** Full check: `.venv\Scripts\python -m pytest -q -p no:cacheprovider`; in `frontend/` `npx tsc --noEmit -p .`,
  `npx vitest run`, `npm run build`; `.venv\Scripts\python -m pytest tests/test_e2e_ui.py -q`.
- [ ] **Step 5:** `.venv\Scripts\python tools\build.py`, `.venv\Scripts\python tools\release.py`, `pkg_check.py`
  smoke test of the package under `build\` (exes cannot run from Temp on this machine); confirm `extension\` is in the
  package.
- [ ] **Step 6: Commit** (run the scratchpad `fix_endings.py` first; check `git show --shortstat`)

```bash
git add -A
git commit -m "0.14.0: World Signal browser extension"
```

- [ ] **Step 7:** Ask the user before publishing (`tools/publish.py --dry-run`, then `tools/publish.py`).
