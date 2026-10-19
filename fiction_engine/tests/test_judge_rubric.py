"""Правила оценки v2 (engine/judge_rubric): определения, шкала, строки связности — и v1 без изменений."""
import pytest

JUDGE = "chatgpt_subscription::gpt-6.1-sol@medium"      # порог 30


@pytest.fixture
def v2(project_id):
    from engine.db import set_setting
    from engine.judge_rubric import RUBRIC_KEY
    set_setting(RUBRIC_KEY, "v2")
    yield
    set_setting(RUBRIC_KEY, "v1")


def _answer(gate="ОК", logic=None, total=36):
    lines = [f"{k}: {v} — за дело" for k, v in
             (("ГОЛОС", 8), ("СТРУКТУРА", 7), ("ПЕРСОНАЖИ", 7), ("СЦЕНЫ", 7), ("ДИАЛОГ", 7))]
    lines += [f"ИТОГ: {total}", f"**СВЯЗНОСТЬ:** {gate} — «в четверг» при пятнице"]
    if logic:
        lines.append(f"ЛОГИКА ВЫВОДОВ: [{logic}] — жетон не доказывает поездок")
    return "\n".join(lines + ["ВЕРДИКТ: ПРИНЯТЬ", "ОБОСНОВАНИЕ: выше порога"])


def _judge(project_id, answer, genre=""):
    from engine.db_narrative import create_pipeline_run
    from engine.pipeline_steps import step_judge
    seen = {}
    def call(model, system, prompt, max_tokens=None, **kw):
        seen["system"] = system
        return answer
    res = {"generated_text": "Глава. " * 50, "critique": "разбор"}
    step_judge(create_pipeline_run(project_id, 1, "w", "c", "w", JUDGE), 1, 1, JUDGE, call, res, genre_key=genre)
    return res, seen["system"]


def test_v1_by_default_and_unchanged(project_id):
    from engine.judge_rubric import rubric
    from engine.pipeline_steps import _build_sys_critic
    assert rubric() == "v1"
    assert "СТРУКТУРА — темп, крюк, финал, движение" in _build_sys_critic("детектив")
    res, system = _judge(project_id, _answer("ГРУБО"), "detective_classic")
    # Прежние правила: строки связности не просят и не читают
    assert "СВЯЗНОСТЬ" not in system and res["verdict"] == "ПРИНЯТЬ" and "judge_gates" not in res


def test_v2_prompts(v2):
    from engine.pipeline_steps import _build_sys_critic
    critic = _build_sys_critic("детектив")
    assert "СТРУКТУРА — форма главы" in critic and "ШКАЛА" in critic
    assert "СВЯЗНОСТЬ: [ОК / ЕСТЬ / ГРУБО]" in critic and "ЛОГИКА ВЫВОДОВ" in critic
    # Логика выводов — свойство жанра: у реализма её нет
    assert "ЛОГИКА ВЫВОДОВ" not in _build_sys_critic("реализм") and "СВЯЗНОСТЬ" in _build_sys_critic("реализм")


def test_v2_gate_sends_back(project_id, v2):
    res, system = _judge(project_id, _answer("ГРУБО"), "detective_classic")
    assert "ЛОГИКА ВЫВОДОВ" in system and "не ГРУБО" in system and "ИТОГ ≥ 30" in system
    assert res["judge_gates"] == {"СВЯЗНОСТЬ": "ГРУБО"}
    assert res["verdict"] == "НА ДОРАБОТКУ" and "ВЕРДИКТ: НА ДОРАБОТКУ" in res["judgment"]
    res, _ = _judge(project_id, _answer("ЕСТЬ", logic="ГРУБО"), "detective_classic")
    assert res["verdict"] == "НА ДОРАБОТКУ"
    # Мелкие ошибки связности — не причина: решает балл
    res, _ = _judge(project_id, _answer("ЕСТЬ", logic="ОК"), "detective_classic")
    assert res["verdict"] == "ПРИНЯТЬ" and res["judge_gates"] == {"СВЯЗНОСТЬ": "ЕСТЬ", "ЛОГИКА ВЫВОДОВ": "ОК"}
    res, _ = _judge(project_id, _answer("ОК", total=28), "detective_classic")
    assert res["verdict"] == "НА ДОРАБОТКУ"


def test_parse_gates():
    from engine.judge_rubric import parse_gates
    assert parse_gates("СВЯЗНОСТЬ: OK\nЛОГИКА ВЫВОДОВ: грубо — вывод из воздуха") == \
        {"СВЯЗНОСТЬ": "ОК", "ЛОГИКА ВЫВОДОВ": "ГРУБО"}
    assert parse_gates("СВЯЗНОСТЬ — есть: «четверг» при пятнице") == {"СВЯЗНОСТЬ": "ЕСТЬ"}
    assert parse_gates("ГОЛОС: 7\nИТОГ: 35") == {}


def test_rubric_setting_route(project_id):
    from web.app import app
    from engine.db_settings import set_active_project
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    c = app.test_client()
    assert c.get("/api/settings/judge_rubric").get_json()["rubric"] == "v1"
    assert c.post("/api/settings/judge_rubric", json={"rubric": "v3"}).status_code == 400
    assert c.post("/api/settings/judge_rubric", json={"rubric": "v2"}).get_json()["rubric"] == "v2"
    assert c.post("/api/settings/judge_rubric", json={"rubric": "v1"}).get_json()["rubric"] == "v1"
