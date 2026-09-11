#!/usr/bin/env python3
"""
Принадлежность объектов активному проекту — ПЕРЕБОРОМ маршрутов.

Часть маршрутов принимает идентификаторы, уникальные на всю базу:
номер генерации, номер запуска pipeline, номер статьи, эталона,
снимка состояния. Они брались из запроса как есть, и объекты другого
проекта были доступны:

    GET  /api/generation/<id>        отдавал текст главы чужого проекта
    POST /api/exemplars/<eid>/delete удалял чужой эталон
    POST /state/apply/<update_id>    гасил чужое ожидающее обновление
    POST /symbols/delete             удалял чужой символ (id из тела)
    POST /voice/delete               удалял чужой профиль голоса

Три яруса «перечисляет», найденные ревью, закрыты здесь одним приёмом.

  1. Список маршрутов. Был перечень из восьми — теперь маршруты
     берутся из url_map и из исходников обработчиков.

  2. Имена параметров. Отбор искал `gen_id` и `run_id`; сквозной
     идентификатор под новым именем (`job_id`) выпадал целиком.
     Теперь признак — НАЛИЧИЕ параметра, а не его имя.

  3. Список проб. Была таблица «маршрут → запрос с чужим id»: новый
     маршрут требовал новой строки, и без неё не проверялся никак.
     Теперь проба СТРОИТСЯ по маршруту: в каждый параметр пути и в
     каждый ключ тела подставляются чужие идентификаторы всех видов,
     какие есть в базе. Новый маршрут проверяется тем же перебором,
     ничего не дописывая.

Проверяется не код ответа — 404 сам по себе ничего не доказывает, —
а два факта: чужой текст не попал в ответ и ни одна чужая строка в
базе не изменилась.
"""

import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

SECRET = "СЕКРЕТНЫЙ"
BLUEPRINTS = Path(__file__).resolve().parents[1] / "web" / "blueprints"


# ─── Исключения, которые ДОКАЗЫВАЮТСЯ, а не объявляются ───────────────────────
#
# Раньше здесь был словарь «маршрут → почему он безопасен». В планировщике
# такой же список подвёл: одна запись оказалась ложной, маршрут вышел
# из-под проб и утекал содержимое чужой сцены при зелёном тесте. Проза
# не проверяется ничем. Теперь каждое исключение — функция, которая
# выполняется и что-то доказывает.

def _proof_pipeline_start(client, f):
    """Создаёт запуск в активном проекте; чужие запуски не трогает."""
    from engine.db import get_pipeline_run
    before = dict(get_pipeline_run(f["run_id"]))
    client.post("/pipeline/start", json={"chapter_num": 1,
                                         "generation_prompt": "задача",
                                         "model_gen": "x::y", "model_critic": "x::y",
                                         "model_editor": "x::y", "model_judge": "x::y"})
    assert dict(get_pipeline_run(f["run_id"])) == before, "чужой запуск изменён"


def _proof_pipeline_delete_history(client, f):
    """Удаляет историю активного проекта; чужие запуски остаются."""
    from engine.db import get_pipeline_run
    client.post("/pipeline/delete-history", json={})
    assert get_pipeline_run(f["run_id"]) is not None, "удалён чужой запуск"


def _proof_pipeline_cleanup(client, f):
    """Чистит незавершённые запуски активного проекта, не чужие."""
    from engine.db import get_pipeline_run
    before = dict(get_pipeline_run(f["run_id"]))
    client.post("/pipeline/cleanup", json={})
    assert dict(get_pipeline_run(f["run_id"])) == before, "изменён чужой запуск"


def _proof_generation_clear(client, f):
    """Очищает историю активного проекта; чужие генерации остаются."""
    from engine.db import get_conn
    client.post("/api/generation/clear", json={})
    with get_conn() as conn:
        left = conn.execute(
            "SELECT count(*) FROM generation_history WHERE project_id=?",
            (f["other"],)).fetchone()[0]
    assert left == 1, "удалена чужая генерация"


def _proof_project_switch(client, f):
    """
    Переключение проекта — законная межпроектная операция.

    Доказательство: маршрут МЕНЯЕТ активный проект и НЕ трогает данные
    того, на который переключились. Это и есть граница: смена
    указателя разрешена, доступ к содержимому — нет.
    """
    from engine.db import get_active_project_id, get_conn
    with get_conn() as conn:
        before = [tuple(r) for r in conn.execute(
            "SELECT * FROM chapters WHERE project_id=?", (f["other"],))]
    client.post(f"/project/{f['other']}/switch")
    assert get_active_project_id() == f["other"], "переключение не сработало"
    with get_conn() as conn:
        after = [tuple(r) for r in conn.execute(
            "SELECT * FROM chapters WHERE project_id=?", (f["other"],))]
    assert after == before, "переключение изменило данные проекта"
    client.post(f"/project/{f['mine']}/switch")


