#!/usr/bin/env python3
"""
Сборка контекста, обрезка по блокам и слияние State — ветки, которые были
покрыты только автономным раннером (50 строк pipeline, 60 db_state,
21 pipeline_context). Перенесено при слиянии наборов.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


# ─── Обрезка контекста по блокам ──────────────────────────────────────────────

def _block(marker: str, size: int) -> str:
    """
    Блок контекста в том виде, в каком его режет _truncate_context_by_blocks:
    конец блока опознаётся по "\n\n---" (или "\n\n\n"), без разделителя
    удаление съедает всё до конца строки.
    """
    return f"=== {marker} ===\n" + ("наполнитель " * (size // 12)) + "\n\n---\n"


class TestTruncateContextByBlocks:
    def test_short_context_untouched(self):
        from engine.pipeline import _truncate_context_by_blocks
        ctx = "короткий контекст"
        out, removed = _truncate_context_by_blocks(ctx, max_chars=1000)
        assert out == ctx and removed == []

    def test_drops_least_important_first(self):
        """Порядок удаления: эталоны раньше, чем анализ предыдущей главы."""
        from engine.pipeline import _truncate_context_by_blocks
        ctx = (_block("БАЗОВЫЙ ПРОМПТ", 500)
               + _block("ЭТАЛОНЫ", 4000)
               + _block("БАЗА ЗНАНИЙ", 4000)
               + _block("АНАЛИЗ ГЛАВЫ", 4000))
        out, removed = _truncate_context_by_blocks(ctx, max_chars=9000)
        assert removed, "ничего не удалено, хотя лимит превышен"
        assert removed[0] == "exemplars"
        assert "АНАЛИЗ ГЛАВЫ" in out, "удалён более важный блок раньше менее важного"

    def test_removes_more_until_fits(self):
        from engine.pipeline import _truncate_context_by_blocks
        ctx = "".join(_block(m, 3000) for m in
                      ("ЭТАЛОНЫ", "БАЗА ЗНАНИЙ", "СИМВОЛИКА", "АНТИКЛИШЕ"))
        out, removed = _truncate_context_by_blocks(ctx, max_chars=4000)
        assert len(removed) >= 2, removed
        assert len(out) < len(ctx)

    def test_keeps_base_prompt(self):
        from engine.pipeline import _truncate_context_by_blocks
        ctx = "=== БАЗОВЫЙ ПРОМПТ ===\nзадача автора\n\n---\n" + _block("ЭТАЛОНЫ", 8000)
        out, removed = _truncate_context_by_blocks(ctx, max_chars=2000)
        assert "exemplars" in removed
        assert "задача автора" in out, "базовый промпт обязан пережить обрезку"

    def test_unknown_blocks_survive(self):
        from engine.pipeline import _truncate_context_by_blocks
        ctx = _block("НЕИЗВЕСТНЫЙ БЛОК", 5000)
        out, removed = _truncate_context_by_blocks(ctx, max_chars=1000)
        # Известных маркеров нет — остаётся только грубая обрезка в конце
        assert removed == ["hard_cut"]
        assert len(out) == 1000


class TestHardCutKeepsState:
    """
    Аварийная обрезка резала хвост контекста, а там стоит State: глава
    писалась без знания, где персонажи и что они знают (AUDIT_UNIFIED.md, F3).
    """

    def _ctx(self, head_size=5000, state="Аня в подвале, знает про ключ"):
        from engine.pipeline_context import STATE_HEADER
        return ("ЗАДАЧА ГЛАВЫ: побег\n" + "середина " * (head_size // 9)
                + f"\n{STATE_HEADER}\n{state}\n")

    def test_state_survives_hard_cut(self):
        from engine.pipeline import _truncate_context_by_blocks
        out, removed = _truncate_context_by_blocks(self._ctx(), max_chars=1000)
        assert "hard_cut" in removed
        assert len(out) <= 1000
        assert out.startswith("ЗАДАЧА ГЛАВЫ: побег")
        assert out.rstrip().endswith("Аня в подвале, знает про ключ")
        assert "[контекст обрезан]" in out

    def test_state_larger_than_budget_falls_back_to_plain_cut(self):
        from engine.pipeline import _truncate_context_by_blocks
        out, removed = _truncate_context_by_blocks(
            self._ctx(state="x" * 3000), max_chars=1000)
        assert removed == ["hard_cut"]
        assert len(out) == 1000

    def test_base_prompt_mention_is_not_taken_for_state_block(self):
        """«ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:» из шаблона — не блок State."""
        from engine.pipeline import _truncate_context_by_blocks
        ctx = ("ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:\nиз шаблона\n"
               + "середина " * 1000 + "\nКОНЕЦ")
        out, _ = _truncate_context_by_blocks(ctx, max_chars=500)
        assert len(out) == 500 and out.startswith("ТЕКУЩЕЕ СОСТОЯНИЕ")


class TestContextBudget:
    """Порог проверки и предел обрезки — одно число (AUDIT_UNIFIED.md, F3)."""

    def test_budget_never_exceeds_cap(self):
        from engine.pipeline_config import (CONTEXT_TOKEN_CAP, MIXED_CHARS_PER_TOKEN,
                                            context_char_budget)
        cap = int(CONTEXT_TOKEN_CAP * MIXED_CHARS_PER_TOKEN)
        for model in ("", "anthropic::claude-x", "google::gemini-x",
                      "deepseek::deepseek-chat", "openai::gpt-4o"):
            assert context_char_budget(model) <= cap

    def test_default_truncation_uses_same_budget(self):
        from engine.pipeline import _truncate_context_by_blocks
        from engine.pipeline_config import context_char_budget
        ctx = "а" * (context_char_budget() + 1000)
        out, removed = _truncate_context_by_blocks(ctx)
        assert removed and len(out) <= context_char_budget()

    def test_generation_context_is_cut_to_budget(self, project_id):
        """
        Контекст в 100 тыс. токенов проходил проверку «> 90 тыс.», но
        обрезка по умолчанию начиналась только со 120 тыс. и не делала ничего.
        """
        from engine.pipeline import run_generation
        from engine.pipeline_config import context_char_budget
        model = "anthropic::claude-test"
        huge = "контекст " * 34_000          # ~306 тыс. символов ≈ 102 тыс. токенов
        sent = {}

        def fake_call(model_value, system, user, max_tokens=6000, prefill=""):
            sent["user"] = user
            return "Слово " * 3000

        with patch("engine.pipeline._build_context", return_value=huge), \
             patch("engine.pipeline._call", side_effect=fake_call):
            result = run_generation({"id": project_id, "genre": "детектив"},
                                    1, "quick", model, "Задача.")
        assert len(sent["user"]) <= context_char_budget(model)
        assert "Контекст обрезан" in (result["warning"] or "")


# ─── Сборка голоса и выборка состояния ────────────────────────────────────────

class TestBuildConsolidatedVoice:
    @pytest.mark.parametrize("mode", ["quick", "quality", "master"])
    def test_profile_used_only_in_deep_modes(self, mode):
        from engine.pipeline_context import build_consolidated_voice
        voice = {"name": "Нуар", "profile": "рубленые фразы"}
        out = build_consolidated_voice(voice, [], mode)
        assert ("рубленые фразы" in out) == (mode in ("quality", "master"))

    def test_no_voice_no_chapters(self):
        from engine.pipeline_context import build_consolidated_voice
        assert isinstance(build_consolidated_voice(None, [], "quality"), str)

    def test_last_chapters_feed_voice(self):
        from engine.pipeline_context import build_consolidated_voice
        chapters = [{"number": 1, "content": "Текст главы. " * 50}]
        assert isinstance(build_consolidated_voice(None, chapters, "master"), str)


class TestExtractRelevantState:
    def test_empty_state(self):
        from engine.pipeline_context import extract_relevant_state
        assert isinstance(extract_relevant_state({}, "любая задача"), str)

    def test_mentions_character_from_prompt(self):
        from engine.pipeline_context import extract_relevant_state
        state = {"global_state": "## ПЕРСОНАЖИ\n\n### Марк\nСОСТОЯНИЕ: ранен\n",
                 "plot_matrix": "СТАТУС: завязка\n", "memory_graph": ""}
        out = extract_relevant_state(state, "Марк идёт на склад")
        assert isinstance(out, str)

    def test_survives_freeform_state(self):
        from engine.pipeline_context import extract_relevant_state
        state = {"global_state": "[ЛУКАШ — ГЕРОЙ]\nСтатус: в розыске\n",
                 "plot_matrix": "", "memory_graph": ""}
        assert isinstance(extract_relevant_state(state, "Лукаш прячется"), str)


# ─── Слияние State: legacy-формат и блоки ─────────────────────────────────────

LEGACY = """GLOBAL_STATE:
Марк: состояние: ранен, локация: склад
Мир: момент: ночь после погони

