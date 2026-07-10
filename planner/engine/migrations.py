"""
engine/migrations.py — система миграций схемы БД.

Принцип:
- Каждая миграция имеет номер версии и список SQL-команд
- Миграции применяются один раз в порядке возрастания версии
- Текущая версия хранится в таблице schema_version
- При старте приложения apply_migrations() применяет всё что ещё не применено

Как добавить новую миграцию:
1. Добавить новый номер в MIGRATIONS с нужными SQL-командами
2. Больше ничего — при следующем запуске применится автоматически
"""

import logging

logger = logging.getLogger(__name__)

# ─── Реестр миграций ──────────────────────────────────────────────────────────
# Ключ = номер версии, значение = список SQL-команд
# ВАЖНО: никогда не редактировать уже применённые миграции — только добавлять новые

MIGRATIONS = {
    1: [
        # Базовая версия — фиксируем что схема уже создана через init_db()
        # Индексы для производительности
        "CREATE INDEX IF NOT EXISTS idx_scenes_project ON scenes(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_scenes_act ON scenes(act_id)",
        "CREATE INDEX IF NOT EXISTS idx_scenes_act_position ON scenes(act_id, position)",
        "CREATE INDEX IF NOT EXISTS idx_links_from ON scene_links(from_id)",
        "CREATE INDEX IF NOT EXISTS idx_links_to ON scene_links(to_id)",
        "CREATE INDEX IF NOT EXISTS idx_snapshots_scene ON scene_snapshots(scene_id)",
        "CREATE INDEX IF NOT EXISTS idx_tags_scene ON scene_tags(scene_id)",
        "CREATE INDEX IF NOT EXISTS idx_beats_scene ON scene_beats(scene_id)",
    ],
    2: [
        # Шаблоны сцен
        """CREATE TABLE IF NOT EXISTS scene_templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            is_global   INTEGER DEFAULT 0,
            emotion     TEXT DEFAULT '',
            location    TEXT DEFAULT '',
            time_of_day TEXT DEFAULT '',
            characters  TEXT DEFAULT '',
            what_happens TEXT DEFAULT '',
            notes       TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now'))
        )""",
        # Глобальные встроенные шаблоны (project_id = NULL, is_global = 1)
        "INSERT OR IGNORE INTO scene_templates (name, is_global, emotion, what_happens) VALUES ('Экшн', 1, 'напряжение', 'Погоня или сражение. Герой в опасности.')",
        "INSERT OR IGNORE INTO scene_templates (name, is_global, emotion, what_happens) VALUES ('Диалог', 1, 'нарастание', 'Два персонажа разговаривают. Раскрывается информация или конфликт.')",
        "INSERT OR IGNORE INTO scene_templates (name, is_global, emotion, what_happens) VALUES ('Экспозиция', 1, 'нейтрально', 'Герой узнаёт новую информацию о мире или ситуации.')",
        "INSERT OR IGNORE INTO scene_templates (name, is_global, emotion, what_happens) VALUES ('Кульминация', 1, 'пик', 'Все линии сходятся. Точка невозврата.')",
        "INSERT OR IGNORE INTO scene_templates (name, is_global, emotion, what_happens) VALUES ('Флэшбек', 1, 'ностальгия', 'Воспоминание. Объясняет мотивацию или раскрывает прошлое.')",
    ],
    3: [
        # Поиск — полнотекстовый индекс FTS5
        """CREATE VIRTUAL TABLE IF NOT EXISTS scenes_fts USING fts5(
            title, what_happens, characters, location, notes,
            content=scenes, content_rowid=id
        )""",
        # Заполняем FTS для существующих сцен
        """INSERT INTO scenes_fts(rowid, title, what_happens, characters, location, notes)
           SELECT id, COALESCE(title,''), COALESCE(what_happens,''),
                  COALESCE(characters,''), COALESCE(location,''), COALESCE(notes,'')
           FROM scenes""",
        # Триггеры для автоматического обновления FTS при изменении сцен
        """CREATE TRIGGER IF NOT EXISTS scenes_fts_insert AFTER INSERT ON scenes BEGIN
            INSERT INTO scenes_fts(rowid, title, what_happens, characters, location, notes)
            VALUES(new.id, COALESCE(new.title,''), COALESCE(new.what_happens,''),
                   COALESCE(new.characters,''), COALESCE(new.location,''), COALESCE(new.notes,''));
        END""",
        """CREATE TRIGGER IF NOT EXISTS scenes_fts_delete AFTER DELETE ON scenes BEGIN
            INSERT INTO scenes_fts(scenes_fts, rowid, title, what_happens, characters, location, notes)
            VALUES('delete', old.id, COALESCE(old.title,''), COALESCE(old.what_happens,''),
                   COALESCE(old.characters,''), COALESCE(old.location,''), COALESCE(old.notes,''));
        END""",
        """CREATE TRIGGER IF NOT EXISTS scenes_fts_update AFTER UPDATE ON scenes BEGIN
            INSERT INTO scenes_fts(scenes_fts, rowid, title, what_happens, characters, location, notes)
            VALUES('delete', old.id, COALESCE(old.title,''), COALESCE(old.what_happens,''),
                   COALESCE(old.characters,''), COALESCE(old.location,''), COALESCE(old.notes,''));
            INSERT INTO scenes_fts(rowid, title, what_happens, characters, location, notes)
            VALUES(new.id, COALESCE(new.title,''), COALESCE(new.what_happens,''),
                   COALESCE(new.characters,''), COALESCE(new.location,''), COALESCE(new.notes,''));
        END""",
    ],
    # Следующие миграции добавлять здесь:
    # 4: [ "ALTER TABLE scenes ADD COLUMN ..." ],
}


# ─── Применение миграций ──────────────────────────────────────────────────────

def get_current_version() -> int:
    from engine.db import get_conn
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version    INTEGER PRIMARY KEY,
                applied_at TEXT DEFAULT (datetime('now'))
            )
        """)
        r = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return r[0] if r[0] is not None else 0


def apply_migrations():
    """Применить все неприменённые миграции. Вызывается при старте."""
    from engine.db import get_conn

    current = get_current_version()
    pending = {v: cmds for v, cmds in MIGRATIONS.items() if v > current}

    if not pending:
        logger.debug(f"БД актуальна (версия {current})")
        return

    for version in sorted(pending):
        cmds = pending[version]
        logger.info(f"Применяю миграцию {version}...")
        try:
            with get_conn() as conn:
                for cmd in cmds:
                    conn.execute(cmd)
                conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (version,)
                )
            logger.info(f"Миграция {version} — OK")
        except Exception as e:
            logger.error(f"Миграция {version} провалилась: {e}")
            raise RuntimeError(f"Миграция {version} провалилась: {e}") from e

    new_version = get_current_version()
    print(f"[planner] БД обновлена до версии {new_version}")
