"""
engine/db.py — база данных планировщика.
SQLite, один файл, автомиграции при старте.
"""
import sqlite3
import os

DB_PATH = os.environ.get("PLANNER_DB", os.path.join(os.path.dirname(__file__), "..", "planner.db"))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            genre       TEXT DEFAULT '',
            description TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS acts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            number     INTEGER NOT NULL,
            title      TEXT NOT NULL,
            color      TEXT DEFAULT '#6b7280',
            UNIQUE(project_id, number)
        );

        CREATE TABLE IF NOT EXISTS scenes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            act_id      INTEGER REFERENCES acts(id) ON DELETE SET NULL,
            position    INTEGER DEFAULT 0,
            title       TEXT DEFAULT '',
            location    TEXT DEFAULT '',
            time_of_day TEXT DEFAULT '',
            characters  TEXT DEFAULT '',
            what_happens TEXT DEFAULT '',
            emotion     TEXT DEFAULT '',
            notes       TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS scene_links (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            from_id  INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
            to_id    INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
            link_type TEXT DEFAULT 'cause',
            label    TEXT DEFAULT '',
            UNIQUE(from_id, to_id)
        );

        CREATE TABLE IF NOT EXISTS scene_snapshots (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id   INTEGER NOT NULL REFERENCES scenes(id) ON DELETE CASCADE,
            reason     TEXT DEFAULT '',
            data       TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)

    # Миграции применяются здесь. Раньше их не вызывал никто: модуль
    # engine/migrations.py обещал в докстринге запуск при старте
    # приложения, но ни одна строка кода его не трогала — 136 строк
    # мёртвого кода, а таблицы из миграций 2 и 3 не создавались.
    from .migrations import apply_migrations
    apply_migrations()


# ─── Projects ────────────────────────────────────────────────────────────────

def get_projects() -> list:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM projects ORDER BY id DESC"
        ).fetchall()]


def get_project(pid: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None


def create_project(name: str, genre: str = "", description: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (name, genre, description) VALUES (?,?,?)",
            (name, genre, description)
        )
        pid = cur.lastrowid
        # Создаём три акта по умолчанию
        default_acts = [
            (1, "Завязка",       "#8b5cf6"),
            (2, "Конфронтация",  "#ef4444"),
            (3, "Развязка",      "#22c55e"),
        ]
        for num, title, color in default_acts:
            conn.execute(
                "INSERT INTO acts (project_id, number, title, color) VALUES (?,?,?,?)",
                (pid, num, title, color)
            )
        return pid


def update_project(pid: int, name: str, genre: str, description: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET name=?, genre=?, description=? WHERE id=?",
            (name, genre, description, pid)
        )


def set_fe_project(pid: int, fe_pid: int | None) -> None:
    """Связать проект планировщика с проектом Fiction Engine."""
    with get_conn() as conn:
        conn.execute("UPDATE projects SET fe_project_id=? WHERE id=?", (fe_pid, pid))


def set_chapter_scenes(pid: int, chapter_num: int, scene_ids: list[int]) -> None:
    """
    Сцены плана главы chapter_num. План главы в FE заменяется целиком, и
    здесь так же: сцены, бывшие в прошлом плане этой главы, метку теряют.
    Снапшот не пишется — это не правка карточки.
    """
    with get_conn() as conn:
        conn.execute("UPDATE scenes SET chapter_num=NULL WHERE project_id=? AND chapter_num=?",
                     (pid, chapter_num))
        conn.executemany("UPDATE scenes SET chapter_num=? WHERE id=? AND project_id=?",
                         [(chapter_num, sid, pid) for sid in scene_ids])


def delete_project(pid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))


# ─── Acts ─────────────────────────────────────────────────────────────────────

def get_acts(project_id: int) -> list:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM acts WHERE project_id=? ORDER BY number", (project_id,)
        ).fetchall()]


