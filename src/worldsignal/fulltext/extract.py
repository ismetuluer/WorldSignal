"""Turn a fetched article page into plain text, or say clearly why that was not possible.

Outcomes (``error_code``):
  bot_check   - the site showed a bot / CAPTCHA check. It is never solved; the site is paused.
  paywall     - the page is behind a subscription wall (no or expired session).
  http_<n>    - the site answered with an error status.
  not_article - the page had no article text (video page, live blog shell, redirect page).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import trafilatura

MIN_CHARS = 400  # shorter than this is a teaser, not a full text
MAX_CHARS = 120_000
# Less than this share of the declared article length means the page showed only its free part.
PARTIAL_RATIO = 0.5
MIN_DECLARED_WORDS = 150
# A text this short that mentions a subscription offer anywhere is the offer, not the article.
SHORT_TEXT = 2000

_BOT_CHECK = re.compile(
    r"verify you are (a )?human|are you a robot|captcha|unusual traffic|checking your browser|"
    r"just a moment\.\.\.|bir dakika lütfen|attention required|access to this page has been denied|"
    r"please enable js and disable any ad blocker|datadome|px-captcha|press & hold",
    re.I,
)
_PAYWALL = re.compile(
    r"subscribe to (continue|read)|to continue reading|already a subscriber|create a free account to|"
    r"this (article|content) is (only )?(available|for) (to )?subscribers|sign in to (continue|read)|"
    r"abonnez-vous|réservée? aux abonnés|il vous reste \d[\d.,]*\s?% de cet article|"
    r"nur für abonnenten|jetzt abonnieren|weiterlesen mit|abone ol(un)? devamını|"
    r"suscríbete para (seguir|continuar) leyendo|exclusivo para suscriptores|abbonati per continuare|"
    r"войдите|подпишитесь|للمشتركين|"
    r"subscribe to unlock|unlock (this|the full) article|full range of subscriptions",
    re.I,
)
# Lines that belong to the page, not to the article: consent notices for embedded media,
# membership prompts, bare "subscribe" buttons.
_BOILERPLATE_LINE = re.compile(
    r"^(to display this content from .{1,40}, you must enable|one of your browser extensions seems to be blocking|"
    r"become an? .{1,40} member to bookmark|want to bookmark your favourite articles|"
    r"(abone ol|subscribe|follow us|takip et)$)",
    re.I,
)


@dataclass
class Extracted:
    text: str | None
    error_code: str | None

    @property
    def ok(self) -> bool:
        return self.text is not None


def _visible_text(html: str, limit: int = 30_000) -> str:
    head = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html[:400_000], flags=re.S | re.I)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", head))[:limit]


def tidy(text: str) -> str:
    """One paragraph per line: spaces inside a line collapsed, empty lines dropped."""
    lines = (re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def strip_boilerplate(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not _BOILERPLATE_LINE.match(line))


def judge(text: str) -> Extracted:
    """Is an extracted text really the article? Also used to re-check texts stored earlier."""
    text = strip_boilerplate(tidy(text))
    if len(text) < MIN_CHARS:
        return Extracted(None, "paywall" if _PAYWALL.search(text) else "not_article")
    if _PAYWALL.search(text[-600:]) or (len(text) < SHORT_TEXT and _PAYWALL.search(text)):
        # A teaser that ends in (or is mostly) a subscription offer.
        return Extracted(None, "paywall")
    return Extracted(text[:MAX_CHARS], None)


def extract(html: str, url: str, status: int | None = 200) -> Extracted:
    """Article text from a page, or the reason there is none."""
    visible = _visible_text(html)
    if status in (401, 403, 429, 503) and _BOT_CHECK.search(visible):
        return Extracted(None, "bot_check")
    if status is not None and status >= 400:
        return Extracted(None, f"http_{status}")
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False, favor_precision=True)
    text = tidy(text or "")
    if len(text) < MIN_CHARS:
        if _BOT_CHECK.search(visible) and len(visible) < 5000:
            return Extracted(None, "bot_check")
        if _PAYWALL.search(visible):
            return Extracted(None, "paywall")
        return Extracted(None, "not_article")
    verdict = judge(text)
    if not verdict.ok:
        return verdict
    declared = declared_word_count(html)
    if declared is not None and len((verdict.text or "").split()) < declared * PARTIAL_RATIO:
        # Far less text than the page says the article has: only the free part was shown.
        return Extracted(None, "paywall")
    return verdict


_WORD_COUNT = re.compile(r'"wordCount"\s*:\s*"?(\d{2,6})')


def declared_word_count(html: str) -> int | None:
    """The article length the page declares in its metadata (schema.org ``wordCount``), if any.

    Short declarations are ignored: for a brief item a few missing words mean nothing."""
    m = _WORD_COUNT.search(html)
    if m is None:
        return None
    n = int(m.group(1))
    return n if n >= MIN_DECLARED_WORDS else None
