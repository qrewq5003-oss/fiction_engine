"""State автора доходит до писателя и в свободном формате, не только по ключам."""
from engine.pipeline_context import STATE_RAW_MAX_CHARS, extract_relevant_state

FREE = {
    "global_state": ("[ЛУКАШ ВАВРА — ГЛАВНЫЙ ГЕРОЙ]\nИмя: Лукаш Вавра, 30 лет\n"
                     "Профессия: инженер-системщик, бывший CTO\n"
                     "Локация: набережная у промышленного района Праги\n"
                     "Статус: единственный выживший, повреждено левое плечо\n\n"
                     "[ПАВЕЛ — ДРУГ]\nИмя: Павел\nСтатус: ищет Лукаша по больницам\n"),
    "plot_matrix": "## ОСНОВНАЯ ЛИНИЯ\n\nСТАТУС: активна\nСЛЕДУЮЩИЙ_ШАГ: найти Павла\n",
    "memory_graph": "",
}
KEYS = {
    "global_state": ("## ПЕРСОНАЖИ\n\n### Лукаш\nСОСТОЯНИЕ: ранен\nЛОКАЦИЯ: больница\n"
                     "ЦЕЛЬ_СЕЙЧАС: выписаться\nЦЕЛЬ_ГЛУБИННАЯ: понять, что он видит\n"),
    "plot_matrix": "", "memory_graph": "",
}


def test_free_form_state_goes_as_text():
    out = extract_relevant_state(FREE, "Глава 2. Лукаш ищет Павла.")
    assert "бывший CTO" in out and "ищет Лукаша по больницам" in out   # раньше — один «## Лукаш»
    assert "СЛЕДУЮЩИЙ ШАГ: найти Павла" in out


def test_keyed_state_stays_structured_and_keeps_deep_goal():
    out = extract_relevant_state(KEYS, "Глава 2. Лукаш в больнице.")
    assert "Состояние: ранен" in out and "Цель глубинная: понять, что он видит" in out
    assert "## ПЕРСОНАЖИ" not in out          # не сырым текстом


def test_raw_state_is_capped_at_line_boundary():
    big = {"global_state": "\n".join(f"Строка {i}: " + "слово " * 20 for i in range(2000)),
           "plot_matrix": "", "memory_graph": ""}
    out = extract_relevant_state(big, "Глава 2.")
    assert len(out) <= STATE_RAW_MAX_CHARS and out.endswith("слово")


def test_pipeline_context_carries_chapter_plan(project_id):
    """План главы из планировщика доходит до писателя и в конвейере, ровно один раз,
    под подписью автора — «от редактора после предыдущей» только заметка движка."""
    from engine.db import save_director_note
    from engine.pipeline_context import AUTHOR_NOTE_MARKER, DIRECTOR_MARKER, build_context
    from engine.state_prompts import build_prompt
    from engine.db_projects import get_project
    save_director_note(project_id, 1, "ПЛАН ГЛАВЫ 2\nСЦЕНА 1: Визит к вдове")
    ctx = build_context(project_id, 2, "Вера едет к вдове.", "quick")
    assert AUTHOR_NOTE_MARKER in ctx and DIRECTOR_MARKER not in ctx and "СЦЕНА 1: Визит к вдове" in ctx
    full = build_context(project_id, 2, build_prompt(project_id, 2, "quick", get_project(project_id)), "quick")
    assert full.count(AUTHOR_NOTE_MARKER) == 1       # в обычной генерации — без дубля
    save_director_note(project_id, 2, "Вера ещё не знает про ключ.", source="auto")
    ctx3 = build_context(project_id, 3, "Вера едет к вдове.", "quick")
    assert DIRECTOR_MARKER in ctx3 and AUTHOR_NOTE_MARKER not in ctx3


