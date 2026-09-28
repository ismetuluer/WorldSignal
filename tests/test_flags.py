"""The "exclusive" and "breaking" badges (flags.py)."""

from datetime import UTC, datetime, timedelta

import pytest

from worldsignal.flags import has_breaking_marker, is_breaking, is_exclusive


@pytest.mark.parametrize("title", [
    "Exclusive: Tesla plans new factory", "EXCLUSIVE-Tesla plans", "[Exclusive] The deal", "(Exclusive) Talks",
    "ÖZEL HABER | Ankara'da kritik toplantı", "Özel: Bakan açıkladı", "Özel haber - Yeni gelişme",
    "Exclusif : l'Élysée prépare", "Exklusiv: Gespräch", "Exclusiva: el plan", "Esclusiva: il piano",
    "Эксклюзив: интервью", "حصري: وثائق", "Reuters EXCLUSIVE shows",
])
def test_exclusive_markers(title):
    assert is_exclusive(title)


@pytest.mark.parametrize("title", [
    "Exclusive rights deal signed", "Özel sektör kredisi arttı", "Özel harekât polisi", "The most exclusive club",
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
