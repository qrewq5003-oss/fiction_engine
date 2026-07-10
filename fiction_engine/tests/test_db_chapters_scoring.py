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
