"""
test_engine_extractors.py — engine/engine_extractors.py

Покрываем все 4 функции:
  A. _is_valuable — фильтр содержательных строк
  B. _extract_mini_section — извлечение MINI-блока
  C. _extract_body_lines — извлечение тела модуля
  D. _extract_module_essence — главная точка входа (quick / quality / master)
"""

import pytest


class TestIsValuable:
    """A. _is_valuable — строка несёт практическую ценность."""

    def test_empty_false(self):
        from engine.engine_extractors import _is_valuable
        assert _is_valuable("") is False

    def test_whitespace_false(self):
        from engine.engine_extractors import _is_valuable
        assert _is_valuable("   ") is False

    def test_emoji_true(self):
        from engine.engine_extractors import _is_valuable
        assert _is_valuable("❌ Не делай так") is True

    def test_zapreshcheno_true(self):
        from engine.engine_extractors import _is_valuable
        assert _is_valuable("Запрещено: называть эмоцию напрямую") is True

    def test_pravilo_true(self):
        from engine.engine_extractors import _is_valuable
        assert _is_valuable("Правило: показывай, не называй") is True

    def test_nelzya_true(self):
        from engine.engine_extractors import _is_valuable
        assert _is_valuable("Нельзя допускать этого") is True

    def test_h2_header_false(self):
        from engine.engine_extractors import _is_valuable
        # ## заголовки — SKIP_PATTERNS
        assert _is_valuable("## ФИЛОСОФИЯ") is False

    def test_version_line_false(self):
        from engine.engine_extractors import _is_valuable
        assert _is_valuable("Версия 2.0") is False


class TestExtractMiniSection:
    """B. _extract_mini_section."""

    def test_no_mini_returns_empty(self):
        from engine.engine_extractors import _extract_mini_section
        assert _extract_mini_section("## ФИЛОСОФИЯ\n\nТекст без MINI.\n") == ""

    def test_double_marker_extracted(self):
        from engine.engine_extractors import _extract_mini_section
        content = (
            "## ФИЛОСОФИЯ\n\nОписание.\n\n"
            "## ## MINI\n\n"
            "Правило: показывай.\nЗапрещено: называть.\n"
        )
        result = _extract_mini_section(content)
        assert "Правило: показывай" in result
        assert "## ## MINI" not in result

    def test_single_marker_extracted(self):
        from engine.engine_extractors import _extract_mini_section
        content = "## АРХИТЕКТУРА\n\nТекст.\n\n## MINI\n\nКлючевой принцип.\n"
        assert "Ключевой принцип" in _extract_mini_section(content)

    def test_code_blocks_excluded_from_mini(self):
        from engine.engine_extractors import _extract_mini_section
        content = (
            "## ## MINI\n\n"
            "Правило первое.\n"
            "```\nкод не попадает\n```\n"
            "Правило второе.\n"
        )
        result = _extract_mini_section(content)
        assert "Правило первое" in result
        assert "Правило второе" in result
        assert "код не попадает" not in result

    def test_double_marker_priority_over_single(self):
        """## ## MINI ищется первым и выигрывает."""
        from engine.engine_extractors import _extract_mini_section
        content = (
            "## MINI\n\nОдиночный — не должен выбраться.\n\n"
            "## ## MINI\n\nДвойной — должен выбраться.\n"
        )
        assert "Двойной" in _extract_mini_section(content)