def _proof_project_delete(client, f):
    """
    Удаление проекта — тоже законная межпроектная операция: список
    проектов общий, из него удаляют любой.

    Доказательство: удаляется ИМЕННО названный проект, а данные
    остальных остаются на месте.
    """
    from engine.db import get_conn, create_project, save_chapter
    victim = create_project("Жертва", "драма")
    save_chapter(victim, 1, "текст жертвы", "Глава")
    with get_conn() as conn:
        other_before = [tuple(r) for r in conn.execute(
            "SELECT * FROM chapters WHERE project_id=?", (f["other"],))]
    client.post(f"/project/{victim}/delete")
    with get_conn() as conn:
        gone = conn.execute("SELECT count(*) FROM chapters WHERE project_id=?",
                            (victim,)).fetchone()[0]
        other_after = [tuple(r) for r in conn.execute(
            "SELECT * FROM chapters WHERE project_id=?", (f["other"],))]
    assert gone == 0, "проект не удалён"
    assert other_after == other_before, "удаление задело чужой проект"


PROOFS = {
    "/pipeline/start":          _proof_pipeline_start,
    "/pipeline/delete-history": _proof_pipeline_delete_history,
    "/pipeline/cleanup":        _proof_pipeline_cleanup,
    "/api/generation/clear":    _proof_generation_clear,
    "/project/<int:pid>/switch": _proof_project_switch,
    "/project/<int:pid>/delete": _proof_project_delete,
}


# ─── Стенд ────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "fe.db")
    from engine.db_core import init_db
    init_db()
    # Ни один зонд не должен уйти в сеть, даже если маршрут дошёл до модели.
    import engine.pipeline as pipeline
    monkeypatch.setattr(pipeline, "_call",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("нет сети")))
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    return app.test_client()


@pytest.fixture
def foreign(client):
    """Чужой проект со ВСЕМИ видами объектов; активен — свой."""
    from engine.db import (create_project, set_active_project, get_conn,
                           init_generation_history, save_chapter, update_state,
                           save_state_update)
    from engine.db_narrative import create_pipeline_run, save_pipeline_iteration

    mine = create_project("Мой", "детектив")
    other = create_project("Чужой", "хоррор")

    init_generation_history()
    save_chapter(other, 7, f"{SECRET} ТЕКСТ ЧУЖОЙ ГЛАВЫ", f"{SECRET} ЗАГОЛОВОК")
    update_state(other, f"{SECRET} СОСТОЯНИЕ ЧУЖОГО", "", "")
    upd = save_state_update(other, 7, '{"global_state_changes":[]}')

    with get_conn() as conn:
        gen_id = conn.execute(
            "INSERT INTO generation_history "
            "(project_id,chapter_num,model,mode,task,result_text,word_count) "
            "VALUES (?,?,?,?,?,?,?)",
            (other, 7, "m", "quick", "чужая задача", f"{SECRET} ТЕКСТ", 2)).lastrowid
        article = conn.execute(
            "INSERT INTO knowledge_base (project_id,title,content) VALUES (?,?,?)",
            (other, "Чужая статья", f"{SECRET} ЗНАНИЕ")).lastrowid
        exemplar = conn.execute(
            "INSERT INTO exemplars (project_id,chapter_num,text) VALUES (?,?,?)",
            (other, 7, f"{SECRET} ЭТАЛОН")).lastrowid
        snapshot_id = conn.execute(
            "INSERT INTO state_history "
            "(project_id,global_state,plot_matrix,memory_graph,reason) VALUES (?,?,?,?,?)",
            (other, f"{SECRET} СНИМОК", "", "", "тест")).lastrowid
        voice = conn.execute(
            "INSERT INTO voice_profiles (project_id,name,profile) VALUES (?,?,?)",
            (other, "Чужой голос", f"{SECRET} ПРОФИЛЬ")).lastrowid
        symbol = conn.execute(
            "INSERT INTO symbols (project_id,name,initial_meaning) VALUES (?,?,?)",
            (other, "Чужой символ", f"{SECRET} СМЫСЛ")).lastrowid
        conn.execute("INSERT INTO l3_memory (project_id,chapter_num,events) VALUES (?,?,?)",
                     (other, 7, f"{SECRET} ПАМЯТЬ"))
        conn.execute("INSERT INTO director_notes (project_id,after_chapter,note) VALUES (?,?,?)",
                     (other, 7, f"{SECRET} РЕМАРКА"))
    run_id = create_pipeline_run(other, 7, "m", "m", "m", "m")
    save_pipeline_iteration(run_id, 1, "generate", "m", "вход", f"{SECRET} ВЫВОД")

    set_active_project(mine)
    return {"mine": mine, "other": other, "gen_id": gen_id, "run_id": run_id,
            "article": article, "exemplar": exemplar, "snapshot": snapshot_id,
            "update": upd, "voice": voice, "symbol": symbol, "chapter": 7}


