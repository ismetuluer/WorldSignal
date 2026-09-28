"""History: day views, reconstructed rankings, milestones, retention and their API."""

from datetime import UTC, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from test_api import TOKEN, ctx  # noqa: F401  (the API fixture)
from test_stories import NOW, seed_articles
from worldsignal.api.app import create_app
from worldsignal.maintenance import VECTOR_KEEP_DAYS, Maintenance
from worldsignal.repo.history import DayView, HistoryRepository, day_view, local_datetime
from worldsignal.repo.stories import StoryRepository
from worldsignal.stories.score import Interest

ISTANBUL = timezone(timedelta(hours=3))
WEIGHTS = {"sources": 0.45, "freshness": 0.25, "turkey": 0.2, "interest": 0.1}


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build(db, sources, articles, specs, groups):
    """Seed articles and put them into stories: groups = [[key, ...], ...]."""
    ids = seed_articles(db, sources, articles, specs)
    stories = StoryRepository(db)
    story_ids = []
    for keys in groups:
        sid = None
        for k in keys:
            sid = stories.assign(ids[k], sid, similarity=1.0)
        story_ids.append(sid)
    return ids, story_ids, stories


# -- day views ------------------------------------------------------------------------------------
def test_day_view_morning_and_whole_day():
    now = datetime(2026, 9, 30, 12, tzinfo=UTC)
    morning = day_view("2026-09-27", "morning", 9, now, ISTANBUL)
    assert morning.as_of == datetime(2026, 9, 27, 6, tzinfo=UTC)  # 09:00 in Istanbul
    assert morning.window_start == morning.as_of - timedelta(hours=24)
    whole = day_view("2026-09-27", "day", 9, now, ISTANBUL)
    assert whole.window_start == datetime(2026, 9, 26, 21, tzinfo=UTC)
    assert whole.as_of == datetime(2026, 9, 27, 21, tzinfo=UTC)


def test_day_view_never_looks_past_now():
    now = datetime(2026, 9, 27, 4, tzinfo=UTC)  # 07:00 in Istanbul, before the morning hour
    assert day_view("2026-09-27", "morning", 9, now, ISTANBUL).as_of == now
    assert day_view("2026-09-27", "day", 9, now, ISTANBUL).as_of == now


def test_local_datetime_uses_the_given_zone():
    assert local_datetime("2026-01-01", 9, ISTANBUL).utcoffset() == timedelta(hours=3)


# -- ranking --------------------------------------------------------------------------------------
SPECS = [
    ("alpha", "a1", "Hormuz drone seized", 300),
    ("beta", "b1", "Hürmüz'de insansız araç", 240),
    ("gamma-live", "g1", "Hormuz drone incident", 60),  # published after the moment we look at
    ("alpha", "a2", "Swiss neutrality vote", 200),
    ("alpha", "a3", "Storm floods New Jersey", 30),  # its whole story is after the moment
    ("beta", "b4", "Eski olay", 60 * 30),  # outside the 24-hour window
]


def test_ranking_uses_only_reports_published_by_then(db, sources, articles):
    ids, (hormuz, swiss, storm, old), stories = build(
        db, sources, articles, SPECS, [["a1", "b1", "g1"], ["a2"], ["a3"], ["b4"]]
    )
    history = HistoryRepository(db, stories)
    as_of = NOW - timedelta(minutes=120)
    page = history.ranking(DayView("x", "morning", as_of, as_of - timedelta(hours=24)), WEIGHTS, Interest())
    by_id = {s["id"]: s for s in page["items"]}
    assert set(by_id) == {hormuz, swiss}  # storm is later, the old story is outside the window
    assert page["items"][0]["id"] == hormuz  # two independent sources beat one
    assert by_id[hormuz]["source_count"] == 2 and by_id[hormuz]["article_count"] == 2
    assert {m["id"] for m in by_id[hormuz]["members"]} == {ids["a1"], ids["b1"]}
    assert by_id[hormuz]["sources"] == ["Alpha News", "Beta Haber"]
    assert by_id[hormuz]["last_seen_at"] == iso(NOW - timedelta(minutes=240))
    # Freshness is measured from that moment, not from today.
    assert next(t for t in by_id[swiss]["score_parts"]["tags"] if t["kind"] == "age")["hours"] == 1.3
    assert page["total"] == 2 and page["unclustered"] == 0

    only_multi = history.ranking(DayView("x", "morning", as_of, as_of - timedelta(hours=24)), WEIGHTS, Interest(),
                                 min_sources=2)
    assert [s["id"] for s in only_multi["items"]] == [hormuz]


