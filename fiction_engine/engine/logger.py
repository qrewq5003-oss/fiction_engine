"""
logger.py — централизованный структурированный логгер.

Заменяет разрозненные log_error() вызовы и except Exception: pass.

Архитектура:
  get_logger(name) — фабрика именованных логгеров.
  EngineLogger     — обёртка с контекстом (project_id, chapter_num).
  Три уровня:
    DEBUG   → файл ~/fiction_engine/engine.log
    WARNING → консоль (stderr)
    ERROR   → файл + таблица engine_error_log в БД

Использование:
  from .logger import get_logger
  log = get_logger(__name__)

  log.debug("build context", project_id=1, chapter=5)
  log.warning("drift check skipped", reason="no reference")

  try:
      risky_call()
  except Exception as e:
      log.error("risky_call failed", exc=e, project_id=1)

  # Или через контекст (удобно внутри одной функции):
  with log.context(project_id=1, chapter_num=5) as ctx:
      ctx.info("generation started")
      ctx.error("api timeout", exc=e)
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


# ─── Директория логов ─────────────────────────────────────────────────────────

LOG_DIR  = Path.home() / "fiction_engine"
LOG_FILE = LOG_DIR / "engine.log"


# ─── Форматтер ────────────────────────────────────────────────────────────────

class StructuredFormatter(logging.Formatter):
    """
    Форматирует запись как строку с контекстными полями.
    Пример: 2026-02-27 12:05:33 | ERROR | pipeline | project=1 ch=5 | api timeout
    """
    def format(self, record: logging.LogRecord) -> str:
        ts   = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        lvl  = record.levelname[:5].ljust(5)
        name = record.name.split(".")[-1][:16].ljust(16)
        msg  = record.getMessage()

        # Дополнительные поля из extra={}
        ctx_parts = []
        for key in ("project_id", "chapter_num", "model", "reason"):
            val = record.__dict__.get(key)
            if val is not None:
                ctx_parts.append(f"{key}={val}")
        ctx = " ".join(ctx_parts)

        parts = [ts, lvl, name]
        if ctx:
            parts.append(ctx)
        parts.append(msg)

        base = " | ".join(parts)

        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)

        return base


# ─── DB Handler ───────────────────────────────────────────────────────────────

class DBHandler(logging.Handler):
    """
    Пишет ERROR и выше в таблицу engine_error_log.
    Никогда не бросает исключение (безопасный handler).
    """
    def __init__(self):
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord):
        try:
            from .db_core import get_conn
            context = record.name + (
                f" | project={record.__dict__.get('project_id', '')}"
                f" ch={record.__dict__.get('chapter_num', '')}"
            ).rstrip(" ch=").rstrip(" | project=")
            error = record.getMessage()
            if record.exc_info:
                error += " :: " + self.formatException(record.exc_info)
            with get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO engine_error_log (context, error) VALUES (?,?)",
                    (context[:500], error[:2000])
                )
        except Exception:
            pass  # handler не должен ломать всё остальное


# ─── Фабрика логгеров ─────────────────────────────────────────────────────────

_initialized = False


def _ensure_initialized():
    global _initialized
    if _initialized:
        return
    _initialized = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("fiction_engine")
    root.setLevel(logging.DEBUG)

    if not root.handlers:
        # ── Файл: всё DEBUG и выше ─────────────────────────────────────────
        try:
            fh = logging.handlers.RotatingFileHandler(
                LOG_FILE,
                maxBytes=5 * 1024 * 1024,   # 5 MB
                backupCount=3,
                encoding="utf-8",
            )
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(StructuredFormatter())
            root.addHandler(fh)
        except Exception:
            pass

        # ── Консоль: WARNING и выше ────────────────────────────────────────
        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.WARNING)
        ch.setFormatter(StructuredFormatter())
        root.addHandler(ch)

        # ── БД: ERROR и выше ───────────────────────────────────────────────
        root.addHandler(DBHandler())

        root.propagate = False


def get_logger(name: str) -> "EngineLogger":
    """
    Получить именованный логгер.
    Имя должно быть __name__ вызывающего модуля:
      from .logger import get_logger
      log = get_logger(__name__)
    """
    _ensure_initialized()
    # Нормализуем имя: убираем package-prefix, оставляем имя модуля
    short = name.split(".")[-1] if "." in name else name
    inner = logging.getLogger(f"fiction_engine.{short}")
    return EngineLogger(inner)


# ─── EngineLogger ─────────────────────────────────────────────────────────────

class EngineLogger:
    """
    Обёртка над стандартным логгером с поддержкой контекстных полей.
    Реализует контракт ErrorBoundary из contracts.py.
    """

    def __init__(self, logger: logging.Logger):
        self._log = logger

    def _extra(self, **kwargs) -> dict:
        return {k: v for k, v in kwargs.items() if v is not None}

    # ─── Уровни ───────────────────────────────────────────────────────────────

    def debug(self, msg: str, **ctx):
        self._log.debug(msg, extra=self._extra(**ctx))

    def info(self, msg: str, **ctx):
        self._log.info(msg, extra=self._extra(**ctx))

    def warning(self, context: str, message: str = "", **ctx):
        full = f"{context}: {message}" if message else context
        self._log.warning(full, extra=self._extra(**ctx))

    def error(self, context: str, exc: Exception | None = None, **ctx):
        """
        Зафиксировать ошибку. Никогда не бросает исключение.
        Реализует ErrorBoundary.capture().
        """
        try:
            extra = self._extra(**ctx)
            if exc is not None:
                self._log.error(context, exc_info=exc, extra=extra)
            else:
                self._log.error(context, extra=extra)
        except Exception:
            pass

    # Алиас для совместимости с contracts.ErrorBoundary
    def capture(self, context: str, error: Exception, level: str = "error") -> None:
        if level == "warning":
            self.warning(context, str(error))
        else:
            self.error(context, exc=error)

    # ─── Контекст (for project/chapter scope) ─────────────────────────────────

    @contextmanager
    def context(self, **ctx_fields):
        """
        Контекстный менеджер — добавляет поля ко всем записям внутри блока.

        with log.context(project_id=1, chapter_num=5) as ctx:
            ctx.info("generation started")
            ctx.error("api call failed", exc=e)
        """
        yield _BoundLogger(self._log, ctx_fields)


class _BoundLogger:
    """Логгер с предустановленными контекстными полями."""

    def __init__(self, logger: logging.Logger, ctx: dict[str, Any]):
        self._log = logger
        self._ctx = ctx

    def _extra(self, **extra) -> dict:
        merged = {**self._ctx, **extra}
        return {k: v for k, v in merged.items() if v is not None}

    def debug(self, msg: str, **kw):
        self._log.debug(msg, extra=self._extra(**kw))

    def info(self, msg: str, **kw):
        self._log.info(msg, extra=self._extra(**kw))

    def warning(self, msg: str, **kw):
        self._log.warning(msg, extra=self._extra(**kw))

    def error(self, msg: str, exc: Exception | None = None, **kw):
        try:
            extra = self._extra(**kw)
            if exc is not None:
                self._log.error(msg, exc_info=exc, extra=extra)
            else:
                self._log.error(msg, extra=extra)
        except Exception:
            pass


# ─── Удобная функция для обратной совместимости с db_core.log_error ──────────

def log_error(context: str, error: Exception, **ctx) -> None:
    """
    Drop-in замена для db_core.log_error().
    Пишет в файл, консоль (если WARNING+) и БД.
    """
    _logger = get_logger("engine")
    _logger.error(context, exc=error, **ctx)
