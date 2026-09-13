#!/usr/bin/env python3
"""
Редактура на первой итерации.

До 13.09.2026 шаг `edit` смотрел только на текст и критику ПРЕДЫДУЩЕЙ
итерации, поэтому на первом проходе не запускался никогда. Цепочка была
генерация → критика → судья: критик называл конкретные проблемы, и никто
их не правил, пока автор не нажмёт «продолжить».

То есть штатным результатом движка был черновик с диагнозом, а не
исправленный текст.

Порядок шагов в профиле DEEP при этом уже был верным — не хватало лишь
того, чтобы редактор видел, что сделали два шага перед ним.

Почему это вообще стоит чинить: замер 19 моделей показал, что ни одна
глава не проходит порог принятия, а двенадцать главных претензий критика
из четырнадцати — про рубленый ритм. Инструкцией в промпте он не
лечится (этап 1 закрыт отрицательным результатом), а переписыванием —
лечится: Kimi K2.5 сдвинула долю коротких с 54% до 40% при схожести 64%.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

GENERATED = "Он встал. Пошёл. " * 60
EDITED    = "Он встал и пошёл, потому что больше ничего не оставалось. " * 25
CRITIQUE  = "ГОЛОС: 5/10\nИТОГ: 25/50\nГЛАВНЫЕ ПРОБЛЕМЫ:\n- рубленый ритм"


@pytest.fixture
def project(monkeypatch):
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "fe.db")
    from engine.db_core import init_db
    init_db()
    from engine.db import create_project
    return create_project("Редактура", "детектив")


def _stub_calls(monkeypatch, seen: list):
    """Заглушка модели: отвечает по роли, записывает, что ей прислали."""
    import engine.pipeline as pipeline

    def fake(model_value, system, user, max_tokens=4096, prefill=""):
        seen.append({"system": system, "user": user})
        low = (system or "").lower()
        if "редактор и автор" in low or "переписыва" in low:
            return EDITED
        if "критик" in low or "оценива" in low:
            return CRITIQUE
        if "главный редактор" in low or "вердикт" in low:
            return "ИТОГ: 30/50\nВЕРДИКТ: НА ДОРАБОТКУ"
        return GENERATED

    monkeypatch.setattr(pipeline, "_call", fake)
    return seen


# ─── Главное: редактура происходит на первом проходе ─────────────────────────

def test_edit_runs_on_the_first_iteration(project, monkeypatch):
    seen = _stub_calls(monkeypatch, [])
    from engine.pipeline import run_pipeline_step, PIPELINE_GENERATE_AND_EDIT
    from engine.db_narrative import create_pipeline_run, get_pipeline_iterations

    run_id = create_pipeline_run(project, 1, "m", "m", "m", "m")
    run_pipeline_step(run_id=run_id, iteration=1, project_id=project, chapter_num=1,
                      generation_prompt="задача", model_gen="m::m", model_critic="m::m",
                      model_editor="m::m", model_judge="m::m",
                      steps=PIPELINE_GENERATE_AND_EDIT)

    stages = [i["stage"] for i in get_pipeline_iterations(run_id)]
    assert "edit" in stages, f"редактуры не было на первом проходе: {stages}"
    assert stages.index("critique") < stages.index("edit"), \
        "редактор отработал до критика — ему нечего было исправлять"


def test_editor_receives_this_iterations_text_and_critique(project, monkeypatch):
    """
    Суть починки. Раньше редактор получал предыдущую итерацию (то есть на
    первом проходе — ничего) и потому молча выходил.
    """
    seen = _stub_calls(monkeypatch, [])
    from engine.pipeline import run_pipeline_step, PIPELINE_GENERATE_AND_EDIT
    from engine.db_narrative import create_pipeline_run

    run_id = create_pipeline_run(project, 1, "m", "m", "m", "m")
    run_pipeline_step(run_id=run_id, iteration=1, project_id=project, chapter_num=1,
                      generation_prompt="задача", model_gen="m::m", model_critic="m::m",
                      model_editor="m::m", model_judge="m::m",
                      steps=PIPELINE_GENERATE_AND_EDIT)

    edit_calls = [c for c in seen if "ОРИГИНАЛЬНЫЙ ТЕКСТ" in c["user"]]
    assert edit_calls, "редактор не получил ни одного запроса"
    body = edit_calls[0]["user"]
    assert GENERATED[:40] in body, "редактор не увидел сгенерированный текст"
    assert "рубленый ритм" in body, "редактор не увидел критику этой же итерации"


def test_result_is_the_edited_text_not_the_draft(project, monkeypatch):
    _stub_calls(monkeypatch, [])
    from engine.pipeline import run_pipeline_step, PIPELINE_GENERATE_AND_EDIT
    from engine.db_narrative import create_pipeline_run

    run_id = create_pipeline_run(project, 1, "m", "m", "m", "m")
    res = run_pipeline_step(run_id=run_id, iteration=1, project_id=project, chapter_num=1,
                            generation_prompt="задача", model_gen="m::m", model_critic="m::m",
                            model_editor="m::m", model_judge="m::m",
                            steps=PIPELINE_GENERATE_AND_EDIT)
    assert res["generated_text"].startswith("Он встал и пошёл"), \
        "наверх ушёл черновик, а не отредактированный текст"
    assert res["stage"] == "edit"


def test_measured_rhythm_reaches_the_editor(project, monkeypatch):
    """
    Замер ритма движок уже делает для критика. Редактору он тоже нужен:
    опыт показал, что модели правят ритм, когда видят своё число, и не
    правят, когда им просто описывают норму.
    """
    seen = _stub_calls(monkeypatch, [])
    from engine.pipeline import run_pipeline_step, PIPELINE_GENERATE_AND_EDIT
    from engine.db_narrative import create_pipeline_run

    run_id = create_pipeline_run(project, 1, "m", "m", "m", "m")
    run_pipeline_step(run_id=run_id, iteration=1, project_id=project, chapter_num=1,
                      generation_prompt="задача", model_gen="m::m", model_critic="m::m",
                      model_editor="m::m", model_judge="m::m",
                      steps=PIPELINE_GENERATE_AND_EDIT)
    edit_calls = [c for c in seen if "ОРИГИНАЛЬНЫЙ ТЕКСТ" in c["user"]]
    assert "РИТМ ПРЕДЛОЖЕНИЙ" in edit_calls[0]["user"], \
        "редактор не получил замеренную долю коротких предложений"


# ─── Прежнее поведение не сломано ────────────────────────────────────────────

def test_continuation_still_edits_previous_text(project, monkeypatch):
    """
    Продолжение главы правит текст ПРЕДЫДУЩЕЙ итерации — этот путь
    работал и должен работать дальше.
    """
    seen = _stub_calls(monkeypatch, [])
    from engine.pipeline import run_pipeline_step, PIPELINE_WITH_EDIT
    from engine.db_narrative import create_pipeline_run

    run_id = create_pipeline_run(project, 1, "m", "m", "m", "m")
    run_pipeline_step(run_id=run_id, iteration=2, project_id=project, chapter_num=1,
                      generation_prompt="задача", model_gen="m::m", model_critic="m::m",
                      model_editor="m::m", model_judge="m::m",
                      previous_text="ПРЕДЫДУЩИЙ ЧЕРНОВИК", previous_critique="плохо",
                      steps=PIPELINE_WITH_EDIT)
    edit_calls = [c for c in seen if "ОРИГИНАЛЬНЫЙ ТЕКСТ" in c["user"]]
    assert edit_calls and "ПРЕДЫДУЩИЙ ЧЕРНОВИК" in edit_calls[0]["user"]


def test_edit_is_skipped_when_there_is_nothing_to_edit(project, monkeypatch):
    """Без текста и критики шаг обязан тихо выйти, а не звать модель."""
    seen = _stub_calls(monkeypatch, [])
    from engine.pipeline_steps import step_edit
    results = {}
    step_edit(1, 1, "задача", "", "", "m::m",
              lambda *a, **k: seen.append("вызвана") or "x", results)
    assert "вызвана" not in seen
    assert results == {}
