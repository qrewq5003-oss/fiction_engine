"""
engine_loaders.py — фасад: путь движка, бюджет токенов, реэкспорт загрузчиков.

Конкретные загрузчики:
  engine_loaders_core.py  — модули, антиклише, диалектика, символика, голос
  engine_loaders_genre.py — каталог, контракты, промпты, профили, арки

Все старые from engine.engine_loaders import ... продолжают работать.
"""

from pathlib import Path
from .engine_config import MODEL_TOKEN_BUDGETS, MODULE_PRIORITY


# ─── Путь к движку ────────────────────────────────────────────────────────────

_DEFAULT_ENGINE_PATH = Path(__file__).parent.parent.parent / "UNIFIED_ENGINE_MASTER"
_FALLBACK_ENGINE_PATH = Path(__file__).parent.parent.parent / "unified_engine" / "UNIFIED_ENGINE_MASTER"


def get_engine_path() -> Path:
    from .db import get_conn
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='unified_engine_path'"
            ).fetchone()
        if row:
            p = Path(row["value"])
            if p.exists():
                return p
    except Exception:
        pass
    if _DEFAULT_ENGINE_PATH.exists():
        return _DEFAULT_ENGINE_PATH
    if _FALLBACK_ENGINE_PATH.exists():
        return _FALLBACK_ENGINE_PATH
    return _DEFAULT_ENGINE_PATH


def engine_available() -> bool:
    return get_engine_path().exists()


# ─── Валидация путей при старте (IDEA 7) ─────────────────────────────────────

# Критические пути — их отсутствие делает engine нефункциональным
_CRITICAL_PATHS = [
    "00_CORE/CORE_FULL.md",
    "00_CORE/CORE_MINI.md",
    "00_CORE/META_RULES.yaml",
    "03_ADVANCED_ENGINES",
    "04_GENRE_ENGINE/catalog",
    "INDEX.json",
]

# Некритические пути — предупреждение, engine продолжает работать
_OPTIONAL_PATHS = [
    "12_ARCS/arcs_by_genre.md",
    "13_VOICE_LIBRARY/voice_check.md",
    "15_SYMBOLISM/symbolism_core.md",
    "14_CHARACTER_DIALECTICS/dialectics_core.md",
    "16_GENRE_CONTRACT/contract_checker.md",
    "10_VALIDATION/checklist_universal.md",
]


def validate_engine_paths() -> dict:
    """
    Проверяет наличие критических и опциональных файлов движка при старте.

    Возвращает:
        {
            "ok":       bool,           # False если отсутствует хотя бы один критический путь
            "missing_critical": [...],  # список отсутствующих критических путей
            "missing_optional": [...],  # список отсутствующих опциональных путей
            "engine_path": str,         # путь к движку
        }

    Вызывать при инициализации приложения (init_db или app startup).
    При ok=False движок не запустится корректно — нужно настроить путь.
    """
    import logging
    log = logging.getLogger(__name__)

    if not engine_available():
        msg = (
            f"UNIFIED_ENGINE_MASTER не найден. "
            f"Проверьте путь: {get_engine_path()}. "
            "Настройте путь в Settings → Engine Path."
        )
        log.error(msg)
        return {
            "ok": False,
            "missing_critical": ["(весь движок недоступен)"],
            "missing_optional": [],
            "engine_path": str(get_engine_path()),
        }

    base = get_engine_path()
    missing_critical = [p for p in _CRITICAL_PATHS if not (base / p).exists()]
    missing_optional = [p for p in _OPTIONAL_PATHS  if not (base / p).exists()]

    if missing_critical:
        log.error(
            f"Fiction Engine: отсутствуют критические файлы движка: {missing_critical}. "
            "Генерация может работать некорректно."
        )
    if missing_optional:
        log.warning(
            f"Fiction Engine: отсутствуют опциональные файлы движка: {missing_optional}. "
            "Некоторые функции недоступны."
        )
    if not missing_critical and not missing_optional:
        log.info(f"Fiction Engine: все файлы движка на месте ({base})")

    return {
        "ok":               len(missing_critical) == 0,
        "missing_critical": missing_critical,
        "missing_optional": missing_optional,
        "engine_path":      str(base),
    }

