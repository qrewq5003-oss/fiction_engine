#!/usr/bin/env python3
"""
Снимки блока движка — того, что база UNIFIED добавляет в промпт генерации.

Зачем. База знаний и код, который её режет, менялись вслепую друг для
друга: правка заголовка в .md или строчки в экстракторе меняла промпт
всех глав, и никто этого не видел (AUDIT_UNIFIED.md, улучшение 5).
Теперь для восьми представительных пар «жанр × режим» полный текст блока
лежит в tests/fixtures/prompt_snapshots/, а сводка по разделам — в
summary.json. Любое изменение промпта роняет тест и видно в диффе ревью.

Изменение намеренное — обновите снимки и закоммитьте их вместе с правкой:

    FE_UPDATE_SNAPSHOTS=1 python -m pytest tests/test_prompt_snapshots.py

Сводка считает «пустые заголовки» — заголовки, под которыми ничего нет,
потому что содержимое было в код-блоке и экстрактор его выбросил (U3).
Их число — мера шума, которую должно снизить улучшение 4.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

KB_PATH = Path(__file__).resolve().parents[2] / "UNIFIED_ENGINE_MASTER"
SNAP_DIR = Path(__file__).parent / "fixtures" / "prompt_snapshots"
SUMMARY = SNAP_DIR / "summary.json"
UPDATE = os.environ.get("FE_UPDATE_SNAPSHOTS") == "1"

MODEL = "anthropic::claude-snapshot"
TASK = "диалог на допросе, описание комнаты, финал главы"

# Каждое семейство жанров, каждый режим, поджанры с известными поломками
CASES = [
    ("detective_classic",   "quick"),
    ("detective_classic",   "quality"),
    ("detective_classic",   "master"),
    ("horror_gothic",       "master"),
    ("romance_historical",  "quality"),
    ("fantasy_urban",       "quality"),
    ("scifi_cyberpunk",     "quick"),
    ("realism_family_saga", "master"),
]


def _case_id(case: tuple[str, str]) -> str:
    return f"{case[0]}__{case[1]}"


def _heading_level(line: str) -> int | None:
    """Уровень заголовка: число «#»; жирная метка «**…:**» — ниже любого."""
    s = line.strip()
    if s.startswith("#"):
        return len(s) - len(s.lstrip("#"))
    if s.startswith("**") and s.endswith(":**"):
        return 7
    return None


def orphan_headings(text: str) -> int:
    """
    Заголовки с пустым разделом: до следующего заголовка того же или
    более высокого уровня нет ни одной строки текста.

    «## Раздел» и сразу «### Подраздел» с текстом — не пустой раздел.
    Считается независимо от кода движка, чтобы метрика не подгонялась
    под то, что движок сам вырезает.
    """
    lines = text.splitlines()
    count = 0
    for i, line in enumerate(lines):
        level = _heading_level(line)
        if level is None:
            continue
        has_text = False
        for nxt in lines[i + 1:]:
            nxt_level = _heading_level(nxt)
            if nxt_level is not None and nxt_level <= level:
                break
            s = nxt.strip()
            if nxt_level is None and s and s not in ("---", "=== / UNIFIED ENGINE ==="):
                has_text = True
                break
        if not has_text:
            count += 1
    return count


# Служебные разделы модулей: описывают устройство «системы» для человека,
# генератору прозы ничего не дают
_META_WORDS = ("НАЗНАЧЕНИЕ", "ФИЛОСОФИЯ", "ИНТЕГРАЦИЯ", "INTEGRATION",
               "АРХИТЕКТУРА", "КОМПОНЕНТЫ СИСТЕМЫ", "СТРУКТУРА СИСТЕМЫ")

# Метки жанровых вариантов («**ХОРРОР:** …») по семействам жанров
_FAMILY_LABELS = {
    "detective": {"ДЕТЕКТИВ", "НУАР"}, "thriller": {"ТРИЛЛЕР"},
    "horror": {"ХОРРОР"}, "romance": {"РОМАНТИКА"}, "fantasy": {"ФЭНТЕЗИ"},
    "scifi": {"НФ"}, "realism": {"РЕАЛИЗМ"},
}
_ALL_LABELS = set().union(*_FAMILY_LABELS.values())