def test_ranking_counts_reports_that_are_not_in_stories(db, sources, articles):
    seed_articles(db, sources, articles, [("alpha", "z1", "Lonely report", 10)])
    history = HistoryRepository(db, StoryRepository(db))
    page = history.ranking(DayView("x", "day", NOW, NOW - timedelta(hours=1)), WEIGHTS, Interest())
    assert page["items"] == [] and page["unclustered"] == 1


def test_ranking_pages_and_skips_disabled_sources(db, sources, articles):
    _, (hormuz, swiss, *_), stories = build(db, sources, articles, SPECS, [["a1", "b1"], ["a2"], ["a3"], ["b4"]])
    history = HistoryRepository(db, stories)
    view = DayView("x", "day", NOW, NOW - timedelta(hours=24))
    first = history.ranking(view, WEIGHTS, Interest(), limit=1)
    second = history.ranking(view, WEIGHTS, Interest(), limit=1, offset=1)
    assert len(first["items"]) == 1 and first["total"] == 3
    assert first["items"][0]["id"] != second["items"][0]["id"]
    alpha = next(s for s in sources.list_sources() if s["slug"] == "alpha")
    sources.update_source(alpha["id"], {"enabled": False})
    left = history.ranking(view, WEIGHTS, Interest())
    assert [s["id"] for s in left["items"]] == [hormuz]  # only Beta's report is left
    assert left["items"][0]["source_count"] == 1


def test_month_groups_reports_by_local_day(db, sources, articles):
    seed_articles(db, sources, articles, [("alpha", "m1", "One", 0), ("beta", "m2", "Two", 0)])
    history = HistoryRepository(db, StoryRepository(db))
    local_now = NOW.astimezone(ISTANBUL)
    days = history.month(local_now.strftime("%Y-%m"), ISTANBUL)
    today = next(d for d in days if d["day"] == local_now.date().isoformat())
    assert today["articles"] >= 2 and today["stories"] == 0
    assert history.month("1999-01", ISTANBUL) == []


# -- milestones -----------------------------------------------------------------------------------
def test_milestones_mark_the_turning_points(db, sources, articles):
    specs = [
        ("alpha", "a1", "Hormuz drone", 300),
        ("gamma-live", "g1", "Hormuz drone", 200),
        ("beta-sister", "s1", "Hürmüz", 150),
        ("beta", "b1", "Hürmüz insansız araç", 100),  # same media group as Beta Sister: no new source
    ]
    ids, (sid,), stories = build(db, sources, articles, specs, [["a1", "g1", "s1", "b1"]])
    with db.transaction() as c:
        c.execute("UPDATE articles SET home_relevance = 'direct' WHERE id = ?", (ids["b1"],))
    ms = HistoryRepository(db, stories).milestones(sid)
    kinds = [(m["kind"], m.get("count"), m["source"]) for m in ms]
    assert kinds == [
        ("first", None, "Alpha News"),
        ("sources", 3, "Beta Sister"),
        ("own_language_source", None, "Beta Sister"),
        ("turkey", None, "Beta Haber"),
        ("latest", None, "Beta Haber"),
    ]
    assert HistoryRepository(db, stories).milestones(99999) == []


def test_story_that_starts_in_turkish_has_no_turkish_source_milestone(db, sources, articles):
    _, (sid,), stories = build(db, sources, articles, [("beta", "b1", "Olay", 10)], [["b1"]])
    assert [m["kind"] for m in HistoryRepository(db, stories).milestones(sid)] == ["first"]


