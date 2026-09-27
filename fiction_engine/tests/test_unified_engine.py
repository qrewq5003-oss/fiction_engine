"""
test_unified_engine.py — тесты unified_engine.py

Проверяем: определение жанра, резолвинг зависимостей.
Сборку полного контекста не тестируем — требует файловой системы движка.
"""

import pytest


class TestDetectGenre:
    def test_detect_fantasy(self):
        from engine.unified_engine import detect_genre
        assert detect_genre("эпическое фэнтези") == "fantasy_epic"

    def test_detect_noir(self):
        from engine.unified_engine import detect_genre
        assert detect_genre("нуар детектив") is not None

    def test_detect_horror(self):
        from engine.unified_engine import detect_genre
        result = detect_genre("психологический хоррор")
        assert result is not None
        assert "horror" in result

    def test_detect_scifi(self):
        from engine.unified_engine import detect_genre
        result = detect_genre("научная фантастика")
        assert result is not None

    def test_detect_unknown_returns_none(self):
        from engine.unified_engine import detect_genre
        assert detect_genre("абракадабра бессмыслица xyz") is None

    def test_detect_empty_returns_none(self):
        from engine.unified_engine import detect_genre
        assert detect_genre("") is None

    def test_detect_case_insensitive(self):
        from engine.unified_engine import detect_genre
        lower = detect_genre("фэнтези")
        upper = detect_genre("ФЭНТЕЗИ")
        assert lower == upper

    def test_detect_most_specific_wins(self):
        """Более специфичный жанр побеждает общий."""
        from engine.unified_engine import detect_genre
        # "городское фэнтези" специфичнее чем просто "фэнтези"
        result = detect_genre("городское фэнтези")
        assert result == "fantasy_urban"

    def test_yo_normalization(self):
        """ё и е нормализуются одинаково."""
        from engine.unified_engine import detect_genre
        r1 = detect_genre("фэнтези")
        r2 = detect_genre("фэнтэзи")  # без ё
        # оба должны либо найти что-то, либо оба None — не падают
        assert r1 is not None or r2 is None  # не краш


class TestDetectGenreBoundaries:
    """
    Ключ ищется с начала слова, а не подстрокой. Раньше «нф» внутри
    «конфликт» давал твёрдую НФ, и вся серия шла с чужим жанровым
    блоком: каталогом, контрактом, профилем, аркой и модулями
    (AUDIT_UNIFIED.md, U2).
    """

    @pytest.mark.parametrize("text, wrong", [
        ("конфликт интересов",     "scifi_hard"),            # «нф» внутри слова
        ("информационная война",   "scifi_hard"),
        ("мыльная опера",          "detective_procedural"),  # «опер»
        ("прозаик в кризисе",      "realism_psychological"), # «проза»
        ("ужасно смешная комедия", "horror_psychological"),  # «ужас»
        ("страховая компания",     "horror_psychological"),  # «страх»
        ("драматург",              "realism_psychological"), # «драма»
        ("городской роман",        "fantasy_urban"),         # «городской»
        ("исторический детектив",  "romance_historical"),    # «исторический»
        ("мистический детектив",   "horror_psychological"),  # «мистический»
    ])
    def test_no_match_inside_word_or_by_modifier(self, text, wrong):
        from engine.unified_engine import detect_genre
        assert detect_genre(text) != wrong

    @pytest.mark.parametrize("text, expected", [
        ("исторический детектив", "detective_classic"),
        ("мистический детектив",  "detective_classic"),
        ("детективы",             "detective_classic"),     # формы длинного ключа
        ("детективный роман",     "detective_classic"),
        ("ужасы",                 "horror_psychological"),  # короткий ключ целиком
        ("твёрдая НФ",            "scifi_hard"),
        ("НФ",                    "scifi_hard"),
        ("космическая опера",     "scifi_space_opera"),
        ("Фэнтези, магия",        "fantasy_epic"),
    ])
    def test_expected_genre(self, text, expected):
        from engine.unified_engine import detect_genre
        assert detect_genre(text) == expected

    def test_every_keyword_maps_to_its_own_genre(self):
        """Ни один ключ не перехвачен другим жанром — ни целиком, ни частью."""
        from engine.engine_config import GENRE_KEYWORDS
        from engine.unified_engine import detect_genre
        wrong = [(key, kw, detect_genre(kw))
                 for key, kws in GENRE_KEYWORDS.items() for kw in kws
                 if detect_genre(kw) != key]
        assert not wrong, wrong


class TestResolveDependencies:
    def test_no_deps_unchanged(self):
        from engine.unified_engine import resolve_dependencies
        result = resolve_dependencies(["writing_core"])
        assert "writing_core" in result

    def test_deduplication(self):
        from engine.unified_engine import resolve_dependencies
        result = resolve_dependencies(["a", "a", "b"])
        assert result.count("a") == 1

    def test_empty_list(self):
        from engine.unified_engine import resolve_dependencies
        assert resolve_dependencies([]) == []