def test_prompt_assist_uses_model_from_page_and_sees_state(project_id, monkeypatch):
    """«Подготовить промт»: модель — со страницы (настройку «model» нигде не задать), State — в контексте."""
    import json as _json
    from unittest.mock import patch
    from web.app import app
    from engine.db_state import update_state
    monkeypatch.setenv("NANO_GPT_API_KEY", "test-key")
    app.config.update(TESTING=True, FE_CSRF=False)
    from engine.db_settings import set_active_project
    set_active_project(project_id)
    update_state(project_id, "[ЛУКАШ]\nСтатус: единственный выживший", "## ОСНОВНАЯ ЛИНИЯ\nСТАТУС: активна", "")
    seen = {}

    def fake(model, system, user, **kw):
        seen["model"], seen["user"] = model, user
        return "ЗАДАЧА: Лукаш ищет Павла по больницам.\nСЦЕНЫ:\n1. Приёмный покой — дежурная не пускает"
    with patch("engine.pipeline.call_llm", side_effect=fake):
        r = app.test_client().post("/api/prompt-assist", json={"chapter_num": 2, "model": "nano_gpt::x/y"})
    body = r.get_json()
    assert r.status_code == 200 and "error" not in body, body
    assert seen["model"] == "nano_gpt::x/y" and "единственный выживший" in seen["user"]


def _assist(project_id, monkeypatch, answer, chapter=2):
    from unittest.mock import patch
    from web.app import app
    from engine.db_settings import set_active_project
    monkeypatch.setenv("NANO_GPT_API_KEY", "test-key")
    app.config.update(TESTING=True, FE_CSRF=False)
    set_active_project(project_id)
    seen = {}

    def fake(model, system, user, **kw):
        seen["user"] = user
        return answer
    with patch("engine.pipeline.call_llm", side_effect=fake):
        r = app.test_client().post("/api/prompt-assist", json={"chapter_num": chapter, "model": "nano_gpt::x/y"})
    return r.get_json(), seen.get("user", "")


def test_prompt_assist_works_over_chapter_plan(project_id, monkeypatch):
    """«Ночная смена» (20.10): кнопка не видела план главы и сочиняла свою — теперь задача поверх плана."""
    from engine.db import save_director_note
    save_director_note(project_id, 1, "ПЛАН ГЛАВЫ 2\nСЦЕНА 1: Морг\n  Когда: понедельник, 8:00\n"
                                      "ПОКА НЕ РАСКРЫВАТЬ:\n- кто сделал укол")
    body, user = _assist(project_id, monkeypatch, "Гл.2 — МОРГ\n\nЗАДАЧА: Вера идёт до конца.\n\n"
                                                  "ТОНАЛЬНОСТЬ: сухая\nЗАКАНЧИВАЕТСЯ НА: признание")
    assert body["ok"] and body["with_plan"] is True
    assert "СЦЕНА 1: Морг" in user and "кто сделал укол" in user
    assert "Не пересказывай план" in user and "СЦЕНЫ:" not in user
    assert "последняя сцена плана" in user
    # Гл.4 «Последнего рейса» (26.10): вывод плана в «ЗАКАНЧИВАЕТСЯ НА» шёл героине готовым
    assert "Толкования и выводы плана" in user and "не вывод, к которому он пришёл" in user


def test_prompt_assist_without_plan_and_model_notes(project_id, monkeypatch):
    """Без плана — прежний формат; приписка модели после промта в задачу не идёт."""
    from engine.db_settings import save_prep
    save_prep(project_id, "plot", "Пролог в 2016 году.\nГл.12 — чужое.\nГл.2 — Вера в морге.\nГл.3 — дальше.")
    body, user = _assist(project_id, monkeypatch, "Гл.2 — МОРГ\n\nЗАДАЧА: Вера в морге, ищет улику, которую все пропустили.\n\n---\n\n"
                                                  "Примечание: в заголовке опечатка.")
    assert body.get("ok"), body
    assert body["with_plan"] is False and "СЦЕНЫ:" in user
    assert "Примечание" not in body["prompt"] and body["prompt"].endswith("все пропустили.")
    # Номер главы — отдельным числом: не «2016» и не «Гл.12»
    assert "(фрагмент про гл.2):\nГл.2 — Вера в морге." in user
