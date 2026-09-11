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


def delete_project(pid: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))


# ─── Acts ─────────────────────────────────────────────────────────────────────

def get_acts(project_id: int) -> list:
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM acts WHERE project_id=? ORDER BY number", (project_id,)
        ).fetchall()]


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
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM scenes WHERE project_id=? ORDER BY act_id, position",
            (project_id,)
        ).fetchall()]


def get_scene(scene_id: int) -> dict | None:
    with get_conn() as conn:
        r = conn.execute("SELECT * FROM scenes WHERE id=?", (scene_id,)).fetchone()
        return dict(r) if r else None


def create_scene(project_id: int, act_id: int | None = None) -> int:
    with get_conn() as conn:
        # Позиция — последняя в акте
        max_pos = conn.execute(
            "SELECT COALESCE(MAX(position),0) FROM scenes WHERE project_id=? AND act_id=?",
            (project_id, act_id)
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO scenes (project_id, act_id, position) VALUES (?,?,?)",
            (project_id, act_id, max_pos + 1)
        )
        return cur.lastrowid


def update_scene(scene_id: int, data: dict, reason: str = "изменена"):
    """Обновляет сцену и создаёт снапшот."""
    fields = ["title", "location", "time_of_day", "characters",
              "what_happens", "emotion", "notes", "act_id", "position"]
    old = get_scene(scene_id)
    if old:
        _create_snapshot(scene_id, old, reason)

    sets = ", ".join(f"{f}=?" for f in fields if f in data)
    vals = [data[f] for f in fields if f in data]
    if not sets:
        return
    vals.append(scene_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE scenes SET {sets}, updated_at=datetime('now') WHERE id=?", vals
        )
    _trim_snapshots(scene_id)


def delete_scene(scene_id: int):
    old = get_scene(scene_id)
    if old:
        _create_snapshot(scene_id, old, "удалена")
    with get_conn() as conn:
        conn.execute("DELETE FROM scenes WHERE id=?", (scene_id,))


def move_scene(scene_id: int, new_act_id: int | None, new_position: int):
    old = get_scene(scene_id)
    if old:
        _create_snapshot(scene_id, old, "перемещена")
    with get_conn() as conn:
        conn.execute(
            "UPDATE scenes SET act_id=?, position=?, updated_at=datetime('now') WHERE id=?",
            (new_act_id, new_position, scene_id)
        )
    _trim_snapshots(scene_id)


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
        cur = conn.execute(
            """INSERT INTO scene_links (from_id, to_id, link_type, label)
               VALUES (?,?,?,?)
               ON CONFLICT(from_id, to_id) DO UPDATE SET
               link_type=excluded.link_type, label=excluded.label""",
            (from_id, to_id, link_type, label)
        )
        return cur.lastrowid


def delete_link(link_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM scene_links WHERE id=?", (link_id,))


# ─── Snapshots ───────────────────────────────────────────────────────────────

import json

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
