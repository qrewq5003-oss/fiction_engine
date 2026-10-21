"""Мелочи разбора 21.10, пакет 2: данные и задания моделей."""
import json


def test_new_character_goes_to_end_of_section():
    from engine.state_merge import _append_char
    text = "## ПЕРСОНАЖИ\n### Варя\nСОСТОЯНИЕ: ищет\n\n## МИР\nНижний"
    out = _append_char(text, "\n### Свидетель\nСОСТОЯНИЕ: []\n")
    assert out.index("### Варя") < out.index("### Свидетель") < out.index("## МИР")


def test_auto_note_does_not_overwrite_and_continuation_keeps_source(project_id):
    from engine.db_core import get_conn
    from engine.db_narrative import add_continuation, get_director_note, save_director_note
    save_director_note(project_id, 4, "ПЛАН ГЛАВЫ 5 …", source="author")
    save_director_note(project_id, 4, "Заметка модели", source="auto")
    assert get_director_note(project_id, 5).startswith("ПЛАН ГЛАВЫ 5")
    save_director_note(project_id, 6, "Не торопи героиню", source="auto")
    add_continuation(project_id, 7, "⚠️ РЕЖИМ: ПРОДОЛЖЕНИЕ ГЛАВЫ — вторая часть")
    with get_conn() as conn:
        src = conn.execute("SELECT source FROM director_notes WHERE project_id=? AND after_chapter=6",
                           (project_id,)).fetchone()[0]
    assert src == "auto"


def test_old_base_fixes(project_id):
    from engine.db_core import _fix_old_data, get_conn
    with get_conn() as conn:
        conn.executescript(
            "DROP TABLE exemplars; CREATE TABLE exemplars (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "project_id INTEGER NOT NULL, chapter_num INTEGER NOT NULL, label TEXT, text TEXT NOT NULL, "
            "created_at TEXT, UNIQUE(project_id, chapter_num));")
        conn.execute("DELETE FROM settings WHERE key='notes_source_fixed'")
        conn.execute("INSERT INTO director_notes (project_id, after_chapter, note, source, created_at) "
                     "VALUES (?, 9, 'Короткая заметка модели', 'author', NULL)", (project_id,))
        conn.execute("INSERT INTO director_notes (project_id, after_chapter, note, source, created_at) "
                     "VALUES (?, 8, 'ПЛАН ГЛАВЫ 9 …', 'author', NULL)", (project_id,))
        _fix_old_data(conn)
        for _ in range(2):
            conn.execute("INSERT INTO exemplars (project_id, chapter_num, text) VALUES (?, 0, 'эталон')", (project_id,))
        src = dict(conn.execute("SELECT after_chapter, source FROM director_notes WHERE project_id=?",
                                (project_id,)).fetchall())
    assert src[9] == "auto" and src[8] == "author"


def test_l3_does_not_nest_itself(project_id):
    from engine.db import get_l3_summary, save_l3_summary
    save_l3_summary(project_id, 2, {"events": "гл.2", "promises": []})
    again = get_l3_summary(project_id, 2)
    save_l3_summary(project_id, 2, again)
    raw = json.loads(get_l3_summary(project_id, 2)["raw_summary"])
    assert "raw_summary" not in raw


def test_side_line_mark_not_doubled():
    from engine.state_merge import SIDE_LINES_HEADER, _Changes, _merge_side_lines, _section_items
    plot = f"{SIDE_LINES_HEADER}\n- Долг Ильи (с гл.18)"
    out = _merge_side_lines({"новые_линии": ["Долг Ильи (с гл.18)"]}, plot, 19, _Changes())
    assert not any("(с гл.18) (с гл.18)" in x for x in _section_items(out, SIDE_LINES_HEADER))


def test_state_restore_writes_one_snapshot(project_id):
    from engine.db_core import get_conn
    from engine.db_state import restore_state_snapshot, update_state
    update_state(project_id, global_state="раз")
    update_state(project_id, global_state="два", _snapshot_reason="ручной")
    with get_conn() as conn:
        sid = conn.execute("SELECT max(id) FROM state_history WHERE project_id=?", (project_id,)).fetchone()[0]
        before = conn.execute("SELECT count(*) FROM state_history WHERE project_id=?", (project_id,)).fetchone()[0]
    assert restore_state_snapshot(project_id, sid)
    with get_conn() as conn:
        after = conn.execute("SELECT count(*) FROM state_history WHERE project_id=?", (project_id,)).fetchone()[0]
    assert after == before + 1


