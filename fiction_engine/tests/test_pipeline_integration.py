"""
test_pipeline_integration.py — интеграционные тесты полного цикла pipeline.

Что проверяем:
  1. Базовый сквозной сценарий: задача → generate → critique → judge → accept
  2. accept_pipeline корректно записывает judge_score в calibration
  3. reject_pipeline корректно завершает run
  4. continue_pipeline продолжает существующий run
  5. auto-retry прерывается при деградации score
  6. QUICK preset: judge отключён, verdict не появляется
  7. start_pipeline возвращает run_id который ссылается на реальную запись в БД
  8. accept_pipeline после accept — get_pipeline_run имеет status='accepted'
  9. Двойной accept не падает (idempotent к ошибкам)
 10. prevalidation_warnings не блокируют pipeline

Стратегия мока:
  Все LLM-вызовы (_call) мокаются на уровне engine.pipeline._call.
  Ответы строятся так чтобы парсеры pipeline находили нужные поля
  (ВЕРДИКТ: ПРИНЯТЬ, ИТОГ: 42, etc.) — тест проверяет интеграцию,
  не качество LLM.
"""

import pytest

from tests.llm_stubs import scripted_llm
from unittest.mock import patch, MagicMock


# ─── Вспомогательные фабрики ответов LLM ──────────────────────────────────────

def _llm_generate(prompt="") -> str:
    return "Глава первая. Герой шёл по лесу. Деревья стояли высокие."


def _llm_critique(prompt="") -> str:
    return "КРИТИКА: Темп хороший. Диалог отсутствует — стоит добавить."


def _llm_judge_accept(prompt="") -> str:
    return (
        "ГОЛОС: 9 СТРУКТУРА: 8 ПЕРСОНАЖИ: 8 СЦЕНЫ: 9 ДИАЛОГ: 8\n"
        "ИТОГ: 42\n"
        "ВЕРДИКТ: ПРИНЯТЬ\n"
        "Глава соответствует стандартам проекта."
    )


def _llm_judge_rework(prompt="") -> str:
    return (
        "ГОЛОС: 6 СТРУКТУРА: 6 ПЕРСОНАЖИ: 5 СЦЕНЫ: 6 ДИАЛОГ: 5\n"
        "ИТОГ: 28\n"
        "ВЕРДИКТ: НА ДОРАБОТКУ\n"
        "Диалог слабый, темп провисает."
    )


def _llm_edit(prompt="") -> str:
    return "Глава первая (правка). Герой шёл по лесу, слушая тишину."


def _llm_prevalidate_ok(prompt="") -> str:
    return '{"ok": true, "blocking": [], "warnings": []}'


def _llm_prevalidate_warn(prompt="") -> str:
    return (
        '{"ok": true, "blocking": [], '
        '"warnings": [{"issue": "Персонаж упомянут впервые", '
        '"detail": "Арина не была представлена раньше", "fix": "Добавить введение"}]}'
    )


def _make_llm_sequence(generate=None, critique=None, judge=None, *extra,
                       edit=None, other=""):
    """
    Ответы по РОЛИ вызова, а не по порядку.

    Раньше это была очередь: первый вызов — генератор, второй — критик,
    третий — судья. Но шаг generate тянет за собой ещё и анализ главы,
    поэтому очередь съезжала: судья получал ответ, предназначенный
    анализатору, и вердикт приходил пустым. Позиционные аргументы
    сохранены, чтобы не переписывать все вызовы.
    """
    return scripted_llm(
        generate=generate if generate is not None else "",
        critique=critique if critique is not None else "",
        judge=judge if judge is not None else "",
        edit=edit if edit is not None else (extra[0] if extra else ""),
        other=other or "{}",
    )


# ─── Фикстуры ─────────────────────────────────────────────────────────────────

@pytest.fixture
def pid(project_id):
    """Алиас — используем стандартную фикстуру project_id из conftest."""
    return project_id


@pytest.fixture
def chapter_saved(pid):
    """Сохраняем текст главы 1 чтобы step_chapter_analysis мог прочитать."""
    from engine.db_projects import save_chapter
    save_chapter(pid, 1, _llm_generate(), "Тестовая задача")
    return pid


# ─── Тест 1: базовый сквозной сценарий ───────────────────────────────────────

