"""Ручное управление автора: правка и удаление глав, чистка истории запусков."""
import pytest


@pytest.fixture
def client(project_id):
    from web.app import app
    from engine.db_settings import set_active_project
    set_active_project(project_id)
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client()


def test_chapter_edit_saves_text(project_id, client):
    from engine.db import get_chapter, save_chapter
    save_chapter(project_id, 1, "В 00:58 было почти два. " * 20, "Глава 1")
    fixed = "В 01:58 было почти два. " * 20
    r = client.post("/chapter/1/save", json={"text": fixed})
    assert r.status_code == 200 and r.get_json()["ok"]
    ch = get_chapter(project_id, 1)
    assert ch["content"].strip() == fixed.strip() and ch["title"] == "Глава 1"
    assert client.post("/chapter/1/save", json={"text": "коротко"}).status_code == 400
    assert client.post("/chapter/9/save", json={"text": fixed}).status_code == 404


def _count(table, project_id, num):
    from engine.db_core import get_conn
    with get_conn() as conn:
        return conn.execute(f"SELECT count(*) FROM {table} WHERE project_id=? AND chapter_num=?",
                            (project_id, num)).fetchone()[0]


def _derived(project_id, num):
    from engine.db_core import get_conn
    from engine.db import save_chapter_analysis, save_state_update
    with get_conn() as conn:
        conn.execute("INSERT INTO l3_memory (project_id,chapter_num,events) VALUES (?,?,?)",
                     (project_id, num, "события"))
    save_chapter_analysis(project_id, num, {"pacing_note": "ровно"})
    save_state_update(project_id, num, "{}")


def test_chapter_delete_removes_text_and_derived(project_id, client):
    from engine.db import get_chapter, save_chapter, save_author_edit
    save_chapter(project_id, 2, "Текст второй главы. " * 10, "Глава 2")
    _derived(project_id, 2)
    save_author_edit(project_id=project_id, chapter_num=2, run_id=None, original_text="а",
                     accepted_text="б", action="accept")
    r = client.post("/chapter/2/delete", json={})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert get_chapter(project_id, 2) is None
    for t in ("l3_memory", "chapter_analysis", "state_updates"):
        assert _count(t, project_id, 2) == 0, t
    assert _count("author_edits", project_id, 2) == 1      # работа автора остаётся
    assert client.post("/chapter/2/delete", json={}).status_code == 404


def test_narrative_purge_drops_only_missing_chapters(project_id, client):
    from engine.db import save_chapter
    save_chapter(project_id, 1, "Текст первой главы. " * 10, "Глава 1")
    _derived(project_id, 1)
    _derived(project_id, 4)                                 # главы 4 нет
    r = client.post("/narrative/purge", json={})
    assert r.status_code == 200 and r.get_json()["deleted"] == 3
    assert _count("chapter_analysis", project_id, 4) == 0
    assert _count("chapter_analysis", project_id, 1) == 1


def test_delete_history_keeps_author_edits(project_id, client):
    """Правка автора ссылалась на запуск, и внешний ключ ронял удаление истории."""
    from engine.db import save_author_edit, get_pipeline_run
    from engine.db_core import get_conn
    from engine.db_narrative import create_pipeline_run
    run = create_pipeline_run(project_id, 1, "m", "m", "m", "m")
    save_author_edit(project_id=project_id, chapter_num=1, run_id=run, original_text="а",
                     accepted_text="", action="reject")
    r = client.post("/pipeline/delete-history", json={})
    assert r.status_code == 200 and r.get_json()["ok"]
    assert get_pipeline_run(run) is None
    with get_conn() as conn:
        rows = conn.execute("SELECT run_id FROM author_edits WHERE project_id=?",
                            (project_id,)).fetchall()
    assert [tuple(x) for x in rows] == [(None,)]


def test_cleanup_spares_judged_and_fresh_runs(project_id, client):
    """«Зависшие» не трогают дописанную главу (ждёт автора) и идущий запуск."""
    from engine.db import get_pipeline_run
    from engine.db_core import get_conn
    from engine.db_narrative import create_pipeline_run, save_pipeline_iteration
    judged, fresh, stale = (create_pipeline_run(project_id, n, "m", "m", "m", "m")
                            for n in (1, 2, 3))
    save_pipeline_iteration(judged, 1, "generate", "m", "в", "текст")
    save_pipeline_iteration(judged, 1, "judge", "m", "в", "оценка", 39, "ПРИНЯТЬ")
    save_pipeline_iteration(fresh, 1, "generate", "m", "в", "текст")
    with get_conn() as conn:
        conn.execute("UPDATE pipeline_runs SET created_at=datetime('now','-2 hours') "
                     "WHERE id IN (?,?,?)", (judged, fresh, stale))
        conn.execute("UPDATE pipeline_iterations SET created_at=datetime('now','-2 hours') "
                     "WHERE run_id=?", (judged,))
    r = client.post("/pipeline/cleanup", json={})
    assert r.get_json()["cleaned"] == 1
    assert get_pipeline_run(stale)["status"] == "rejected"
    assert get_pipeline_run(judged)["status"] == "running"
    assert get_pipeline_run(fresh)["status"] == "running"
