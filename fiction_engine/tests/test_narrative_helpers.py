"""test_narrative_helpers.py — get_nil, get_narrative_metrics"""
import pytest


class TestGetNil:
    def test_returns_narrative_intelligence_instance(self):
        from engine.narrative_intelligence import get_nil, NarrativeIntelligence
        assert isinstance(get_nil(), NarrativeIntelligence)

    def test_singleton_returns_same_object(self):
        from engine.narrative_intelligence import get_nil
        assert get_nil() is get_nil()


class TestGetNarrativeMetrics:
    def test_returns_dict(self, project_id):
        from engine.narrative_intelligence import get_narrative_metrics
        assert isinstance(get_narrative_metrics(project_id, through_chapter=3), dict)

    def test_no_data_no_crash(self, project_id):
        from engine.narrative_intelligence import get_narrative_metrics
        assert isinstance(get_narrative_metrics(project_id, through_chapter=1), dict)
