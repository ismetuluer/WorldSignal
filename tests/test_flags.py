"""The "exclusive" and "breaking" badges (flags.py)."""

from datetime import UTC, datetime, timedelta

import pytest

from worldsignal.flags import article_kind, group_condition, has_breaking_marker, is_breaking, is_exclusive, is_opinion


@pytest.mark.parametrize("title", [
    "Exclusive: Tesla plans new factory", "EXCLUSIVE-Tesla plans", "[Exclusive] The deal", "(Exclusive) Talks",
    "ÖZEL HABER | Ankara'da kritik toplantı", "Özel: Bakan açıkladı", "Özel haber - Yeni gelişme",
    "Exclusif : l'Élysée prépare", "Exklusiv: Gespräch", "Exclusiva: el plan", "Esclusiva: il piano",
    "Эксклюзив: интервью", "حصري: وثائق", "Reuters EXCLUSIVE shows", "Scoop: Senate forecast rattles retreat",
    "Exclusive - Cost pressures force Honda to rework India strategy", "Reuters exclusive: Ford production down", "CNN Exclusive: the plan",
    # Trend News Agency marks it at the end.
    "JAC Motors supplies vehicles to Kyrgyzstan (Exclusive)", "Caspian priorities [exclusive] ",
])
def test_exclusive_markers(title):
    assert is_exclusive(title)


@pytest.mark.parametrize("title", [
    "Exclusive rights deal signed", "Özel sektör kredisi arttı", "Özel harekât polisi", "The most exclusive club",
    "Talks on exclusive (rights)", "Club goes exclusive", "Ice cream scoop prices rise", "Weekend Reads: an exclusive look at mining",
    "Why exclusive: the club's rules",
    "", None,
])
def test_everyday_words_are_not_exclusive(title):
    assert not is_exclusive(title)


@pytest.mark.parametrize("title", [
    "BREAKING: Explosion in port", "Breaking news: x", "SON DAKİKA: Deprem", "Son dakika haberi: Ankara",
    "SON DAKİKA | Ankara", "FLASH - Deprem", "Flaş: Açıklama", "عاجل: انفجار", "Срочно: заявление",
    "Eilmeldung: Rücktritt", "Última hora: terremoto", "[Breaking] Fire",
])
def test_breaking_markers(title):
    assert has_breaking_marker(title)


@pytest.mark.parametrize("title", ["Flash-flood warning issued", "Flash floods hit", "Breaking Bad actor dies",
                                   "Urgently needed aid", ""])
def test_everyday_words_are_not_breaking(title):
    assert not has_breaking_marker(title)


NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


def ago(minutes: int) -> datetime:
    return NOW - timedelta(minutes=minutes)


def test_a_story_spreading_now_is_breaking():
    assert is_breaking([("a", ago(10), "x"), ("b", ago(30), "y"), ("c", ago(55), "z")], NOW)


def test_a_media_group_counts_once_and_old_reports_do_not_count():
    assert not is_breaking([("a", ago(10), "x"), ("a", ago(20), "y"), ("b", ago(30), "z")], NOW)
    assert not is_breaking([("a", ago(10), "x"), ("b", ago(30), "y"), ("c", ago(90), "z")], NOW)


def test_a_publishers_breaking_marker_counts_for_two_hours():
    assert is_breaking([("a", ago(100), "BREAKING: Earthquake")], NOW)
    assert not is_breaking([("a", ago(130), "BREAKING: Earthquake")], NOW)


def test_a_report_dated_slightly_in_the_future_is_fresh():
    assert is_breaking([("a", NOW + timedelta(minutes=2), "x"), ("b", ago(1), "y"), ("c", ago(2), "z")], NOW)


# -- the feed's "exclusive" / "opinion" groups ---------------------------------------------------
@pytest.mark.parametrize("title,url", [
    ("Why the ceasefire will not hold", "https://www.nytimes.com/2026/09/28/opinion/ceasefire.html"),
    ("The quiet shift", "https://www.theguardian.com/commentisfree/2026/sep/28/quiet-shift"),
    ("Ekonomide yeni dönem", "https://www.hurriyet.com.tr/yazarlar/ahmet-hakan/ekonomide-yeni-donem-42"),
    ("Merz und die Mitte", "https://www.spiegel.de/meinung/merz-und-die-mitte-a-1234"),
    ("Analysis: What Beijing wants", "https://example.com/world/asia/beijing"),
    ("Görüş - Doğu Akdeniz'de denge", "https://example.com/haber/dogu-akdeniz"),
    ("Мнение: переговоры зашли в тупик", "https://example.ru/news/123"),
    ("Destroying the regime is not the same as saving Iran - opinion", "https://example.com/international/article-1"),
])
def test_opinion_pieces(title, url):
    assert is_opinion(title, url)
    assert article_kind(title, url) == "opinion"


@pytest.mark.parametrize("title,url", [
    ("Opinion polls show a tight race", "https://example.com/politics/polls"),  # no label separator
    ("Analysts expect a rate cut", "https://example.com/markets/rates"),
    ("Yorumcular ne diyor?", "https://example.com/haber/spor"),
    ("Commentary box moves", "https://example.com/sport/commentary-box"),  # "/comment" is not a whole segment
    ("Fed faces a tough analysis", "https://example.com/markets/fed"),  # no separator before the word
])
def test_ordinary_reports_are_not_opinion(title, url):
    assert not is_opinion(title, url)
    assert article_kind(title, url) is None


def test_exclusive_wins_over_opinion():
    assert article_kind("Exclusive: The memo", "https://example.com/opinion/memo") == "exclusive"


def test_group_condition_mixes_catalog_groups_and_kinds():
    assert group_condition([]) is None
    sql, params = group_condition(["western", "opinion", "western"])
    assert params == ["western", "opinion"]
    assert sql == "(s.catalog_group IN (?) OR ws_kind(a.title, a.url, a.summary, a.page_exclusive) IN (?))"
    assert group_condition(["exclusive"]) == ("(ws_kind(a.title, a.url, a.summary, a.page_exclusive) IN (?))", ["exclusive"])


def test_the_summary_can_carry_the_marker_when_the_headline_does_not():
    # The Guardian and The Independent open the standfirst with it.
    assert is_exclusive("Cash grab: candidates asked for money", "Exclusive: Many applicants left feeling used")
    assert is_exclusive("Couples out of pocket", "Exclusive : Couples left devastated by the collapse")
    assert not is_exclusive("Cover story", "An exclusive look at how we designed our cover")  # in the middle: not a label
    assert not is_exclusive("Speaking exclusively to the Post", "Speaking exclusively to the Post, the leader says")
    assert article_kind("Plain headline", "https://x.example/a", "Exclusive: the plan") == "exclusive"


@pytest.mark.parametrize(("title", "summary", "source"), [
    # Ordinary sourcing and "we have the documents" wording are not the publisher's label; they are never guessed into one.
    ("Cost pressures and deadlock force Honda to rework India strategy, sources say", "", "Reuters"),
    ("Schneider Said to Near Deal", "The deal, people familiar with the matter said, could be announced", "Bloomberg"),
    ("How Cornell Punished Each of the 7 Men", "Summaries obtained by The New York Times offer a detailed look", "The New York Times"),
    ("Virologist tells CNN about infection at Russian lab", "", "CNN"),
])
def test_the_wording_of_a_story_is_never_taken_for_the_publishers_label(title, summary, source):
    assert not is_exclusive(title, summary)
