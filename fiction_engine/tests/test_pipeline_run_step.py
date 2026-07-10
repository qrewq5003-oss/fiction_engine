"""test_pipeline_run_step.py — run_pipeline_step orchestration"""
import pytest
from unittest.mock import patch


def _make_run(project_id):
    from engine.db import create_pipeline_run
    return create_pipeline_run(project_id, 1, "m","m","m","m")


class TestRunPipelineStep:
    def test_returns_dict(self, project_id):
        from engine.pipeline import run_pipeline_step
        run_id = _make_run(project_id)
        with patch("engine.pipeline._execute_steps",
                   return_value={"generated_text":"txt","verdict":"ПРИНЯТЬ","judge_score":40.0}):
            r = run_pipeline_step(run_id,1,project_id,1,"gp","m","m","m","m")
        assert isinstance(r, dict)

    def test_delegates_to_execute_steps(self, project_id):
        from engine.pipeline import run_pipeline_step
        run_id = _make_run(project_id)
        with patch("engine.pipeline._execute_steps", return_value={}) as mock:
            run_pipeline_step(run_id,1,project_id,1,"gp","m","m","m","m")
        mock.assert_called_once()

    def test_passes_previous_text(self, project_id):
        from engine.pipeline import run_pipeline_step
        run_id = _make_run(project_id)
        captured = {}
        def fake(**kw): captured.update(kw); return {}
        with patch("engine.pipeline._execute_steps", side_effect=fake):
            run_pipeline_step(run_id,1,project_id,1,"gp","m","m","m","m",
                              previous_text="PREV_TEXT")
        assert captured.get("previous_text") == "PREV_TEXT"

    def test_no_previous_uses_default_steps(self, project_id):
        from engine.pipeline import run_pipeline_step, DEFAULT_PIPELINE
        run_id = _make_run(project_id)
        captured = {}
        def fake(**kw): captured.update(kw); return {}
        with patch("engine.pipeline._execute_steps", side_effect=fake):
            run_pipeline_step(run_id,1,project_id,1,"gp","m","m","m","m")
        # steps should be DEFAULT_PIPELINE (no previous text/critique)
        assert captured.get("steps") is DEFAULT_PIPELINE

    def test_previous_text_and_critique_uses_edit_pipeline(self, project_id):
        from engine.pipeline import run_pipeline_step, PIPELINE_WITH_EDIT
        run_id = _make_run(project_id)
        captured = {}
        def fake(**kw): captured.update(kw); return {}
        with patch("engine.pipeline._execute_steps", side_effect=fake):
            run_pipeline_step(run_id,1,project_id,1,"gp","m","m","m","m",
                              previous_text="текст", previous_critique="критика")
        assert captured.get("steps") is PIPELINE_WITH_EDIT
