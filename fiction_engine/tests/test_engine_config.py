"""
test_engine_config.py — engine/engine_config.py

Нет функций — только данные. Тестируем что:
A. Паттерны компилируются без ошибок
B. _COMPILED_PATTERNS матчат ценные строки
C. _SKIP_PATTERNS матчат балласт
D. MODULE_PRIORITY — словарь с разумными значениями
E. GENRE_KEYWORDS — корректная структура
"""
import pytest


class TestCompiledPatterns:
    def test_patterns_importable(self):
        from engine.engine_config import _COMPILED_PATTERNS, _SKIP_PATTERNS
        assert len(_COMPILED_PATTERNS) > 0
        assert len(_SKIP_PATTERNS) > 0

    def test_compiled_pattern_matches_rule_text(self):
        from engine.engine_config import _COMPILED_PATTERNS
        rule_text = "Запрещено использовать клише сердце сжалось"
        assert any(p.search(rule_text) for p in _COMPILED_PATTERNS)

    def test_compiled_pattern_matches_emoji_marker(self):
        from engine.engine_config import _COMPILED_PATTERNS
        text = "❌ Не делай так — это плохо"
        assert any(p.search(text) for p in _COMPILED_PATTERNS)

    def test_compiled_pattern_matches_nelzya(self):
        from engine.engine_config import _COMPILED_PATTERNS
        text = "Нельзя называть эмоцию напрямую"
        assert any(p.search(text) for p in _COMPILED_PATTERNS)


class TestSkipPatterns:
    def test_skip_metadata_lines(self):
        """
        Пропускаются строки-метаданные в том виде, в каком они реально
        стоят в файлах базы знаний: **Модуль:**, **Версия:** и т.п.
        Прежние примеры («## ФИЛОСОФИЯ МОДУЛЯ», «Версия 2.0») были из
        другого формата и не встречаются в UNIFIED_ENGINE_MASTER.
        """
        from engine.engine_config import _SKIP_PATTERNS
        for text in ("**Модуль:** 01_tension_curve",
                     "**Версия:** 2.0",
                     "**Зависимости:** нет",
                     "---"):
            assert any(p.match(text) for p in _SKIP_PATTERNS), text

    def test_headers_are_kept_not_skipped(self):
        """Заголовки — структура, они намеренно попадают в выжимку."""
        from engine.engine_config import _SKIP_PATTERNS, _COMPILED_PATTERNS
        text = "## ФИЛОСОФИЯ МОДУЛЯ"
        assert not any(p.match(text) for p in _SKIP_PATTERNS)
        assert any(p.search(text) for p in _COMPILED_PATTERNS)

    def test_dont_skip_content_line(self):
        from engine.engine_config import _SKIP_PATTERNS
        text = "Правило: показывай через действие"
        assert not any(p.match(text) for p in _SKIP_PATTERNS)


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
