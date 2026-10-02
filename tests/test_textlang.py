"""The language of a report follows its letters when the feed's label cannot be right (textlang.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from test_ai import MINI_CATALOG
from worldsignal.collector.rss import ParsedEntry
from worldsignal.repo.articles import ArticleFilter
from worldsignal.repo.history import HistoryRepository
from worldsignal.repo.stories import StoryRepository
from worldsignal.textlang import correct, detect


@pytest.mark.parametrize("text, expected", [
    ("東京外為市場・15時＝ドル157円後半、朝方に一時円高", "ja"),
    ("政府は新たな経済対策を発表した", "ja"),  # kanji with kana
    ("中国央行宣布下调存款准备金率", "zh"),
    ("서울 외환시장에서 달러 강세", "ko"),
    ("الرئيس السوري يستقبل وفدا", "ar"),
    ("پارلمان ایران لایحه را تصویب کرد", "fa"),
    ("Президент провёл встречу с министрами", "ru"),
    ("Президент провів зустріч з міністрами", "uk"),
    ("ממשלת ישראל אישרה את התקציב", "he"),
    ("Tokyo döviz piyasası", None),
    ("Reuters 東京", None),  # too little to tell
    ("", None),
])
def test_detect(text, expected):
    assert detect(text) == expected


def test_a_label_of_the_right_script_is_kept():
    assert correct("uk", "Президент провів зустріч з міністрами") == "uk"
    assert correct("ja", "日本政府経済対策発表") == "ja"  # all kanji, still Japanese
    assert correct("fa", "پارلمان ایران لایحه را تصویب کرد") == "fa"
    assert correct("en", "Latin text stays English") == "en"
    assert correct("tr", "Çok güzel bir haber başlığı") == "tr"


def test_a_label_of_another_script_is_replaced():
    assert correct("en", "東京外為市場・15時＝ドル157円後半") == "ja"
    assert correct("en", "الرئيس السوري يستقبل وفدا") == "ar"
    assert correct(None, "서울 외환시장에서 달러 강세") == "ko"


def entry(key, title):
    return ParsedEntry(key, f"https://beta.example/{key}", title, "", None, datetime.now(UTC))


def test_new_reports_and_the_one_time_repair(db, sources, articles):
    sources.seed_from_catalog(MINI_CATALOG)
    beta = next(s for s in sources.list_sources() if s["slug"] == "beta")
    with db.transaction() as c:
        articles.insert_entries(c, source_id=beta["id"], feed_id=beta["feeds"][0]["id"], language="en",
                                now=datetime.now(UTC), entries=[entry("a", "東京外為市場・15時＝ドル157円後半"),
                                                                 entry("b", "Markets rally on jobs data")])
    langs = {r["title"][:2]: r["language"] for r in articles.list(ArticleFilter())}
    assert langs == {"東京": "ja", "Ma": "en"}

    # Rows written before the fix carry the feed's label; the repair corrects them once and leaves the rest.
    with db.transaction() as c:
        c.execute("UPDATE articles SET language = 'en'")
    history = HistoryRepository(db, StoryRepository(db))
    assert history.repair_languages() == 1
    assert history.repair_languages() == 0
    assert {r["title"][:2]: r["language"] for r in articles.list(ArticleFilter())} == {"東京": "ja", "Ma": "en"}