# -- retention ------------------------------------------------------------------------------------
def test_prune_removes_old_full_texts_and_vectors_but_keeps_the_news(db, sources, articles, settings):
    specs = [("alpha", "old", "Old report", 60 * 24 * 40), ("alpha", "new", "New report", 60)]
    ids, _, stories = build(db, sources, articles, specs, [["old"], ["new"]])
    with db.transaction() as c:
        for key in ("old", "new"):
            c.execute("INSERT INTO article_fulltext (article_id, status, text, queued_at) VALUES (?, 'done', 'metin', ?)",
                      (ids[key], iso(NOW)))
            c.execute("INSERT INTO article_embeddings (article_id, model, vector, created_at) VALUES (?, 'm', x'00', ?)",
                      (ids[key], iso(NOW)))
    history = HistoryRepository(db, stories)
    assert history.prune(NOW, 0, VECTOR_KEEP_DAYS) == {"fulltexts": 0, "vectors": 1}  # 0 = keep full texts
    assert history.prune(NOW, 30, VECTOR_KEEP_DAYS) == {"fulltexts": 1, "vectors": 0}
    left = {r[0] for r in db.conn.execute("SELECT article_id FROM article_fulltext")}
    assert left == {ids["new"]}
    assert db.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 2
    assert db.conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0] == 2
    assert history.database_size() > 0


def test_maintenance_applies_the_setting_and_reports(db, sources, articles, settings):
    ids, _, stories = build(db, sources, articles, [("alpha", "old", "Old", 60 * 24 * 10)], [["old"]])
    with db.transaction() as c:
        c.execute("INSERT INTO article_fulltext (article_id, status, text, queued_at) VALUES (?, 'done', 'metin', ?)",
                  (ids["old"], iso(NOW)))
    m = Maintenance(HistoryRepository(db, stories), settings, clock=lambda: NOW)
    assert m.run_once()["fulltexts"] == 0  # default keeps 30 days
    settings.set("retention.fulltext_days", 7)
    assert m.run_once()["fulltexts"] == 1
    st = m.status()
    assert st["last_run_at"] == iso(NOW) and st["last_removed"]["fulltexts"] == 1 and st["database_bytes"] > 0


# -- API ------------------------------------------------------------------------------------------
def client_for(ctx):  # noqa: F811
    return TestClient(create_app(ctx), headers={"X-WorldSignal-Token": TOKEN})


def test_history_api(ctx, db, sources, articles):  # noqa: F811
    _, (hormuz, _, storm, _), _ = build(db, sources, articles, SPECS, [["a1", "b1", "g1"], ["a2"], ["a3"], ["b4"]])
    storm_day = (NOW - timedelta(minutes=30)).astimezone().date().isoformat()  # local day of the storm report
    with client_for(ctx) as c:
        month = c.get("/api/history", params={"month": storm_day[:7]}).json()
        assert storm_day in [d["day"] for d in month["days"]]
        day = c.get(f"/api/history/{storm_day}", params={"moment": "day"}).json()
        assert day["future"] is False and day["moment"] == "day"
        assert storm in [s["id"] for s in day["items"]]
        future = c.get("/api/history/2999-01-01").json()
        assert future["future"] is True and future["items"] == [] and future["total"] == 0
        assert c.get("/api/history/2026-13-45").status_code == 422
        assert c.get("/api/history/2026-09-27", params={"moment": "noon"}).status_code == 422
        story = c.get(f"/api/stories/{hormuz}").json()
        assert [m["kind"] for m in story["milestones"]][0] == "first"
        assert c.patch("/api/settings", json={"retention.fulltext_days": 90}).json()["retention.fulltext_days"] == 90
        assert c.patch("/api/settings", json={"history.morning_hour": 24}).status_code == 422
        assert "maintenance" in c.get("/api/status").json()
        # One local day of single reports (for days before stories existed).
        listed = c.get("/api/articles", params={"day": storm_day}).json()["items"]
        assert "Storm floods New Jersey" in [a["title"] for a in listed]
        assert c.get("/api/articles", params={"day": "1999-01-01"}).json()["items"] == []
        assert c.get("/api/articles", params={"day": "yesterday"}).status_code == 422
