"""Сверка главы с планом (engine/plan_check, «Мастерская» → «📋 Сверить с планом»)."""
import json

PLAN = """ПЛАН ГЛАВЫ 2

СЦЕНА 1: Больница
  Локация: палата / Утро
  Что происходит: Лукаш приходит в себя, видит линии в капельнице.

СЦЕНА 2: Павел с кофе
  Что происходит: Павел рассказывает про трансформатор.

СЦЕНА 3: Звонок Матея
  Что происходит: Матей требует молчать."""

TEXT = ("Лукаш открыл глаза. Над кроватью висела капельница, и в прозрачной трубке "
        "шла тонкая голубая сетка, ровная, как разметка на чертеже. " * 3 +
        "Павел вошёл с двумя стаканами кофе и сел на край кровати.")


def test_plan_items_formats():
    from engine.plan_check import plan_items
    items = plan_items(PLAN)
    assert [i.split(":")[0] for i in items] == ["СЦЕНА 1", "СЦЕНА 2", "СЦЕНА 3"]
    assert "капельнице" in items[0] and "трансформатор" in items[1]
    assert plan_items("1. Больница\n2. Коридор\n3. Звонок") == ["1. Больница", "2. Коридор", "3. Звонок"]
    assert plan_items("Лукаш в больнице, Павел рядом.") == ["Лукаш в больнице, Павел рядом."]
    assert plan_items("") == []


def test_check_plan_verifies_quotes_and_fills_gaps():
    from engine.plan_check import check_plan
    answer = {"items": [
        {"n": 1, "status": "есть", "quote": "в прозрачной трубке шла тонкая голубая сетка", "note": ""},
        {"n": 2, "status": "частично", "quote": "Павел рассказал всё про трансформатор подробно",
         "note": "про трансформатор не сказано"},
    ]}
    prompts = []
    out = check_plan(2, PLAN, TEXT, lambda p: (prompts.append(p), json.dumps(answer, ensure_ascii=False))[1])
    assert "[3] СЦЕНА 3: Звонок Матея" in prompts[0] and "=== ГЛАВА 2 ===" in prompts[0]
    assert [x["status"] for x in out] == ["есть", "частично", "?"]       # пропущенный пункт — «?»
    assert out[0]["quote_ok"] is True
    assert out[1]["quote_ok"] is False                                   # выдуманная цитата
    assert out[1]["note"] == "про трансформатор не сказано"


def test_quote_found_tolerates_speaker_and_ellipsis():
    from engine.plan_check import quote_found
    text = "— У меня на двенадцатом сегменте провал по фазе, — сказала она. Раз в четыре секунды."
    assert quote_found('Вероника: "У меня на двенадцатом сегменте провал по фазе... Раз в четыре секунды."', text)
    assert not quote_found("Мать позвонила из Брно рано утром", text)
    assert not quote_found("", text)


def test_checker_is_other_family(monkeypatch):
    import engine.continuity_checker as cc
    import engine.pipeline_config as pc
    from engine.plan_check import plan_checker_model
    SONNET, SOL = pc.SONNET, pc.SOL
    monkeypatch.setattr(cc, "continuity_model", lambda: SOL)
    monkeypatch.setattr(pc, "default_role_models", lambda: {"judge": SONNET})
    assert plan_checker_model(SONNET) == (SOL, "")
    assert plan_checker_model(SOL) == (SONNET, "")                       # свой не судит своего
    monkeypatch.setattr(pc, "default_role_models", lambda: {"judge": SOL})
    model, why = plan_checker_model(SOL)
    assert model == "" and "другого семейства" in why


def test_endpoint(project_id, monkeypatch):
    from web.app import app
    from engine.db import save_director_note, set_active_project
    import engine.pipeline as pipeline
    import engine.plan_check as pcheck
    set_active_project(project_id)
    c = app.test_client()
    body = {"chapter_num": 2, "text": TEXT, "model_gen": "claude_subscription::claude-sonnet-5-5"}
    r = c.post("/pipeline/plan_check", json=body)
    assert r.status_code == 400 and "нет плана" in r.get_json()["error"]

    save_director_note(project_id, 1, PLAN)
    monkeypatch.setattr(pcheck, "plan_checker_model", lambda m: ("chatgpt_subscription::gpt-6.1-sol@medium", ""))
    monkeypatch.setattr(pipeline, "call_llm", lambda model, sys, prompt, max_tokens=0: json.dumps(
        {"items": [{"n": 1, "status": "есть", "quote": "Павел вошёл с двумя стаканами кофе"}]}, ensure_ascii=False))
    d = c.post("/pipeline/plan_check", json=body).get_json()
    assert d["ok"] and d["checker"] == "gpt-6.1-sol@medium"
    assert [x["status"] for x in d["items"]] == ["есть", "?", "?"] and d["items"][0]["quote_ok"]


def test_plan_end_line_names_last_scene_and_skips_hold():
    """Писатель шёл дальше плана (книга 3, 18.10): ему сказано, какой сценой глава кончается."""
    from engine.plan_check import plan_end_line
    plan = ("ПЛАН ГЛАВЫ 1\n\nСЦЕНА 1: Паром\n  Локация: озеро\n\nСЦЕНА 3: Пустая полка\n"
            "  Что происходит: нет журнала\n\nПОКА НЕ РАСКРЫВАТЬ (…):\n- СЦЕНА 9: не сцена, а запрет")
    end = plan_end_line(plan)
    assert "СЦЕНА 3: Пустая полка" in end and "СЦЕНА 9" not in end
    # Крючок стиля — внутри последней сцены, а не второй финал (гл.12, 26.10)
    assert "внутри этой сцены" in end
    assert plan_end_line("Заметка редактора без сцен") == ""


