#!/usr/bin/env python3
"""
Legacy-путь слияния State и сборка жанровых частей промпта.

Перенесено из run_tests.py: 44 строки db_state и 18 state_prompts были
покрыты только автономным раннером.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


# ─── GLOBAL_STATE: текстовый формат ───────────────────────────────────────────

class TestApplyGlobalBlock:
    def _apply(self, block, state_text):
        from engine.db_state import _apply_global_block
        changes, new_chars = [], []
        out = _apply_global_block(
            block, state_text,
            lambda field, before, after: changes.append(field), new_chars)
        return out, changes, new_chars

    def test_updates_existing_character(self):
        out, changes, new = self._apply(
            "Марк: состояние: ранен, локация: склад",
            "## ПЕРСОНАЖИ\n\n### Марк\nСОСТОЯНИЕ: спокоен\nЛОКАЦИЯ: дом\n")
        assert "ранен" in out and not new

    def test_finds_character_in_author_format(self):
        """Заголовок [ИМЯ — РОЛЬ] — раньше персонаж дублировался."""
        out, changes, new = self._apply(
            "Марк: состояние: ранен",
            "[МАРК — ГЕРОЙ]\nВозраст: 34\nСтатус: спокоен\n")
        assert not new, "персонаж задублирован вместо обновления"
        assert "ранен" in out

    def test_adds_unknown_character(self):
        out, changes, new = self._apply(
            "Лиза: состояние: испугана, локация: лес",
            "## ПЕРСОНАЖИ\n\n### Марк\nСОСТОЯНИЕ: спокоен\n")
        assert "Лиза" in new and "Лиза" in out

    @pytest.mark.parametrize("skip", ["Мир", "МИР", "Новые линии", "Закрытые линии"])
    def test_service_sections_skipped(self, skip):
        out, changes, new = self._apply(f"{skip}: что-то происходит",
                                        "## ПЕРСОНАЖИ\n\n### Марк\nСОСТОЯНИЕ: спокоен\n")
        assert not new and skip not in new

    def test_garbage_section_ignored(self):
        out, changes, new = self._apply("строка без двоеточия в начале",
                                        "### Марк\nСОСТОЯНИЕ: спокоен\n")
        assert not new

    def test_empty_block_is_noop(self):
        state = "### Марк\nСОСТОЯНИЕ: спокоен\n"
        out, changes, new = self._apply("", state)
        assert out == state and not changes


# ─── PLOT_MATRIX ──────────────────────────────────────────────────────────────

class TestApplyPlotBlock:
    def _apply(self, block, plot_text):
        from engine.db_state import _apply_plot_block
        changes = []
        out = _apply_plot_block(block, plot_text,
                                lambda f, b, a: changes.append(f))
        return out, changes

    def test_updates_next_step(self):
        out, changes = self._apply("следующий шаг: найти свидетеля",
                                   "СЛЕДУЮЩИЙ_ШАГ: ждать\n")
        assert "найти свидетеля" in out and changes

    def test_without_marker_is_noop(self):
        plot = "СЛЕДУЮЩИЙ_ШАГ: ждать\n"
        out, changes = self._apply("ничего похожего", plot)
        assert out == plot and not changes

    def test_placeholder_ignored(self):
        plot = "СЛЕДУЮЩИЙ_ШАГ: ждать\n"
        out, changes = self._apply("следующий шаг: [не изменилось]", plot)
        assert out == plot


# ─── ЗНАЕТ ────────────────────────────────────────────────────────────────────

class TestApplyCharKnows:
    def _apply(self, val, block):
        from engine.db_state import _apply_char_knows
        changes = []
        out = _apply_char_knows(val, block, "Марк",
                                lambda f, b, a: changes.append(f))
        return out, changes

    def test_appends_to_existing(self):
        out, changes = self._apply("убийца — брат",
                                   "СОСТОЯНИЕ: спокоен\nЗНАЕТ: имя жертвы\n")
        assert "убийца — брат" in out and "имя жертвы" in out and changes

    def test_replaces_empty_list_marker(self):
        out, _ = self._apply("первый факт", "ЗНАЕТ: []\n")
        assert "первый факт" in out and "[]" not in out

    def test_creates_field_when_absent(self):
        out, changes = self._apply("новый факт", "СОСТОЯНИЕ: спокоен\n")
        assert "новый факт" in out and changes

    def test_placeholder_ignored(self):
        block = "ЗНАЕТ: имя жертвы\n"
        out, changes = self._apply("[без изменений]", block)
        assert out == block and not changes


# ─── Жанровые части промпта ───────────────────────────────────────────────────

class TestGenreParts:
    @pytest.mark.parametrize("genre", ["фэнтези", "городское фэнтези", "детектив",
                                       "нуар", "хоррор", "триллер", "romance",
                                       "научная фантастика", ""])
    def test_identity_always_string(self, genre):
        from engine.state_prompts import _genre_identity
        out = _genre_identity(genre)
        assert isinstance(out, str) and out

    @pytest.mark.parametrize("genre", ["детектив", "нуар", "фэнтези", "хоррор",
                                       "триллер", "романтика", ""])
    def test_rules_always_string(self, genre):
        from engine.state_prompts import _genre_rules
        assert isinstance(_genre_rules(genre), str)

    def test_detective_rules_differ_from_default(self):
        from engine.state_prompts import _genre_rules
        assert _genre_rules("детектив") != _genre_rules("нет такого жанра")


class TestExtractNextContext:
    def test_none_returns_empty(self):
        from engine.state_prompts import _extract_next_context
        assert _extract_next_context(None) == ""

    def test_pulls_block_from_analysis(self):
        from engine.state_prompts import _extract_next_context
        upd = {"raw_analysis": "АНАЛИЗ\n\nКОНТЕКСТ ДЛЯ СЛЕДУЮЩЕЙ ГЛАВЫ:\n"
                               "Марк идёт на склад.\n"}
        assert isinstance(_extract_next_context(upd), str)

    def test_missing_block_returns_empty_or_text(self):
        from engine.state_prompts import _extract_next_context
        assert isinstance(_extract_next_context({"raw_analysis": "без блока"}), str)

    def test_empty_analysis(self):
        from engine.state_prompts import _extract_next_context
        assert _extract_next_context({"raw_analysis": ""}) == ""


# ─── Валидация путей движка ───────────────────────────────────────────────────

class TestValidateEnginePaths:
    def test_real_engine_is_ok(self):
        from engine.engine_loaders import validate_engine_paths, engine_available
        if not engine_available():
            pytest.skip("движок недоступен")
        res = validate_engine_paths()
        assert res["ok"] is True
        assert res["missing_critical"] == []

    def test_missing_engine_reports_not_ok(self, tmp_path):
        from engine.engine_loaders import validate_engine_paths
        with patch("engine.engine_loaders.get_engine_path", return_value=tmp_path / "нет"):
            res = validate_engine_paths()
        assert res["ok"] is False and res["missing_critical"]

    def test_partial_engine_lists_missing(self, tmp_path):
        from engine.engine_loaders import validate_engine_paths
        (tmp_path / "00_CORE").mkdir()
        (tmp_path / "00_CORE" / "CORE_FULL.md").write_text("x", encoding="utf-8")
        with patch("engine.engine_loaders.get_engine_path", return_value=tmp_path):
            res = validate_engine_paths()
        assert res["ok"] is False
        assert any("INDEX.json" in m for m in res["missing_critical"])
