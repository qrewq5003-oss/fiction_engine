"""test_db_chapters_scoring.py — save_chapter_score, get_judge_score_history, format_score_history"""
import pytest


class TestSaveChapterScore:
    def test_returns_true_on_success(self, project_id):
        from engine.db_chapters import save_chapter_score
        result = save_chapter_score(project_id, 1,
                                    {"total": 7.5, "literary_quality": 8})
        assert result is True

    def test_overwrites_on_duplicate(self, project_id):
        from engine.db_chapters import save_chapter_score
        save_chapter_score(project_id, 1, {"total": 6.0})
        result = save_chapter_score(project_id, 1, {"total": 8.0})
        assert result is True   # no crash, upsert


class TestGetJudgeScoreHistory:
    def test_empty_initially(self, project_id):
        from engine.db_chapters import get_judge_score_history
        assert get_judge_score_history(project_id) == []

    def test_returns_list_of_dicts(self, project_id):
        from engine.db_chapters import get_judge_score_history
        assert isinstance(get_judge_score_history(project_id, n=10), list)

    def test_max_score_per_chapter(self, project_id):
        from engine.db import create_pipeline_run, save_pipeline_iteration
        from engine.db_chapters import get_judge_score_history
        run = create_pipeline_run(project_id, 1, "m","m","m","m")
        save_pipeline_iteration(run, 1, "judge", "m", "p", "t", score=35.0)
        save_pipeline_iteration(run, 2, "judge", "m", "p", "t", score=42.0)
        h = get_judge_score_history(project_id)
        assert len(h) == 1 and h[0]["score"] == pytest.approx(42.0)

    def test_n_limit_honoured(self, project_id):
        from engine.db import create_pipeline_run, save_pipeline_iteration
        from engine.db_chapters import get_judge_score_history
        for ch in range(1, 12):
            r = create_pipeline_run(project_id, ch, "m","m","m","m")
            save_pipeline_iteration(r, 1, "judge", "m", "p", "t", score=float(ch*3))
        assert len(get_judge_score_history(project_id, n=5)) <= 5

    def test_only_judge_stage_counted(self, project_id):
        from engine.db import create_pipeline_run, save_pipeline_iteration
        from engine.db_chapters import get_judge_score_history
        r = create_pipeline_run(project_id, 1, "m","m","m","m")
        save_pipeline_iteration(r, 1, "critique", "m", "p", "t", score=99.0)
        h = get_judge_score_history(project_id)
        assert h == []


class TestFormatScoreHistory:
    def test_empty_history_empty_string(self):
        from engine.db_chapters import format_score_history
        assert format_score_history([], current_chapter=5) == ""

    def test_none_scores_empty_string(self):
        from engine.db_chapters import format_score_history
        assert format_score_history([{"chapter_num":1,"score":None}], 2) == ""

    def test_contains_average(self):
        from engine.db_chapters import format_score_history
        h = [{"chapter_num":1,"score":30.0},
             {"chapter_num":2,"score":40.0},
             {"chapter_num":3,"score":35.0}]
        r = format_score_history(h, current_chapter=4)
        assert "35.0" in r

    def test_contains_best_score(self):
        from engine.db_chapters import format_score_history
        h = [{"chapter_num":1,"score":28.0},{"chapter_num":2,"score":45.0}]
        r = format_score_history(h, current_chapter=3)
        assert "45" in r

    def test_single_entry_no_crash(self):
        from engine.db_chapters import format_score_history
        r = format_score_history([{"chapter_num":1,"score":38.0}], 2)
        assert isinstance(r, str) and "38" in r

    def test_only_earlier_chapters_and_last_is_latest(self):
        """Обход 20.10: судье гл.12 — «Лучший: 34 (гл.23)», «Последний» — самая ранняя глава окна."""
        from engine.db_chapters import format_score_history
        h = [{"chapter_num": 23, "score": 34.0}, {"chapter_num": 12, "score": 29.0},
             {"chapter_num": 11, "score": 31.0}, {"chapter_num": 9, "score": 33.0}]
        r = format_score_history(h, current_chapter=12)
        assert "гл.23" not in r and "гл.12" not in r
        assert "Лучший: 33.0/50 (гл.9)" in r and "Последний: 31.0/50 (гл.11)" in r


def test_history_before_chapter(project_id):
    from engine.db import create_pipeline_run, save_pipeline_iteration
    from engine.db_chapters import get_judge_score_history
    for ch in (1, 2, 3, 4):
        save_pipeline_iteration(create_pipeline_run(project_id, ch, "m", "m", "m", "m"),
                                1, "judge", "m", "p", "t", score=30.0 + ch)
    assert [h["chapter_num"] for h in get_judge_score_history(project_id, before_chapter=3)] == [2, 1]