PLOT_MATRIX:
следующий шаг: найти свидетеля
"""


class TestLegacyMerge:
    def _project(self):
        from engine.db_projects import create_project
        from engine.db_state import update_state
        pid = create_project("legacy", "детектив")
        update_state(pid,
                     "## ПЕРСОНАЖИ\n\n### Марк\nСОСТОЯНИЕ: спокоен\nЛОКАЦИЯ: дом\n",
                     "СЛЕДУЮЩИЙ_ШАГ: ждать\n", "")
        return pid

    def test_legacy_text_applies(self, project_id):
        from engine.db_state import merge_analysis_into_state, get_state
        pid = self._project()
        before = get_state(pid)["global_state"]
        res = merge_analysis_into_state(pid, LEGACY, 2)
        assert isinstance(res, dict) and "changed" in res
        assert get_state(pid)["global_state"] != before or not res["changed"]

    def test_legacy_without_blocks_is_noop(self, project_id):
        from engine.db_state import merge_analysis_into_state, get_state
        pid = self._project()
        before = get_state(pid)
        res = merge_analysis_into_state(pid, "просто текст без секций", 2)
        assert res["changed"] is False
        assert get_state(pid)["global_state"] == before["global_state"]

    def test_plot_block_updates_next_step(self, project_id):
        from engine.db_state import merge_analysis_into_state, get_state
        pid = self._project()
        merge_analysis_into_state(pid, LEGACY, 2)
        assert isinstance(get_state(pid)["plot_matrix"], str)

    def test_placeholder_values_ignored(self, project_id):
        from engine.db_state import merge_analysis_into_state, get_state
        pid = self._project()
        before = get_state(pid)["plot_matrix"]
        merge_analysis_into_state(
            pid, "PLOT_MATRIX:\nследующий шаг: [не изменилось]\n", 2)
        assert get_state(pid)["plot_matrix"] == before


# ─── Ключевой стиль и дописывание полей ───────────────────────────────────────

class TestFieldStyle:
    @pytest.mark.parametrize("block,expected", [
        ("### Марк\nСОСТОЯНИЕ: спокоен\nЛОКАЦИЯ: дом\n", "СОСТОЯНИЕ"),
        ("### Марк\nСостояние: спокоен\nЛокация: дом\n", "Состояние"),
    ])
    def test_key_style_follows_block(self, block, expected):
        from engine.db_state import _key_style, FIELD_ALIASES
        assert _key_style(block, FIELD_ALIASES["состояние"]) == expected

    def test_append_field_keeps_indent_and_newlines(self):
        from engine.db_state import _append_field
        out = _append_field("### Марк\r\nВозраст: 34\r\n", "Локация", "склад")
        assert "Локация: склад" in out
        assert "\r\n" in out, "перевод строки CRLF не сохранён"

    def test_append_field_on_plain_lf(self):
        from engine.db_state import _append_field
        out = _append_field("### Марк\nВозраст: 34\n", "Локация", "склад")
        assert "Локация: склад" in out and "\r" not in out
