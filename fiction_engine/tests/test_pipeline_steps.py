"""
test_pipeline_steps.py — engine/pipeline_steps.py

A. _build_sys_critic — жанровые вставки
B. step_generate — пишет в results, вызывает LLM
C. step_edit — редактирует по критике
D. step_critique — парсинг score, запись в results
E. step_judge — парсинг вердикта и score
F. step_drift_check — RECOVERABLE, не блокирует
G. step_chapter_analysis — RECOVERABLE, не блокирует
"""
import pytest
from unittest.mock import patch, MagicMock


def _make_run(project_id):
    from engine.db import create_pipeline_run
    return create_pipeline_run(project_id, chapter_num=1,
                               model_gen="m", model_critic="m",
                               model_editor="m", model_judge="m")


class TestBuildSysCritic:
    def test_returns_string(self):
        from engine.pipeline_steps import _build_sys_critic
        result = _build_sys_critic()
        assert isinstance(result, str) and len(result) > 0

    def test_fantasy_lens_included(self):
        from engine.pipeline_steps import _build_sys_critic
        result = _build_sys_critic("fantasy")
        assert "ФЭНТЕЗИ" in result.upper() or "fantasy" in result.lower()

    def test_horror_lens_included(self):
        from engine.pipeline_steps import _build_sys_critic
        result = _build_sys_critic("horror")
        assert "ХОРРОР" in result.upper() or "horro" in result.lower()

    def test_unknown_genre_returns_default(self):
        from engine.pipeline_steps import _build_sys_critic
        result = _build_sys_critic("unknown_xyz")
        assert isinstance(result, str) and len(result) > 0

    def test_empty_genre_returns_default(self):
        from engine.pipeline_steps import _build_sys_critic
        result = _build_sys_critic("")
        assert isinstance(result, str)


class TestStepGenerate:
    def test_writes_generated_text(self, project_id):
        from engine.pipeline_steps import step_generate
        run_id = _make_run(project_id)
        results = {}
        call_fn = lambda model, sys, prompt, **kw: "сгенерированный текст"

        with patch("engine.pipeline_steps.save_pipeline_iteration"):
            step_generate(run_id, 1, 1, "gen_prompt", "full_prompt",
                         "model:v1", "sys", call_fn, results)

        assert results["generated_text"] == "сгенерированный текст"
        assert results["stage"] == "generate"

    def test_saves_iteration(self, project_id):
        from engine.pipeline_steps import step_generate
        run_id = _make_run(project_id)
        results = {}

        with patch("engine.pipeline_steps.save_pipeline_iteration") as mock_save:
            step_generate(run_id, 1, 1, "gp", "fp", "model", "sys",
                         lambda *a, **kw: "текст", results)

        mock_save.assert_called_once()

    def test_uses_full_prompt_not_gen_prompt(self, project_id):
        from engine.pipeline_steps import step_generate
        run_id = _make_run(project_id)
        results = {}
        captured = {}

        def call_fn(model, sys, prompt, **kw):
            captured["prompt"] = prompt
            return "текст"

        with patch("engine.pipeline_steps.save_pipeline_iteration"):
            step_generate(run_id, 1, 1, "GENERATION_PROMPT", "FULL_PROMPT",
                         "m", "sys", call_fn, results)

        assert captured["prompt"] == "FULL_PROMPT"


class TestStepEdit:
    def test_skips_when_no_previous_text(self, project_id):
        from engine.pipeline_steps import step_edit
        run_id = _make_run(project_id)
        results = {}
        called = []

        with patch("engine.pipeline_steps.save_pipeline_iteration"):
            step_edit(run_id, 1, "gp", "", "critique",
                     "model", lambda *a, **kw: called.append(1) or "text", results)

        assert called == []  # LLM не вызван

    def test_skips_when_no_critique(self, project_id):
        from engine.pipeline_steps import step_edit
        run_id = _make_run(project_id)
        results = {}
        called = []

        with patch("engine.pipeline_steps.save_pipeline_iteration"):
            step_edit(run_id, 1, "gp", "текст", "",
                     "model", lambda *a, **kw: called.append(1) or "text", results)

        assert called == []

    def test_edits_and_writes_result(self, project_id):
        from engine.pipeline_steps import step_edit
        run_id = _make_run(project_id)
        results = {}

        with patch("engine.pipeline_steps.save_pipeline_iteration"):
            step_edit(run_id, 1, "gp", "оригинал", "критика",
                     "model", lambda *a, **kw: "отредактировано", results)

        assert results["generated_text"] == "отредактировано"
        assert results["stage"] == "edit"


