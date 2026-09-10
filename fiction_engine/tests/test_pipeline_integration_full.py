"""
test_pipeline_integration_full.py — интеграционный тест полного цикла pipeline.

Реальная БД (in-memory SQLite через conftest), реальная pipeline-логика,
реальные DB-операции. Мокается только _call — граница с внешним LLM API.

Что проверяется:
  A. start_pipeline: generate → critique → judge → verdict "ПРИНЯТЬ"
  B. start_pipeline: verdict "НА ДОРАБОТКУ", данные в БД корректны
  C. continue_pipeline: edit → critique → judge после первого цикла
  D. accept_pipeline: статус run меняется, judge_score сохраняется
  E. reject_pipeline: статус run меняется
  F. AUTO_IMPROVE: авто-retry при "НА ДОРАБОТКУ", защита от деградации
  G. Данные итераций в БД: stage, score, output_text записаны верно
  H. parse_score / parse_verdict сквозной: текст судьи → результат в dict
"""

import pytest
from unittest.mock import patch

from tests.llm_stubs import scripted_llm


# ─── Фикстуры ────────────────────────────────────────────────────────────────

MODEL = "anthropic_direct::claude-test"

GENERATE_RESPONSE = "Текст главы. " * 200   # ~2600 символов, правдоподобный объём

CRITIQUE_ACCEPT = (
    "ГОЛОС: 8\n"
    "СТРУКТУРА: 8\n"
    "ПЕРСОНАЖИ: 8\n"
    "СЦЕНЫ: 8\n"
    "ДИАЛОГ: 8\n"
    "ИТОГ: 40\n"
)

CRITIQUE_REJECT = (
    "ГОЛОС: 5\n"
    "СТРУКТУРА: 5\n"
    "ПЕРСОНАЖИ: 6\n"
    "СЦЕНЫ: 5\n"
    "ДИАЛОГ: 5\n"
    "ИТОГ: 26\n"
)

JUDGE_ACCEPT = (
    "ИТОГ: 40\n"
    "ВЕРДИКТ: ПРИНЯТЬ\n"
    "ОБОСНОВАНИЕ: Хороший текст.\n"
)

JUDGE_REJECT = (
    "ИТОГ: 26\n"
    "ВЕРДИКТ: НА ДОРАБОТКУ\n"
    "ОБОСНОВАНИЕ: Слабый темп.\n"
)

EDIT_RESPONSE = "Отредактированный текст главы. " * 200

JUDGE_AFTER_EDIT = (
    "ИТОГ: 39\n"
    "ВЕРДИКТ: ПРИНЯТЬ\n"
    "ОБОСНОВАНИЕ: После правки стало лучше.\n"
)


def _pipeline_kwargs(project_id, chapter_num=1):
    return dict(
        project_id=project_id,
        chapter_num=chapter_num,
        generation_prompt="Написать главу про встречу с драконом.",
        model_gen=MODEL,
        model_critic=MODEL,
        model_editor=MODEL,
        model_judge=MODEL,
    )


# ─── A. Полный цикл generate→critique→judge, вердикт ПРИНЯТЬ ────────────────

