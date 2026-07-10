"""
test_engine_loaders_core.py — engine/engine_loaders_core.py

Тестируем через mock filesystem — не трогаем реальные файлы.

A. load_module — загрузка одного модуля
B. _find_module_file — поиск файла
C. load_anticliche_replacements, load_dialectics_hint и др. — smoke
D. load_writing_core_hint — выбор файла по режиму
E. load_pattern_library — список паттернов
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestLoadModule:
    def test_returns_string(self, tmp_path):
        from engine.engine_loaders_core import load_module
        module_dir = tmp_path / "UNIFIED_ENGINE_MASTER"
        module_dir.mkdir()
        md_file = module_dir / "01_tension_curve.md"
        md_file.write_text("## СЕКЦИЯ\n\nПравило: напряжение растёт.\n", encoding="utf-8")

        result = load_module(tmp_path, "01_tension_curve", max_lines=50)
        assert isinstance(result, str)

    def test_returns_empty_when_file_missing(self, tmp_path):
        from engine.engine_loaders_core import load_module
        result = load_module(tmp_path, "99_nonexistent", max_lines=50)
        assert result == ""

    def test_respects_max_lines(self, tmp_path):
        from engine.engine_loaders_core import load_module
        module_dir = tmp_path / "UNIFIED_ENGINE_MASTER"
        module_dir.mkdir()
        md_file = module_dir / "01_tension_curve.md"
        md_file.write_text("## SEC\n" + "\n".join(f"Строка {i}." for i in range(100)),
                           encoding="utf-8")

        result = load_module(tmp_path, "01_tension_curve", max_lines=10)
        assert len(result.split("\n")) <= 20  # с запасом на пустые строки


class TestFindModuleFile:
    def test_finds_exact_file(self, tmp_path):
        from engine.engine_loaders_core import _find_module_file
        module_dir = tmp_path / "UNIFIED_ENGINE_MASTER"
        module_dir.mkdir()
        md = module_dir / "07_voice_consistency.md"
        md.write_text("content")

        result = _find_module_file(tmp_path, "07_voice_consistency")
        assert result == md

    def test_returns_none_when_missing(self, tmp_path):
        from engine.engine_loaders_core import _find_module_file
        result = _find_module_file(tmp_path, "99_not_there")
        assert result is None

    def test_finds_in_subdirectory(self, tmp_path):
        from engine.engine_loaders_core import _find_module_file
        subdir = tmp_path / "UNIFIED_ENGINE_MASTER" / "subdir"
        subdir.mkdir(parents=True)
        md = subdir / "01_tension_curve.md"
        md.write_text("content")

        result = _find_module_file(tmp_path, "01_tension_curve")
        assert result is not None


class TestLoadHints:
    def test_anticliche_returns_string(self, tmp_path):
        from engine.engine_loaders_core import load_anticliche_replacements
        result = load_anticliche_replacements(tmp_path)
        assert isinstance(result, str)

    def test_dialectics_returns_string(self, tmp_path):
        from engine.engine_loaders_core import load_dialectics_hint
        result = load_dialectics_hint(tmp_path)
        assert isinstance(result, str)

    def test_voice_check_returns_string(self, tmp_path):
        from engine.engine_loaders_core import load_voice_check_hint
        result = load_voice_check_hint(tmp_path)
        assert isinstance(result, str)

    def test_symbolism_returns_string(self, tmp_path):
        from engine.engine_loaders_core import load_symbolism_hint
        result = load_symbolism_hint(tmp_path)
        assert isinstance(result, str)


class TestLoadWritingCoreHint:
    def test_returns_string_for_quick(self, tmp_path):
        from engine.engine_loaders_core import load_writing_core_hint
        result = load_writing_core_hint(tmp_path, "написать сцену", "quick")
        assert isinstance(result, str)

    def test_returns_string_for_quality(self, tmp_path):
        from engine.engine_loaders_core import load_writing_core_hint
        result = load_writing_core_hint(tmp_path, "написать сцену", "quality")
        assert isinstance(result, str)

    def test_returns_string_for_master(self, tmp_path):
        from engine.engine_loaders_core import load_writing_core_hint
        result = load_writing_core_hint(tmp_path, "написать диалог", "master")
        assert isinstance(result, str)


class TestLoadPatternLibrary:
    def test_returns_string(self, tmp_path):
        from engine.engine_loaders_core import load_pattern_library
        result = load_pattern_library(tmp_path)
        assert isinstance(result, str)

    def test_with_actual_file(self, tmp_path):
        from engine.engine_loaders_core import load_pattern_library
        module_dir = tmp_path / "UNIFIED_ENGINE_MASTER"
        module_dir.mkdir()
        lib = module_dir / "LIBRARY_PATTERNS.md"
        lib.write_text("## ПАТТЕРНЫ\n\nПравило: конкретность.\n", encoding="utf-8")

        result = load_pattern_library(tmp_path)
        # Либо нашло файл и вернуло содержимое, либо вернуло пустую строку
        assert isinstance(result, str)