def meta_sections(text: str) -> int:
    return sum(1 for l in text.splitlines()
               if l.startswith("#") and any(w in l.upper() for w in _META_WORDS))


def foreign_genre_variants(text: str, genre_key: str) -> int:
    """Строки «**ЖАНР:** …» чужих семейств — правила не того жанра."""
    import re
    own = _FAMILY_LABELS.get(genre_key.split("_")[0], set())
    count = 0
    for l in text.splitlines():
        m = re.match(r"\*\*([^*]+):\*\*", l.strip())
        if not m:
            continue
        parts = {p.strip() for p in m.group(1).split("/")}
        if parts & _ALL_LABELS and not parts & own:
            count += 1
    return count


@pytest.fixture(scope="module")
def render():
    assert KB_PATH.is_dir(), f"UNIFIED_ENGINE_MASTER не найден: {KB_PATH}"
    import engine.engine_loaders as loaders
    from engine.unified_engine import (build_engine_context, _build_fixed_sections,
                                       _build_module_sections)
    mp = pytest.MonkeyPatch()
    mp.setattr(loaders, "get_engine_path", lambda: KB_PATH)

    def _render(genre_key: str, mode: str) -> tuple[str, dict]:
        master = mode == "master"
        text = build_engine_context(genre_key, mode, model_value=MODEL,
                                    include_dialectics=master, task_text=TASK)
        sections = (_build_fixed_sections(genre_key, mode, master, TASK)
                    + _build_module_sections(mode, genre_key, None, TASK, None))
        summary = {
            "chars": len(text),
            "orphan_headings": orphan_headings(text),
            "meta_sections": meta_sections(text),
            "foreign_genre_variants": foreign_genre_variants(text, genre_key),
            "sections": {name: len(content) for name, content in sections},
        }
        return text, summary

    yield _render
    mp.undo()


@pytest.fixture(scope="module")
def stored_summary():
    if SUMMARY.exists():
        return json.loads(SUMMARY.read_text(encoding="utf-8"))
    return {}


@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_engine_block_matches_snapshot(render, case):
    text, _ = render(*case)
    path = SNAP_DIR / f"{_case_id(case)}.txt"
    if UPDATE:
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
        return
    assert path.exists(), (
        f"нет снимка {path.name}; создайте: FE_UPDATE_SNAPSHOTS=1 pytest {Path(__file__).name}")
    stored = path.read_text(encoding="utf-8")
    if text != stored:
        old, new = stored.splitlines(), text.splitlines()
        first = next((i for i, (a, b) in enumerate(zip(old, new)) if a != b),
                     min(len(old), len(new)))
        pytest.fail(
            f"{_case_id(case)}: блок движка изменился "
            f"({len(stored)} → {len(text)} символов), первое расхождение в строке {first + 1}:\n"
            f"  было: {old[first] if first < len(old) else '<конец>'}\n"
            f"  стало: {new[first] if first < len(new) else '<конец>'}\n"
            "Если так и задумано — FE_UPDATE_SNAPSHOTS=1 и закоммитьте снимки.")


def test_summary_matches(render, stored_summary):
    """Сводка — короткий дифф для ревью: какие разделы выросли или исчезли."""
    current = {_case_id(c): render(*c)[1] for c in CASES}
    if UPDATE:
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        SUMMARY.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
        return
    assert current == stored_summary, (
        "сводка блоков движка изменилась; если так и задумано — "
        "FE_UPDATE_SNAPSHOTS=1 и закоммитьте снимки")


def test_no_stale_snapshots():
    """Снимок без случая в CASES — мусор, который никто не проверяет."""
    expected = {f"{_case_id(c)}.txt" for c in CASES}
    present = {p.name for p in SNAP_DIR.glob("*.txt")} if SNAP_DIR.exists() else set()
    assert present <= expected, f"лишние снимки: {sorted(present - expected)}"


def test_orphan_heading_counter():
    text = ("## Раздел\n\n**Формула:**\n\n### Следующий\nтекст\n"
            "**Итог:**\n\n## Пустой\n---\n")
    # «## Раздел» не пуст: в его подразделе есть текст
    assert orphan_headings(text) == 3   # «Формула», «Итог», «Пустой»
