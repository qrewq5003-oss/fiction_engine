"""
State с переводами строк Windows, ГДЕ_СЕЙЧАС, метки глав — найдено на книге
автора 17.10: после глав 2 и 3 четыре персонажа задвоились, разделы
повторились, «гл.2: гл.2:», а ГДЕ_СЕЙЧАС остался из главы 1.
"""
import json

GLOBAL = ("## ПЕРСОНАЖИ\r\n\r\n### Лукаш Вавра\r\nСОСТОЯНИЕ: вывих плеча\r\nЛОКАЦИЯ: у скорой\r\n"
          "ЦЕЛЬ_СЕЙЧАС: []\r\nЗНАЕТ: []\r\nНЕ_ЗНАЕТ: []\r\n\r\n### Павел Новак\r\nСОСТОЯНИЕ: потрясён\r\n"
          "ЛОКАЦИЯ: у скорой\r\nЗНАЕТ: []\r\n")
PLOT = ("## ОСНОВНАЯ ЛИНИЯ\r\n\r\nСТАТУС: активна\r\nГДЕ_СЕЙЧАС: ночь катастрофы, подножка скорой\r\n"
        "СЛЕДУЮЩИЙ_ШАГ: больница\r\n\r\n## ОТКРЫТЫЕ ВОПРОСЫ\r\n- гл.1: Почему выжил один?\r\n")


def _crlf_state(pid):
    """Записать State в обход update_state — как он лежит у автора с прошлых версий."""
    from engine.db import get_conn
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO state_engine (project_id, global_state, plot_matrix, memory_graph) "
                     "VALUES (?,?,?,?)", (pid, GLOBAL, PLOT, ""))


def test_crlf_state_merges_into_existing_characters(project_id):
    from engine.db_state import get_state, merge_analysis_into_state
    _crlf_state(project_id)
    assert "\r" not in get_state(project_id)["global_state"]
    res = merge_analysis_into_state(project_id, json.dumps({
        "global_state_changes": [{"name": "Лукаш Вавра", "состояние": "ожог ладоней", "локация": "дома"},
                                 {"name": "Павел Новак", "локация": "набережная", "узнал": "сетка светится"}],
        "plot_changes": {"где_сейчас": "утро, набережная у подстанции, рядом Павел"},
        "open_questions": ["гл.3: Кто звонит семьям?", "Почему выжил один?"],
        "memory_changes": []}, ensure_ascii=False), 3)
    s = get_state(project_id)
    g, p = s["global_state"], s["plot_matrix"]
    assert g.count("### Лукаш Вавра") == 1 and g.count("### Павел Новак") == 1
    assert res["new_chars"] == []
    assert "СОСТОЯНИЕ: ожог ладоней" in g and "ЛОКАЦИЯ: набережная" in g and "сетка светится" in g
    assert "ГДЕ_СЕЙЧАС: утро, набережная у подстанции, рядом Павел" in p
    assert p.count("## ОТКРЫТЫЕ ВОПРОСЫ") == 1
    assert "- гл.3: Кто звонит семьям?" in p and "гл.3: гл.3" not in p
    assert p.count("Почему выжил один?") == 1                   # уже был — не повторён


def test_update_state_stores_lf(project_id):
    from engine.db import get_conn
    from engine.db_state import update_state
    update_state(project_id, global_state="a\r\nb", plot_matrix="c\rd")
    with get_conn() as conn:
        row = conn.execute("SELECT global_state, plot_matrix FROM state_engine WHERE project_id=?",
                           (project_id,)).fetchone()
    assert (row[0], row[1]) == ("a\nb", "c\nd")


def test_series_details_no_double_prefix():
    from engine.state_merge import merge_series_details, series_details
    t = merge_series_details("", ["гл.2: Горак — седая щетина", "палата на четверых"], 2)
    assert series_details(t) == ["гл.2: Горак — седая щетина", "гл.2: палата на четверых"]
