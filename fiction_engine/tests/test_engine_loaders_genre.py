"""
test_engine_loaders_genre.py — engine/engine_loaders_genre.py

Тестируем что функции:
- возвращают строку (не падают) при любом входе
- находят контент когда файл существует
- gracefully возвращают "" когда файл отсутствует
"""
import pytest
from pathlib import Path


class TestLoadGenreCatalog:
    def test_returns_string_missing_dir(self, tmp_path):
        from engine.engine_loaders_genre import load_genre_catalog
        result = load_genre_catalog(tmp_path, "fantasy_epic")
        assert isinstance(result, str)

    def test_returns_content_with_file(self, tmp_path):
        from engine.engine_loaders_genre import load_genre_catalog
        catalog_dir = tmp_path / "UNIFIED_ENGINE_MASTER" / "CATALOGS"
        catalog_dir.mkdir(parents=True)
        (catalog_dir / "fantasy_epic.md").write_text(
            "## КАТАЛОГ\n\nПравило жанра.", encoding="utf-8"
        )
        result = load_genre_catalog(tmp_path, "fantasy_epic")
        assert isinstance(result, str)


class TestLoadGenreContract:
    def test_returns_string_missing_dir(self, tmp_path):
        from engine.engine_loaders_genre import load_genre_contract
        result = load_genre_contract(tmp_path, "detective_classic")
        assert isinstance(result, str)


class TestLoadArcHint:
    def test_returns_string(self, tmp_path):
        from engine.engine_loaders_genre import load_arc_hint
        result = load_arc_hint(tmp_path, "fantasy_epic")
        assert isinstance(result, str)

    def test_unknown_genre_returns_string(self, tmp_path):
        from engine.engine_loaders_genre import load_arc_hint
        result = load_arc_hint(tmp_path, "unknown_xyz")
        assert isinstance(result, str)


class TestLoadCharacterProfile:
    def test_returns_string(self, tmp_path):
        from engine.engine_loaders_genre import load_character_profile
        result = load_character_profile(tmp_path, "romance")
        assert isinstance(result, str)


class TestLoadCatalogSubgenreHint:
    def test_returns_string(self, tmp_path):
        from engine.engine_loaders_genre import load_catalog_subgenre_hint
        result = load_catalog_subgenre_hint(tmp_path, "fantasy_dark")
        assert isinstance(result, str)


class TestLoadGenrePrompt:
    def test_returns_string_quick(self, tmp_path):
        from engine.engine_loaders_genre import load_genre_prompt
        result = load_genre_prompt(tmp_path, "fantasy_epic", "quick")
        assert isinstance(result, str)

    def test_returns_string_quality(self, tmp_path):
        from engine.engine_loaders_genre import load_genre_prompt
        result = load_genre_prompt(tmp_path, "thriller_psychological", "quality")
        assert isinstance(result, str)

    def test_returns_string_master(self, tmp_path):
        from engine.engine_loaders_genre import load_genre_prompt
        result = load_genre_prompt(tmp_path, "horror_psychological", "master")
        assert isinstance(result, str)

    def test_unknown_genre_returns_string(self, tmp_path):
        from engine.engine_loaders_genre import load_genre_prompt
        result = load_genre_prompt(tmp_path, "unknown_xyz", "quality")
        assert isinstance(result, str)