def test_plan_end_line_reaches_writer(project_id):
    from engine.db import save_director_note
    from engine.state_prompts import _director_block
    assert "ГЛАВА ЗАКАНЧИВАЕТСЯ" in _director_block("СЦЕНА 1: Паром\n\nСЦЕНА 2: Маяк")
    assert "ГЛАВА ЗАКАНЧИВАЕТСЯ" not in _director_block("Сделай Анну злее")


def test_plan_reading_line_for_scene_plans_only():
    """Гл.4 «Последнего рейса» (24–26.10): толкование из плана становилось готовым выводом
    героини. Писателю после плана со сценами — как его читать; заметке редактора — нет."""
    from engine.plan_check import PLAN_READING, plan_reading_line, plan_writer_lines
    plan = "СЦЕНА 1: Дверь\n  «Запертая каюта» значит только, что кто-то вышел\n\nСЦЕНА 2: Журнал"
    assert plan_reading_line(plan) == PLAN_READING
    assert plan_reading_line("Сделай Анну злее") == ""
    assert plan_reading_line("Заметка\n\nПОКА НЕ РАСКРЫВАТЬ (…):\n- СЦЕНА 9: запрет") == ""
    lines = plan_writer_lines(plan)
    assert lines.startswith(PLAN_READING) and "ГЛАВА ЗАКАНЧИВАЕТСЯ" in lines


def test_plan_reading_reaches_writer_both_ways(project_id):
    """И обычная генерация (state_prompts), и конвейер (pipeline_context) дают строку писателю."""
    from engine.db import save_director_note
    from engine.pipeline_context import build_context
    from engine.state_prompts import _director_block
    plan = "СЦЕНА 1: Дверь\n  «Запертая каюта» значит только, что кто-то вышел\n\nСЦЕНА 2: Журнал"
    assert "КАК ЧИТАТЬ ПЛАН" in _director_block(plan)
    save_director_note(project_id, 0, plan)
    assert "КАК ЧИТАТЬ ПЛАН" in build_context(project_id, 1, "Задача главы")


def test_editor_plan_task_warns_against_plan_conclusions():
    from engine.point_edit import plan_task
    task = plan_task([{"n": 1, "item": "СЦЕНА 1: Дверь", "note": "вывода нет"}])
    assert "не вставляй готовым выводом" in task


# ─── Писатель под сильную модель (разбор формулировок 26.10) ─────────────────

def test_writer_system_prompt_without_pressure():
    """Без «провала задания» и «строго следуешь» — порядок старшинства; объём из конфига."""
    from engine.pipeline_config import MIN_CHAPTER_WORDS, TARGET_CHAPTER_WORDS
    from engine.pipeline_llm import _build_sys_generator
    s = _build_sys_generator("детектив")
    assert "провал" not in s and "Строго следуешь" not in s and "ТРЕБОВАНИЕ" not in s
    assert "старше" in s and "план главы и задача" in s
    assert f"{MIN_CHAPTER_WORDS}–{TARGET_CHAPTER_WORDS}" in s


def test_next_step_not_sent_with_scene_plan(project_id):
    """«СЛЕДУЮЩИЙ ШАГ» State — догадка анализа; при плане со сценами она с ним спорила."""
    from engine.db import save_director_note
    from engine.db_state import get_state, update_state
    from engine.pipeline_context import build_context, extract_relevant_state
    update_state(project_id, "## ПЕРСОНАЖИ\n### Вера\nСОСТОЯНИЕ: тревога\n",
                 "## ОСНОВНАЯ ЛИНИЯ\nСЛЕДУЮЩИЙ_ШАГ: Вера идёт в морг\n", "")
    s = get_state(project_id)
    assert "СЛЕДУЮЩИЙ ШАГ" in extract_relevant_state(s, "Вера")
    assert "СЛЕДУЮЩИЙ ШАГ" not in extract_relevant_state(s, "Вера", with_next=False)
    assert "Вера идёт в морг" in build_context(project_id, 1, "Вера ищет улики")
    save_director_note(project_id, 0, "СЦЕНА 1: Причал\n  Вера встречает следователя\n\nСЦЕНА 2: Морг")
    assert "Вера идёт в морг" not in build_context(project_id, 1, "Вера ищет улики")


def test_previous_analysis_for_writer_has_no_gaps_and_no_payoff_order():
    from engine.chapter_analyzer import ChapterAnalysis, format_analysis_for_prompt
    a = ChapterAnalysis(project_id=1, chapter_num=3, arc_progress={"Вера": "решилась"},
                        opened_promises=["кто звонил в 2:14"], logical_gaps=["откуда ключ"],
                        conflict_score=0.5, pacing_note="", analysis_quality="ok")
    writer = format_analysis_for_prompt(a)
    assert "решилась" in writer
    assert "откуда ключ" not in writer and "payoff" not in writer and "2:14" not in writer


def test_writer_system_prompt_has_volume_self_check():
    """Без «провала задания» главы стали короче (27.10) — самопроверка объёма, та же, что в шаблонах."""
    from engine.pipeline_config import volume_check_for_prompt
    from engine.pipeline_llm import _build_sys_generator
    s = _build_sys_generator("детектив")
    assert volume_check_for_prompt() in s and "провал" not in s
