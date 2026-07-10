"""
error_policy.py — Централизованная политика обработки ошибок.

Проблема которую решает:
    В pipeline.py ~15 try/except блоков с разной логикой:
    где-то log_error и continue, где-то тихий return None,
    где-то прокидывают дальше. Нет единого понимания — что
    блокирует выполнение, что деградирует молча, что критично.

Решение — три уровня с явной семантикой:

    RECOVERABLE — ошибка не влияет на результат пользователя.
                  Логируем, возвращаем fallback, продолжаем.
                  Пример: не загрузился модуль unified_engine.

    DEGRADED    — функция работает, но хуже обычного.
                  Логируем с пометкой, возвращаем degraded fallback.
                  Пример: не построился голосовой контекст — генерация
                           пройдёт без него.

    FATAL       — продолжать нельзя, пользователь должен узнать.
                  Логируем, бросаем PipelineError (не тихо).
                  Пример: API вернул пустой ответ для шага generate.

Использование:

    from .error_policy import error_boundary, ErrorLevel, PipelineError

    # Декоратор — самый частый случай:
    @error_boundary(level=ErrorLevel.DEGRADED, fallback="")
    def _load_voice_context(project_id: int) -> str:
        ...  # если упадёт — вернёт "" и залогирует

    # Явный вызов в блоке try/except:
    try:
        result = risky_call()
    except Exception as e:
        handle_error("_build_context drift", e, level=ErrorLevel.RECOVERABLE)
        result = None

    # Проверка уровня вручную:
    policy = ErrorPolicy.for_step("generate")
    policy.handle("api call", exc)  # FATAL — бросит PipelineError
"""

from __future__ import annotations

import functools
from enum import Enum
from typing import Any, Callable, TypeVar

from .logger import get_logger

log = get_logger(__name__)

F = TypeVar("F", bound=Callable)


# ─── Уровни ──────────────────────────────────────────────────────────────────

class ErrorLevel(Enum):
    """Уровень критичности ошибки."""
    RECOVERABLE = "recoverable"  # логируй, продолжай с fallback — пользователь не заметит
    DEGRADED    = "degraded"     # логируй, продолжай без фичи — качество снизится
    FATAL       = "fatal"        # стоп, уведоми пользователя — продолжать нельзя


# ─── Исключение для FATAL ────────────────────────────────────────────────────

class PipelineError(RuntimeError):
    """
    Бросается при FATAL-ошибке в pipeline.
    Содержит контекст и оригинальное исключение.

    Перехватывается в start_pipeline() и возвращается пользователю
    как понятное сообщение об ошибке, не как traceback.
    """
    def __init__(self, context: str, original: Exception):
        self.context  = context
        self.original = original
        super().__init__(f"[FATAL] {context}: {original}")


# ─── Политика для конкретного контекста ─────────────────────────────────────

class ErrorPolicy:
    """
    Политика обработки ошибок для конкретного контекста.

    Инстанцируется через ErrorPolicy.for_step() или ErrorPolicy(level).
    """

    # Политики по шагам pipeline — явная документация что блокирует, что нет
    _STEP_POLICIES: dict[str, ErrorLevel] = {
        "generate":  ErrorLevel.FATAL,       # без генерации нечего возвращать
        "critique":  ErrorLevel.DEGRADED,    # без критики — текст всё равно есть
        "edit":      ErrorLevel.DEGRADED,    # без редактуры — возвращаем оригинал
        "judge":     ErrorLevel.DEGRADED,    # без судьи — принимаем по умолчанию
        "context":   ErrorLevel.DEGRADED,    # без контекста — генерация хуже
        "memory":    ErrorLevel.RECOVERABLE, # без памяти — генерация без истории
        "engine":    ErrorLevel.RECOVERABLE, # без unified engine — без подсказок
        "drift":     ErrorLevel.RECOVERABLE, # drift check — фоновый, не блокирует
        "analysis":  ErrorLevel.RECOVERABLE, # chapter analysis — фоновый
        "symbols":   ErrorLevel.RECOVERABLE, # символы — фоновый
        "voice":     ErrorLevel.RECOVERABLE, # голос — фоновый
    }

    def __init__(self, level: ErrorLevel):
        self.level = level

    @classmethod
    def for_step(cls, step_name: str) -> "ErrorPolicy":
        """Получить политику для шага pipeline по имени."""
        level = cls._STEP_POLICIES.get(step_name, ErrorLevel.RECOVERABLE)
        return cls(level)

    def handle(
        self,
        context: str,
        exc: Exception,
        fallback: Any = None,
        *,
        project_id: int | None = None,
        chapter_num: int | None = None,
    ) -> Any:
        """
        Обработать исключение согласно политике.

        RECOVERABLE → логируем debug, возвращаем fallback
        DEGRADED    → логируем warning, возвращаем fallback
        FATAL       → логируем error, бросаем PipelineError

        Returns:
            fallback при RECOVERABLE/DEGRADED
            Никогда не возвращает при FATAL (бросает PipelineError)
        """
        ctx_kw: dict = {}
        if project_id is not None:
            ctx_kw["project_id"] = project_id
        if chapter_num is not None:
            ctx_kw["chapter_num"] = chapter_num

        if self.level == ErrorLevel.RECOVERABLE:
            log.debug(f"[RECOVERABLE] {context}: {exc}", **ctx_kw)
            return fallback

        elif self.level == ErrorLevel.DEGRADED:
            log.warning(
                f"[DEGRADED] {context}: {exc}",
                **ctx_kw,
            )
            return fallback

        else:  # FATAL
            log.error(f"[FATAL] {context}", exc=exc, **ctx_kw)
            raise PipelineError(context, exc)


# ─── Декоратор ───────────────────────────────────────────────────────────────

def error_boundary(
    level: ErrorLevel = ErrorLevel.RECOVERABLE,
    fallback: Any = None,
    context: str | None = None,
) -> Callable[[F], F]:
    """
    Декоратор — оборачивает функцию в ErrorPolicy.handle().

    Args:
        level:    уровень критичности (по умолчанию RECOVERABLE)
        fallback: что вернуть при ошибке (по умолчанию None)
        context:  имя контекста для лога (по умолчанию — имя функции)

    Примеры:

        @error_boundary(level=ErrorLevel.DEGRADED, fallback="")
        def load_voice(project_id: int) -> str:
            ...

        @error_boundary(level=ErrorLevel.FATAL)
        def call_api(prompt: str) -> str:
            ...  # если упадёт — бросит PipelineError

        # Асинхронные функции тоже поддерживаются:
        @error_boundary(level=ErrorLevel.RECOVERABLE, fallback={})
        async def fetch_state(project_id: int) -> dict:
            ...
    """
    policy = ErrorPolicy(level)

    def decorator(fn: F) -> F:
        ctx = context or fn.__qualname__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except PipelineError:
                raise  # не перехватываем FATAL повторно
            except Exception as exc:
                return policy.handle(ctx, exc, fallback)

        return wrapper  # type: ignore[return-value]

    return decorator


# ─── Удобная функция ─────────────────────────────────────────────────────────

def handle_error(
    context: str,
    exc: Exception,
    level: ErrorLevel = ErrorLevel.RECOVERABLE,
    fallback: Any = None,
    **ctx_kw,
) -> Any:
    """
    Прямой вызов без декоратора — для use-case внутри try/except.

    try:
        result = risky()
    except Exception as e:
        result = handle_error("risky", e, level=ErrorLevel.DEGRADED, fallback=[])
    """
    return ErrorPolicy(level).handle(context, exc, fallback, **ctx_kw)
