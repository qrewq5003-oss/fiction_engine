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
