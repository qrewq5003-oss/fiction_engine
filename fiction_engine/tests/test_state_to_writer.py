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
