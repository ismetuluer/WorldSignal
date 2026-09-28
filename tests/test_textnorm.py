import pytest

from worldsignal.textnorm import build_fts_query, fold_for_search, strip_html


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("IRAK", "irak"),
        ("ırak", "irak"),
        ("Irak", "irak"),
        ("İSTANBUL", "istanbul"),
        ("i̇stanbul", "istanbul"),  # decomposed i + combining dot
        ("Şişli ÇAĞLAYAN", "şişli çağlayan"),
        ("Москва", "москва"),
        ("", ""),
        (None, ""),
    ],
)
def test_fold_for_search_turkish_i(text, expected):
    assert fold_for_search(text) == expected


def test_strip_html_removes_tags_and_entities():
    assert strip_html("<p>A &amp; B</p>\n<img src='x'>  C") == "A & B C"
    assert strip_html(None) == ""


def test_build_fts_query_quotes_every_term():
    assert build_fts_query("İstanbul deprem") == '"istanbul"* AND "deprem"*'


@pytest.mark.parametrize("hostile", ['"', "*", "NEAR(", "a OR", ")(", "title:x", "-"])
def test_build_fts_query_never_passes_syntax_through(hostile):
    q = build_fts_query(hostile)
    if q is not None:
        # Only quoted word tokens joined with AND remain.
        for part in q.split(" AND "):
            assert part.startswith('"') and part.endswith('"*')


def test_build_fts_query_empty():
    assert build_fts_query("   ") is None
    assert build_fts_query("!!!") is None


def test_build_fts_query_limits_terms():
    q = build_fts_query(" ".join(f"w{i}" for i in range(50)))
    assert q.count(" AND ") == 11
