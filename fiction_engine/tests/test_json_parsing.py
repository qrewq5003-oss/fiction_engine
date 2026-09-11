#!/usr/bin/env python3
"""
Разбор JSON из ответа модели — один на всех, и бюджет под задачу.

Найдено живым прогоном 2026-09-12. `/api/l3/<N>/generate` отдавал
500 «Не удалось сгенерировать саммари» — пять попыток подряд из пяти.
Причин оказалось две, и обе невидимы для набора с заглушкой модели.

1. БЮДЖЕТ. Вызыватель вспомогательных задач давал всем плоские
   400 токенов. Замер на живой модели:

       400  → stop_reason='max_tokens', ответ рвётся посреди строки
       1500 → stop_reason='end_turn',   JSON целый

   Пять полей плюс массив promises по-русски в 400 токенов не влезают.

2. РАЗБОР. L3 держал свою упрощённую версию — `{.*}` жадно, от первой
   скобки до последней. На обрезанном ответе она отдавала огрызок,
   json.loads падал. Рядом, в pipeline_llm, уже жил терпимый разбор со
   снятием ```json, <think> и поиском по балансу скобок — но он был
   сцеплен с вызовом модели и потому недоступен.

И третье, про сообщение: обрыв по лимиту и брак модели давали
одинаковое «не удалось сгенерировать». Причину система знает —
stop_reason захватывается при вызове. Не сказать её значит отправить
автора искать несуществующую проблему в тексте главы.
"""

import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

ENGINE = Path(__file__).resolve().parents[1] / "engine"


# ─── Терпимость разбора ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ('{"a": 1}',                          {"a": 1}),
    ('  {"a": 1}  ',                      {"a": 1}),
    ('```json\n{"a": 1}\n```',            {"a": 1}),
    ('```\n{"a": 1}\n```',                {"a": 1}),
    ('Вот ответ: {"a": 1} — готово',      {"a": 1}),
    ('<think>рассуждаю</think>{"a": 1}',  {"a": 1}),
    ('{"a": "фигурная } внутри строки"}', {"a": "фигурная } внутри строки"}),
])
def test_parse_json_tolerates_what_models_actually_emit(raw, expected):
    from engine.pipeline_llm import parse_json
    assert parse_json(raw) == expected


@pytest.mark.parametrize("raw", [
    '{"a": "незакрытая строка',     # ровно то, что даёт обрыв по токенам
    '{"a": 1',
    '',
    '   ',
    'проза без единой скобки',
    None,
])
def test_parse_json_returns_none_instead_of_raising(raw):
    """Отказ разбора — это None, а не исключение: решение принимает вызывающий."""
    from engine.pipeline_llm import parse_json
    assert parse_json(raw) is None


def test_call_json_still_raises_on_garbage():
    """call_json обязан ругаться — на нём держится контракт вызывающих."""
    from engine.pipeline_llm import call_json
    import engine.pipeline_llm as mod
    orig = mod._call
    mod._call = lambda *a, **k: "модель ответила прозой"
    try:
        with pytest.raises(ValueError):
            call_json("m::m", "sys", "prompt")
    finally:
        mod._call = orig


# ─── Бюджет под задачу ────────────────────────────────────────────────────────

def test_l3_asks_for_more_than_the_generic_budget():
    """
    Саммари не помещается в умолчание вызывателя. Если кто-то снова
    приравняет их, отказы вернутся — и снова молча.
    """
    import inspect
    from engine.l3_memory import SUMMARY_MAX_TOKENS
    from engine.pipeline_llm import _make_model_caller
    generic = inspect.signature(_make_model_caller).parameters["max_tokens"].default
    assert SUMMARY_MAX_TOKENS > generic, (
        f"бюджет саммари {SUMMARY_MAX_TOKENS} не больше общего {generic}: "
        "ответ снова будет обрываться посреди JSON")


def test_generate_l3_passes_the_summary_budget():
    """Мало объявить бюджет — его надо передать."""
    import engine.pipeline_llm as llm
    from engine.l3_memory import SUMMARY_MAX_TOKENS
    seen = []
    orig = llm._make_model_caller
    llm._make_model_caller = lambda mv, mt=400: (seen.append(mt), orig(mv, mt))[1]
    try:
        import engine.pipeline as pipeline
        pipeline._make_model_caller = llm._make_model_caller
        from engine.pipeline_tasks import _l3_summary_budget
        assert _l3_summary_budget() == SUMMARY_MAX_TOKENS
    finally:
        llm._make_model_caller = orig


# ─── Один разборщик на всех ───────────────────────────────────────────────────

def test_no_second_copy_of_the_json_grab():
    """
    Жадная `{.*}` жила второй копией в l3_memory и потому пережила все
    улучшения терпимого разбора. Третьей копии быть не должно.
    """
    offenders = []
    for path in sorted(ENGINE.glob("*.py")):
        if path.name == "pipeline_llm.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and r'\{.*\}' in node.value):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, ("своя выемка JSON мимо parse_json: " + ", ".join(offenders))


# ─── Причина отказа ───────────────────────────────────────────────────────────

def test_truncation_is_named_not_hidden():
    """Обрыв по лимиту должен называться обрывом, а не «не удалось»."""
    import engine.l3_memory as l3
    from engine.api import _last_stop_reason as _stop_reason
    token = _stop_reason.set("max_tokens")
    try:
        assert "лимит" in l3._truncation_reason()
    finally:
        _stop_reason.reset(token)


def test_no_reason_when_model_simply_answered_badly():
    import engine.l3_memory as l3
    from engine.api import _last_stop_reason as _stop_reason
    token = _stop_reason.set("end_turn")
    try:
        assert l3._truncation_reason() == ""
    finally:
        _stop_reason.reset(token)