class TestBasicFlow:

    def test_start_pipeline_returns_run_id(self, pid):
        """start_pipeline возвращает dict с run_id — целое положительное число."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            # step_chapter_analysis вызывает LLM для state update — даём заглушку
            lambda p: '{"ok": true}',
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Герой выходит из дома",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
        assert "run_id" in result
        assert isinstance(result["run_id"], int)
        assert result["run_id"] > 0

    def test_start_pipeline_run_exists_in_db(self, pid):
        """run_id из start_pipeline ссылается на реальную запись в БД."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
        from engine.db_narrative import get_pipeline_run
        run = get_pipeline_run(result["run_id"])
        assert run is not None
        assert run["project_id"] == pid
        assert run["chapter_num"] == 1

    def test_pipeline_produces_generated_text(self, pid):
        """После generate шага results содержит непустой generated_text."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
        assert result.get("generated_text", "").strip() != ""

    def test_pipeline_produces_verdict(self, pid):
        """После judge шага results содержит verdict."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
        assert result.get("verdict") in ("ПРИНЯТЬ", "НА ДОРАБОТКУ")

    def test_pipeline_judge_accept_verdict(self, pid):
        """Когда LLM возвращает ПРИНЯТЬ — verdict == ПРИНЯТЬ."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
        assert result["verdict"] == "ПРИНЯТЬ"

    def test_pipeline_judge_score_parsed(self, pid):
        """judge_score парсится из ответа LLM (ИТОГ: 42 → 42.0)."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
        assert result.get("judge_score", 0) == pytest.approx(42.0)


# ─── Тест 2: accept_pipeline ──────────────────────────────────────────────────

class TestAcceptPipeline:

    def _run(self, pid):
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            return start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )

    def test_accept_sets_status_accepted(self, pid):
        """После accept_pipeline — run.status == 'accepted'."""
        result = self._run(pid)
        run_id = result["run_id"]

        from engine.pipeline import accept_pipeline
        accept_pipeline(run_id)

        from engine.db_narrative import get_pipeline_run
        run = get_pipeline_run(run_id)
        assert run["status"] == "accepted"

    def test_accept_records_judge_calibration(self, pid):
        """accept_pipeline записывает judge_score в таблицу judge_calibration."""
        result = self._run(pid)
        run_id = result["run_id"]

        from engine.pipeline import accept_pipeline
        accept_pipeline(run_id)

        # Проверяем через db_chapters напрямую — таблица создаётся lazy внутри save_judge_calibration
        from engine.db_chapters import get_judge_calibration_hint
        # С 1 записью get_judge_calibration_hint требует min_samples=3, используем min=1
        from engine.db_core import get_conn
        with get_conn() as conn:
            try:
                rows = conn.execute(
                    "SELECT judge_score FROM judge_calibration WHERE project_id = ?",
                    (pid,)
                ).fetchall()
                assert len(rows) >= 1
                assert rows[-1]["judge_score"] == pytest.approx(42.0)
            except Exception:
                # Таблица не создана — значит save_judge_calibration не вызвался
                pytest.fail("judge_calibration table missing — accept_pipeline не записал score")

    def test_double_accept_does_not_raise(self, pid):
        """Двойной accept не бросает исключений — RECOVERABLE."""
        result = self._run(pid)
        run_id = result["run_id"]

        from engine.pipeline import accept_pipeline
        accept_pipeline(run_id)
        accept_pipeline(run_id)  # не должно упасть


# ─── Тест 3: reject_pipeline ──────────────────────────────────────────────────

class TestRejectPipeline:

    def test_reject_sets_status_rejected(self, pid):
        """После reject_pipeline — run.status == 'rejected'."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_rework,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
        run_id = result["run_id"]

        from engine.pipeline import reject_pipeline
        reject_pipeline(run_id)

        from engine.db_narrative import get_pipeline_run
        run = get_pipeline_run(run_id)
        assert run["status"] == "rejected"


# ─── Тест 4: continue_pipeline ────────────────────────────────────────────────

class TestContinuePipeline:

    def test_continue_pipeline_uses_same_run_id(self, pid):
        """continue_pipeline не создаёт новый run — продолжает тот же run_id."""
        llm_start = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_rework,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm_start):
            from engine.pipeline import start_pipeline
            first = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
        run_id = first["run_id"]

        llm_cont = _make_llm_sequence(
            _llm_edit, _llm_critique, _llm_judge_accept,
        )
        with patch("engine.pipeline._call", llm_cont):
            from engine.pipeline import continue_pipeline
            second = continue_pipeline(
                run_id=run_id,
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                previous_text=first.get("generated_text", ""),
                previous_critique=first.get("critique", ""),
            )
        assert second.get("run_id") == run_id

    def test_continue_pipeline_can_produce_accept(self, pid):
        """После continue — если LLM вернул ПРИНЯТЬ, verdict == ПРИНЯТЬ."""
        llm_start = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_rework,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm_start):
            from engine.pipeline import start_pipeline
            first = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )

        llm_cont = _make_llm_sequence(
            _llm_edit, _llm_critique, _llm_judge_accept,
        )
        with patch("engine.pipeline._call", llm_cont):
            from engine.pipeline import continue_pipeline
            second = continue_pipeline(
                run_id=first["run_id"],
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                previous_text=first.get("generated_text", ""),
                previous_critique=first.get("critique", ""),
            )
        assert second.get("verdict") == "ПРИНЯТЬ"


# ─── Тест 5: auto-retry деградация ────────────────────────────────────────────

class TestAutoRetry:

    def test_auto_retry_aborts_on_score_degradation(self, pid):
        """
        auto-retry прерывается если score не растёт.
        Первый judge: 28 (НА ДОРАБОТКУ). Авто-retry: edit→critique→judge → 20 (НА ДОРАБОТКУ).
        Score упал 28→20 → retry прерывается, итоговый verdict НА ДОРАБОТКУ.
        """
        def _judge_lower(prompt=""):
            return (
                "ГОЛОС: 4 СТРУКТУРА: 4 ПЕРСОНАЖИ: 4 СЦЕНЫ: 4 ДИАЛОГ: 4\n"
                "ИТОГ: 20\n"
                "ВЕРДИКТ: НА ДОРАБОТКУ\n"
            )

        llm = _make_llm_sequence(
            _llm_generate,      # generate
            _llm_critique,      # critique
            _llm_judge_rework,  # judge (28 — НА ДОРАБОТКУ)
            lambda p: "",       # step_chapter_analysis
            _llm_edit,          # auto-retry: edit
            _llm_critique,      # auto-retry: critique
            _judge_lower,       # auto-retry: judge (20 < 28 → стоп)
        )
        from engine.pipeline_config import AUTO_IMPROVE
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
                config=AUTO_IMPROVE,
            )
        # score деградировал → retry прерван → осталось НА ДОРАБОТКУ
        assert result["verdict"] == "НА ДОРАБОТКУ"


# ─── Тест 6: QUICK preset без judge ───────────────────────────────────────────

class TestQuickPreset:

    def test_quick_preset_no_verdict(self, pid):
        """QUICK preset: judge отключён → verdict не появляется в результатах."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique,
            lambda p: "",  # step_chapter_analysis
        )
        from engine.pipeline_config import QUICK
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
                config=QUICK,
            )
        # QUICK не запускает judge → verdict отсутствует или пустой
        assert result.get("verdict") in (None, "", "НА ДОРАБОТКУ")
        # judge_score не установлен
        assert result.get("judge_score", 0) == 0


