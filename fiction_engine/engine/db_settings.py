"""
db_settings.py — слой конфигурации.

Ответственность: API ключи, настройки приложения, активный проект,
секции подготовки (prep).

Не знает о содержимом проектов (главах, state и т.д.).
"""

import os
from .db_core import get_conn, log_error
from .error_policy import error_boundary, handle_error, ErrorLevel


# ─── API ключи ────────────────────────────────────────────────────────────────

def save_api_key(provider: str, key: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO api_keys (provider, api_key) VALUES (?,?)",
            (provider, key)
        )


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
def _get_api_key_from_db(provider: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT api_key FROM api_keys WHERE provider=?", (provider,)
        ).fetchone()
    return row["api_key"] if row else None


def get_api_key(provider: str) -> str | None:
    result = _get_api_key_from_db(provider)
    if result:
        return result

    # Fallback к переменным окружения
    env_map = {
        "anthropic_direct": "ANTHROPIC_API_KEY",
        "nano_gpt":         "NANO_GPT_API_KEY",
        "openai_direct":    "OPENAI_API_KEY",
        "gemini_direct":    "GEMINI_API_KEY",
        "deepseek_direct":  "DEEPSEEK_API_KEY",
    }
    return os.environ.get(env_map.get(provider, ""))


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback={})
def get_all_api_keys() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT provider, api_key FROM api_keys").fetchall()
    result = {}
    for r in rows:
        k = r["api_key"]
        result[r["provider"]] = k[:8] + "..." + k[-4:] if len(k) > 12 else "***"
    return result


# ─── Настройки ────────────────────────────────────────────────────────────────

@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
def get_setting(key: str) -> str | None:
    """Получить значение настройки по ключу."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
    return row["value"] if row else None


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
def set_setting(key: str, value: str) -> None:
    """Сохранить настройку."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
            (key, value)
        )


# ─── Активный проект ──────────────────────────────────────────────────────────

def get_active_project_id() -> int | None:
    value = get_setting("active_project")
    return int(value) if value else None


def set_active_project(project_id: int) -> None:
    set_setting("active_project", str(project_id))


# ─── Prep Layer ───────────────────────────────────────────────────────────────

PREP_SECTIONS = {
    "characters":  "Персонажи",
    "world":       "Мир и магия",
    "plot":        "Сюжет и арки",
    "notes":       "Заметки автора",
}

PREP_DEFAULTS = {
    "characters": """# Персонажи

## [Имя]
Роль: [протагонист / антагонист / второстепенный]
Возраст: []
Внешность: []
Характер: []
Мотивация: []
Тайна / внутренний конфликт: []
Особенности речи: []
Арка персонажа: []

---
""",
    "world": """# Мир и магия

## Общее
[Опиши мир в 2-3 предложениях]

## Магическая система / технологии
Правила: []
Ограничения: []
Цена: []

## Локации
### [Название]
[Описание, атмосфера, что здесь происходит]

## Политика / фракции
[Кто с кем, кто против кого]

## Важные детали мира
- []
""",
    "plot": """# Сюжет и арки

## Главная линия
Завязка: []
Конфликт: []
Кульминация (планируемая): []
Развязка: []

## Арки
### Арка 1: []
Главы: []
Цель: []
Поворот: []

## Ключевые повороты (спойлеры)
1. []
2. []

## Темы
[Основная тема и подтемы]
""",
    "notes": """# Заметки автора

## Голос и стиль
[Что важно для этого проекта — тон, темп, POV]

## Запрещённые ходы для этой истории
- []

## Идеи для будущих глав
- []

## Вопросы без ответа
- []
""",
}


def get_prep(project_id: int) -> dict:
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT section, content FROM prep_data WHERE project_id=?",
                (project_id,)
            ).fetchall()
        result = {s: PREP_DEFAULTS[s] for s in PREP_SECTIONS}
        for row in rows:
            if row["section"] in result:
                result[row["section"]] = row["content"]
        return result
    except Exception as e:
        handle_error(f"get_prep({project_id})", e, level=ErrorLevel.RECOVERABLE)
        return {s: PREP_DEFAULTS[s] for s in PREP_SECTIONS}


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
def save_prep(project_id: int, section: str, content: str) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO prep_data (project_id, section, content)
               VALUES (?,?,?)
               ON CONFLICT(project_id, section) DO UPDATE SET
                 content=excluded.content, updated_at=datetime('now')""",
            (project_id, section, content)
        )


def get_prep_context(project_id: int) -> str:
    """Собрать весь prep в единый контекстный блок для генерации."""
    prep = get_prep(project_id)
    parts = []
    for section, label in PREP_SECTIONS.items():
        content = prep[section].strip()
        if content and content != PREP_DEFAULTS[section].strip():
            parts.append(f"=== {label.upper()} ===\n{content}")
    return "\n\n".join(parts) if parts else ""
