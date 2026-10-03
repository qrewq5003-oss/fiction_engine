"""
test_engine_extractors.py — engine/engine_extractors.py

Секции PROMPT модулей и чистка шума: служебные разделы, пустые
заголовки, жанровые варианты чужих жанров.
"""

import pytest


# ─── Очистка от шума (улучшение 4а, AUDIT_UNIFIED.md U3) ─────────────────────

class TestStripMetaSections:
    def test_meta_section_removed_whole(self):
        from engine.engine_extractors import _strip_meta_sections
        src = ("# Модуль\n## 🎯 НАЗНАЧЕНИЕ\nсистема рекомендует\n### Подраздел\nещё\n"
               "## ПРАВИЛА\nпиши коротко\n")
        out = _strip_meta_sections(src)
        assert "система рекомендует" not in out and "ещё" not in out
        assert "## ПРАВИЛА\nпиши коротко" in out

    def test_mini_is_not_meta(self):
        from engine.engine_extractors import _strip_meta_sections
        src = "## MINI (QUICK режим)\nсуть\n## ИНТЕГРАЦИЯ\nсвязи\n"
        assert _strip_meta_sections(src).strip() == "## MINI (QUICK режим)\nсуть"


class TestDropEmptyHeadings:
    def test_heading_with_code_stripped_body_removed(self):
        from engine.engine_extractors import drop_empty_headings
        src = "**Формула усталости:**\n\n### Следующий\nтекст"
        assert drop_empty_headings(src) == "### Следующий\nтекст"

    def test_parent_with_filled_subsection_kept(self):
        from engine.engine_extractors import drop_empty_headings
        src = "## Раздел\n### Подраздел\nтекст"
        assert drop_empty_headings(src) == src

    def test_parent_emptied_by_children_removed(self):
        from engine.engine_extractors import drop_empty_headings
        src = "## Раздел\n### Пусто\n**Метка:**\n---\n## Другой\nтекст"
        assert drop_empty_headings(src) == "---\n## Другой\nтекст"

    def test_bold_label_with_inline_text_is_not_heading(self):
        from engine.engine_extractors import drop_empty_headings
        src = "**Правило:** пиши коротко"
        assert drop_empty_headings(src) == src


class TestFilterGenreVariants:
    SRC = ("### Жанровые варианты\n"
           "**ДЕТЕКТИВ/НУАР:** улики\n\n**ХОРРОР:** страх\n\n"
           "**РОМАНТИКА:** химия\n**Правило:** общее")

    def test_keeps_own_family_and_non_genre_labels(self):
        from engine.engine_extractors import filter_genre_variants
        out = filter_genre_variants(self.SRC, "detective_noir")
        assert "улики" in out and "**Правило:** общее" in out
        assert "страх" not in out and "химия" not in out

    def test_unknown_genre_keeps_all(self):
        from engine.engine_extractors import filter_genre_variants
        assert filter_genre_variants(self.SRC, None) == self.SRC


class TestPromptSections:
    SRC = ("# Модуль\n\n## PROMPT:QUICK\n<!-- для автора -->\nядро\n\n"
           "## PROMPT:FULL\nдополнение\n\n---\n\n## НАЗНАЧЕНИЕ\nсистема\n")

    def test_quick_only_core(self):
        from engine.engine_extractors import extract_prompt_sections
        assert extract_prompt_sections(self.SRC, full=False) == "ядро"

    def test_full_is_core_plus_extra(self):
        from engine.engine_extractors import extract_prompt_sections
        assert extract_prompt_sections(self.SRC, full=True) == "ядро\n\nдополнение"

    def test_absent_falls_back(self):
        from engine.engine_extractors import extract_prompt_sections
        assert extract_prompt_sections("## MINI\nсуть", full=True) is None

    def test_essence_ignores_line_limit_for_explicit_sections(self):
        from engine.engine_extractors import _extract_module_essence
        src = "## PROMPT:QUICK\n" + "\n".join(f"строка {i}" for i in range(50))
        assert _extract_module_essence(src, 30).count("строка") == 50

    def test_essence_without_sections_is_empty(self):
        """Прежний разбор MINI и тела убран: без секций модуль не идёт в промпт."""
        from engine.engine_extractors import _extract_module_essence
        src = "## MINI\n" + "Правило: показывай.\n" * 8
        assert _extract_module_essence(src, 70) == ""
