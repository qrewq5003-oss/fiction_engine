#!/usr/bin/env python3
"""
Принадлежность объектов активному проекту — ПЕРЕБОРОМ маршрутов.

Большинство маршрутов работают от `chapter_num` и разрешают его внутри
активного проекта. Но часть принимает СКВОЗНЫЕ идентификаторы — номер
генерации и номер запуска pipeline уникальны на всю базу, — и брала их
из запроса как есть:

    GET  /api/generation/<id>        отдавал текст главы чужого проекта
    POST /api/generation/<id>/delete удалял чужую генерацию
    GET  /pipeline/<run_id>/history  показывал чужие итерации
    POST /pipeline/reject            менял статус чужого запуска

Найдено при перепроверке закрытых этапов той же меркой, которой ревью
поймало планировщик: перечисляет тест объекты проверки или перебирает.

Здесь — перебирает. Каждый маршрут со сквозным идентификатором обязан
быть либо накрыт пробой с чужим объектом, либо объявлен безопасным с
обоснованием. Новый обработчик, не попавший ни туда ни сюда, роняет
сборку.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


# ─── Маршруты со сквозным идентификатором, которым чужой объект не страшен ────

SAFE_BY_DESIGN = {
    "/pipeline/start":          "создаёт запуск в активном проекте",
    "/pipeline/delete-history": "удаляет историю активного проекта, id не принимает",
    "/pipeline/cleanup":        "чистит незавершённые запуски активного проекта",
    "/api/generation/clear":    "очищает историю активного проекта целиком",
}


@pytest.fixture
def client(monkeypatch):
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "fe.db")
    from engine.db_core import init_db
    init_db()
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    return app.test_client()


@pytest.fixture
def foreign(client):
    """Чужой проект с генерацией и запуском pipeline; активен — свой."""
    from engine.db import (create_project, set_active_project, get_conn,
                           init_generation_history)
    from engine.db_narrative import create_pipeline_run, save_pipeline_iteration

    mine = create_project("Мой", "детектив")
    other = create_project("Чужой", "хоррор")

    init_generation_history()
    with get_conn() as conn:
        gen_id = conn.execute(
            "INSERT INTO generation_history "
            "(project_id,chapter_num,model,mode,task,result_text,word_count) "
            "VALUES (?,?,?,?,?,?,?)",
            (other, 1, "m", "quick", "чужая задача", "СЕКРЕТНЫЙ ТЕКСТ", 2)).lastrowid
    run_id = create_pipeline_run(other, 1, "m", "m", "m", "m")
    save_pipeline_iteration(run_id, 1, "generate", "m", "вход", "СЕКРЕТНЫЙ ВЫВОД")

    set_active_project(mine)
    return {"mine": mine, "other": other, "gen_id": gen_id, "run_id": run_id}


def _probes(f: dict) -> dict:
    """Маршрут → (метод, путь, тело) с ЧУЖИМИ идентификаторами."""
    g, r = f["gen_id"], f["run_id"]
    return {
        "/api/generation/<int:gen_id>":        ("GET", f"/api/generation/{g}", None),
        "/api/generation/<int:gen_id>/delete": ("POST", f"/api/generation/{g}/delete", None),
        "/api/generation/<int:gen_id>/score":  ("POST", f"/api/generation/{g}/score", {}),
        "/pipeline/<int:run_id>/history":      ("GET", f"/pipeline/{r}/history", None),
        "/pipeline/<int:run_id>/compare":      ("GET", f"/pipeline/{r}/compare", None),
        "/pipeline/reject":   ("POST", "/pipeline/reject", {"run_id": r}),
        "/pipeline/accept":   ("POST", "/pipeline/accept",
                               {"run_id": r, "chapter_num": 1, "final_text": "текст"}),
        "/pipeline/continue": ("POST", "/pipeline/continue",
                               {"run_id": r, "chapter_num": 1}),
    }


def _global_id_routes(app) -> set[str]:
    """
    Маршруты, принимающие сквозной идентификатор объекта.

    В пути — gen_id или run_id; в теле — run_id (его берут accept,
    reject и continue).
    """
    from_path = {str(rule) for rule in app.url_map.iter_rules()
                 if rule.arguments & {"gen_id", "run_id"}}

    from_body = set()
    bp_dir = Path(__file__).resolve().parents[1] / "web" / "blueprints"
    import re
    for f in bp_dir.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        for m in re.finditer(r'@bp\.route\("([^"]+)"[^)]*\)\s*\ndef (\w+)\(', src):
            start = m.end()
            body = src[start:start + 900]
            if 'get("run_id")' in body or 'data["run_id"]' in body:
                from_body.add(m.group(1))
    return from_path | from_body


# ─── Полнота перебора ─────────────────────────────────────────────────────────

def test_every_global_id_route_is_accounted_for(client, foreign):
    """
    Каждый маршрут со сквозным идентификатором либо проверяется пробой,
    либо объявлен безопасным. Новый обработчик обязан попасть в один из
    списков — иначе проедет тихо, как проехали четыре прошлых.
    """
    from web.app import app
    covered = set(_probes(foreign)) | set(SAFE_BY_DESIGN)
    unaccounted = sorted(_global_id_routes(app) - covered)
    assert not unaccounted, (
        "маршруты не описаны в проверке принадлежности: " + ", ".join(unaccounted)
        + "\nДобавь пробу в _probes() или обоснование в SAFE_BY_DESIGN."
    )


def test_probe_map_has_no_stale_entries(client, foreign):
    from web.app import app
    existing = {str(r) for r in app.url_map.iter_rules()}
    stale = sorted(set(_probes(foreign)) - existing)
    assert not stale, f"пробы ссылаются на несуществующие маршруты: {stale}"


# ─── Отказ и сохранность ──────────────────────────────────────────────────────

def test_all_probes_reject_foreign_objects(client, foreign):
    allowed = []
    for rule, (method, path, body) in sorted(_probes(foreign).items()):
        resp = (client.post(path, json=body) if method == "POST"
                else client.get(path, follow_redirects=False))
        if resp.status_code < 400:
            allowed.append(f"{rule} → {resp.status_code}")
    assert not allowed, "чужой объект доступен: " + "; ".join(allowed)


def test_foreign_text_never_leaks(client, foreign):
    """
    Ответ не должен содержать чужой текст — ни как есть, ни в
    \\uXXXX-экранировании, которым jsonify кодирует кириллицу.
    Первый зонд искал только кириллицу и утечку пропустил.
    """
    escaped = "СЕКРЕТНЫЙ".encode("unicode_escape").decode("ascii")
    for method, path, body in _probes(foreign).values():
        resp = (client.post(path, json=body) if method == "POST"
                else client.get(path))
        text = resp.data.decode("utf-8", "replace")
        assert "СЕКРЕТНЫЙ" not in text, f"{path}: чужой текст в ответе"
        assert escaped not in text, f"{path}: чужой текст в экранированном виде"


def test_foreign_data_unchanged(client, foreign):
    """404 сам по себе ничего не доказывает — данные должны быть целы."""
    from engine.db import get_conn

    def snapshot():
        with get_conn() as conn:
            gens = conn.execute(
                "SELECT count(*) FROM generation_history WHERE project_id=?",
                (foreign["other"],)).fetchone()[0]
            status = conn.execute(
                "SELECT status FROM pipeline_runs WHERE id=?",
                (foreign["run_id"],)).fetchone()[0]
        return gens, status

    before = snapshot()
    for method, path, body in _probes(foreign).values():
        if method == "POST":
            client.post(path, json=body)
        else:
            client.get(path)
    assert snapshot() == before, "чужие данные изменены"


# ─── Свои объекты доступны ────────────────────────────────────────────────────

def test_own_objects_remain_accessible(client, foreign):
    """Защита не должна ломать работу с активным проектом."""
    from engine.db import get_conn, get_active_project_id
    pid = get_active_project_id()
    with get_conn() as conn:
        gen_id = conn.execute(
            "INSERT INTO generation_history "
            "(project_id,chapter_num,model,mode,task,result_text,word_count) "
            "VALUES (?,?,?,?,?,?,?)",
            (pid, 1, "m", "quick", "своя задача", "свой текст", 2)).lastrowid

    resp = client.get(f"/api/generation/{gen_id}")
    assert resp.status_code == 200
    assert json.loads(resp.data)["task"] == "своя задача"
    assert client.post(f"/api/generation/{gen_id}/delete").status_code == 200
