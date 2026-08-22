#!/usr/bin/env python3
"""
check_architecture.py — линтер архитектурных границ.

Правило: web/blueprints/ не должен импортировать приватные
функции engine (начинающиеся с _) или обходить публичный API pipeline.

Запуск:
    python check_architecture.py          # проверка, exit 1 если есть нарушения
    python check_architecture.py --warn   # только предупреждения, exit 0 всегда

Добавить в CI:
    python check_architecture.py || exit 1
"""

import re
import os
import sys
import ast
from pathlib import Path
from dataclasses import dataclass

APP = Path(__file__).parent


# ─── Правила ─────────────────────────────────────────────────────────────────

@dataclass
class Rule:
    pattern: str          # regex применяется к каждой строке
    message: str          # что нарушено
    applies_to: str       # glob-паттерн для файлов (относительно APP)
    severity: str = "ERROR"  # ERROR | WARN


RULES: list[Rule] = [
    # Приватные функции pipeline запрещены в web-слое
    Rule(
        pattern=r'from engine\.pipeline import _\w+',
        message="Импорт приватной функции pipeline (_*). "
                "Используй публичный API: call_llm (сырой вызов модели), run_generation, "
                "call_json, score_text, generate_l3, generate_director_note_for_chapter, "
                "auto_drift_check_if_needed, run_narrative_analysis, run_batch_l3.",
        applies_to="web/",
    ),
    # l3_memory — только через pipeline.generate_l3
    Rule(
        pattern=r'from engine\.l3_memory import',
        message="Прямой импорт из l3_memory. "
                "Используй engine.pipeline.run_batch_l3(project_id, model_value, chapter_nums) "
                "для генерации и engine.pipeline.get_active_promises_for_project(project_id) "
                "для чтения активных обещаний.",
        applies_to="web/",
    ),
    # Приватные утилиты state
    Rule(
        pattern=r'from engine\.state import strip_empty_placeholders',
        message="strip_empty_placeholders — внутренняя утилита state. "
                "Вызывается только внутри pipeline.run_generation.",
        applies_to="web/",
    ),
    # get_prep_context не должен появляться в _worker (уже в run_generation)
    Rule(
        pattern=r'from engine\.db import get_prep_context',
        message="get_prep_context вызывается внутри pipeline.run_generation. "
                "В web-слое допустим только в prep_size (чтение размера для UI).",
        applies_to="web/blueprints/generate_bp.py",
        severity="WARN",
    ),
    # build_prompt из state — допустим в prompt_generate, нежелателен в worker
    Rule(
        pattern=r'from engine\.state import build_prompt',
        message="build_prompt используется в /prompt/generate (показ промпта пользователю) — "
                "допустимо. Если появляется в _worker — нарушение.",
        applies_to="web/",
        severity="WARN",
    ),
    # Прямые вызовы engine.api из web (кроме get_all_models_flat)
    Rule(
        pattern=r'from engine\.api import (?!get_all_models_flat|MODELS)\w+',
        message="Прямой импорт из engine.api (кроме get_all_models_flat/MODELS). "
                "Используй db.get_api_key или публичный API pipeline.",
        applies_to="web/",
    ),
]


# ─── Проверка ─────────────────────────────────────────────────────────────────

@dataclass
class Violation:
    file: str
    line: int
    text: str
    rule: Rule


def check_file(path: Path, rules: list[Rule]) -> list[Violation]:
    rel = str(path.relative_to(APP))
    src = path.read_text(encoding="utf-8")
    violations = []
    for i, line in enumerate(src.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for rule in rules:
            if not rel.startswith(rule.applies_to.rstrip("/")):
                # Проверяем точный файл или префикс директории
                if not (rule.applies_to.endswith("/") and rel.startswith(rule.applies_to)) and \
                   rule.applies_to != rel:
                    continue
            if re.search(rule.pattern, stripped):
                violations.append(Violation(rel, i, stripped, rule))
    return violations


def run(warn_only: bool = False) -> int:
    """Запустить проверку. Возвращает количество ERROR-нарушений."""
    all_violations: list[Violation] = []

    # Собираем .py файлы в web/
    for path in sorted(APP.rglob("web/**/*.py")):
        if "__pycache__" in str(path):
            continue
        all_violations.extend(check_file(path, RULES))

    # Также проверяем engine/ — там нарушений быть не должно по другим правилам
    # (пока пропускаем, engine сам по себе может быть связным)

    errors = [v for v in all_violations if v.rule.severity == "ERROR"]
    warns  = [v for v in all_violations if v.rule.severity == "WARN"]

    if not all_violations:
        print("✓ Архитектурные границы соблюдены. Нарушений нет.")
        return 0

    if errors:
        print(f"✗ Найдено нарушений: {len(errors)} ERROR, {len(warns)} WARN\n")
    else:
        print(f"⚠ Найдено предупреждений: {len(warns)} WARN\n")

    for v in all_violations:
        prefix = "ERROR" if v.rule.severity == "ERROR" else "WARN "
        print(f"  [{prefix}] {v.file}:{v.line}")
        print(f"           Строка: {v.text}")
        print(f"           Причина: {v.rule.message}")
        print()

    if errors and not warn_only:
        print(f"Запусти с --warn чтобы выйти с кодом 0 несмотря на ошибки.")
        return len(errors)

    return 0


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    warn_only = "--warn" in sys.argv
    exit_code = run(warn_only=warn_only)

    if exit_code > 0:
        sys.exit(1)
    sys.exit(0)
