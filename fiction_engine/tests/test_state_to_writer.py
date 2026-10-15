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
    """План главы из планировщика доходит до писателя и в конвейере, ровно один раз."""
    from engine.db import save_director_note
    from engine.pipeline_context import DIRECTOR_MARKER, build_context
    from engine.state_prompts import build_prompt
    from engine.db_projects import get_project
    save_director_note(project_id, 1, "ПЛАН ГЛАВЫ 2\nСЦЕНА 1: Визит к вдове")
    ctx = build_context(project_id, 2, "Вера едет к вдове.", "quick")
    assert DIRECTOR_MARKER in ctx and "СЦЕНА 1: Визит к вдове" in ctx
    full = build_context(project_id, 2, build_prompt(project_id, 2, "quick", get_project(project_id)), "quick")
    assert full.count(DIRECTOR_MARKER) == 1          # в обычной генерации — без дубля