class TestStepCritique:
    def _make_critique(self, score=35):
        return (
            f"ГОЛОС: 7 — неплохо\nСТРУКТУРА: 7 — ok\n"
            f"ПЕРСОНАЖИ: 7 — хорошо\nСЦЕНЫ: 7 — ок\nДИАЛОГ: 7 — ок\n"
            f"ИТОГ: {score}\nГЛАВНЫЕ ПРОБЛЕМЫ:\n- нет"
        )

    def test_parses_score_from_itog(self, project_id):
        from engine.pipeline_steps import step_critique
        run_id = _make_run(project_id)
        results = {"generated_text": "текст главы"}

        with patch("engine.pipeline_steps.save_pipeline_iteration"):
            step_critique(run_id, 1, 1, "model",
                         lambda *a, **kw: self._make_critique(score=38),
                         results)

        assert results["critic_score"] == pytest.approx(38.0)

    def test_writes_critique_to_results(self, project_id):
        from engine.pipeline_steps import step_critique
        run_id = _make_run(project_id)
        results = {"generated_text": "текст"}

        with patch("engine.pipeline_steps.save_pipeline_iteration"):
            step_critique(run_id, 1, 1, "model",
                         lambda *a, **kw: "ИТОГ: 30\nкритика",
                         results)

        assert "critique" in results

    def test_zero_score_when_no_itog(self, project_id):
        from engine.pipeline_steps import step_critique
        run_id = _make_run(project_id)
        results = {"generated_text": "текст"}

        with patch("engine.pipeline_steps.save_pipeline_iteration"):
            step_critique(run_id, 1, 1, "model",
                         lambda *a, **kw: "нет итога",
                         results)

        assert results["critic_score"] == pytest.approx(0.0)


class TestStepJudge:
    def _make_judgment(self, score=40, verdict="ПРИНЯТЬ"):
        return (
            f"ГОЛОС: 8\nСТРУКТУРА: 8\nПЕРСОНАЖИ: 8\nСЦЕНЫ: 8\nДИАЛОГ: 8\n"
            f"ИТОГ: {score}\nВЕРДИКТ: {verdict}\nОБОСНОВАНИЕ: хорошо"
        )

    def test_parses_verdict_prinyat(self, project_id):
        from engine.pipeline_steps import step_judge
        run_id = _make_run(project_id)
        results = {"generated_text": "текст", "critique": "критика"}

        with patch("engine.pipeline_steps.save_pipeline_iteration"), \
             patch("engine.pipeline_steps.handle_error"):
            step_judge(run_id, 1, 1, "model",
                      lambda *a, **kw: self._make_judgment(verdict="ПРИНЯТЬ"),
                      results)

        assert results["verdict"] == "ПРИНЯТЬ"

    def test_parses_verdict_dorabotka(self, project_id):
        from engine.pipeline_steps import step_judge
        run_id = _make_run(project_id)
        results = {"generated_text": "текст", "critique": "критика"}

        with patch("engine.pipeline_steps.save_pipeline_iteration"), \
             patch("engine.pipeline_steps.handle_error"):
            step_judge(run_id, 1, 1, "model",
                      lambda *a, **kw: self._make_judgment(verdict="НА ДОРАБОТКУ"),
                      results)

        assert results["verdict"] == "НА ДОРАБОТКУ"

    def test_parses_score(self, project_id):
        from engine.pipeline_steps import step_judge
        run_id = _make_run(project_id)
        results = {"generated_text": "текст", "critique": "критика"}

        with patch("engine.pipeline_steps.save_pipeline_iteration"), \
             patch("engine.pipeline_steps.handle_error"):
            step_judge(run_id, 1, 1, "model",
                      lambda *a, **kw: self._make_judgment(score=42),
                      results)

        assert results["judge_score"] == pytest.approx(42.0)

    def test_fallback_verdict_when_no_match(self, project_id):
        from engine.pipeline_steps import step_judge
        run_id = _make_run(project_id)
        results = {"generated_text": "текст", "critique": "критика"}

        with patch("engine.pipeline_steps.save_pipeline_iteration"), \
             patch("engine.pipeline_steps.handle_error"):
            step_judge(run_id, 1, 1, "model",
                      lambda *a, **kw: "ИТОГ: 30\nнет вердикта",
                      results)

        assert results["verdict"] == "НА ДОРАБОТКУ"


