"""The publisher's "Exclusive" label read from the article page (fulltext/labels.py)."""

import pytest

from test_fulltext import world  # noqa: F401  (a few seeded reports and their queue)
from worldsignal.flags import is_exclusive
from worldsignal.fulltext.labels import page_is_exclusive

PAD = "<p>" + "Body text of the article. " * 20 + "</p>"


def page(head: str = "", body: str = "") -> str:
    return f"<html><head><title>A headline - Paper</title>{head}</head><body>{body}{PAD}</body></html>"


@pytest.mark.parametrize("html", [
    # The Guardian / The Independent: the description opens with the label (measured on real pages).
    page('<meta name="description" content="Exclusive: Average of nearly five crimes a day">'),
    page('<meta property="og:description" content="Exclusive : New analysis of climate disasters">'),
    # tags / keywords
    page('<meta name="keywords" content="Politics, Exclusive, Spain">'),
    page('<meta property="article:tag" content="exclusive">'),
    page('<meta name="parsely-tags" content="scoop">'),
    # structured data
    page('<script type="application/ld+json">{"@type": "NewsArticle", "keywords": ["Iran", "Exclusive"]}</script>'),
    page('<script type="application/ld+json">{"@graph": [{"@type": "NewsArticle", "articleSection": "Exclusive"}]}</script>'),
    # a label above the headline, inside the article
    page(body='<article><span class="kicker">EXCLUSIVE</span><h1>Headline</h1><p>text</p></article>'),
    page(body='<main><div class="label">Exclusive:</div><h1>Headline</h1></main>'),
    page(body='<article><a href="/exclusive">Scoop</a><h1>Headline</h1></article>'),
    # the page's own headline
    page('<meta property="og:title" content="Exclusive: the plan">'),
    page('<meta property="og:title" content="Scoop: the plan">'),
])
def test_the_label_is_found(html):
    assert page_is_exclusive(html)


@pytest.mark.parametrize("html", [
    page('<meta name="description" content="An exclusive look at how we designed our cover">'),
    page('<meta name="keywords" content="Politics, Exclusive rights, Spain">'),  # a keyword that merely contains the word
    page(body="<article><h1>Headline</h1><p>The label says Exclusive in the middle of a sentence.</p></article>"),
    page(body='<nav><a href="/exclusives">Exclusive</a></nav><article><h1>Headline</h1></article>'),  # navigation
    page(body='<article><h1>Headline</h1></article><footer><span>Exclusive</span></footer>'),
    page(body='<article><aside><span>Exclusive</span></aside><h1>Headline</h1></article>'),
    page(body="<article><h1>Exclusive rights deal for the league announced after a long negotiation</h1></article>"),  # not a label
    page(),
    "",
    "<html><body>too short</body></html>",
    "\x00 not html at all \x00" * 40,
])
def test_the_label_is_not_invented(html):
    assert not page_is_exclusive(html)


def test_the_standfirst_of_the_feed_summary_is_read_the_same_way():
    assert is_exclusive("Cash grab", "Exclusive: Many applicants left feeling used")
    assert is_exclusive("Italy offers help", "Italy's minister said in an exclusive interview with The National that")
    assert is_exclusive("Probe", "The deal was exclusively reported by Axios")
    assert not is_exclusive("Cover", "An exclusive look at how we designed our cover")


def test_recording_a_page_marks_the_article_even_when_only_the_teaser_is_readable(world):
    from datetime import UTC, datetime

    from worldsignal.fulltext.fetch import Page
    from worldsignal.fulltext.outcome import record_page

    repo, ids = world["repo"], world["ids"]
    repo.request(ids["a1"])
    job = repo.next_job(datetime.now(UTC), 99, modes=("http",))
    teaser = page('<meta property="og:description" content="Exclusive: the plan">', "<p>Subscribe to continue reading</p>")
    outcome = record_page(repo, job, Page(200, teaser, "https://x.example/a1"), {}, datetime.now(UTC), lambda: None)
    assert not outcome.ok  # no text, but ...
    row = world["db"].conn.execute("SELECT page_exclusive FROM articles WHERE id = ?", (ids["a1"],)).fetchone()
    assert row["page_exclusive"] == 1


def test_a_marked_page_shows_in_the_exclusive_group_and_the_feed_flag(world, articles):  # noqa: F811
    from worldsignal.repo.articles import ArticleFilter

    ids, db = world["ids"], world["db"]
    with db.transaction() as c:
        c.execute("UPDATE articles SET page_exclusive = 1 WHERE id = ?", (ids["a1"],))
    items = articles.list(ArticleFilter(groups=("exclusive",), limit=50))
    assert [i["id"] for i in items] == [ids["a1"]] and items[0]["exclusive"] is True
    assert "page_exclusive" not in items[0]


def test_pages_are_kept_for_diagnosis_only_while_asked_and_only_the_newest(world, tmp_path):
    from datetime import UTC, datetime

    from worldsignal.fulltext import outcome
    from worldsignal.fulltext.fetch import Page
    from worldsignal.fulltext.outcome import record_page

    repo, ids = world["repo"], world["ids"]
    repo.request(ids["a1"])
    job = repo.next_job(datetime.now(UTC), 99, modes=("http",))
    shown = page(body="<article><h1>Headline</h1></article>")
    folder = tmp_path / "debug"
    record_page(repo, job, Page(200, shown, "https://x.example/a1"), {}, datetime.now(UTC), lambda: None, debug_dir=folder)
    assert not folder.exists()  # off by default
    prefs = {"debug.save_pages": True}
    record_page(repo, job, Page(200, shown, "https://x.example/a1"), prefs, datetime.now(UTC), lambda: None, debug_dir=folder)
    kept = list(folder.glob("*.html"))
    assert len(kept) == 1 and kept[0].name.startswith(f"{ids['a1']}-") and "Headline" in kept[0].read_text(encoding="utf-8")
    for i in range(outcome.KEEP_DEBUG_PAGES + 5):
        (folder / f"old-{i}.html").write_text("x", encoding="utf-8")
    record_page(repo, job, Page(200, shown, "https://x.example/a1"), prefs, datetime.now(UTC), lambda: None, debug_dir=folder)
    assert len(list(folder.glob("*.html"))) == outcome.KEEP_DEBUG_PAGES