# ─── Отбор маршрутов и построение проб ────────────────────────────────────────

_ID_READ = re.compile(r'(?:get\(["\'](\w*_?id)["\']\)|data\[["\'](\w*_?id)["\']\])')
_ROUTE_DEF = re.compile(r'@bp\.route\("([^"]+)"[^)]*\)\s*\ndef (\w+)\(')


def _body_id_keys() -> dict[str, set[str]]:
    """Маршрут → ключи тела, из которых обработчик читает идентификатор."""
    found: dict[str, set[str]] = {}
    for path in sorted(BLUEPRINTS.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        for m in _ROUTE_DEF.finditer(src):
            body = src[m.end():m.end() + 900]
            keys = {g.group(1) or g.group(2) for g in _ID_READ.finditer(body)}
            if keys:
                found.setdefault(m.group(1), set()).update(keys)
    return found


def _id_taking_routes(app) -> set[str]:
    """
    Маршруты, которым можно подсунуть идентификатор извне.

    Признак — НАЛИЧИЕ параметра пути (любого, под любым именем) или
    чтение идентификатора из тела запроса. Ни имя параметра, ни метод
    в отборе не участвуют.
    """
    from_path = {str(rule) for rule in app.url_map.iter_rules()
                 if rule.arguments and not str(rule).startswith("/static")}
    return from_path | set(_body_id_keys())


def _foreign_values(f: dict) -> list:
    """Все чужие идентификаторы — подставляем каждый в каждый параметр."""
    return sorted({f[k] for k in ("gen_id", "run_id", "article", "exemplar",
                                  "snapshot", "update", "voice", "symbol",
                                  "chapter", "other")})


def _requests_for(rule, f: dict, body_keys: dict[str, set[str]]) -> list[tuple]:
    """
    Построить запросы с чужими идентификаторами для одного маршрута.

    Подставляется КАЖДЫЙ чужой идентификатор в КАЖДЫЙ параметр: какой
    именно объект имеет в виду параметр с именем `id`, из маршрута не
    видно, а перебор значений снимает вопрос и заодно не требует
    таблицы «маршрут → вид объекта», которая снова была бы перечнем.
    """
    path_tpl = str(rule)
    methods = sorted((rule.methods or {"GET"}) - {"HEAD", "OPTIONS"})
    out = []
    for value in _foreign_values(f):
        path = path_tpl
        for arg in rule.arguments:
            path = re.sub(r"<[^<>]*\b" + re.escape(arg) + r">", str(value), path)
        body = ({k: value for k in body_keys.get(path_tpl, ())}
                if body_keys.get(path_tpl) else None)
        for method in methods:
            out.append((method, path, body))
        if not rule.arguments and not body:
            break
    return out


def _snapshot_foreign(pid: int) -> dict:
    """Все строки чужого проекта во всех таблицах, где есть project_id."""
    from engine.db import get_conn
    with get_conn() as conn:
        tables = [t for (t,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")
            if any(c[1] == "project_id" for c in conn.execute(f"PRAGMA table_info({t})"))]
        return {t: [tuple(r) for r in conn.execute(
            f"SELECT * FROM {t} WHERE project_id=?", (pid,))] for t in tables}


def _send(client, method, path, body):
    try:
        if method == "GET":
            return client.get(path, follow_redirects=False)
        return client.open(path, method=method, json=body or {})
    except Exception:
        # Падение обработчика — не утечка; проверяем факты, а не коды.
        return None


def _swept_rules(app, f):
    """Маршруты под общим перебором: все отобранные минус доказанные."""
    covered = set(PROOFS)
    return [r for r in app.url_map.iter_rules()
            if str(r) in _id_taking_routes(app) and str(r) not in covered]


# ─── Полнота отбора ───────────────────────────────────────────────────────────

def test_every_id_taking_route_is_swept_or_proven(client, foreign):
    """
    У каждого маршрута с идентификатором есть проверка: либо общий
    перебор строит для него запрос, либо он объявлен межпроектным
    и доказан функцией. Третьего состояния — «никак не проверен» —
    быть не может.
    """
    from web.app import app
    body_keys = _body_id_keys()
    swept = {str(r) for r in _swept_rules(app, foreign)
             if _requests_for(r, foreign, body_keys)}
    unaccounted = sorted(_id_taking_routes(app) - swept - set(PROOFS))
    assert not unaccounted, (
        "маршруты не попали ни под перебор, ни под доказательство: "
        + ", ".join(unaccounted))


def test_proofs_cover_only_real_routes(client, foreign):
    from web.app import app
    existing = {str(r) for r in app.url_map.iter_rules()}
    stale = sorted(set(PROOFS) - existing)
    assert not stale, f"доказательства для несуществующих маршрутов: {stale}"


def test_sweep_actually_sends_requests(client, foreign):
    """
    Страховка от зелени на пустом месте: перебор обязан реально
    отправлять запросы. Проба, которая ничего не вызвала, покажет
    «чужое цело» с тем же успехом, что и защищённый маршрут.
    """
    from web.app import app
    body_keys = _body_id_keys()
    total = sum(len(_requests_for(r, foreign, body_keys))
                for r in _swept_rules(app, foreign))
    assert total > 100, f"перебор построил всего {total} запросов"


# ─── Сам перебор ──────────────────────────────────────────────────────────────

def test_no_route_leaks_foreign_text(client, foreign):
    """
    Чужой текст не должен появиться в ответе — ни как есть, ни в
    \\uXXXX-экранировании, которым jsonify кодирует кириллицу.
    Первый зонд искал только кириллицу и утечку пропустил.
    """
    from web.app import app
    escaped = SECRET.encode("unicode_escape").decode("ascii")
    body_keys = _body_id_keys()
    leaks = []
    for rule in _swept_rules(app, foreign):
        for method, path, body in _requests_for(rule, foreign, body_keys):
            resp = _send(client, method, path, body)
            if resp is None:
                continue
            text = resp.data.decode("utf-8", "replace")
            if SECRET in text or escaped in text:
                leaks.append(f"{method} {path}")
    assert not leaks, "чужой текст в ответе: " + "; ".join(sorted(set(leaks)))


def test_no_route_changes_foreign_data(client, foreign):
    """
    404 сам по себе ничего не доказывает — чужие строки должны быть
    целы. Именно так нашлись удаление чужого эталона, гашение чужого
    обновления состояния и удаление чужого символа.
    """
    from web.app import app
    body_keys = _body_id_keys()
    before = _snapshot_foreign(foreign["other"])
    for rule in _swept_rules(app, foreign):
        for method, path, body in _requests_for(rule, foreign, body_keys):
            _send(client, method, path, body)
    after = _snapshot_foreign(foreign["other"])
    changed = sorted(t for t in before if before[t] != after[t])
    if not changed:
        return
    # Локализуем виновника поимённо, иначе отчёт бесполезен.
    culprits = []
    for rule in _swept_rules(app, foreign):
        for method, path, body in _requests_for(rule, foreign, body_keys):
            snap = _snapshot_foreign(foreign["other"])
            _send(client, method, path, body)
            if _snapshot_foreign(foreign["other"]) != snap:
                culprits.append(f"{method} {path}")
    assert False, (f"изменены чужие таблицы: {', '.join(changed)}; "
                   f"маршруты: {', '.join(sorted(set(culprits))) or 'не воспроизвелось'}")


def test_every_exception_is_proven(client, foreign):
    """Каждое исключение доказывает безопасность выполнением, а не текстом."""
    for rule, proof in sorted(PROOFS.items()):
        proof(client, foreign)


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
        exemplar = conn.execute(
            "INSERT INTO exemplars (project_id,chapter_num,text) VALUES (?,?,?)",
            (pid, 1, "свой эталон")).lastrowid
        symbol = conn.execute(
            "INSERT INTO symbols (project_id,name) VALUES (?,?)",
            (pid, "свой символ")).lastrowid
        voice = conn.execute(
            "INSERT INTO voice_profiles (project_id,name,profile) VALUES (?,?,?)",
            (pid, "свой голос", "{}")).lastrowid

    resp = client.get(f"/api/generation/{gen_id}")
    assert resp.status_code == 200
    assert json.loads(resp.data)["task"] == "своя задача"
    assert client.post(f"/api/generation/{gen_id}/delete").status_code == 200
    assert client.post(f"/api/exemplars/{exemplar}/delete").status_code == 200
    assert client.post("/symbols/appearance",
                       json={"symbol_id": symbol, "chapter": 1,
                             "meaning": "смысл"}).status_code == 200
    assert client.post("/symbols/delete", json={"id": symbol}).status_code == 200
    assert client.post("/voice/delete", json={"id": voice}).status_code == 200