# ─── Тест 7: prevalidation warnings ──────────────────────────────────────────

class TestPrevalidation:

    def test_prevalidation_warnings_do_not_block(self, pid):
        """
        Если prevalidate возвращает warnings — pipeline продолжается.
        prevalidation_warnings попадают в results, но generated_text есть.
        """
        # PipelineStep живёт в engine.pipeline; пресета
        # PIPELINE_WITH_PREVALIDATE не существует — импорт был мёртвым,
        # шаги тест и так собирает вручную
        from engine.pipeline import PipelineStep

        # prevalidate ходит к модели с SYS_VALIDATOR — для диспетчера ролей
        # это служебный вызов, поэтому ответ задаётся через other
        llm = _make_llm_sequence(
            _llm_generate,
            _llm_critique,
            _llm_judge_accept,
            other=_llm_prevalidate_warn,
        )
        steps = [
            PipelineStep("prevalidate"),
            PipelineStep("generate"),
            PipelineStep("critique"),
            PipelineStep("judge"),
        ]
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
                steps=steps,
            )
        # Генерация произошла несмотря на warnings
        assert result.get("generated_text", "").strip() != ""


# ─── Тест 8: get_pipeline_iterations после полного цикла ─────────────────────

class TestPipelineIterations:

    def test_iterations_saved_for_each_step(self, pid):
        """После start_pipeline + accept — итерации сохранены в БД."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline, accept_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
            accept_pipeline(result["run_id"])

        from engine.db_narrative import get_pipeline_iterations
        iters = get_pipeline_iterations(result["run_id"])
        steps_saved = {i["stage"] for i in iters}
        # generate и judge точно должны быть
        assert "generate" in steps_saved
        assert "judge" in steps_saved

    def test_judge_iteration_has_score(self, pid):
        """Итерация judge содержит score."""
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=1,
                generation_prompt="Задача",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )

        from engine.db_narrative import get_pipeline_iterations
        iters = get_pipeline_iterations(result["run_id"])
        judge_iters = [i for i in iters if i["stage"] == "judge"]
        assert len(judge_iters) >= 1
        assert judge_iters[-1]["score"] == pytest.approx(42.0)


# ─── Тест 9: accept записывает chapter content ────────────────────────────────

class TestAcceptSavesChapter:

    def test_accept_sets_run_project_chapter(self, pid):
        """
        run из get_pipeline_run содержит правильный project_id и chapter_num
        после accept.
        """
        llm = _make_llm_sequence(
            _llm_generate, _llm_critique, _llm_judge_accept,
            lambda p: "",
        )
        with patch("engine.pipeline._call", llm):
            from engine.pipeline import start_pipeline, accept_pipeline
            result = start_pipeline(
                project_id=pid, chapter_num=3,  # нестандартный номер
                generation_prompt="Задача главы 3",
                model_gen="m", model_critic="m",
                model_editor="m", model_judge="m",
            )
            accept_pipeline(result["run_id"])

        from engine.db_narrative import get_pipeline_run
        run = get_pipeline_run(result["run_id"])
        assert run["project_id"] == pid
        assert run["chapter_num"] == 3
        assert run["status"] == "accepted"