class TestStartPipelineAccept:
    def test_returns_verdict_prinyat(self, project_id):
        from engine.pipeline import start_pipeline
        responses = scripted_llm(generate=GENERATE_RESPONSE,
                                 critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)
        with patch("engine.pipeline._call", side_effect=responses):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result["verdict"] == "ПРИНЯТЬ"

    def test_judge_score_correct(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result["judge_score"] == pytest.approx(40.0)

    def test_generated_text_in_result(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result["generated_text"] == GENERATE_RESPONSE

    def test_run_id_returned(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert isinstance(result["run_id"], int) and result["run_id"] > 0

    def test_run_exists_in_db(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.db_narrative import get_pipeline_run
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        run = get_pipeline_run(result["run_id"])
        assert run is not None
        assert run["project_id"] == project_id
        assert run["chapter_num"] == 1


# ─── B. Полный цикл, вердикт НА ДОРАБОТКУ ───────────────────────────────────

class TestStartPipelineReject:
    def test_returns_verdict_na_dorabotku(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_REJECT, judge=JUDGE_REJECT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result["verdict"] == "НА ДОРАБОТКУ"

    def test_low_judge_score(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_REJECT, judge=JUDGE_REJECT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result["judge_score"] == pytest.approx(26.0)

    def test_critique_in_result(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_REJECT, judge=JUDGE_REJECT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result.get("critique"), "critique должна быть непустой"


# ─── C. continue_pipeline: edit→critique→judge ───────────────────────────────

class TestContinuePipeline:
    def _start_rejected(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_REJECT, judge=JUDGE_REJECT)):
            return start_pipeline(**_pipeline_kwargs(project_id))

    def test_continue_returns_verdict(self, project_id):
        from engine.pipeline import continue_pipeline
        first = self._start_rejected(project_id)
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(edit=EDIT_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_AFTER_EDIT)):
            result = continue_pipeline(
                run_id=first["run_id"],
                project_id=project_id,
                chapter_num=1,
                generation_prompt="Написать встречу.",
                previous_text=first["generated_text"],
                previous_critique=first["critique"],
            )
        assert result["verdict"] in ("ПРИНЯТЬ", "НА ДОРАБОТКУ")

    def test_continue_uses_same_run_id(self, project_id):
        from engine.pipeline import continue_pipeline
        first = self._start_rejected(project_id)
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(edit=EDIT_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_AFTER_EDIT)):
            result = continue_pipeline(
                run_id=first["run_id"],
                project_id=project_id,
                chapter_num=1,
                generation_prompt="Написать встречу.",
                previous_text=first["generated_text"],
                previous_critique=first["critique"],
            )
        assert result["run_id"] == first["run_id"]

    def test_continue_iteration_increments(self, project_id):
        from engine.pipeline import continue_pipeline
        from engine.db_narrative import get_pipeline_iterations
        first = self._start_rejected(project_id)
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(edit=EDIT_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_AFTER_EDIT)):
            continue_pipeline(
                run_id=first["run_id"],
                project_id=project_id,
                chapter_num=1,
                generation_prompt="Написать встречу.",
                previous_text=first["generated_text"],
                previous_critique=first["critique"],
            )
        iters = get_pipeline_iterations(first["run_id"])
        iterations_nums = {i["iteration"] for i in iters}
        assert 1 in iterations_nums and 2 in iterations_nums


# ─── D. accept_pipeline ──────────────────────────────────────────────────────

class TestAcceptPipeline:
    def _start_and_get_run_id(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        return result["run_id"]

    def test_status_becomes_accepted(self, project_id):
        from engine.pipeline import accept_pipeline
        from engine.db_narrative import get_pipeline_run
        run_id = self._start_and_get_run_id(project_id)
        accept_pipeline(run_id)
        run = get_pipeline_run(run_id)
        assert run["status"] == "accepted"

    def test_run_exists_after_accept(self, project_id):
        from engine.pipeline import accept_pipeline
        from engine.db_narrative import get_pipeline_run
        run_id = self._start_and_get_run_id(project_id)
        accept_pipeline(run_id)
        assert get_pipeline_run(run_id) is not None


# ─── E. reject_pipeline ──────────────────────────────────────────────────────

class TestRejectPipeline:
    def _start_and_get_run_id(self, project_id):
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_REJECT, judge=JUDGE_REJECT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        return result["run_id"]

    def test_status_becomes_rejected(self, project_id):
        from engine.pipeline import reject_pipeline
        from engine.db_narrative import get_pipeline_run
        run_id = self._start_and_get_run_id(project_id)
        reject_pipeline(run_id)
        run = get_pipeline_run(run_id)
        assert run["status"] == "rejected"


# ─── F. AUTO_IMPROVE: авто-retry при НА ДОРАБОТКУ ───────────────────────────

class TestAutoImprove:
    def test_auto_retry_improves_score(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.pipeline_config import AUTO_IMPROVE

        # Первый цикл: generate + critique(reject) + judge(reject)
        # Авто-retry: edit + critique(accept) + judge(accept) — score выше
        # Сценарий по итерациям: критик и судья браковали, после правки приняли
        responses = scripted_llm(
            generate=GENERATE_RESPONSE,
            critique=[CRITIQUE_REJECT, CRITIQUE_ACCEPT],
            judge=[JUDGE_REJECT, JUDGE_AFTER_EDIT],
            edit=EDIT_RESPONSE,
        )
        with patch("engine.pipeline._call", side_effect=responses):
            result = start_pipeline(**_pipeline_kwargs(project_id), config=AUTO_IMPROVE)

        # Авто-retry должен был улучшить score или принять
        assert result["verdict"] == "ПРИНЯТЬ" or result["judge_score"] > 26.0

    def test_auto_retry_stops_on_degradation(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.pipeline_config import AUTO_IMPROVE

        # Судья держит один и тот же низкий балл на всех итерациях:
        # улучшения нет → авто-повтор обязан прерваться, а не крутиться
        responses = scripted_llm(
            generate=GENERATE_RESPONSE,
            critique=CRITIQUE_REJECT,
            judge=JUDGE_REJECT,
            edit=EDIT_RESPONSE,
        )
        with patch("engine.pipeline._call", side_effect=responses):
            result = start_pipeline(**_pipeline_kwargs(project_id), config=AUTO_IMPROVE)

        # Должен остановиться, не упасть
        assert result["verdict"] == "НА ДОРАБОТКУ"
        assert result["judge_score"] == pytest.approx(26.0)


# ─── G. Данные итераций в БД ─────────────────────────────────────────────────

class TestIterationsInDB:
    def test_three_iterations_saved(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.db_narrative import get_pipeline_iterations
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        iters = get_pipeline_iterations(result["run_id"])
        stages = {i["stage"] for i in iters}
        assert "generate" in stages
        assert "critique" in stages
        assert "judge" in stages

    def test_generate_output_text_saved(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.db_narrative import get_pipeline_iterations
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        iters = get_pipeline_iterations(result["run_id"])
        gen = next(i for i in iters if i["stage"] == "generate")
        assert gen["output_text"] == GENERATE_RESPONSE

    def test_judge_score_saved_in_db(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.db_narrative import get_pipeline_iterations
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        iters = get_pipeline_iterations(result["run_id"])
        judge = next(i for i in iters if i["stage"] == "judge")
        assert judge["score"] == pytest.approx(40.0)

    def test_judge_verdict_saved_in_db(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.db_narrative import get_pipeline_iterations
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        iters = get_pipeline_iterations(result["run_id"])
        judge = next(i for i in iters if i["stage"] == "judge")
        assert judge["verdict"] == "ПРИНЯТЬ"

    def test_iteration_number_is_1(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.db_narrative import get_pipeline_iterations
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        iters = get_pipeline_iterations(result["run_id"])
        for i in iters:
            assert i["iteration"] == 1

    def test_model_saved_in_iteration(self, project_id):
        from engine.pipeline import start_pipeline
        from engine.db_narrative import get_pipeline_iterations
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        iters = get_pipeline_iterations(result["run_id"])
        for i in iters:
            # колонка в схеме называется model_used
            assert i["model_used"] == MODEL


# ─── H. Сквозной: текст судьи → результат dict ───────────────────────────────

class TestEndToEndScoring:
    def test_score_flows_through_pipeline(self, project_id):
        """parse_score и parse_verdict читают то что вернул _call → попадает в result."""
        from engine.pipeline import start_pipeline
        custom_judge = "ИТОГ: 42.5\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Отлично.\n"
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=custom_judge)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result["judge_score"] == pytest.approx(42.5)
        assert result["verdict"] == "ПРИНЯТЬ"

    def test_low_score_flows_through_pipeline(self, project_id):
        custom_judge = "ИТОГ: 18\nВЕРДИКТ: НА ДОРАБОТКУ\nОБОСНОВАНИЕ: Слабо.\n"
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_REJECT, judge=custom_judge)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result["judge_score"] == pytest.approx(18.0)
        assert result["verdict"] == "НА ДОРАБОТКУ"

    def test_no_itog_falls_back_to_criteria_sum(self, project_id):
        """Если судья не написал ИТОГ — parse_score суммирует критерии."""
        from engine.pipeline import start_pipeline
        judge_no_itog = (
            "ГОЛОС: 8\nСТРУКТУРА: 8\nПЕРСОНАЖИ: 8\nСЦЕНЫ: 8\nДИАЛОГ: 8\n"
            "ВЕРДИКТ: ПРИНЯТЬ\n"
        )
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=judge_no_itog)):
            result = start_pipeline(**_pipeline_kwargs(project_id))
        assert result["judge_score"] == pytest.approx(40.0)

    def test_multiple_chapters_independent(self, project_id):
        """Два прогона для разных глав не мешают друг другу."""
        from engine.pipeline import start_pipeline
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_ACCEPT, judge=JUDGE_ACCEPT)):
            r1 = start_pipeline(**_pipeline_kwargs(project_id, chapter_num=1))

        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=GENERATE_RESPONSE, critique=CRITIQUE_REJECT, judge=JUDGE_REJECT)):
            r2 = start_pipeline(**_pipeline_kwargs(project_id, chapter_num=2))

        assert r1["verdict"] == "ПРИНЯТЬ"
        assert r2["verdict"] == "НА ДОРАБОТКУ"
        assert r1["run_id"] != r2["run_id"]
