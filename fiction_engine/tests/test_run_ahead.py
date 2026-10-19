"""Сторож забеганий в «Мастерской»: глава раскрыла то, что по плану вперёд позже («Фон», 19.10)."""
import json

import pytest

TEXT = ("Гоша вздохнул и наконец сказал правду. Фондом занимался Марат, а я только подписывал бумаги, "
        "которые он приносил. Варя записала это в блокнот. ") * 20


@pytest.fixture(autouse=True)
def checker(use_temp_db):
    """Проверяющий другой семьи, чем писатель Sonnet, — как в наборе «Пишет Sonnet»."""
    from engine.db_settings import set_setting
    set_setting("continuity_model", "chatgpt_subscription::gpt-6.1-sol@medium")


@pytest.fixture
def client(project_id):
    from web.app import app
    from engine.db_settings import set_active_project
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def _answer(*found):
    return json.dumps({"happened": list(found)}, ensure_ascii=False)


def test_future_saved_apart_from_plan(project_id, client):
    from engine.db import get_director_note
    from engine.run_ahead import get_future
    r = client.post("/api/chapter_plan/7/save", json={"pid": project_id, "note": "ПЛАН ГЛАВЫ 7\nСЦЕНА 1: Кофейня",
                                                      "future": "- дальше «Признание»: Гоша признаётся"})
    assert r.get_json()["ok"]
    assert get_future(project_id, 7) == "- дальше «Признание»: Гоша признаётся"
    assert "Признание" not in get_director_note(project_id, 7)        # писателю план вперёд не идёт
    client.post("/api/chapter_plan/7/save", json={"pid": project_id, "note": "ПЛАН ГЛАВЫ 7", "future": ""})
    assert get_future(project_id, 7) == ""


def test_find_keeps_only_quoted_and_sorts_kind(project_id):
    from engine.run_ahead import find_run_ahead
    prompts = []

    def ask(p):
        prompts.append(p)
        return _answer({"plan": "гл.15 «Признание»", "kind": "Раскрытие",
                        "quote": "Фондом занимался Марат, а я только подписывал бумаги", "why": "признание раньше"},
                       {"plan": "гл.9", "kind": "раскрытие", "quote": "Марат сам во всём сознался", "why": "выдумано"},
                       {"plan": "гл.12", "kind": "деталь", "quote": "Варя записала это в блокнот", "why": "блокнот"})
    found = find_run_ahead(7, TEXT, "СЦЕНА 1: Кофейня", "- гл.15 «Признание»: Гоша признаётся",
                           "Варя — стримерша", "гл.6: Варя у Гоши", ask)
    assert [(x["kind"], x["plan"]) for x in found] == [("раскрытие", "гл.15 «Признание»"), ("деталь", "гл.12")]
    assert "УЖЕ ПРОИЗОШЛО" in prompts[0] and "гл.15 «Признание»" in prompts[0]
    assert find_run_ahead(7, TEXT, "", "", "", "", ask) == [] and len(prompts) == 1   # без плана вперёд — без вызова


def test_known_has_no_plot_and_no_private_notes(project_id):
    from engine.db import save_director_note, save_l3_summary
    from engine.db_settings import save_prep
    from engine.run_ahead import run_ahead_for, save_future
    save_prep(project_id, "characters", "## Варя\nСтримерша, 23 года")
    save_prep(project_id, "plot", "Сюжет: Марат — Тень_НН")
    save_prep(project_id, "notes", "РАЗГАДКА: виновен Марат")
    save_director_note(project_id, 0, "ПЛАН ГЛАВЫ 1\nСЦЕНА 1: Пальто\nПОКА НЕ РАСКРЫВАТЬ (…):\n- чьё пальто")
    save_l3_summary(project_id, 2, {"events": "Варя говорит с Дашей", "characters": "", "conflicts": "",
                                    "promises": [], "mood": ""})
    seen = []
    assert run_ahead_for(project_id, 3, TEXT, lambda p: seen.append(p) or _answer()) is None   # плана вперёд нет
    save_future(project_id, 3, "- дальше «Признание»: Гоша признаётся")
    assert run_ahead_for(project_id, 3, TEXT, lambda p: seen.append(p) or _answer()) == []
    p = seen[0]
    assert "Стримерша, 23 года" in p and "гл.1: ПЛАН ГЛАВЫ 1 СЦЕНА 1: Пальто" in p and "гл.2: Варя говорит с Дашей" in p
    assert "РАЗГАДКА" not in p and "Тень_НН" not in p and "чьё пальто" not in p


def test_plan_check_returns_ahead(project_id, client):
    from unittest.mock import patch
    from engine.db import save_director_note
    from engine.run_ahead import save_future
    save_director_note(project_id, 6, "ПЛАН ГЛАВЫ 7\nСЦЕНА 1: Кофейня\n  Что происходит: Гоша врёт")
    items = json.dumps({"items": [{"n": 1, "status": "есть", "quote": "Варя записала это в блокнот", "note": ""}]})
    reveal = _answer({"plan": "гл.15", "kind": "раскрытие",
                      "quote": "Фондом занимался Марат, а я только подписывал бумаги", "why": "рано"})
    with patch("engine.pipeline.call_llm", side_effect=[items]):
        r = client.post("/pipeline/plan_check", json={"chapter_num": 7, "text": TEXT,
                                                      "model_gen": "claude_subscription::claude-sonnet-5-5"}).get_json()
    assert r["ok"] and r["ahead"] is None                        # плана вперёд нет — сторож молчит
    save_future(project_id, 7, "- гл.15 «Признание»: Гоша признаётся")
    with patch("engine.pipeline.call_llm", side_effect=[items, reveal]):
        r = client.post("/pipeline/plan_check", json={"chapter_num": 7, "text": TEXT,
                                                      "model_gen": "claude_subscription::claude-sonnet-5-5"}).get_json()
    assert [x["kind"] for x in r["ahead"]] == ["раскрытие"] and r["ahead_error"] == ""


def test_editor_gets_reveal_as_task(project_id):
    from engine.pipeline_steps import _ahead_reveals
    from engine.point_edit import PLAN_MARK, ahead_task
    from engine.run_ahead import save_future
    call = lambda model, system, p: _answer({"plan": "гл.15", "kind": "раскрытие",                   # noqa: E731
                                             "quote": "Фондом занимался Марат, а я только подписывал бумаги",
                                             "why": "рано"})
    assert _ahead_reveals(project_id, 7, TEXT, "claude_subscription::claude-sonnet-5-5", call) == ([], "")
    save_future(project_id, 7, "- гл.15 «Признание»: Гоша признаётся")
    reveals, err = _ahead_reveals(project_id, 7, TEXT, "claude_subscription::claude-sonnet-5-5", call)
    assert len(reveals) == 1 and not err
    task = ahead_task(reveals)
    assert "ЗАБЕГАНИЕ ВПЕРЁД" in task and "Фондом занимался Марат" in task and PLAN_MARK in task
