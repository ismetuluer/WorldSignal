from datetime import UTC, datetime, timedelta

import pytest

from conftest import MINI_CATALOG
from worldsignal.collector.rss import ParsedEntry
from worldsignal.repo.articles import ArticleFilter
from worldsignal.repo.sources import Conflict, NotFound

NOW = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


def entry(key, title, summary="", minutes_ago=10, published=True):
    return ParsedEntry(
        dedupe_key=key, url=f"https://x.example/{key}", title=title, summary=summary, author=None,
        published_at=NOW - timedelta(minutes=minutes_ago) if published else None,
    )


def seed(sources):
    sources.seed_from_catalog(MINI_CATALOG)
    return {s["slug"]: s for s in sources.list_sources()}


def insert(db, articles, source, entries, now=NOW):
    with db.transaction() as c:
        return articles.insert_entries(c, source_id=source["id"], feed_id=source["feeds"][0]["id"],
                                       language=source["language"], entries=entries, now=now)


# -- sources ---------------------------------------------------------------------
def test_seed_creates_sources_and_disables_unverified(sources):
    by_slug = seed(sources)
    assert set(by_slug) == {"alpha", "beta", "gamma"}
    assert by_slug["alpha"]["enabled"] and by_slug["alpha"]["verified"]
    assert not by_slug["gamma"]["enabled"] and not by_slug["gamma"]["verified"]
    assert by_slug["gamma"]["status"] == "disabled"
    assert by_slug["alpha"]["status"] == "pending"


def test_seed_is_idempotent_and_keeps_user_edits(sources):
    by_slug = seed(sources)
    sources.update_source(by_slug["alpha"]["id"], {"name": "Alpha (edited)", "reliability": 1.5})
    assert sources.seed_from_catalog(MINI_CATALOG) == 0
    again = {s["slug"]: s for s in sources.list_sources()}
    assert again["alpha"]["name"] == "Alpha (edited)"
    assert again["alpha"]["reliability"] == 1.5
    assert len(again) == 3


def test_deleted_catalog_source_is_not_re_added(sources):
    by_slug = seed(sources)
    sources.delete_source(by_slug["beta"]["id"])
    sources.seed_from_catalog(MINI_CATALOG)
    assert "beta" not in {s["slug"] for s in sources.list_sources()}


def test_new_catalog_feed_is_added_to_existing_source(sources):
    seed(sources)
    catalog = {"sources": [dict(MINI_CATALOG["sources"][0])]}
    catalog["sources"][0]["feeds"] = [
        *catalog["sources"][0]["feeds"],
        {"url": "https://alpha.example/rss2", "label": "Business", "verified": True},
    ]
    assert sources.seed_from_catalog(catalog) == 1


def test_user_source_slug_is_unique_and_feed_url_conflicts(sources):
    seed(sources)
    first = sources.create_source({"name": "Alpha News"}, "https://new.example/rss")
    second = sources.create_source({"name": "Alpha News"}, "https://new2.example/rss")
    slugs = {s["id"]: s["slug"] for s in sources.list_sources()}
    assert slugs[first] == "alpha-news" and slugs[second] == "alpha-news-2"
    with pytest.raises(Conflict):
        sources.create_source({"name": "Dup"}, "https://alpha.example/rss")
    # The failed create must not leave a half-created source behind.
    assert "dup" not in slugs.values() and all(s["name"] != "Dup" for s in sources.list_sources())


def test_turkish_name_slug(sources):
    sid = sources.create_source({"name": "Işık Haber Ağı"}, "https://isik.example/rss")
    assert sources.get_source(sid)["slug"] == "isik-haber-agi"


def test_update_and_delete_missing_raise_not_found(sources):
    with pytest.raises(NotFound):
        sources.update_source(9999, {"name": "x"})
    with pytest.raises(NotFound):
        sources.delete_source(9999)
    with pytest.raises(NotFound):
        sources.update_feed(9999, {"enabled": False})
    with pytest.raises(NotFound):
        sources.add_feed(9999, "https://z.example/rss", None)


