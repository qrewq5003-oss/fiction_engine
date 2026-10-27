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
    res = {"generated_text": "Глава. " * 2100, "critique": "разбор"}
    step_judge(create_pipeline_run(project_id, 1, "w", "c", "w", JUDGE), 1, 1, JUDGE, call, res, genre_key=genre)
    return res, seen["system"]


def test_v2_by_default_v1_unchanged(project_id):
    from engine.db import set_setting
    from engine.judge_rubric import RUBRIC_KEY, rubric
    from engine.pipeline_steps import _build_sys_critic
    assert rubric() == "v2"
    set_setting(RUBRIC_KEY, "v1")
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


def test_v2_judge_sees_one_text():
    """С 23.10 судья видит одну главу: ни «двух вариантов», ни «УЛУЧШЕНИЙ после редактуры»."""
    from engine.judge_rubric import sys_judge
    s = sys_judge(30, 4, "детектив")
    assert "два варианта" not in s and "УЛУЧШЕНИЯ" not in s
    assert "ОСТАТОК:" in s and "ВЕРДИКТ:" in s


def test_v2_gate_sends_back(project_id, v2):
    res, system = _judge(project_id, _answer("ГРУБО"), "detective_classic")
    assert "ЛОГИКА ВЫВОДОВ" in system and "не ГРУБО" in system and "ИТОГ ≥ 30" in system
    # «Фон» 20.10: «ГРУБО» ставили за даты и по одному разбору критика
    assert "ЕСТЬ, а не ГРУБО" in system and "только из разбора критика" in system
    assert res["judge_gates"] == {"СВЯЗНОСТЬ": "ГРУБО"}
    assert res["verdict"] == "НА ДОРАБОТКУ" and "ВЕРДИКТ: НА ДОРАБОТКУ" in res["judgment"]
    res, _ = _judge(project_id, _answer("ЕСТЬ", logic="ГРУБО"), "detective_classic")
    assert res["verdict"] == "НА ДОРАБОТКУ"
    # Мелкие ошибки связности — не причина: решает балл
    res, _ = _judge(project_id, _answer("ЕСТЬ", logic="ОК"), "detective_classic")
    assert res["verdict"] == "ПРИНЯТЬ" and res["judge_gates"] == {"СВЯЗНОСТЬ": "ЕСТЬ", "ЛОГИКА ВЫВОДОВ": "ОК"}
    res, _ = _judge(project_id, _answer("ОК", total=28), "detective_classic")
    assert res["verdict"] == "НА ДОРАБОТКУ"


def test_critic_has_no_judge_line(v2):
    from engine.pipeline_steps import _build_sys_critic
    critic = _build_sys_critic("детектив")
    assert "ЕСТЬ, а не ГРУБО" in critic and "только из разбора критика" not in critic


def test_rough_lines_go_to_editor(project_id, v2, monkeypatch):
    """«ГРУБО» судьи прошлого круга — задание редактору первым; «ГРУБО» критика —
    только по строке, которую судья тоже счёл грубой (судья снизил — обычное замечание)."""
    from engine import pipeline_steps, point_edit
    from engine.db_narrative import create_pipeline_run, save_pipeline_iteration
    from engine.judge_rubric import rough_lines
    critique = ("ГОЛОС: 7 — ок\n**СВЯЗНОСТЬ:** ГРУБО — Лёша в гл.3 не видел записи, а здесь цитирует её\n"
                "ЛОГИКА ВЫВОДОВ: ЕСТЬ — «жетон» не доказывает поездок")
    judgment = "СВЯЗНОСТЬ: ОК — нет\nЛОГИКА ВЫВОДОВ: ГРУБО — вывод «это он» без улики"
    assert rough_lines("СВЯЗНОСТЬ: ЕСТЬ — четверг при пятнице") == []
    run = create_pipeline_run(project_id, 1, "w", "c", "e", JUDGE)
    save_pipeline_iteration(run, 1, "judge", JUDGE, "текст", judgment, score=34, verdict="ПРИНЯТЬ")
    seen = {}
    def fake_point_edit(text, critique, task, call):
        seen["critique"] = critique
        return {"text": text, "applied": [], "failed": [], "changed": 0}
    monkeypatch.setattr(point_edit, "point_edit", fake_point_edit)
    monkeypatch.setattr(pipeline_steps, "_plan_misses", lambda *a, **k: ([], ""))
    monkeypatch.setattr(pipeline_steps, "_ahead_reveals", lambda *a, **k: ([], ""))
    res = {}
    pipeline_steps.step_edit(run, 2, "задача", "Глава. " * 50, critique, "e", lambda *a, **k: "", res,
                             project_id=project_id, chapter_num=1)
    task = seen["critique"]
    first = task.split("\n\n")[0]
    assert task.startswith("СНАЧАЛА — СВЯЗНОСТЬ")
    assert "вывод «это он» без улики" in first
    # СВЯЗНОСТЬ судья счёл ОК — «ГРУБО» критика не срочное задание (в режиме self
    # разбор критика редактору не идёт вовсе)
    assert "Лёша в гл.3 не видел записи" not in task
    assert "«жетон» не доказывает" not in first
    assert res["edit_report"]["rough"] == 1


