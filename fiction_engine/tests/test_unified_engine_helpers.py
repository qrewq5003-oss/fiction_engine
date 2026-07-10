"""test_unified_engine_helpers.py — get_active_modules, build_engine_context, get_all_genre_options"""
import pytest
from unittest.mock import patch


class TestGetActiveModules:
    def test_returns_list(self):
        from engine.unified_engine import get_active_modules
        assert isinstance(get_active_modules("фэнтези"), list)

    def test_nonempty_for_known_genre(self):
        from engine.unified_engine import get_active_modules
        assert len(get_active_modules("фэнтези", mode="quick")) > 0

    def test_no_duplicates(self):
        from engine.unified_engine import get_active_modules
        modules = get_active_modules("детектив", mode="quality")
        assert len(modules) == len(set(modules))

    def test_each_item_is_string(self):
        from engine.unified_engine import get_active_modules
        for m in get_active_modules("триллер", mode="master"):
            assert isinstance(m, str)

    def test_unknown_genre_no_crash(self):
        from engine.unified_engine import get_active_modules
        result = get_active_modules("абракадабра xyz", mode="quick")
        assert isinstance(result, list)

    def test_master_at_least_as_many_as_quick(self):
        from engine.unified_engine import get_active_modules
        quick  = get_active_modules("фэнтези", mode="quick")
        master = get_active_modules("фэнтези", mode="master")
        assert len(master) >= len(quick)


class TestBuildEngineContext:
    def test_empty_string_when_engine_unavailable(self):
        from engine.unified_engine import build_engine_context
        with patch("engine.unified_engine.engine_available", return_value=False):
            assert build_engine_context("фэнтези", mode="quick") == ""

    def test_returns_string_type(self):
        from engine.unified_engine import build_engine_context
        with patch("engine.unified_engine.engine_available", return_value=False):
            assert isinstance(build_engine_context("детектив", mode="quality"), str)


class TestGetAllGenreOptions:
    def test_returns_list(self):
        from engine.unified_engine import get_all_genre_options
        assert isinstance(get_all_genre_options(), list)

    def test_empty_when_engine_unavailable(self):
        from engine.unified_engine import get_all_genre_options
        with patch("engine.unified_engine.engine_available", return_value=False):
            assert get_all_genre_options() == []

    def test_each_item_has_key_label_when_available(self):
        from engine.unified_engine import get_all_genre_options, engine_available
        if not engine_available():
            pytest.skip("engine not installed")
        for item in get_all_genre_options():
            assert "key" in item and "label" in item
