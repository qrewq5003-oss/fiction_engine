"""
test_peak_finales.py — engine/peak_finales.py

A. get_peak_finale — возврат техники по источнику
B. get_all_sources — список всех источников
"""
import pytest


class TestGetPeakFinale:
    def test_known_source_returns_string(self):
        from engine.peak_finales import get_peak_finale, get_all_sources
        sources = get_all_sources()
        if not sources:
            pytest.skip("no sources defined")
        result = get_peak_finale(sources[0])
        assert isinstance(result, str)

    def test_unknown_source_returns_none(self):
        from engine.peak_finales import get_peak_finale
        result = get_peak_finale("nonexistent_source_xyz_123")
        assert result is None

    def test_empty_source_returns_none(self):
        from engine.peak_finales import get_peak_finale
        result = get_peak_finale("")
        assert result is None

    def test_result_nonempty_for_valid_source(self):
        from engine.peak_finales import get_peak_finale, get_all_sources
        sources = get_all_sources()
        if not sources:
            pytest.skip("no sources defined")
        result = get_peak_finale(sources[0])
        if result is not None:
            assert len(result.strip()) > 0


class TestGetAllSources:
    def test_returns_list(self):
        from engine.peak_finales import get_all_sources
        result = get_all_sources()
        assert isinstance(result, list)

    def test_each_item_is_string(self):
        from engine.peak_finales import get_all_sources
        for source in get_all_sources():
            assert isinstance(source, str)

    def test_no_duplicates(self):
        from engine.peak_finales import get_all_sources
        sources = get_all_sources()
        assert len(sources) == len(set(sources))
