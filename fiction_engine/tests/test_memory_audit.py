"""Сверка памяти (tools/memory_audit.py): ловит должность не того героя, базу только читает."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import memory_audit as ma

CHARACTERS = """# Персонажи

## Варвара (Варя) Лыкова
Роль: хозяйка бани у перевоза

## Другие
- Захар Ильич — княжий тиун в посаде, судит земельные дела
- Тихон, 60 — паромщик на перевозе
"""
CH9 = "— Тиунов писарь. Захара Ильича. «Ер» с хвостом, — сказал Ефим. Долг шестьдесят серебряников."
CH19 = "Тиун Захар Ильич держал лист двумя пальцами. С краю сидел писарь, молодой."


def _db(tmp_path, state, fact):
    """Минимальная база в схеме приложения: проект, две главы, подготовка, State, запись библии."""
    db = tmp_path / "projects.db"
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE chapters (id INTEGER PRIMARY KEY, project_id INT, number INT, content TEXT);
        CREATE TABLE prep_data (id INTEGER PRIMARY KEY, project_id INT, section TEXT, content TEXT);
        CREATE TABLE state_engine (id INTEGER PRIMARY KEY, project_id INT, global_state TEXT,
                                   plot_matrix TEXT, memory_graph TEXT);
        CREATE TABLE series_bible (id INTEGER PRIMARY KEY, project_id INT, kind TEXT, name TEXT, attr TEXT,
                                   value TEXT, chapter_num INT, status TEXT, reason TEXT, created_at TEXT);
    """)
    c.execute("INSERT INTO projects VALUES (1, 'Книга')")
    c.executemany("INSERT INTO chapters (project_id, number, content) VALUES (1, ?, ?)", [(9, CH9), (19, CH19)])
    c.execute("INSERT INTO prep_data (project_id, section, content) VALUES (1, 'characters', ?)", (CHARACTERS,))
    c.execute("INSERT INTO state_engine (project_id, global_state, plot_matrix, memory_graph) VALUES (1, ?, '', '')",
              (state,))
    c.execute("INSERT INTO series_bible (project_id, kind, name, attr, value, chapter_num, status) "
              "VALUES (1, 'вещь', 'запись долга', 'список', ?, 9, 'введено')", (fact,))
    c.commit()
    c.close()
    return db


def _found(db):
    d = ma.load(db, 1)
    items = ma.memory_items(d)
    return {title: fn(d, items) for title, fn in ma.CHECKS}


def test_catches_role_of_another_person(tmp_path):
    """«Тиунов писарь. Захара Ильича» разбор прочёл как «писарь Захар Ильич» — по подготовке он тиун."""
    db = _db(tmp_path, "Список писан рукой тиунова писаря Захара Ильича.",
             "рука тиунова писаря Захара Ильича; долг шестьдесят серебряников")
    roles = _found(db)["Роли"]
    assert len(roles) == 2 and all("Захар" in what and "писар" in what for _, what, _ in roles)


def test_clean_memory_has_no_findings(tmp_path):
    db = _db(tmp_path, "Список писан рукой писаря тиуна Захара Ильича.",
             "рука писаря тиуна Захара Ильича; долг шестьдесят серебряников")
    assert not any(_found(db).values())


def test_numbers_quotes_and_names_not_in_text(tmp_path):
    db = _db(tmp_path, "Ефим сказал: «Долг сто серебряников». Деньги принёс Лукьянов.",
             "рука писаря тиуна Захара Ильича; долг семьдесят серебряников")
    found = _found(db)
    assert [w for _, w, _ in found["Цитаты"]] == ["цитаты нет в тексте глав"]
    assert any("Лукьянов" in w for _, w, _ in found["Имена"])
    assert any(": 70" in w for _, w, _ in found["Числа и месяцы"])


def test_number_words():
    assert ma.tokens("сто двадцать серебряников, тридцать одна кружка", False) == {120, 31}
    assert ma.tokens("чистыми двести. Десять серебряников", False) == {200, 10}
    assert ma.tokens("Тысяча триста девяносто шесть шагов, 14 июня", False) == {1396, 14, "мес:июн"}


def test_database_is_not_changed(tmp_path):
    db = _db(tmp_path, "Список писан рукой тиунова писаря Захара Ильича.", "рука тиунова писаря Захара Ильича")
    before = db.read_bytes()
    _found(db)
    assert db.read_bytes() == before


def test_state_page_mentions_script(project_id):
    """На странице State — подсказка, как запустить сверку для этого проекта."""
    from engine.db_settings import set_active_project
    from web.app import app
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    html = app.test_client().get("/state").get_data(as_text=True)
    assert f"memory_audit.py {project_id} --out audit.md" in html