def save_acts(project_id: int, acts: list[dict]) -> list[int]:
    """
    Все акты проекта разом, в одной транзакции: номера уникальны в проекте, и
    обмен номерами 1↔2 или новый акт после удаления давали по отдельности
    конфликт — изменения молча не сохранялись (разбор планировщика 21.10).
    acts: [{id|None, number, title, color}]. ValueError — номера неверны.
    """
    nums = [int(a.get("number") or 0) for a in acts]
    if any(n < 1 for n in nums) or len(set(nums)) != len(nums):
        raise ValueError("номера актов — разные целые числа от 1")
    ids = []
    with get_conn() as conn:
        own = {r[0] for r in conn.execute("SELECT id FROM acts WHERE project_id=?", (project_id,))}
        # Сначала временные номера: иначе обмен упирается в UNIQUE на полпути
        conn.execute("UPDATE acts SET number=-id WHERE project_id=?", (project_id,))
        for a, n in zip(acts, nums):
            if a.get("id") and int(a["id"]) in own:
                conn.execute("UPDATE acts SET number=?, title=?, color=? WHERE id=? AND project_id=?",
                             (n, a.get("title") or "Акт", a.get("color") or "#6b7280", int(a["id"]), project_id))
                ids.append(int(a["id"]))
            else:
                cur = conn.execute("INSERT INTO acts (project_id, number, title, color) VALUES (?,?,?,?)",
                                   (project_id, n, a.get("title") or "Акт", a.get("color") or "#6b7280"))
                ids.append(cur.lastrowid)
        # Акты проекта, которых нет в списке, — с прежними номерами за концом
        rest = conn.execute("SELECT id FROM acts WHERE project_id=? AND number < 0 ORDER BY -number",
                            (project_id,)).fetchall()
        top = max(nums, default=0)
        for i, (aid,) in enumerate(rest, 1):
            conn.execute("UPDATE acts SET number=? WHERE id=?", (top + i, aid))
    return ids


def save_act(project_id: int, act_id: int | None, number: int, title: str, color: str) -> int:
    with get_conn() as conn:
        if act_id:
            conn.execute(
                "UPDATE acts SET number=?, title=?, color=? WHERE id=? AND project_id=?",
                (number, title, color, act_id, project_id)
            )
            return act_id
        else:
            cur = conn.execute(
                "INSERT INTO acts (project_id, number, title, color) VALUES (?,?,?,?)",
                (project_id, number, title, color)
            )
            return cur.lastrowid


def delete_act(act_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM acts WHERE id=?", (act_id,))


# ─── Scenes ───────────────────────────────────────────────────────────────────

def get_scenes(project_id: int) -> list:
    """Сцены проекта в порядке доски: по номеру акта (не по id), без акта — в конце."""
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT s.* FROM scenes s LEFT JOIN acts a ON a.id = s.act_id WHERE s.project_id=? "
            "ORDER BY a.number IS NULL, a.number, s.position, s.id",
            (project_id,)
        ).fetchall()]


def get_scene(scene_id: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM scenes WHERE id=?", (scene_id,)).fetchone()
        return dict(r) if r else None


def create_scene(project_id: int, act_id: int | None = None) -> int:
    with get_conn() as conn:
        # Позиция — последняя в акте; «IS»: у сцен без акта act_id=NULL, и «=»
        # не находил ни одной — все получали позицию 1 (разбор 21.10)
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position),0) FROM scenes WHERE project_id=? AND act_id IS ?",
            (project_id, act_id)
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO scenes (project_id, act_id, position) VALUES (?,?,?)",
            (project_id, act_id, max_pos + 1)
        )
        return cur.lastrowid


def update_scene(scene_id: int, data: dict, reason: str = "изменена", snapshot: bool = True):
    """Обновляет сцену и создаёт снапшот."""
    fields = ["title", "location", "day", "time_of_day", "characters",
              "what_happens", "emotion", "hold", "notes", "act_id", "position"]
    sets =", ".join(f"{f}=?" for f in fields if f in data)
    vals = [data[f] for f in fields if f in data]
    if not sets:
        return
    old = get_scene(scene_id)
    # Снапшот — только если что-то меняется. Автосохранение при уходе со
    # страницы писало копию на каждый уход, и десять одинаковых копий
    # вытесняли из истории настоящие версии
    if snapshot and old and any(_norm(old.get(f)) != _norm(data[f]) for f in fields if f in data):
        _create_snapshot(scene_id, old, reason)
    vals.append(scene_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE scenes SET {sets}, updated_at=datetime('now') WHERE id=?", vals
        )
    _trim_snapshots(scene_id)


