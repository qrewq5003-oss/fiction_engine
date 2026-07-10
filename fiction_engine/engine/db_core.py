"""
db_core.py — инфраструктурный слой БД.

Ответственность: ТОЛЬКО соединение, создание схемы, миграции,
шаблоны по умолчанию и логирование ошибок.

Ничего не знает о проектах, главах или настройках.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / "fiction_engine" / "projects.db"

# Импорт логгера отложен чтобы избежать циклической зависимости
# (logger импортирует db_core для DBHandler)
def _get_log():
    from .logger import get_logger
    return get_logger(__name__)


# ─── Соединение ───────────────────────────────────────────────────────────────

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ─── Схема ────────────────────────────────────────────────────────────────────

def init_db():
    """Единая инициализация всех таблиц + миграции для существующих БД."""
    with get_conn() as conn:
        conn.executescript("""
        -- ─── Ядро ──────────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            genre       TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            config      TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS chapters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            number      INTEGER NOT NULL,
            title       TEXT,
            content     TEXT NOT NULL,
            word_count  INTEGER,
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(project_id, number)
        );

        CREATE TABLE IF NOT EXISTS state_engine (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id   INTEGER NOT NULL REFERENCES projects(id) UNIQUE,
            global_state TEXT DEFAULT '',
            plot_matrix  TEXT DEFAULT '',
            memory_graph TEXT DEFAULT '',
            updated_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS state_updates (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id   INTEGER NOT NULL REFERENCES projects(id),
            chapter_num  INTEGER NOT NULL,
            raw_analysis TEXT,
            applied      INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL UNIQUE,
            api_key  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS prep_data (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            section     TEXT NOT NULL,
            content     TEXT DEFAULT '',
            updated_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(project_id, section)
        );

        -- ─── Генерации ─────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS generation_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id   INTEGER NOT NULL REFERENCES projects(id),
            chapter_num  INTEGER NOT NULL,
            model        TEXT,
            mode         TEXT,
            task         TEXT,
            result_text  TEXT,
            word_count   INTEGER,
            score        REAL,
            score_details TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        -- ─── Символы ───────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS symbols (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id      INTEGER NOT NULL REFERENCES projects(id),
            name            TEXT NOT NULL,
            symbol_type     TEXT DEFAULT 'предмет',
            introduced_ch   INTEGER,
            initial_meaning TEXT DEFAULT '',
            appearances     TEXT DEFAULT '[]',
            planned         TEXT DEFAULT '[]',
            related_chars   TEXT DEFAULT '',
            notes           TEXT DEFAULT '',
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_symbols_project ON symbols(project_id);

        -- ─── Голосовые профили ─────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS voice_profiles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            name        TEXT NOT NULL,
            source      TEXT DEFAULT 'custom',
            profile     TEXT DEFAULT '',
            samples     TEXT DEFAULT '',
            active      INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        -- ─── Pipeline ──────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id   INTEGER NOT NULL REFERENCES projects(id),
            chapter_num  INTEGER NOT NULL,
            status       TEXT DEFAULT 'running',
            model_gen    TEXT,
            model_critic TEXT,
            model_editor TEXT,
            model_judge  TEXT,
            created_at   TEXT DEFAULT (datetime('now')),
            finished_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS pipeline_iterations (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       INTEGER NOT NULL REFERENCES pipeline_runs(id),
            iteration    INTEGER NOT NULL,
            stage        TEXT NOT NULL,
            model_used   TEXT,
            input_text   TEXT,
            output_text  TEXT,
            score        REAL,
            verdict      TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        -- ─── Эталоны (few-shot) ────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS exemplars (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            chapter_num INTEGER NOT NULL,
            label       TEXT,
            text        TEXT NOT NULL,
            created_at  TEXT
        );

        -- ─── State History ─────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS state_history (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id   INTEGER NOT NULL REFERENCES projects(id),
            global_state TEXT,
            plot_matrix  TEXT,
            memory_graph TEXT,
            reason       TEXT,
            saved_at     TEXT
        );

        -- ─── Режиссёрские заметки ──────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS director_notes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id    INTEGER NOT NULL REFERENCES projects(id),
            after_chapter INTEGER NOT NULL,
            note          TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now')),
            UNIQUE(project_id, after_chapter)
        );

        -- ─── Дрейф голоса ─────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS voice_drift_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            chapter_num INTEGER NOT NULL,
            score       REAL NOT NULL,
            issues      TEXT DEFAULT '',
            checked_at  TEXT DEFAULT (datetime('now'))
        );

        -- ─── L3 Memory ─────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS l3_memory (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            chapter_num INTEGER NOT NULL,
            events      TEXT DEFAULT '',
            characters  TEXT DEFAULT '',
            conflicts   TEXT DEFAULT '',
            promises    TEXT DEFAULT '',
            mood        TEXT DEFAULT '',
            raw_summary TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now')),
            UNIQUE(project_id, chapter_num)
        );

        -- ─── Оценки глав (авто) ────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS chapter_scores (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            chapter_num INTEGER NOT NULL,
            total       REAL,
            details     TEXT,
            scored_at   TEXT DEFAULT (datetime('now')),
            UNIQUE(project_id, chapter_num)
        );

        -- ─── База знаний ───────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS knowledge_base (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id  INTEGER NOT NULL REFERENCES projects(id),
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            tags        TEXT DEFAULT '',
            auto_inject INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_kb_project ON knowledge_base(project_id);

        -- ─── Лог ошибок движка ─────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS engine_error_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            context     TEXT NOT NULL,
            error       TEXT NOT NULL,
            logged_at   TEXT DEFAULT (datetime('now'))
        );

        -- ─── Когнитивный анализ глав ────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS chapter_analysis (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id       INTEGER NOT NULL REFERENCES projects(id),
            chapter_num      INTEGER NOT NULL,
            arc_progress     TEXT DEFAULT '{}',
            character_deltas TEXT DEFAULT '[]',
            opened_promises  TEXT DEFAULT '[]',
            closed_promises  TEXT DEFAULT '[]',
            causal_chains    TEXT DEFAULT '[]',
            logical_gaps     TEXT DEFAULT '[]',
            conflict_score   REAL  DEFAULT 0.0,
            pacing_note      TEXT  DEFAULT '',
            plot_threads     TEXT  DEFAULT '{}',
            analysis_quality TEXT  DEFAULT 'ok',
            raw_data         TEXT  DEFAULT '{}',
            opening_type     TEXT  DEFAULT '',
            closing_type     TEXT  DEFAULT '',
            created_at       TEXT  DEFAULT (datetime('now')),
            UNIQUE(project_id, chapter_num)
        );

        -- ─── Правки автора (обучение на голосе) ──────────────────────────────
        -- Каждая запись — одна принятая/отклонённая итерация pipeline.
        -- Через 10-20 глав из этой таблицы можно извлекать паттерны промптом.
        CREATE TABLE IF NOT EXISTS author_edits (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id      INTEGER NOT NULL REFERENCES projects(id),
            chapter_num     INTEGER NOT NULL,
            run_id          INTEGER REFERENCES pipeline_runs(id),
            original_text   TEXT NOT NULL,
            accepted_text   TEXT NOT NULL,
            rejection_reason TEXT DEFAULT '',
            action          TEXT DEFAULT 'accept',   -- 'accept' | 'reject' | 'manual_edit'
            judge_score     REAL,
            created_at      TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_author_edits_project ON author_edits(project_id);
        """)

    _run_migrations()


def _run_migrations():
    """Безопасные ALTER TABLE для существующих баз данных."""
    migrations = [
        ("generation_history", "score",         "ALTER TABLE generation_history ADD COLUMN score REAL"),
        ("generation_history", "score_details",  "ALTER TABLE generation_history ADD COLUMN score_details TEXT"),
        ("generation_history", "task",           "ALTER TABLE generation_history ADD COLUMN task TEXT"),
        ("chapters",           "title",          "ALTER TABLE chapters ADD COLUMN title TEXT"),
        ("projects",           "config",         "ALTER TABLE projects ADD COLUMN config TEXT DEFAULT '{}'"),
        ("voice_profiles",     "source",         "ALTER TABLE voice_profiles ADD COLUMN source TEXT DEFAULT 'custom'"),
        ("knowledge_base",     "auto_inject",    "ALTER TABLE knowledge_base ADD COLUMN auto_inject INTEGER DEFAULT 0"),
        ("engine_error_log",   "context",        "CREATE TABLE IF NOT EXISTS engine_error_log (id INTEGER PRIMARY KEY AUTOINCREMENT, context TEXT NOT NULL, error TEXT NOT NULL, logged_at TEXT DEFAULT (datetime('now')))"),
        ("chapter_analysis",   "project_id",     "CREATE TABLE IF NOT EXISTS chapter_analysis (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, chapter_num INTEGER NOT NULL, arc_progress TEXT DEFAULT '{}', character_deltas TEXT DEFAULT '[]', opened_promises TEXT DEFAULT '[]', closed_promises TEXT DEFAULT '[]', causal_chains TEXT DEFAULT '[]', logical_gaps TEXT DEFAULT '[]', conflict_score REAL DEFAULT 0.0, pacing_note TEXT DEFAULT '', plot_threads TEXT DEFAULT '{}', analysis_quality TEXT DEFAULT 'ok', raw_data TEXT DEFAULT '{}', created_at TEXT DEFAULT (datetime('now')), UNIQUE(project_id, chapter_num))"),
        # Трекинг структурных паттернов (пункт 6: monotony detection)
        ("chapter_analysis",   "opening_type",   "ALTER TABLE chapter_analysis ADD COLUMN opening_type TEXT DEFAULT ''"),
        ("chapter_analysis",   "closing_type",   "ALTER TABLE chapter_analysis ADD COLUMN closing_type TEXT DEFAULT ''"),
        # Правки автора — фундамент DATA_DRIVEN_LEARNING (пункт 2)
        ("author_edits",       "id",             "CREATE TABLE IF NOT EXISTS author_edits (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, chapter_num INTEGER NOT NULL, run_id INTEGER, original_text TEXT NOT NULL, accepted_text TEXT NOT NULL, rejection_reason TEXT DEFAULT '', action TEXT DEFAULT 'accept', judge_score REAL, created_at TEXT DEFAULT (datetime('now')))"),
    ]
    with get_conn() as conn:
        for table, col, sql in migrations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                # Колонка/таблица уже существует — штатная ситуация для миграций
                pass


# ─── Логирование ошибок ───────────────────────────────────────────────────────

def log_error(context: str, error: Exception) -> None:
    """
    Записать ошибку — делегирует в централизованный logger.py.
    Оставлен для обратной совместимости: везде где был `from .db_core import log_error`.
    Никогда не бросает исключение.
    """
    try:
        _get_log().error(context, exc=error)
    except Exception:
        # Абсолютный fallback — прямо в БД без logger
        try:
            with get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO engine_error_log (context, error) VALUES (?,?)",
                    (context[:500], f"{type(error).__name__}: {error}"[:2000])
                )
        except sqlite3.Error:
            # БД недоступна — молча игнорируем, логировать некуда
            pass


def get_error_log(limit: int = 50) -> list[dict]:
    """Получить последние N записей лога ошибок для дебага."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT context, error, logged_at FROM engine_error_log "
                "ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


# ─── Шаблоны State Engine ─────────────────────────────────────────────────────

def _default_global():
    return """## ПЕРСОНАЖИ

### [Имя]
СОСТОЯНИЕ: [физическое и эмоциональное одним предложением]
ЛОКАЦИЯ: [где находится]
ЦЕЛЬ_СЕЙЧАС: [что хочет прямо сейчас]
ЦЕЛЬ_ГЛУБИННАЯ: [что хочет на самом деле — может не осознавать]
ЗНАЕТ: []
НЕ_ЗНАЕТ: []
ИЗМЕНЕНИЕ: [Гл.—]

---

## МИР

МОМЕНТ: [текущий момент одним предложением]
УГРОЗА: []
НЕ_ДОЛЖНО_СЛУЧИТЬСЯ: [что нельзя допустить в следующей главе]
"""


def _default_plot():
    return """## ОСНОВНАЯ ЛИНИЯ

СТАТУС: [активна / приостановлена / завершена]
ГДЕ_СЕЙЧАС: []
СЛЕДУЮЩИЙ_ШАГ: []
ИЗМЕНЕНИЕ: [Гл.—]

---

## ВТОРОСТЕПЕННЫЕ ЛИНИИ

---

## ОТКРЫТЫЕ ВОПРОСЫ

---

## ЧТО НЕЛЬЗЯ ЗАБЫТЬ

"""


def _default_memory():
    return """## КТО ЧТО ЗНАЕТ

### [Имя]
ЗНАЕТ: []
НЕ_ЗНАЕТ: []
ДУМАЕТ_ЧТО_ЗНАЕТ: []

---

## СЕКРЕТЫ И ТАЙНЫ

## ИНФОРМАЦИОННЫЙ БАЛАНС (кто знает больше всех)

"""