def load_module_dependencies_from_index() -> dict[str, list[str]] | None:
    """
    Читает INDEX.json из UNIFIED_ENGINE_MASTER и строит граф зависимостей модулей.

    INDEX.json хранит список файлов по директориям. Зависимости кодируются
    полем "dependencies" внутри каждого файлового описания (если есть),
    или через отдельный ключ "module_dependencies" на верхнем уровне.

    Возвращает словарь {module_name: [dep1, dep2]} или None если
    INDEX.json недоступен или не содержит зависимостей — в этом случае
    caller должен использовать хардкод из engine_config.py как fallback.
    """
    import json

    index_path = get_engine_path() / "INDEX.json"
    if not index_path.exists():
        return None

    try:
        with open(index_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    # Прямой ключ module_dependencies в INDEX.json (приоритет)
    if "module_dependencies" in data:
        deps = data["module_dependencies"]
        if isinstance(deps, dict):
            return deps

    # Если структуры module_dependencies нет — вернуть None,
    # чтобы caller использовал хардкод из engine_config.py
    return None


def get_module_dependencies() -> dict[str, list[str]]:
    """
    Возвращает граф зависимостей модулей.

    Приоритет: INDEX.json > хардкод в engine_config.py
    Это единственное место где нужно менять зависимости —
    или в INDEX.json (если там есть ключ module_dependencies),
    или в engine_config.MODULE_DEPENDENCIES как fallback.
    """
    from_index = load_module_dependencies_from_index()
    if from_index is not None:
        return from_index

    # Fallback: хардкод из engine_config.py
    from .engine_config import MODULE_DEPENDENCIES
    return MODULE_DEPENDENCIES


# ─── Бюджет токенов ───────────────────────────────────────────────────────────

def get_token_budget(model_value: str) -> int:
    if not model_value:
        return MODEL_TOKEN_BUDGETS["default"]
    m = model_value.lower()
    if "claude" in m:   return MODEL_TOKEN_BUDGETS["claude"]
    if "gemini" in m:   return MODEL_TOKEN_BUDGETS["gemini"]
    if "gpt-4o" in m:   return MODEL_TOKEN_BUDGETS["gpt-4o"]
    if "gpt" in m:      return MODEL_TOKEN_BUDGETS["gpt-4"]
    if "deepseek" in m: return MODEL_TOKEN_BUDGETS["deepseek"]
    return MODEL_TOKEN_BUDGETS["default"]


def _trim_modules_to_budget(
    module_sections: list[tuple[str, str]],
    budget_chars: int,
) -> list[str]:
    """Резать модули по приоритету пока не уложимся в бюджет.

    Итеративный алгоритм: продолжает halvinge низкоприоритетных модулей
    пока total > budget_chars или пока все модули не достигли минимума.
    Гарантирует выполнение бюджета в O(n * log(max_content)) итерациях.
    """
    total = sum(len(c) for _, c in module_sections)
    if total <= budget_chars:
        return [c for _, c in module_sections]

    result = list(module_sections)
    MIN_LENGTH = 50  # не режем модуль до менее чем 50 символов

    while True:
        total = sum(len(c) for _, c in result)
        if total <= budget_chars:
            break

        # Найти модуль с наименьшим приоритетом (режем первым)
        # и ещё достаточно длинный для halving
        best_idx = None
        best_priority = -1
        for i, (name, content) in enumerate(result):
            if len(content) <= MIN_LENGTH:
                continue
            priority = MODULE_PRIORITY.get(name, 5)
            if priority > best_priority:
                best_priority = priority
                best_idx = i

        if best_idx is None:
            # Все модули на минимуме — выходим (бюджет не гарантирован,
            # но дальнейшее резание бессмысленно)
            break

        name, content = result[best_idx]
        result[best_idx] = (name, content[:len(content) // 2])

    return [c for _, c in result]


# ─── Реэкспорт загрузчиков (обратная совместимость) ──────────────────────────

from .engine_loaders_core import (   # noqa: E402, F401
    load_module       as _load_module,
    load_anticliche_replacements  as _load_anticliche_replacements_fn,
    load_dialectics_hint          as _load_dialectics_hint_fn,
    load_symbolism_hint           as _load_symbolism_hint_fn,
    load_voice_check_hint         as _load_voice_check_hint_fn,
    load_writing_core_hint        as _load_writing_core_hint_fn,
    load_validation_checklist     as _load_validation_checklist_fn,
    load_pattern_library          as _load_pattern_library_fn,
)

from .engine_loaders_genre import (  # noqa: E402, F401
    load_genre_catalog            as _load_genre_catalog_fn,
    load_genre_contract           as _load_genre_contract_fn,
    load_genre_prompt             as _load_genre_prompt_fn,
    load_character_profile        as _load_character_profile_fn,
    load_arc_hint                 as _load_arc_hint_fn,
    load_catalog_subgenre_hint    as _load_catalog_subgenre_hint_fn,
)


# Обёртки с сигнатурой оригинальных функций (принимают только строки, путь берут сами)

def _load_genre_catalog(genre_key: str) -> str:
    return _load_genre_catalog_fn(get_engine_path(), genre_key)

def _load_anticliche_replacements() -> str:
    return _load_anticliche_replacements_fn(get_engine_path())

def _load_genre_contract(genre_key: str) -> str:
    return _load_genre_contract_fn(get_engine_path(), genre_key)

def _load_dialectics_hint() -> str:
    return _load_dialectics_hint_fn(get_engine_path())

def _load_arc_hint(genre_key: str) -> str:
    return _load_arc_hint_fn(get_engine_path(), genre_key)

def _load_character_profile(genre_key: str) -> str:
    return _load_character_profile_fn(get_engine_path(), genre_key)

def _load_symbolism_hint() -> str:
    return _load_symbolism_hint_fn(get_engine_path())

def _load_voice_check_hint() -> str:
    return _load_voice_check_hint_fn(get_engine_path())

def _load_catalog_subgenre_hint(genre_key: str) -> str:
    return _load_catalog_subgenre_hint_fn(get_engine_path(), genre_key)

def _load_genre_prompt(genre_key: str, mode: str) -> str:
    return _load_genre_prompt_fn(get_engine_path(), genre_key, mode)

def _load_writing_core_hint(task_text: str, mode: str) -> str:
    return _load_writing_core_hint_fn(get_engine_path(), task_text, mode)

def _load_validation_checklist(genre_key: str | None, max_lines: int = 30) -> str:
    return _load_validation_checklist_fn(get_engine_path(), genre_key, max_lines)

def _load_pattern_library(genre_key: str | None, mode: str, task_text: str = "") -> str:
    return _load_pattern_library_fn(get_engine_path(), genre_key, mode, task_text)