def delete_scene(scene_id: int):
    """Удалить сцену; она и её связи — в корзину проекта (scene_trash): снимок
    «удалена» стирался каскадом, и вернуть сцену было нельзя."""
    old = get_scene(scene_id)
    with get_conn() as conn:
        if old:
            links = [dict(r) for r in conn.execute(
                "SELECT from_id, to_id, link_type, label FROM scene_links WHERE from_id=? OR to_id=?",
                (scene_id, scene_id))]
            conn.execute("INSERT INTO scene_trash (project_id, data, links) VALUES (?,?,?)",
                         (old["project_id"], json.dumps(old, ensure_ascii=False),
                          json.dumps(links, ensure_ascii=False)))
            conn.execute("DELETE FROM scene_trash WHERE project_id=? AND id NOT IN (SELECT id FROM scene_trash "
                         "WHERE project_id=? ORDER BY id DESC LIMIT 50)", (old["project_id"], old["project_id"]))
        conn.execute("DELETE FROM scenes WHERE id=?", (scene_id,))


def get_trash(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT id, data, deleted_at FROM scene_trash WHERE project_id=? ORDER BY id DESC",
                            (project_id,)).fetchall()
    out = []
    for r in rows:
        d = json.loads(r["data"])
        out.append({"id": r["id"], "title": d.get("title") or "Без названия",
                    "chapter_num": d.get("chapter_num"), "deleted_at": r["deleted_at"]})
    return out


def restore_from_trash(project_id: int, trash_id: int) -> int | None:
    """Вернуть сцену из корзины: новая запись в конце её акта (или «без акта»,
    если акта нет), связи — с теми сценами, что ещё есть. → id сцены или None."""
    with get_conn() as conn:
        row = conn.execute("SELECT data, links FROM scene_trash WHERE id=? AND project_id=?",
                           (trash_id, project_id)).fetchone()
        if not row:
            return None
        d = json.loads(row["data"])
        act = d.get("act_id")
        if act and not conn.execute("SELECT 1 FROM acts WHERE id=? AND project_id=?", (act, project_id)).fetchone():
            act = None
        pos = conn.execute("SELECT COALESCE(MAX(position),0) FROM scenes WHERE project_id=? AND act_id IS ?",
                           (project_id, act)).fetchone()[0] + 1
        cols = [c for c in ("title", "location", "day", "time_of_day", "characters", "what_happens",
                            "emotion", "hold", "notes") if c in d]
        cur = conn.execute(
            f"INSERT INTO scenes (project_id, act_id, position, {', '.join(cols)}) "
            f"VALUES (?,?,?,{','.join('?' * len(cols))})", (project_id, act, pos, *[d[c] for c in cols]))
        new_id = cur.lastrowid
        own = {r[0] for r in conn.execute("SELECT id FROM scenes WHERE project_id=?", (project_id,))}
        for ln in json.loads(row["links"] or "[]"):
            a = new_id if ln["from_id"] == d["id"] else ln["from_id"]
            b = new_id if ln["to_id"] == d["id"] else ln["to_id"]
            if a in own and b in own and a != b:
                conn.execute("INSERT INTO scene_links (from_id, to_id, link_type, label) VALUES (?,?,?,?) "
                             "ON CONFLICT(from_id, to_id) DO NOTHING", (a, b, ln["link_type"], ln["label"]))
        conn.execute("DELETE FROM scene_trash WHERE id=?", (trash_id,))
    return new_id


def move_scene(scene_id: int, new_act_id: int | None, index: int):
    """
    Поставить сцену в акт на место index (0 — первой), перенумеровав сцены
    обоих актов, в одной транзакции. Раньше позиция была «длина колонки»
    без учёта места бросания и без перенумерации — дубли позиций, порядок
    сцен (а с ним план главы) не определён. Снимок не пишется: текст не
    меняется, а «перемещена» вытесняла из истории настоящие версии (21.10).
    """
    old = get_scene(scene_id)
    if not old:
        return
    with get_conn() as conn:
        pid = old["project_id"]
        target = [r[0] for r in conn.execute(
            "SELECT id FROM scenes WHERE project_id=? AND act_id IS ? AND id != ? ORDER BY position, id",
            (pid, new_act_id, scene_id))]
        index = max(0, min(int(index or 0), len(target)))
        target.insert(index, scene_id)
        conn.execute("UPDATE scenes SET act_id=?, updated_at=datetime('now') WHERE id=?", (new_act_id, scene_id))
        conn.executemany("UPDATE scenes SET position=? WHERE id=?", [(i + 1, s) for i, s in enumerate(target)])
        if old["act_id"] != new_act_id:
            rest = [r[0] for r in conn.execute(
                "SELECT id FROM scenes WHERE project_id=? AND act_id IS ? ORDER BY position, id",
                (pid, old["act_id"]))]
            conn.executemany("UPDATE scenes SET position=? WHERE id=?", [(i + 1, s) for i, s in enumerate(rest)])


