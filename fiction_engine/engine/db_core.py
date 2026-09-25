"""
db_core.py — инфраструктурный слой БД.

Ответственность: ТОЛЬКО соединение, создание схемы, миграции,
шаблоны по умолчанию и логирование ошибок.

Ничего не знает о проектах, главах или настройках.
"""

import sqlite3
from typing import TYPE_CHECKING

if TYPE_CHECKING:                     # только для аннотаций
    from .logger import EngineLogger
from datetime import datetime
from pathlib import Path

DB_PATH = Path.home() / "fiction_engine" / "projects.db"

# Результат включения WAL: имя режима ("wal", "delete") либо "недоступен: ...".
# None — ещё не пробовали. Заполняется при первом get_conn().
WAL_STATUS: str | None = None

# Импорт логгера отложен чтобы избежать циклической зависимости
# (logger импортирует db_core для DBHandler)
def _get_log() -> "EngineLogger":
    from .logger import get_logger
    return get_logger(__name__)


# ─── Соединение ───────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    """
    Соединение с БД.

    PRAGMA-настройки задаются на каждое соединение — в SQLite они не хранятся
    в файле (кроме journal_mode) и сбрасываются при каждом подключении:

      foreign_keys=ON — объявленные в схеме REFERENCES без этого не работают,
                        SQLite по умолчанию их не проверяет. Именно поэтому
                        удаление проекта годами оставляло сирот в 11 таблицах.
      journal_mode=WAL — читатели не блокируют писателя. Генерация идёт в
                        фоновых потоках параллельно запросам веб-интерфейса.
      busy_timeout    — вместо мгновенного "database is locked" ждать до 5 с.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # WAL не везде доступен (сетевые ФС). Логировать отсюда нельзя: DBHandler
    # логгера сам вызывает get_conn — получилась бы рекурсия. Поэтому причина
    # отказа сохраняется в модульной переменной, её видно в /settings и в CLI.
    global WAL_STATUS
    if WAL_STATUS is None:
        try:
            WAL_STATUS = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        except sqlite3.Error as e:
            WAL_STATUS = f"недоступен: {e}"
    elif not WAL_STATUS.startswith("недоступен"):
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def project_scoped_tables(conn: sqlite3.Connection) -> list[str]:
    """
    Таблицы, у которых есть колонка project_id.

    Список берётся из схемы, а не из константы: раньше delete_project держал
    захардкоженный перечень из шести таблиц, отстал от схемы и оставлял
    осиротевшие строки в остальных одиннадцати.
    """
    names = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    scoped = []
    for t in names:
        cols = [c["name"] for c in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        if "project_id" in cols:
            scoped.append(t)
    return scoped


def count_orphans() -> dict[str, int]:
    """Сколько строк ссылается на несуществующие проекты. Ничего не меняет."""
    result: dict[str, int] = {}
    with get_conn() as conn:
        for t in project_scoped_tables(conn):
            try:
                n = conn.execute(
                    f"SELECT count(*) AS n FROM {t} "
                    "WHERE project_id NOT IN (SELECT id FROM projects)"
                ).fetchone()["n"]
            except sqlite3.Error:
                continue
            if n:
                result[t] = n
    return result


def cleanup_orphans() -> dict[str, int]:
    """
    Удалить строки, ссылающиеся на несуществующие проекты.

    Вызывать осознанно (CLI `python3 cli.py cleanup`), а не при каждом старте:
    это удаление данных, пусть и принадлежавших уже удалённым проектам.
    """
    removed = count_orphans()
    if not removed:
        return {}
    with get_conn() as conn:
        for t in removed:
            conn.execute(
                f"DELETE FROM {t} WHERE project_id NOT IN (SELECT id FROM projects)")
    return removed


# ─── Схема ────────────────────────────────────────────────────────────────────

def init_db() -> None:
    """Единая инициализация всех таблиц + миграции для существующих БД."""
    with get_conn() as conn:
        conn.executescript("""
        -- ─── Ядро ──────────────────────────────────────────────────────────────
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            genre       TEXT,
            genre_key   TEXT,
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


def _run_migrations() -> None:
    """Безопасные ALTER TABLE для существующих баз данных."""
    migrations = [
        ("generation_history", "score",         "ALTER TABLE generation_history ADD COLUMN score REAL"),
        ("generation_history", "score_details",  "ALTER TABLE generation_history ADD COLUMN score_details TEXT"),
        ("generation_history", "task",           "ALTER TABLE generation_history ADD COLUMN task TEXT"),
        ("chapters",           "title",          "ALTER TABLE chapters ADD COLUMN title TEXT"),
        ("projects",           "config",         "ALTER TABLE projects ADD COLUMN config TEXT DEFAULT '{}'"),
        # Ключ жанра, выбранный автором. NULL — не выбран: движок определяет
        # жанр по свободному тексту projects.genre, а интерфейс просит выбрать
        ("projects",           "genre_key",      "ALTER TABLE projects ADD COLUMN genre_key TEXT"),
        ("voice_profiles",     "source",         "ALTER TABLE voice_profiles ADD COLUMN source TEXT DEFAULT 'custom'"),
        ("knowledge_base",     "auto_inject",    "ALTER TABLE knowledge_base ADD COLUMN auto_inject INTEGER DEFAULT 0"),
        ("engine_error_log",   "context",        "CREATE TABLE IF NOT EXISTS engine_error_log (id INTEGER PRIMARY KEY AUTOINCREMENT, context TEXT NOT NULL, error TEXT NOT NULL, logged_at TEXT DEFAULT (datetime('now')))"),
        ("chapter_analysis",   "project_id",     "CREATE TABLE IF NOT EXISTS chapter_analysis (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, chapter_num INTEGER NOT NULL, arc_progress TEXT DEFAULT '{}', character_deltas TEXT DEFAULT '[]', opened_promises TEXT DEFAULT '[]', closed_promises TEXT DEFAULT '[]', causal_chains TEXT DEFAULT '[]', logical_gaps TEXT DEFAULT '[]', conflict_score REAL DEFAULT 0.0, pacing_note TEXT DEFAULT '', plot_threads TEXT DEFAULT '{}', analysis_quality TEXT DEFAULT 'ok', raw_data TEXT DEFAULT '{}', created_at TEXT DEFAULT (datetime('now')), UNIQUE(project_id, chapter_num))"),
        # Трекинг структурных паттернов (пункт 6: monotony detection)
        ("chapter_analysis",   "opening_type",   "ALTER TABLE chapter_analysis ADD COLUMN opening_type TEXT DEFAULT ''"),
        ("chapter_analysis",   "closing_type",   "ALTER TABLE chapter_analysis ADD COLUMN closing_type TEXT DEFAULT ''"),
        # Правки автора — фундамент DATA_DRIVEN_LEARNING (пункт 2)
        # Учёт расходов на вызовы моделей. Движок не знал, во что обходится
        # глава: ни токенов, ни стоимости никуда не писалось, и на вопрос
        # «сколько потрачено» приходилось считать вызовы по памяти.
        # cost_usd пустой — значит тариф неизвестен (перепродавец не вернул
        # цену, нашей таблицы на эту модель нет); токены при этом записаны.
        ("api_usage",          "id",             "CREATE TABLE IF NOT EXISTS api_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, model TEXT NOT NULL, operation TEXT DEFAULT '', input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0, cost_usd REAL, project_id INTEGER, chapter_num INTEGER, created_at TEXT DEFAULT (datetime('now')))"),
        ("author_edits",       "id",             "CREATE TABLE IF NOT EXISTS author_edits (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, chapter_num INTEGER NOT NULL, run_id INTEGER, original_text TEXT NOT NULL, accepted_text TEXT NOT NULL, rejection_reason TEXT DEFAULT '', action TEXT DEFAULT 'accept', judge_score REAL, created_at TEXT DEFAULT (datetime('now')))"),
    ]
    # «Уже существует» — штатный исход повторного прогона миграции.
    # Всё остальное (опечатка в SQL, битая схема) молча глотать нельзя:
    # миграция просто не применится, а узнается об этом через отказ
    # где-то далеко и позже.
    _EXPECTED = ("already exists", "duplicate column name")

    with get_conn() as conn:
        for table, col, sql in migrations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                if any(mark in str(e).lower() for mark in _EXPECTED):
                    continue
                _get_log().error(
                    f"миграция не применилась: {table}.{col}", exc=e)


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
        except Exception:
            # Логировать некуда — молча сдаёмся. Ловим Exception, а не
            # sqlite3.Error: обещание «никогда не бросает» должно держаться
            # при любом отказе, иначе ошибка логирования подменит собой ту
            # ошибку, ради записи которой сюда и пришли.
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

def _default_global() -> str:
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


def _default_plot() -> str:
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


def _default_memory() -> str:
    return """## КТО ЧТО ЗНАЕТ

### [Имя]
ЗНАЕТ: []
НЕ_ЗНАЕТ: []
ДУМАЕТ_ЧТО_ЗНАЕТ: []

---

## СЕКРЕТЫ И ТАЙНЫ

## ИНФОРМАЦИОННЫЙ БАЛАНС (кто знает больше всех)

"""
