"""Pages the user sends from their own browser (clip.py): parsing, source matching, storing, the API."""

import json
from datetime import UTC, datetime

import pytest

from conftest import MINI_CATALOG  # noqa: F401  (documents where the sources come from)
from test_api import H, add_articles, client, ctx  # noqa: F401  (fixtures)
from worldsignal.clip import MAX_CLIP_CHARS, ClipError, parse_clip

PARAGRAPHS = "".join(
    f"<p>Paragraf {i}: Alpha kaynağındaki haberin ayrıntıları burada uzun uzun anlatılıyor ve okunuyor.</p>" for i in range(14)
)


def page(body: str = PARAGRAPHS, title: str = "Alpha haberi") -> str:
    return f"<html><head><title>{title}</title></head><body><nav>menü</nav><article><h1>{title}</h1>{body}</article></body></html>"


def clip(url="https://www.alpha.example/world/2026/story-1?utm_source=x", html=None, **extra) -> str:
    return json.dumps({"ws": 1, "url": url, "title": "Alpha haberi", "lang": "tr-TR", "html": html or page(), **extra})


# -- parsing --------------------------------------------------------------------------------------
def test_a_good_clip_is_parsed():
    c = parse_clip(clip())
    assert c.url.startswith("https://www.alpha.example/") and c.title == "Alpha haberi" and c.lang == "tr"


@pytest.mark.parametrize("raw,code", [
    ("not json at all", "bad_clip"),
    ("[1, 2]", "bad_clip"),
    (json.dumps({"url": "https://a.example/x", "html": page()}), "bad_clip"),  # not from the bookmark (no "ws")
    (json.dumps({"ws": 1, "url": "javascript:alert(1)", "html": page()}), "bad_url"),
    (json.dumps({"ws": 1, "url": "ftp://a.example/x", "html": page()}), "bad_url"),
    (json.dumps({"ws": 1, "url": "https://a.example/x", "html": "<p>tiny</p>"}), "bad_clip"),
])
def test_bad_clips_are_refused_with_a_reason(raw, code):
    with pytest.raises(ClipError) as info:
        parse_clip(raw)
    assert info.value.code == code


def test_a_huge_clip_is_refused_before_it_is_read():
    with pytest.raises(ClipError) as info:
        parse_clip("x" * (MAX_CLIP_CHARS + 1))
    assert info.value.code == "too_large"


def test_a_title_is_cleaned_and_shortened():
    long = json.dumps({"ws": 1, "url": "https://a.example/x", "title": "  A \n  başlık " + "x" * 500, "html": page()})
    title = parse_clip(long).title
    assert title.startswith("A başlık") and len(title) == 300 and "\n" not in title


# -- storing ------------------------------------------------------------------------------------------
def test_a_page_becomes_a_report_of_the_source_of_its_site_with_its_full_text(ctx):
    added = ctx.clips.add(clip(), now=datetime(2026, 9, 27, 8, 0, tzinfo=UTC))
    assert added["source"] == "Alpha News" and added["created"] and added["chars"] > 500
    row = ctx.db.conn.execute(
        "SELECT a.title, a.url, a.language, a.dedupe_key, s.slug FROM articles a JOIN sources s ON s.id = a.source_id "
        "WHERE a.id = ?", (added["article_id"],)).fetchone()
    assert row["slug"] == "alpha" and row["language"] == "tr" and row["title"] == "Alpha haberi"
    assert "utm_source" not in row["dedupe_key"]  # tracking parameters are dropped like everywhere
    ft = ctx.fulltext.get(added["article_id"])
    assert ft["status"] == "done" and ft["method"] == "clip" and "Paragraf 3" in ft["text"]
    assert "menü" not in ft["text"]  # the article text is picked out of the page
    # It is searchable like any report.
    hit = ctx.db.conn.execute("SELECT COUNT(*) FROM articles_fts WHERE articles_fts MATCH 'alpha'").fetchone()[0]
    assert hit >= 1


def test_sending_the_same_page_again_updates_it_instead_of_adding_a_second_report(ctx):
    first = ctx.clips.add(clip())
    again = ctx.clips.add(clip(html=page(PARAGRAPHS + "<p>Yeni bir paragraf sonradan eklendi ve uzun uzun anlatıldı.</p>")))
    assert again["article_id"] == first["article_id"] and again["created"] is False
    assert "Yeni bir paragraf" in ctx.fulltext.get(first["article_id"])["text"]
    assert ctx.db.conn.execute("SELECT COUNT(*) FROM articles WHERE url LIKE '%story-1%'").fetchone()[0] == 1


def test_a_page_of_an_unknown_site_goes_to_the_added_by_hand_source(ctx):
    added = ctx.clips.add(clip(url="https://news.unknown-site.example/a/1"))
    assert added["source"] == "Elle eklenenler"
    again = ctx.clips.add(clip(url="https://news.unknown-site.example/a/2"))
    assert ctx.db.conn.execute("SELECT COUNT(*) FROM sources WHERE slug = 'manual'").fetchone()[0] == 1  # one, reused
    assert again["article_id"] != added["article_id"]


def test_a_site_is_matched_by_its_domain_not_by_a_lookalike(ctx):
    assert ctx.clips.add(clip(url="https://alpha.example/x"))["source"] == "Alpha News"
    assert ctx.clips.add(clip(url="https://edition.alpha.example/x"))["source"] == "Alpha News"  # a sub-domain
    assert ctx.clips.add(clip(url="https://notalpha.example/x"))["source"] == "Elle eklenenler"


def test_a_page_without_an_article_or_behind_a_paywall_says_why(ctx):
    with pytest.raises(ClipError) as info:
        ctx.clips.add(clip(html="<html><body>" + "<div>menu</div>" * 40 + "</body></html>"))
    assert info.value.code == "not_article"
    wall = page("<p>Subscribe to keep reading. This article is for subscribers only.</p>" * 2)
    with pytest.raises(ClipError) as info:
        ctx.clips.add(clip(html=wall))
    assert info.value.code in ("paywall", "not_article")
    assert ctx.db.conn.execute("SELECT COUNT(*) FROM articles WHERE url LIKE '%story-1%'").fetchone()[0] == 0  # nothing stored


# -- the API ------------------------------------------------------------------------------------------
def test_the_api_adds_a_page_and_queues_its_summary(client, ctx):
    r = client.post("/api/clips", headers=H, json={"clip": clip()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "Alpha News" and body["chars"] > 500
    listed = client.get("/api/articles?hours=48", headers=H).json()["items"]
    mine = next(a for a in listed if a["id"] == body["article_id"])
    assert mine["fulltext_status"] == "done" and mine["ai_status"] == "pending"


def test_the_api_explains_refusals_and_needs_the_token(client):
    assert client.post("/api/clips", headers=H, json={"clip": "hello"}).json()["detail"]["code"] == "clip_bad_clip"
    r = client.post("/api/clips", headers=H, json={"clip": clip(html="<html><body>" + "<i>x</i>" * 60 + "</body></html>")})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "clip_not_article"
    assert client.post("/api/clips", json={"clip": clip()}).status_code == 401
    assert client.post("/api/clips", headers=H, json={}).status_code == 422