def import_chapter(project_id: int, act_id: int | None, chapter_num: int,
                   scenes: list[dict], links: list[dict]) -> list[int]:
    """
    Сцены главы из её текста (engine/chapter_import) — в акт, по порядку
    глав, с меткой главы; связи — между ними и со сценами доски этого
    проекта. Одна транзакция: полглавы на доске не остаётся.
    links: {"from": ["new", i] | ["board", id], "to": …, "type", "label"}.
    """
    from .chapter_import import FIELDS, insert_position
    with get_conn() as conn:
        act = [dict(r) for r in conn.execute(
            "SELECT id, chapter_num FROM scenes WHERE project_id=? AND act_id IS ? ORDER BY position, id",
            (project_id, act_id)).fetchall()]
        at = insert_position(act, chapter_num)
        new_ids = []
        for s in scenes:
            cur = conn.execute(
                f"INSERT INTO scenes (project_id, act_id, chapter_num, {', '.join(FIELDS)}) "
                f"VALUES (?,?,?,{','.join('?' * len(FIELDS))})",
                (project_id, act_id, chapter_num, *[str(s.get(f) or "") for f in FIELDS]))
            new_ids.append(cur.lastrowid)
        order = [s["id"] for s in act[:at]] + new_ids + [s["id"] for s in act[at:]]
        conn.executemany("UPDATE scenes SET position=? WHERE id=?",
                         [(i + 1, sid) for i, sid in enumerate(order)])
        own = {r[0] for r in conn.execute("SELECT id FROM scenes WHERE project_id=?", (project_id,))}
        for ln in links:
            ids = []
            for kind, ref in (ln["from"], ln["to"]):
                ids.append(new_ids[ref] if kind == "new" and 0 <= ref < len(new_ids)
                           else ref if kind == "board" and ref in own else None)
            if None in ids or ids[0] == ids[1]:
                continue
            conn.execute(
                """INSERT INTO scene_links (from_id, to_id, link_type, label) VALUES (?,?,?,?)
                   ON CONFLICT(from_id, to_id) DO NOTHING""",
                (ids[0], ids[1], ln.get("type") or "cause", ln.get("label") or ""))
        return new_ids


# ─── Scene Links ─────────────────────────────────────────────────────────────

def get_links(project_id: int) -> list:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            """SELECT sl.*, s1.title as from_title, s2.title as to_title
               FROM scene_links sl
               JOIN scenes s1 ON sl.from_id = s1.id
               JOIN scenes s2 ON sl.to_id   = s2.id
               WHERE s1.project_id=?""",
            (project_id,)
        ).fetchall()]


def save_link(from_id: int, to_id: int, link_type: str, label: str = "") -> int:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO scene_links (from_id, to_id, link_type, label)
               VALUES (?,?,?,?)
               ON CONFLICT(from_id, to_id) DO UPDATE SET
               link_type=excluded.link_type, label=excluded.label""",
            (from_id, to_id, link_type, label)
        )
        # id — настоящей связи: при повторе (upsert) lastrowid давал 0, и граф
        # рисовал дубль ребра с id 0 (разбор планировщика 21.10)
        return conn.execute("SELECT id FROM scene_links WHERE from_id=? AND to_id=?",
                            (from_id, to_id)).fetchone()[0]


def delete_link(link_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM scene_links WHERE id=?", (link_id,))


# ─── Snapshots ───────────────────────────────────────────────────────────────

import json


def _norm(v) -> str:
    """Значение поля для сравнения: None и «», 3 и «3» — одно и то же."""
    return "" if v is None else str(v).strip()


def _create_snapshot(scene_id: int, data: dict, reason: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO scene_snapshots (scene_id, reason, data) VALUES (?,?,?)",
            (scene_id, reason, json.dumps(data, ensure_ascii=False))
        )


def _trim_snapshots(scene_id: int, keep: int = 10):
    with get_conn() as conn:
        ids = conn.execute(
            "SELECT id FROM scene_snapshots WHERE scene_id=? ORDER BY id DESC LIMIT -1 OFFSET ?",
            (scene_id, keep)
        ).fetchall()
        if ids:
            conn.execute(
                f"DELETE FROM scene_snapshots WHERE id IN ({','.join(str(r['id']) for r in ids)})"
            )


def get_snapshots(scene_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, reason, created_at, data FROM scene_snapshots WHERE scene_id=? ORDER BY id DESC",
            (scene_id,)
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["data"] = json.loads(d["data"])
        result.append(d)
    return result