def test_update_ignores_non_editable_fields(sources, db):
    by_slug = seed(sources)
    sources.update_source(by_slug["alpha"]["id"], {"slug": "hacked", "origin": "user", "name": "Alpha 2"})
    s = sources.get_source(by_slug["alpha"]["id"])
    assert s["slug"] == "alpha" and s["origin"] == "catalog" and s["name"] == "Alpha 2"


def test_due_feeds_respects_enabled_flags(sources):
    by_slug = seed(sources)
    now = "2026-09-27T08:00:00Z"
    assert {f.source_id for f in sources.due_feeds(now)} == {by_slug["alpha"]["id"], by_slug["beta"]["id"]}
    sources.update_feed(by_slug["alpha"]["feeds"][0]["id"], {"enabled": False})
    assert {f.source_id for f in sources.due_feeds(now)} == {by_slug["beta"]["id"]}
    sources.update_source(by_slug["beta"]["id"], {"enabled": False})
    assert sources.due_feeds(now) == []


# -- articles --------------------------------------------------------------------
def test_insert_dedupes_and_indexes(db, sources, articles):
    s = seed(sources)["beta"]
    assert insert(db, articles, s, [entry("a", "IRAK'ta seçim"), entry("b", "İstanbul'da yağış")]) == 2
    assert insert(db, articles, s, [entry("a", "IRAK'ta seçim"), entry("c", "Yeni")]) == 1
    assert db.conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0] == 3


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("ırak", {"a"}), ("IRAK", {"a"}), ("irak", {"a"}), ("Irak", {"a"}),
        ("istanbul", {"b"}), ("İSTANBUL", {"b"}), ("ISTANBUL", {"b"}),
        ("secim", {"a"}), ("seçim", {"a"}), ("yağ", {"b"}),
        ("москва", {"r"}), ("القدس", {"ar"}),
        ('"', set()), ("", {"a", "b", "r", "ar"}),
    ],
)
def test_search_is_turkish_aware(db, sources, articles, query, expected):
    s = seed(sources)["beta"]
    insert(db, articles, s, [
        entry("a", "IRAK'ta seçim sonuçları"),
        entry("b", "İstanbul'da şiddetli yağış"),
        entry("r", "Москва заявила"),
        entry("ar", "أخبار القدس اليوم"),
    ])
    found = {item["url"].rsplit("/", 1)[1] for item in articles.list(ArticleFilter(query=query or None))}
    assert found == expected


def test_future_and_missing_dates_are_clamped_to_first_seen(db, sources, articles):
    s = seed(sources)["beta"]
    insert(db, articles, s, [entry("future", "Gelecek", minutes_ago=-180), entry("nodate", "Tarihsiz", published=False)])
    rows = {r["title"]: r for r in articles.list(ArticleFilter())}
    assert rows["Gelecek"]["sort_at"] == "2026-09-27T08:00:00Z"
    assert rows["Gelecek"]["published_at"] == "2026-09-27T11:00:00Z"
    assert rows["Tarihsiz"]["sort_at"] == "2026-09-27T08:00:00Z"


def test_filters_and_pagination(db, sources, articles):
    by_slug = seed(sources)
    insert(db, articles, by_slug["alpha"], [entry(f"a{i}", f"Alpha {i}", minutes_ago=i) for i in range(5)])
    insert(db, articles, by_slug["beta"], [entry(f"b{i}", f"Beta {i}", minutes_ago=i) for i in range(3)])
    assert len(articles.list(ArticleFilter(regions=["turkey"]))) == 3
    assert len(articles.list(ArticleFilter(groups=["western"]))) == 5
    assert len(articles.list(ArticleFilter(languages=["tr"]))) == 3
    assert len(articles.list(ArticleFilter(source_ids=[by_slug["alpha"]["id"]]))) == 5
    assert len(articles.list(ArticleFilter(since="2026-09-27T07:57:30Z"))) == 6  # 0,1,2 min ago from both sources

    seen = []
    cursor = None
    while True:
        page = articles.list(ArticleFilter(limit=3, before=cursor))
        seen += [p["id"] for p in page]
        if len(page) < 3:
            break
        cursor = (page[-1]["sort_at"], page[-1]["id"])
    assert len(seen) == 8 and len(set(seen)) == 8