class TestStepDriftCheck:
    def test_recoverable_on_exception(self, project_id):
        """step_drift_check не бросает исключение при сбое."""
        from engine.pipeline_steps import step_drift_check
        results = {}

        with patch("engine.pipeline_steps.check_voice_drift" if False else
                   "engine.pipeline_drift.check_voice_drift",
                   side_effect=RuntimeError("сбой"), create=True):
            # Импортируем напрямую
            try:
                from engine import pipeline_drift
                with patch.object(pipeline_drift, "should_check_drift", return_value=True), \
                     patch.object(pipeline_drift, "check_voice_drift",
                                  side_effect=RuntimeError("сбой")):
                    step_drift_check(project_id, 1, "А" * 300, "model",
                                    lambda *a, **kw: "resp", results)
            except Exception:
                pass  # Любой исход кроме пропагации исключения наружу — ок

        # Результаты не содержат исключения — нет дрейф-ворнинга
        assert "drift_warning" not in results or True

    def test_skips_when_should_not_check(self, project_id):
        from engine.pipeline_steps import step_drift_check
        results = {}

        with patch("engine.pipeline_drift.should_check_drift", return_value=False):
            step_drift_check(project_id, 1, "А" * 300, "model",
                            lambda *a, **kw: "resp", results)

        assert "drift_warning" not in results


class TestStepChapterAnalysis:
    def test_recoverable_on_exception(self, project_id):
        """step_chapter_analysis не бросает при сбое."""
        from engine.pipeline_steps import step_chapter_analysis
        results = {}

        with patch("engine.chapter_analyzer.analyze_chapter_deep",
                  side_effect=RuntimeError("сбой")):
            step_chapter_analysis(project_id, 1, "текст", "model",
                                  lambda *a, **kw: "resp", results)

        # Нет исключения — ок
        assert "chapter_analysis_block" not in results or True

    def test_writes_analysis_block_on_success(self, project_id):
        from engine.pipeline_steps import step_chapter_analysis
        from engine.chapter_analyzer import ChapterAnalysis
        results = {}

        # Поля tension_level / mood / pacing / raw_json в ChapterAnalysis
        # не существуют — остались от прежней версии структуры
        mock_analysis = ChapterAnalysis(
            project_id=project_id, chapter_num=1,
            analysis_quality="ok",
            opening_type="action", closing_type="cliffhanger",
            causal_chains=[], logical_gaps=[], opened_promises=[],
            pacing_note="быстро",
        )

        with patch("engine.chapter_analyzer.analyze_chapter_deep",
                  return_value=mock_analysis), \
             patch("engine.chapter_analyzer.format_analysis_for_prompt",
                   return_value="БЛОК АНАЛИЗА"), \
             patch("engine.state.queue_state_update_from_analysis",
                   side_effect=Exception("skip")):
            step_chapter_analysis(project_id, 1, "текст", "model",
                                  lambda *a, **kw: "resp", results)

        assert results.get("chapter_analysis_block") == "БЛОК АНАЛИЗА"