class TestExtractBodyLines:
    """C. _extract_body_lines."""

    def test_respects_max_lines(self):
        from engine.engine_extractors import _extract_body_lines
        content = "## РАЗДЕЛ\n" + "\n".join(f"Строка {i}." for i in range(200))
        result = _extract_body_lines(content, max_lines=10)
        # небольшой допуск на пустые строки
        assert len(result.split("\n")) <= 15

    def test_skips_mini_section(self):
        from engine.engine_extractors import _extract_body_lines
        content = (
            "## РАЗДЕЛ\nДо MINI.\n"
            "## ## MINI\nСодержимое MINI.\n"
        )
        result = _extract_body_lines(content, max_lines=50)
        assert "Содержимое MINI" not in result

    def test_skips_code_blocks(self):
        from engine.engine_extractors import _extract_body_lines
        content = (
            "## РАЗДЕЛ\nДо кода.\n"
            "```\nкод не попадает\n```\n"
            "После кода.\n"
        )
        result = _extract_body_lines(content, max_lines=50)
        assert "код не попадает" not in result
        assert "После кода" in result

    def test_ignores_content_before_first_header(self):
        from engine.engine_extractors import _extract_body_lines
        content = "Метаданные\nВерсия 2.0\n## РАЗДЕЛ\nРеальный контент.\n"
        result = _extract_body_lines(content, max_lines=50)
        assert "Метаданные" not in result
        assert "Реальный контент" in result

    def test_collapses_double_empty_lines(self):
        from engine.engine_extractors import _extract_body_lines
        content = "## РАЗДЕЛ\nСтрока.\n\n\n\nДругая строка.\n"
        result = _extract_body_lines(content, max_lines=50)
        assert "\n\n\n" not in result


class TestExtractModuleEssence:
    """D. _extract_module_essence — главная точка входа."""

    def _module_with_mini(self, mini_lines=8, body_lines=40):
        mini = "\n".join(f"Правило {i}: делай X." for i in range(mini_lines))
        body = "\n".join(f"Строка тела {i}." for i in range(body_lines))
        return (
            "## ФИЛОСОФИЯ\nАрхитектурное описание.\n\n"
            f"## ## MINI\n\n{mini}\n\n"
            f"## ДЕТАЛИ\n\n{body}\n"
        )

    def test_quick_uses_mini(self):
        """max_lines<=35, MINI>=5 строк → только MINI, тело не добавляется."""
        from engine.engine_extractors import _extract_module_essence
        result = _extract_module_essence(self._module_with_mini(mini_lines=8), max_lines=30)
        assert "Правило 0" in result
        assert "Строка тела" not in result

    def test_quick_fallback_when_mini_short(self):
        """max_lines<=35, MINI<5 строк → fallback на начало файла."""
        from engine.engine_extractors import _extract_module_essence
        content = (
            "## ФИЛОСОФИЯ\n"
            "Ключевой принцип.\nВажное правило.\n\n"
            "## ## MINI\nДве строки.\n"
        )
        result = _extract_module_essence(content, max_lines=30)
        assert result != ""

    def test_quality_combines_mini_and_body(self):
        """max_lines>35, MINI>=5 → MINI + тело."""
        from engine.engine_extractors import _extract_module_essence
        result = _extract_module_essence(self._module_with_mini(), max_lines=60)
        assert "Правило 0" in result
        assert "Строка тела" in result

    def test_quality_respects_max_lines(self):
        """Результат не превышает max_lines в 2 раза."""
        from engine.engine_extractors import _extract_module_essence
        result = _extract_module_essence(self._module_with_mini(body_lines=200), max_lines=50)
        assert len(result.split("\n")) <= 80

    def test_no_mini_returns_body(self):
        """Нет MINI, quality режим → тело файла."""
        from engine.engine_extractors import _extract_module_essence
        content = "## РАЗДЕЛ\n" + "\n".join(f"Строка {i}." for i in range(60))
        result = _extract_module_essence(content, max_lines=50)
        assert "Строка 0" in result

    def test_empty_content_returns_empty(self):
        from engine.engine_extractors import _extract_module_essence
        assert _extract_module_essence("", max_lines=30) == ""

    def test_only_metadata_no_header_returns_empty(self):
        """Нет ## заголовка — skip_header не сбрасывается, возвращаем пустоту."""
        from engine.engine_extractors import _extract_module_essence
        assert _extract_module_essence("Версия 2.0\nСтатус: READY\n", max_lines=30) == ""

    def test_architecture_text_excluded(self):
        """Архитектурные заголовки в теле не попадают как контент."""
        from engine.engine_extractors import _extract_module_essence
        content = (
            "## ФИЛОСОФИЯ\n"
            "## ## MINI\n"
            "Правило: показывай.\n" * 8
        )
        result = _extract_module_essence(content, max_lines=30)
        assert "## ## MINI" not in result