def test_closed_run_drops_reviewer_inputs(project_id):
    from engine.db import get_pipeline_iterations, save_pipeline_iteration
    from engine.db_narrative import create_pipeline_run, finish_pipeline_run
    run = create_pipeline_run(project_id, 1, "w::x", "c::x", "w::x", "j::x")
    save_pipeline_iteration(run, 1, "generate", "w::x", "задача", "Глава. " * 50)
    save_pipeline_iteration(run, 1, "critique", "c::x", "Глава. " * 50, "разбор")
    save_pipeline_iteration(run, 1, "judge", "j::x", "Глава. " * 50, "вердикт", score=33)
    finish_pipeline_run(project_id, run, "accepted")
    its = {i["stage"]: i for i in get_pipeline_iterations(run)}
    assert its["critique"]["input_text"] == "" and its["judge"]["input_text"] == ""
    assert its["generate"]["input_text"] == "задача" and its["judge"]["score"] == 33


def test_refusing_critic_is_not_passed_to_judge():
    from unittest.mock import patch
    from engine.pipeline_steps import step_critique, step_judge
    seen = {}

    def call(model, system, user, **kw):
        if "редактор серии" in system or "главный редактор" in system:
            seen["judge"] = user
            return "ГОЛОС: 7\nСТРУКТУРА: 7\nПЕРСОНАЖИ: 7\nСЦЕНЫ: 7\nДИАЛОГ: 7\nИТОГ: 35\nСВЯЗНОСТЬ: ОК\nВЕРДИКТ: ПРИНЯТЬ"
        return "Не могу оценить этот текст."
    res = {"generated_text": "Глава. " * 300}
    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_critique(0, 1, 1, "c::x", call, res)
        assert res.get("critique_error")
        step_judge(0, 1, 1, "j::x", call, res)
    assert "Не могу оценить" not in seen["judge"]


def test_analysis_sees_entities_named_in_chapter(project_id):
    from engine.series_bible import KNOWN_MAX, _add, known_for_analysis, record
    record(project_id, [{"kind": "персонаж", "name": "Зинаида Ахметова", "attr": "роль", "value": "соседка",
                         "changed": ""}], 1)
    for i in range(KNOWN_MAX + 5):
        # Напрямую: record сводит похожие имена в одну сущность
        _add(project_id, {"kind": "место", "name": f"Место-{i}", "attr": "улица", "value": f"улица {i}"},
             2, "введено")
    assert "Зинаида" in known_for_analysis(project_id, 10, "Зинаида Ахметова открыла дверь.")
    assert "Зинаида" not in known_for_analysis(project_id, 10, "")


def test_prompt_assist_promises_are_text_at_chapter():
    from web.blueprints.generate_prompt import _open_promises
    l3 = {"chapter_num": 3, "promises": [{"id": "3_0", "text": "Кто взял ключ", "resolved": False},
                                         {"id": "3_1", "text": "Чей нож", "resolved": True, "resolved_chapter": 5},
                                         {"id": "3_2", "text": "Закрыто давно", "resolved": True,
                                          "resolved_chapter": 3}]}
    out = _open_promises(l3, 4)
    assert out == "Кто взял ключ; Чей нож" and "resolved" not in out


def test_cognitive_memory_keeps_promises_of_early_chapters(project_id):
    from engine.cognitive_memory import get_cognitive_context
    from engine.db import save_l3_summary
    save_l3_summary(project_id, 1, {"events": "гл.1", "promises": [{"id": "1_0", "text": "Тайна подвала",
                                                                      "resolved": False}]})
    for n in range(2, 15):
        save_l3_summary(project_id, n, {"events": f"гл.{n}", "promises": []})
    assert "Тайна подвала" in get_cognitive_context(project_id, 15)
