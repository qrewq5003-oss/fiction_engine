#!/usr/bin/env python3
"""
Разбор оценки и вердикта — на НАСТОЯЩЕМ выводе модели.

Образцы в tests/fixtures/ сняты с живого запуска pipeline 2026-09-12
(run_id 62, Claude Haiku 4.5, проект «Инженер Хаоса», глава 3). Это не
выдумка под регулярку: ровно этот текст сломал разбор.

В одном запуске одна и та же модель написала

    критику как   ## ИТОГ: 24/50        → разобралось в 24.0
    вердикт как   **ИТОГ:** 24/50       → разобралось в 0.0

потому что `ИТОГ:\\s*(\\d+)` требует цифру сразу после двоеточия, а там
стояли звёздочки. С вердиктом было опаснее: `**ВЕРДИКТ:** ПРИНЯТЬ` тоже
не совпадал, а значение по умолчанию — «НА ДОРАБОТКУ». Принятая глава
возвращалась автору на доработку, и он платил за новые итерации уже
готового текста.

Почему это не ловилось набором из 1080 тестов: заглушка модели отдаёт
строку, написанную под регулярку. Проверялся разбор собственного
образца, а не того, что пишет живая модель. Отсюда правило — образцы
здесь снимаются с прогона и не переписываются вручную.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ─── Настоящий вывод модели ───────────────────────────────────────────────────

def test_real_judge_output_parses_to_its_own_number():
    """Судья написал «ИТОГ: 24/50» — значит 24, а не 0."""
    from engine.pipeline_llm import parse_score
    text = _fixture("real_judge_2026_09_12.txt")
    assert "**ИТОГ:**" in text, "образец потерял разметку — он больше не про то"
    assert parse_score(text) == 24.0


def test_real_critique_output_still_parses():
    """Критика без разметки разбиралась и раньше — не сломать её починкой."""
    from engine.pipeline_llm import parse_score
    assert parse_score(_fixture("real_critique_2026_09_12.txt")) == 24.0


def test_real_judge_criteria_parse():
    from engine.pipeline_llm import parse_criterion
    text = _fixture("real_judge_2026_09_12.txt")
    assert [parse_criterion(text, l) for l in
            ("ГОЛОС", "СТРУКТУРА", "ПЕРСОНАЖИ", "СЦЕНЫ", "ДИАЛОГ")] == [6, 5, 4, 4, 5]


# ─── Вердикт: подмена «ПРИНЯТЬ» на «НА ДОРАБОТКУ» ─────────────────────────────

@pytest.mark.parametrize("text", [
    "ВЕРДИКТ: ПРИНЯТЬ",
    "**ВЕРДИКТ:** ПРИНЯТЬ",
    "**ВЕРДИКТ:** **ПРИНЯТЬ**",
    "## ВЕРДИКТ: ПРИНЯТЬ",
    "__ВЕРДИКТ:__ ПРИНЯТЬ",
    "`ВЕРДИКТ:` ПРИНЯТЬ",
])
def test_accept_is_never_silently_turned_into_rework(text):
    """
    Самое дорогое последствие: значение по умолчанию — «НА ДОРАБОТКУ»,
    поэтому НЕсовпадение регулярки неотличимо от настоящего отказа.
    """
    from engine.pipeline_llm import parse_verdict
    assert parse_verdict(text) == "ПРИНЯТЬ", f"принятая глава прочитана как отказ: {text!r}"


def test_rework_stays_rework():
    from engine.pipeline_llm import parse_verdict
    for text in ("ВЕРДИКТ: НА ДОРАБОТКУ", "**ВЕРДИКТ:** **НА ДОРАБОТКУ**"):
        assert parse_verdict(text) == "НА ДОРАБОТКУ"


def test_missing_verdict_defaults_to_rework():
    """Нет вердикта — не принимаем. Умолчание осторожное, и таким остаётся."""
    from engine.pipeline_llm import parse_verdict
    assert parse_verdict("модель ответила не по форме") == "НА ДОРАБОТКУ"


# ─── Разметка вокруг чисел ────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("ИТОГ: 42",        42.0),
    ("**ИТОГ:** 42",    42.0),
    ("## ИТОГ: 42/50",  42.0),
    ("*ИТОГ:* 42.5",    42.5),
    ("~~ИТОГ:~~ 42",    42.0),
    ("`ИТОГ:` 42",      42.0),
])
def test_markup_around_total_does_not_hide_it(text, expected):
    from engine.pipeline_llm import parse_score
    assert parse_score(text) == expected


def test_falls_back_to_sum_of_criteria_when_total_absent():
    from engine.pipeline_llm import parse_score
    assert parse_score("**ГОЛОС:** 6\n**СТРУКТУРА:** 5\n**ПЕРСОНАЖИ:** 4\n"
                       "**СЦЕНЫ:** 4\n**ДИАЛОГ:** 5") == 24.0


def test_no_scores_at_all_gives_zero():
    from engine.pipeline_llm import parse_score
    assert parse_score("модель ответила прозой без оценок") == 0.0


# ─── Один разборщик на всех ───────────────────────────────────────────────────

def test_no_module_parses_scores_with_its_own_regex():
    """
    Регулярка разбора жила в шести местах, и починка одного оставила бы
    пять. Разбор обязан быть в pipeline_llm — остальные модули зовут его.
    """
    import ast
    engine_dir = Path(__file__).resolve().parents[1] / "engine"
    offenders = []
    for path in sorted(engine_dir.glob("*.py")):
        if path.name == "pipeline_llm.py":
            continue
        src = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(src)):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            v = node.value
            # Признак регулярки, а не текста промпта: экранирование \\s*.
            # Системные промпты тоже содержат «ВЕРДИКТ: ПРИНЯТЬ» — это
            # описание формата для модели, и трогать его нельзя.
            if "\\s*" not in v:
                continue
            if "ИТОГ:" in v or ("ВЕРДИКТ:" in v and "ПРИНЯТЬ" in v):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, ("разбор оценки продублирован мимо parse_score/parse_verdict: "
                           + ", ".join(offenders))
