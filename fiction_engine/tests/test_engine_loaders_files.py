#!/usr/bin/env python3
"""
Загрузчики блоков движка против НАСТОЯЩЕЙ базы знаний.

Перенесено из run_tests.py при слиянии наборов: pytest-тесты работали
с временными каталогами и не доходили до веток разбора реальных файлов —
103 строки engine_loaders_core и 44 строки engine_loaders_genre были
покрыты только автономным раннером.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


@pytest.fixture(scope="module")
def kb() -> Path:
    """Путь к UNIFIED_ENGINE_MASTER; тесты пропускаются, если базы нет."""
    from engine.engine_loaders import get_engine_path, engine_available
    if not engine_available():
        pytest.skip("UNIFIED_ENGINE_MASTER недоступен")
    return get_engine_path()


# ─── 06_PATTERN_LIBRARY ───────────────────────────────────────────────────────

class TestPatternLibrary:
    @pytest.mark.parametrize("genre", ["detective_classic", "fantasy_epic",
                                       "horror_gothic", "romance_contemporary"])
    def test_returns_content_for_known_genres(self, kb, genre):
        from engine.engine_loaders_core import load_pattern_library
        out = load_pattern_library(kb, genre, "quality")
        assert isinstance(out, str) and out.strip()

    def test_mode_affects_volume(self, kb):
        from engine.engine_loaders_core import load_pattern_library
        quick = load_pattern_library(kb, "detective_classic", "quick")
        master = load_pattern_library(kb, "detective_classic", "master")
        assert len(master) >= len(quick)

    def test_task_text_pulls_situations(self, kb):
        from engine.engine_loaders_core import load_pattern_library
        out = load_pattern_library(kb, "detective_classic", "master",
                                   task_text="допрос свидетеля и поиск улик")
        assert isinstance(out, str)

    def test_unknown_genre_does_not_crash(self, kb):
        from engine.engine_loaders_core import load_pattern_library
        assert isinstance(load_pattern_library(kb, "нет_такого", "quick"), str)

    def test_missing_dir_returns_empty(self, tmp_path):
        from engine.engine_loaders_core import load_pattern_library
        assert load_pattern_library(tmp_path, "detective_classic", "quick") == ""


# ─── 01_WRITING_CORE ──────────────────────────────────────────────────────────

class TestWritingCoreHint:
    @pytest.mark.parametrize("task,mode", [
        ("написать диалог двух героев", "quick"),
        ("описать комнату и атмосферу", "quality"),
        ("сцена драки на крыше", "master"),
        ("показать страх героя", "master"),
    ])
    def test_picks_files_by_keywords(self, kb, task, mode):
        from engine.engine_loaders_core import load_writing_core_hint
        assert isinstance(load_writing_core_hint(kb, task, mode), str)

    def test_empty_task_returns_empty(self, kb):
        from engine.engine_loaders_core import load_writing_core_hint
        assert load_writing_core_hint(kb, "", "quality") == ""

    def test_missing_dir_returns_empty(self, tmp_path):
        from engine.engine_loaders_core import load_writing_core_hint
        assert load_writing_core_hint(tmp_path, "диалог", "quick") == ""


# ─── Универсальные подсказки ──────────────────────────────────────────────────

class TestHints:
    def test_symbolism(self, kb):
        from engine.engine_loaders_core import load_symbolism_hint
        assert load_symbolism_hint(kb).strip()

    def test_voice_check(self, kb):
        from engine.engine_loaders_core import load_voice_check_hint
        assert load_voice_check_hint(kb).strip()

    def test_dialectics(self, kb):
        from engine.engine_loaders_core import load_dialectics_hint
        assert isinstance(load_dialectics_hint(kb), str)

    def test_anticliche(self, kb):
        from engine.engine_loaders_core import load_anticliche_replacements
        assert load_anticliche_replacements(kb).strip()

    @pytest.mark.parametrize("fn_name", ["load_symbolism_hint", "load_voice_check_hint",
                                          "load_dialectics_hint",
                                          "load_anticliche_replacements"])
    def test_missing_files_return_empty(self, tmp_path, fn_name):
        import engine.engine_loaders_core as core
        assert getattr(core, fn_name)(tmp_path) == ""


# ─── 10_VALIDATION ────────────────────────────────────────────────────────────

class TestValidationChecklist:
    @pytest.mark.parametrize("genre", ["detective_classic", "fantasy_epic",
                                       "horror_gothic", "scifi_hard",
                                       "romance_contemporary", "thriller_spy",
                                       "realism_social", None])
    def test_universal_plus_genre(self, kb, genre):
        from engine.engine_loaders_core import load_validation_checklist
        out = load_validation_checklist(kb, genre)
        assert isinstance(out, str) and out.strip()

    def test_max_lines_limits_output(self, kb):
        from engine.engine_loaders_core import load_validation_checklist
        short = load_validation_checklist(kb, "detective_classic", max_lines=5)
        long = load_validation_checklist(kb, "detective_classic", max_lines=60)
        assert len(short.split("\n")) <= len(long.split("\n"))

    def test_missing_dir_returns_empty(self, tmp_path):
        from engine.engine_loaders_core import load_validation_checklist
        assert load_validation_checklist(tmp_path, "detective_classic") == ""


# ─── _read_md_useful ──────────────────────────────────────────────────────────

class TestReadMdUseful:
    def test_keeps_block_content_drops_fences(self, tmp_path):
        """
        Содержимое ``` -блоков сохраняется, ограждения убираются.

        Это намеренно: в базе знаний внутри блоков лежат примеры прозы
        «✅ ХОРОШО / ❌ ПЛОХО» — их 579 против 457 технических блоков.
        """
        from engine.engine_loaders_core import _read_md_useful
        f = tmp_path / "m.md"
        f.write_text(
            "## ШАПКА\n"
            "Полезная строка один.\n"
            "```\n✅ ХОРОШО:\n— Ты опоздал.\n```\n"
            "Полезная строка два.\n",
            encoding="utf-8",
        )
        joined = "\n".join(_read_md_useful(f, max_lines=20))
        assert "— Ты опоздал." in joined, "пример прозы потерян"
        assert "```" not in joined, "ограждение блока не убрано"
        assert "Полезная строка два." in joined

    def test_respects_max_lines(self, tmp_path):
        from engine.engine_loaders_core import _read_md_useful
        f = tmp_path / "m.md"
        f.write_text("## ШАПКА\n" + "\n".join(f"строка {i}" for i in range(50)),
                     encoding="utf-8")
        assert len(_read_md_useful(f, max_lines=7)) <= 7

    def test_real_module_file(self, kb):
        from engine.engine_loaders_core import _read_md_useful
        f = kb / "00_CORE" / "style_rules.md"
        if not f.exists():
            pytest.skip("файл не найден")
        assert _read_md_useful(f, max_lines=20)


