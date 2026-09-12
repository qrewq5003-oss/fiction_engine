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


# ─── Главная претензия критика ────────────────────────────────────────────────
#
# Найдено при сравнении моделей 2026-09-12: во всех пяти прогонах score_text
# возвращал main_issue пустым. Выемка требовала дефис сразу на следующей
# строке после «ГЛАВНЫЕ ПРОБЛЕМЫ:», а живой критик пишет решётки, пустую
# строку и нумерацию. Автор не видел, что именно критику не понравилось —
# и понять это по одним баллам нельзя.

def test_real_scorer_output_yields_a_main_issue():
    from engine.pipeline_llm import parse_first_item
    raw = _fixture("real_scorer_2026_09_12.txt")
    assert "## ГЛАВНЫЕ ПРОБЛЕМЫ:" in raw, "образец потерял разметку — он больше не про то"
    issue = parse_first_item(raw, "ГЛАВНЫЕ ПРОБЛЕМЫ")
    assert issue, "главная претензия критика не извлечена"
    assert len(issue) > 20, f"извлечён огрызок: {issue!r}"


@pytest.mark.parametrize("raw,expected", [
    ("ГЛАВНЫЕ ПРОБЛЕМЫ:\n- дефис сразу",          "дефис сразу"),
    ("## ГЛАВНЫЕ ПРОБЛЕМЫ:\n\n**1. нумерация**",  "нумерация"),
    ("ГЛАВНЫЕ ПРОБЛЕМЫ\n\n* звёздочка",           "звёздочка"),
    ("ГЛАВНЫЕ ПРОБЛЕМЫ:\n\n• буллет",             "буллет"),
    ("__ГЛАВНЫЕ ПРОБЛЕМЫ:__\n2) скобка",          "скобка"),
])
def test_any_list_marker_and_markup_is_accepted(raw, expected):
    from engine.pipeline_llm import parse_first_item
    assert parse_first_item(raw, "ГЛАВНЫЕ ПРОБЛЕМЫ") == expected


def test_missing_section_gives_empty_string():
    from engine.pipeline_llm import parse_first_item
    assert parse_first_item("критик ответил прозой", "ГЛАВНЫЕ ПРОБЛЕМЫ") == ""


def test_score_text_no_longer_parses_the_section_itself():
    """Третьей копии выемки быть не должно — разбор в pipeline_llm."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "pipeline_tasks.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and "ГЛАВНЫЕ ПРОБЛЕМЫ" in node.value and "\\s*" in node.value):
            pytest.fail(f"своя выемка осталась на строке {node.lineno}")
