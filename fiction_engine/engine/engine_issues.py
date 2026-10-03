"""
engine_issues.py — сбои базы знаний при сборке блока движка.

Зачем. Загрузчики UNIFIED при любой ошибке возвращали пустую строку, а
сборка блока движка целиком гасилась как RECOVERABLE. Глава уходила в
модель без контракта, правил жанра или всего блока, а автор об этом не
узнавал: запись была только в логе (AUDIT_UNIFIED.md, F4).

Как. Генерация открывает сбор (collect_engine_issues), сборка блока
отмечает каждый пропавший раздел (note_engine_issue), а генерация
показывает итог автору в предупреждении (engine_issues_note). Вне сбора
отметка только пишется в лог — загрузчики можно звать откуда угодно.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from .logger import get_logger

_issues: ContextVar[list[str] | None] = ContextVar("engine_issues", default=None)


def note_engine_issue(what: str, exc: Exception | None = None) -> None:
    """Отметить пропавший раздел блока движка: в лог и в текущий сбор."""
    log = get_logger(__name__)
    if exc is not None:
        log.error(f"база знаний: {what}", exc)
    else:
        log.warning("база знаний", what)
    bucket = _issues.get()
    if bucket is not None and what not in bucket:
        bucket.append(what)


@contextmanager
def collect_engine_issues() -> Iterator[list[str]]:
    """Собрать отметки за время сборки контекста одной генерации."""
    bucket: list[str] = []
    token = _issues.set(bucket)
    try:
        yield bucket
    finally:
        _issues.reset(token)


def engine_issues_note(issues: list[str]) -> str:
    """Строка для автора; пусто, если сбоев не было."""
    if not issues:
        return ""
    return ("База знаний: " + "; ".join(issues)
            + ". Глава сгенерирована без этого — проверь путь к базе в настройках.")
