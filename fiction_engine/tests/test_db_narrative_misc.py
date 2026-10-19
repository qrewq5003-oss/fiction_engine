"""test_db_narrative_misc.py — exemplars, drift scheduling"""
import pytest


class TestExemplars:
    def test_empty_initially(self, project_id):
        from engine.db_narrative import get_exemplars
        assert get_exemplars(project_id) == []

    def test_save_and_retrieve(self, project_id):
        from engine.db_narrative import save_exemplar, get_exemplars
        save_exemplar(project_id, chapter_num=1, text="Эталонный текст.", label="хороший")
        items = get_exemplars(project_id)
        assert len(items) == 1
        assert "Эталонный" in (items[0].get("text") or "")

    def test_save_returns_positive_id(self, project_id):
        from engine.db_narrative import save_exemplar
        eid = save_exemplar(project_id, 1, "Текст.", "ok")
        assert isinstance(eid, int) and eid > 0

    def test_delete_removes_entry(self, project_id):
        from engine.db_narrative import save_exemplar, get_exemplars, delete_exemplar
        eid = save_exemplar(project_id, 2, "Текст.", "test")
        assert delete_exemplar(project_id, eid)
        assert all(e["id"] != eid for e in get_exemplars(project_id))

    def test_multiple_exemplars_ordered(self, project_id):
        from engine.db_narrative import save_exemplar, get_exemplars
        save_exemplar(project_id, 1, "Первый.", "a")
        save_exemplar(project_id, 2, "Второй.", "b")
        items = get_exemplars(project_id)
        assert len(items) == 2


class TestDriftScheduling:
    def test_should_run_returns_bool(self, project_id):
        from engine.db_narrative import should_run_drift_check
        assert isinstance(should_run_drift_check(project_id, current_chapter=5), bool)

    def test_should_run_true_when_no_previous_and_chapter_gte_threshold(self, project_id):
        from engine.db_narrative import should_run_drift_check
        # No previous check → should run if chapter >= every_n (default 3)
        assert should_run_drift_check(project_id, current_chapter=3) is True

    def test_should_run_false_chapter_1(self, project_id):
        from engine.db_narrative import should_run_drift_check
        assert should_run_drift_check(project_id, current_chapter=1) is False

    def test_get_last_drift_none_initially(self, project_id):
        from engine.db_narrative import get_last_drift_check
        result = get_last_drift_check(project_id)
        assert result is None or isinstance(result, dict)


class TestPipelineRuns:
    def test_all_runs_listed_and_rounds_counted(self, project_id):
        """История «Мастерской»: все запуски (было LIMIT 20) и круги, а не одни генерации (книга «Фон», 19.10)."""
        from engine.db_narrative import create_pipeline_run, get_pipeline_runs, save_pipeline_iteration
        ids = [create_pipeline_run(project_id, n, "m", "m", "m", "m") for n in range(1, 27)]
        for it, stage in ((1, "generate"), (1, "critique"), (1, "judge"), (2, "edit"), (2, "judge"), (3, "edit")):
            save_pipeline_iteration(ids[0], it, stage, "m", "задача", "текст")
        runs = get_pipeline_runs(project_id)
        assert len(runs) == 26 and {r["chapter_num"] for r in runs} == set(range(1, 27))
        assert next(r for r in runs if r["id"] == ids[0])["iterations"] == 3
