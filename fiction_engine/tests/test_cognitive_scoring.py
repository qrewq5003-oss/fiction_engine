"""test_cognitive_scoring.py — score_summary, chapter_total_score"""
import pytest


def _s(**kw):
    base = dict(events="", characters="", conflicts="", promises="", mood="")
    base.update(kw)
    return base


class TestScoreSummary:
    def test_empty_returns_empty_dict(self):
        from engine.cognitive_memory import score_summary
        assert score_summary(_s(), distance=1) == {}

    def test_nonempty_field_gets_positive_score(self):
        from engine.cognitive_memory import score_summary
        r = score_summary(_s(events="событие"), distance=1)
        assert "events" in r and r["events"] > 0

    def test_only_nonempty_fields_scored(self):
        from engine.cognitive_memory import score_summary
        r = score_summary(_s(events="событие"), distance=1)
        assert "events" in r
        for k in ("characters","conflicts","promises","mood"):
            assert k not in r

    def test_closer_chapter_scores_higher(self):
        from engine.cognitive_memory import score_summary
        near = score_summary(_s(promises="вернётся"), distance=1)
        far  = score_summary(_s(promises="вернётся"), distance=15)
        assert near.get("promises", 0) >= far.get("promises", 0)

    def test_all_five_fields_when_filled(self):
        from engine.cognitive_memory import score_summary
        r = score_summary(_s(events="е",characters="п",conflicts="к",promises="о",mood="т"),
                          distance=1)
        assert len(r) == 5


class TestChapterTotalScore:
    def test_empty_is_zero(self):
        from engine.cognitive_memory import chapter_total_score
        assert chapter_total_score(_s(), distance=1) == pytest.approx(0.0)

    def test_filled_is_positive(self):
        from engine.cognitive_memory import chapter_total_score
        assert chapter_total_score(_s(events="е", promises="о"), distance=1) > 0

    def test_returns_float(self):
        from engine.cognitive_memory import chapter_total_score
        assert isinstance(chapter_total_score(_s(events="х"), distance=2), (int, float))

    def test_near_chapter_heavier_than_far(self):
        from engine.cognitive_memory import chapter_total_score
        s = _s(events="е", promises="о")
        assert chapter_total_score(s, 1) >= chapter_total_score(s, 10)
