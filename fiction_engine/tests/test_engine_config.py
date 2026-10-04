"""
test_engine_config.py — engine/engine_config.py

Нет функций — только данные. Тестируем что:
A. MODULE_PRIORITY — словарь с разумными значениями
B. GENRE_KEYWORDS — корректная структура
"""
import pytest


class TestModulePriority:
    def test_priority_is_dict(self):
        from engine.engine_config import MODULE_PRIORITY
        assert isinstance(MODULE_PRIORITY, dict)

    def test_priorities_are_integers(self):
        from engine.engine_config import MODULE_PRIORITY
        for k, v in MODULE_PRIORITY.items():
            assert isinstance(v, int), f"{k}: {v} is not int"

    def test_priorities_in_valid_range(self):
        from engine.engine_config import MODULE_PRIORITY
        for k, v in MODULE_PRIORITY.items():
            assert 1 <= v <= 10, f"{k}: priority {v} out of range"

    def test_known_modules_present(self):
        from engine.engine_config import MODULE_PRIORITY
        # Базовые модули должны быть в приоритетах
        assert "07_voice_consistency" in MODULE_PRIORITY
        assert "01_tension_curve" in MODULE_PRIORITY


class TestGenreKeywords:
    def test_genre_keywords_is_dict(self):
        from engine.engine_config import GENRE_KEYWORDS
        assert isinstance(GENRE_KEYWORDS, dict)

    def test_each_genre_has_list(self):
        from engine.engine_config import GENRE_KEYWORDS
        for genre, keywords in GENRE_KEYWORDS.items():
            assert isinstance(keywords, list), f"{genre} keywords is not list"
            assert len(keywords) > 0, f"{genre} has no keywords"

    def test_fantasy_genre_present(self):
        from engine.engine_config import GENRE_KEYWORDS
        fantasy_genres = [g for g in GENRE_KEYWORDS if "fantasy" in g]
        assert len(fantasy_genres) > 0

    def test_detective_genre_present(self):
        from engine.engine_config import GENRE_KEYWORDS
        detective_genres = [g for g in GENRE_KEYWORDS if "detective" in g]
        assert len(detective_genres) > 0