def test_disabled_source_articles_are_hidden(db, sources, articles):
    s = seed(sources)["alpha"]
    insert(db, articles, s, [entry("x", "Hidden later")])
    sources.update_source(s["id"], {"enabled": False})
    assert articles.list(ArticleFilter()) == []


def test_deleting_source_removes_articles_and_index(db, sources, articles):
    s = seed(sources)["beta"]
    insert(db, articles, s, [entry("a", "Silinecek haber")])
    sources.delete_source(s["id"])
    assert db.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0
    assert db.conn.execute("SELECT COUNT(*) FROM articles_fts").fetchone()[0] == 0


def test_large_batch_insert(db, sources, articles):
    s = seed(sources)["alpha"]
    n = insert(db, articles, s, [entry(f"k{i}", f"Story number {i} İzmir", summary="x" * 500) for i in range(3000)])
    assert n == 3000
    assert len(articles.list(ArticleFilter(query="izmir", limit=500))) == 500


# -- settings --------------------------------------------------------------------
def test_settings_defaults_and_roundtrip(settings):
    prefs = settings.get_preferences()
    assert prefs["ui.language"] == "tr" and prefs["ui.theme"] == "system"
    settings.set_many({"ui.language": "en", "ui.theme": "dark"})
    prefs = settings.get_preferences()
    assert prefs["ui.language"] == "en" and prefs["ui.theme"] == "dark"


def test_local_time_labelled_as_utc_is_corrected(db, sources, articles):
    """CNN Türk / Jerusalem Post style feeds: Turkish/Israeli time labelled as GMT (+3 h)."""
    s = seed(sources)["beta"]
    shifted = [
        entry("n1", "Yeni 1", minutes_ago=-170),   # really 10 min ago, labelled 2h50m ahead
        entry("n2", "Yeni 2", minutes_ago=-150),   # really 30 min ago
        entry("o1", "Eski", minutes_ago=60),       # really 4 h ago, labelled 1 h ago
    ]
    insert(db, articles, s, shifted)
    rows = {r["title"]: r for r in articles.list(ArticleFilter())}
    assert rows["Yeni 1"]["sort_at"] == "2026-09-27T07:50:00Z"
    assert rows["Yeni 2"]["sort_at"] == "2026-09-27T07:30:00Z"
    assert rows["Eski"]["sort_at"] == "2026-09-27T04:00:00Z"
    # The raw feed value is kept for transparency.
    assert rows["Yeni 1"]["published_at"] == "2026-09-27T10:50:00Z"
    assert [r["title"] for r in articles.list(ArticleFilter())] == ["Yeni 1", "Yeni 2", "Eski"]


def test_timezone_correction_ignores_single_or_far_future_items():
    from worldsignal.repo.articles import timezone_correction

    one_scheduled = [entry("a", "Plan", minutes_ago=-120), entry("b", "Normal", minutes_ago=5)]
    assert timezone_correction(one_scheduled, NOW) == timedelta(0)
    far = [entry("a", "Edition", minutes_ago=-60 * 48), entry("b", "Edition 2", minutes_ago=-60 * 30)]
    assert timezone_correction(far, NOW) == timedelta(0)
    skew = [entry("a", "Skew", minutes_ago=-2), entry("b", "Skew 2", minutes_ago=-3)]
    assert timezone_correction(skew, NOW) == timedelta(0)