def test_parse_gates():
    from engine.judge_rubric import parse_gates
    assert parse_gates("СВЯЗНОСТЬ: OK\nЛОГИКА ВЫВОДОВ: грубо — вывод из воздуха") == \
        {"СВЯЗНОСТЬ": "ОК", "ЛОГИКА ВЫВОДОВ": "ГРУБО"}
    assert parse_gates("СВЯЗНОСТЬ — есть: «четверг» при пятнице") == {"СВЯЗНОСТЬ": "ЕСТЬ"}
    assert parse_gates("ГОЛОС: 7\nИТОГ: 35") == {}


def test_rubric_setting_route(project_id):
    from engine.db_settings import set_active_project
    from web.app import app
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    c = app.test_client()
    assert c.get("/api/settings/judge_rubric").get_json()["rubric"] == "v2"
    assert c.post("/api/settings/judge_rubric", json={"rubric": "v3"}).status_code == 400
    assert c.post("/api/settings/judge_rubric", json={"rubric": "v2"}).get_json()["rubric"] == "v2"
    assert c.post("/api/settings/judge_rubric", json={"rubric": "v1"}).get_json()["rubric"] == "v1"


def test_judge_gets_no_score_history(project_id):
    """История оценок проекта судье не уходит: на оценку не влияла, а раньше в ней была эта глава."""
    from engine.db_narrative import create_pipeline_run, save_pipeline_iteration
    run = create_pipeline_run(project_id, 1, "w", "c", "w", JUDGE)
    save_pipeline_iteration(run, 1, "judge", JUDGE, "текст", "ИТОГ: 34", score=34, verdict="ПРИНЯТЬ")
    from engine.pipeline_steps import step_judge
    seen = {}
    def call(model, system, prompt, max_tokens=None, **kw):
        seen["system"] = system
        return _answer()
    res = {"generated_text": "Глава. " * 2100, "critique": "разбор"}
    step_judge(create_pipeline_run(project_id, 2, "w", "c", "w", JUDGE), 1, 2, JUDGE, call, res, project_id=project_id)
    assert "ИСТОРИЯ ОЦЕНОК" not in seen["system"] and "34/50" not in seen["system"]



def test_genre_contract_does_not_promise_verdict(project_id, v2):
    """«Нарушение контракта — доработка» код не применял: задание судьи — как считает код (21.10)."""
    res, system = _judge(project_id, _answer("ОК", logic="ОК"), "detective_classic")
    assert "независимо от prose score" not in system
    assert "обещание книги" in system and "ЛОГИКА ВЫВОДОВ) — в ней" in system and "ОСТАТОК" in system


# ─── Судья и критик: разбор формулировок 26.10 ───────────────────────────────

def test_red_flags_reach_judge_as_flags_not_requirements():
    """Загрузчик терял заголовок «## КРАСНЫЕ ФЛАГИ» — «[ ] Детектив знает ответ слишком рано»
    судья видел требованием. Теперь раздел подписан, пункты — «✗»."""
    from engine.engine_loaders import get_engine_path
    from engine.engine_loaders_core import load_validation_checklist
    out = load_validation_checklist(get_engine_path(), "detective_classic")
    assert "КРАСНЫЕ ФЛАГИ (этого быть не должно):" in out
    assert "✗ Детектив знает ответ слишком рано" in out and "[ ] Детектив знает ответ" not in out
    assert "СТРУКТУРА ГЛАВЫ:" in out and "---" not in out
    assert "cliches_list" not in out and "с предыдущими главами" not in out


def test_judge_format_and_final_chapter():
    from engine.judge_rubric import CRITERIA, sys_judge
    s = sys_judge(30, 4, "детектив")
    assert "ОБОСНОВАНИЕ" not in s and "ВЕРДИКТ:" in s
    assert "в развязке книги — закрывает ли обещанное" in CRITERIA


def test_critic_v2_no_every_scene_demands_and_no_forced_three():
    from engine.pipeline_steps import _build_sys_critic
    for genre in ("детектив", "триллер", "хоррор"):
        c = _build_sys_critic(genre)
        assert "в каждой сцене" not in c and "Каждая сцена" not in c
        assert "ГЛАВНЫЕ ПРОБЛЕМЫ (до трёх" in c and "для редактора" not in c
