import asyncio

import pytest

from worldsignal.catalog import load_catalog
from worldsignal.collector.rss import fetch_feed, make_client
from worldsignal.repo.sources import CATALOG_GROUPS, REGIONS
from worldsignal.single_instance import InstanceLock


def test_catalog_is_consistent():
    catalog = load_catalog()
    sources = catalog["sources"]
    slugs = [s["slug"] for s in sources]
    urls = [f["url"] for s in sources for f in s["feeds"]]
    assert len(slugs) == len(set(slugs))
    assert len(urls) == len(set(urls))
    for s in sources:
        assert s["group"] in CATALOG_GROUPS, s["slug"]
        assert s["region"] in REGIONS, s["slug"]
        assert len(s["language"]) == 2
        assert s["feeds"], s["slug"]
        # A verified source only ships feeds that passed verification.
        if s["verified"]:
            assert all(f["verified"] for f in s["feeds"]), s["slug"]
        else:
            assert not any(f["verified"] for f in s["feeds"]), s["slug"]
    assert sum(s["verified"] for s in sources) >= 80
    # Every catalog group is represented by at least one working source.
    assert {s["group"] for s in sources if s["verified"]} == set(CATALOG_GROUPS)


def test_catalog_seeds_real_database(sources):
    added = sources.seed_from_catalog(load_catalog())
    assert added == sum(len(s["feeds"]) for s in load_catalog()["sources"])
    enabled = [s for s in sources.list_sources() if s["enabled"]]
    assert all(s["verified"] for s in enabled)


def test_second_instance_cannot_take_lock(tmp_path):
    first = InstanceLock(tmp_path / "i.lock", tmp_path / "i.json")
    second = InstanceLock(tmp_path / "i.lock", tmp_path / "i.json")
    assert first.acquire()
    first.publish(1234, "tok")
    assert (tmp_path / "i.json").exists()
    assert not second.acquire()
    first.release()
    assert not (tmp_path / "i.json").exists()
    assert second.acquire()
    second.release()


@pytest.mark.network
def test_live_catalog_sample_is_reachable():
    """Spot-check a few verified feeds against the real internet (pytest -m network)."""
    sample = [s["feeds"][0]["url"] for s in load_catalog()["sources"] if s["verified"]][:10]

    async def run():
        async with make_client() as client:
            ok = 0
            for url in sample:
                try:
                    result = await fetch_feed(client, url)
                    ok += bool(result.feed and result.feed.entries)
                except Exception:
                    pass
            return ok

    assert asyncio.run(run()) >= 8


def test_catalog_update_retires_dead_feeds_and_switches_on_rescued_sources(sources):
    import copy

    from conftest import MINI_CATALOG

    sources.seed_from_catalog(MINI_CATALOG)
    before = {s["slug"]: s for s in sources.list_sources()}
    assert not before["gamma"]["enabled"]  # no working feed: added switched off
    sources.update_source(before["alpha"]["id"], {"enabled": False})  # the user's own choice

    newer = copy.deepcopy(MINI_CATALOG)
    newer["retired_feeds"] = ["https://alpha.example/rss", "https://gamma.example/rss"]
    newer["sources"][0]["feeds"] = [{"url": "https://www.bing.com/news/search?q=site%3Aalpha.example&format=rss",
                                     "label": "Bing", "verified": True}]
    newer["sources"][2].update(verified=True, feeds=[{"url": "https://gamma.example/feed/", "label": "All",
                                                      "verified": True}])
    sources.seed_from_catalog(newer)
    after = {s["slug"]: s for s in sources.list_sources()}
    assert [f["url"] for f in after["alpha"]["feeds"]] == [newer["sources"][0]["feeds"][0]["url"]]
    assert not after["alpha"]["enabled"]  # the user's choice is kept
    assert after["gamma"]["enabled"] and [f["url"] for f in after["gamma"]["feeds"]] == ["https://gamma.example/feed/"]
    assert after["beta"]["feeds"][0]["url"] == "https://beta.example/rss"  # untouched


def test_catalog_has_no_google_news_links():
    """Google News article links cannot be opened from the company network (they end in a robot check)."""
    catalog = load_catalog()
    assert not [f["url"] for s in catalog["sources"] for f in s["feeds"] if "news.google.com" in f["url"]]
    assert all(u not in {f["url"] for s in catalog["sources"] for f in s["feeds"]} for u in catalog["retired_feeds"])
    assert len([s for s in catalog["sources"] if s["group"] == "sports" and s["verified"]]) >= 10