# ─── Жанровые загрузчики ──────────────────────────────────────────────────────

class TestGenreLoaders:
    @pytest.mark.parametrize("genre", ["detective_classic", "fantasy_epic",
                                       "horror_gothic", "scifi_hard",
                                       "romance_contemporary", "thriller_spy"])
    def test_contract(self, kb, genre):
        from engine.engine_loaders_genre import load_genre_contract
        assert isinstance(load_genre_contract(kb, genre), str)

    @pytest.mark.parametrize("genre", ["fantasy_epic", "fantasy_urban",
                                       "detective_classic", "horror_gothic"])
    def test_arc_hint(self, kb, genre):
        from engine.engine_loaders_genre import load_arc_hint
        assert isinstance(load_arc_hint(kb, genre), str)

    @pytest.mark.parametrize("genre", ["detective_classic", "fantasy_epic",
                                       "horror_gothic", "romance_contemporary"])
    def test_character_profile(self, kb, genre):
        from engine.engine_loaders_genre import load_character_profile
        assert isinstance(load_character_profile(kb, genre), str)

    @pytest.mark.parametrize("genre", ["detective_classic", "fantasy_epic",
                                       "horror_gothic"])
    @pytest.mark.parametrize("mode", ["quick", "quality", "master"])
    def test_genre_prompt(self, kb, genre, mode):
        from engine.engine_loaders_genre import load_genre_prompt
        assert isinstance(load_genre_prompt(kb, genre, mode), str)

    @pytest.mark.parametrize("genre", ["detective_classic", "fantasy_urban",
                                       "horror_gothic", "scifi_cyberpunk"])
    def test_catalog(self, kb, genre):
        from engine.engine_loaders_genre import load_genre_catalog
        assert isinstance(load_genre_catalog(kb, genre), str)

    def test_subgenre_hint(self, kb):
        from engine.engine_loaders_genre import load_catalog_subgenre_hint
        assert isinstance(load_catalog_subgenre_hint(kb, "fantasy_urban"), str)

    def test_missing_engine_returns_empty(self, tmp_path):
        import engine.engine_loaders_genre as g
        for fn in ("load_genre_contract", "load_arc_hint",
                   "load_character_profile", "load_genre_catalog"):
            assert getattr(g, fn)(tmp_path, "detective_classic") == ""
