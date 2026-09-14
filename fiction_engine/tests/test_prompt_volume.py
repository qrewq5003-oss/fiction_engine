#!/usr/bin/env python3
"""
Требование объёма одинаково во всех промптах генерации.

Промптов три — quick, quality, master, — и требование объёма в каждом
своё, набранное руками. Разойтись им ничего не мешало, и они разошлись:
quick просил «2500-3000 слов (считай абзацы — их должно быть 15-20)»,
то есть 125-200 слов на абзац, а два других на тот же объём — 25-35
абзацев. Одно и то же требование в двух арифметиках.

Тест перебирает СБОРЩИКИ промптов, а не их список: новый режим попадёт
под проверку сам.

Что здесь НЕ проверяется — сколько слов выдаст модель. Это свойство
модели, а не промпта: замер 2026-09-12 показал, что haiku упирается
около 1900-2000 за вызов при любой формулировке, а бюджет токенов
(11730) не расходуется и наполовину.
"""

import re
import sys
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()

MODES = ("quick", "quality", "master")


def _prompts() -> dict[str, str]:
    """Собранный промпт каждого режима — через публичный build_prompt."""
    from engine.state_prompts import build_prompt
    project = {"id": 1, "name": "Проект", "genre": "детектив"}
    return {mode: build_prompt(1, 3, mode, project) for mode in MODES}


@pytest.fixture
def prompts(monkeypatch):
    import tempfile
    from pathlib import Path
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "fe.db")
    from engine.db_core import init_db
    init_db()
    from engine.db import create_project
    create_project("Проект", "детектив")
    return _prompts()


def test_every_mode_states_the_word_target(prompts):
    for mode, text in prompts.items():
        assert re.search(r"2500-3000 слов", text), f"{mode}: нет требования объёма"


def test_paragraph_ranges_agree_across_modes(prompts):
    """
    Одно требование — одна арифметика. Расхождение 15-20 против 25-35
    означало, что в quick абзац втрое длиннее, чем в остальных.
    """
    ranges = {}
    for mode, text in prompts.items():
        m = re.search(r"\((\d+)-(\d+) абзацев\)", text)
        assert m, f"{mode}: не сказано, сколько абзацев"
        ranges[mode] = (int(m.group(1)), int(m.group(2)))
    assert len(set(ranges.values())) == 1, f"режимы расходятся в абзацах: {ranges}"


def test_paragraph_range_is_arithmetically_possible(prompts):
    """
    Слов на абзац должно получаться правдоподобно. 2500-3000 слов в
    15-20 абзацах — это 125-200 слов на абзац; в текстах прогона выходило
    20-30. Верхняя граница держит формулировку в пределах разумного.
    """
    text = prompts["quick"]
    words = [int(x) for x in re.search(r"(\d+)-(\d+) слов", text).groups()]
    paras = [int(x) for x in re.search(r"\((\d+)-(\d+) абзацев\)", text).groups()]
    per_para = words[1] / paras[0]
    assert per_para <= 120, (
        f"{per_para:.0f} слов на абзац — столько не пишут; "
        "требование объёма и требование абзацев противоречат друг другу")


def test_every_mode_asks_the_model_to_check_its_own_length(prompts):
    """
    Самопроверка перед финалом. На голом запросе она давала +20%
    (1599 → 1925 слов, haiku 4.5); на полном промпте движка прирост
    оказался куда меньше — 1196 → 1209 и 1295 → 1417. Оставлена потому,
    что не вредит, но обещать по ней ничего нельзя.
    """
    for mode, text in prompts.items():
        assert "проверь себя" in text, f"{mode}: нет самопроверки объёма"
        assert "2500" in text.split("проверь себя")[1][:160], \
            f"{mode}: самопроверка не называет число"


# ─── Ритм: генератор судится по правилу, которого не видел ───────────────────
#
# Замер 19 моделей (2026-09-13): двенадцать главных претензий критика из
# четырнадцати — про рубленый ритм, 61-91% коротких предложений при норме
# 30%. Норму считает analyze_sentence_rhythm и передаёт КРИТИКУ. Генератору
# её не показывали ни в одном режиме: в quick стояло противоположное
# («Экшн/напряжение: короткие предложения 5-10 слов»), в quality не было
# ни слова, в master одно упоминание.
#
# Модели разных семейств и размеров ошибались одинаково, потому что
# выполняли инструкцию, а судили их по другой.

def test_every_mode_states_the_rhythm_rule(prompts):
    for mode, text in prompts.items():
        assert "РИТМ ПРЕДЛОЖЕНИЙ" in text, f"{mode}: генератору не сказали про ритм"


def test_the_contradicting_advice_is_gone(prompts):
    """
    «Короткие предложения (5-10 слов)» прямо толкало к тому, за что потом
    снижают оценку. Если вернётся — набор обязан упасть.
    """
    for mode, text in prompts.items():
        assert "5-10 слов" not in text, f"{mode}: вернулся совет рубить фразы"


def test_prompt_numbers_come_from_the_same_place_as_the_check(prompts):
    """
    Главное здесь. Числа в промпте и числа, по которым считает критик, —
    один экземпляр, а не две копии. Копии уже расходились: «15-20 абзацев»
    против «25-35» на один и тот же объём.
    """
    from engine.pipeline_config import (RHYTHM_TARGET, RHYTHM_SHORT_MAX,
                                        RHYTHM_LONG_MIN, RHYTHM_RANGE)
    for mode, text in prompts.items():
        assert f"меньше {RHYTHM_SHORT_MAX} слов" in text, f"{mode}: граница короткого разошлась"
        assert f"больше {RHYTHM_LONG_MIN} слов" in text, f"{mode}: граница длинного разошлась"
        for part in ("short", "medium", "long"):
            assert f"около {RHYTHM_TARGET[part]}%" in text, f"{mode}: доля {part} разошлась"
        assert f"Не больше {RHYTHM_RANGE['short'][1]}%" in text, f"{mode}: потолок коротких разошёлся"


def test_analyzer_uses_the_same_constants():
    """Вторая половина того же: анализатор не должен знать своих чисел."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "pipeline_steps.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "analyze_sentence_rhythm")
    literals = {n.value for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, int)}
    forbidden = {8, 20, 30, 40, 50, 60, 10} & literals
    assert not forbidden, (
        f"анализатор держит свои числа {sorted(forbidden)} вместо констант "
        "из pipeline_config — они разойдутся с промптом")


def test_rhythm_rule_reacts_to_the_constants(monkeypatch):
    """Проверка проверки: если сдвинуть норму, промпт обязан сдвинуться."""
    import engine.pipeline_config as cfg
    monkeypatch.setitem(cfg.RHYTHM_TARGET, "short", 42)
    assert "около 42%" in cfg.rhythm_rule_for_prompt()


# ─── Детали должны действовать, а не украшать ────────────────────────────────
#
# Замер 14.09: СЦЕНЫ — слабейший критерий (среднее 4.8, семёрку берёт 1
# текст из 15, минимальным оказывается 7 раз из 15). Претензия критика
# однородна в 15 случаях из 15, и она НЕ «мало деталей», а «детали не
# действуют»: «описан декоративно, но не ощутимо», «остаётся декорацией»,
# «музей как локация не дышит».
#
# Промпт при этом просил «Место: [конкретно, с одной АТМОСФЕРНОЙ деталью]» —
# то есть буквально заказывал украшение, за которое снижают оценку. Третье
# такое расхождение после ритма и числа абзацев.

def test_every_mode_demands_acting_details(prompts):
    for mode, text in prompts.items():
        assert "ДЕТАЛИ ДОЛЖНЫ ДЕЙСТВОВАТЬ" in text, f"{mode}: правило о деталях потерялось"


def test_decorative_detail_request_is_gone(prompts):
    for mode, text in prompts.items():
        assert "атмосферной деталью" not in text, f"{mode}: промпт снова заказывает украшение"


def test_detail_rule_has_one_source(prompts):
    """
    Как с ритмом и абзацами: правило живёт в одном месте, а промпт его
    подставляет. Копии в этом проекте расходились трижды.
    """
    from engine.pipeline_config import detail_rule_for_prompt
    rule = detail_rule_for_prompt()
    first_line = rule.splitlines()[0]
    for mode, text in prompts.items():
        assert first_line in text, f"{mode}: правило разошлось с источником"


def test_rule_reacts_to_its_source(monkeypatch):
    """Проверка проверки: подменили источник — промпт обязан измениться."""
    import engine.pipeline_config as cfg
    import engine.state_prompts as sp
    monkeypatch.setattr(cfg, "detail_rule_for_prompt", lambda: "ПРОВЕРОЧНАЯ СТРОКА")
    assert sp._detail_block() == "ПРОВЕРОЧНАЯ СТРОКА"


# ─── Объём: одно число, а не девять копий ────────────────────────────────────
#
# «2500-3000 слов» было вписано в промпты девятью литералами, а код
# проверял по TARGET_CHAPTER_WORDS и MIN_ACCEPTABLE_WORDS. Значения
# совпадали, но сходство держалось на внимательности: у
# TARGET_CHAPTER_WORDS так и стоял комментарий «верх требования ИЗ
# ПРОМПТОВ» — зависимость признана и оставлена ручной.
#
# Ровно так уже разошлись числа абзацев (15-20 против 25-35 на один объём)
# и норма ритма, которую знал только критик. Третий случай за проект.

def test_volume_numbers_in_prompts_come_from_constants(prompts):
    from engine.pipeline_config import MIN_CHAPTER_WORDS, TARGET_CHAPTER_WORDS
    for mode, text in prompts.items():
        assert f"{MIN_CHAPTER_WORDS}-{TARGET_CHAPTER_WORDS} слов" in text, \
            f"{mode}: требование к объёму разошлось с константами"


def test_self_check_uses_the_same_lower_bound(prompts):
    from engine.pipeline_config import MIN_CHAPTER_WORDS
    for mode, text in prompts.items():
        if "проверь себя" in text:
            assert f"написано ли уже {MIN_CHAPTER_WORDS} слов" in text, \
                f"{mode}: самопроверка объёма считает от другого числа"


def test_prompt_follows_the_constant_when_it_moves(monkeypatch):
    """Проверка проверки: сдвинули константу — промпт обязан сдвинуться."""
    import engine.pipeline_config as cfg
    monkeypatch.setattr(cfg, "MIN_CHAPTER_WORDS", 1234)
    assert "1234-" in cfg.volume_rule_for_prompt()
    assert "1234 слов" in cfg.volume_check_for_prompt()


def test_lower_bound_is_above_the_failure_threshold():
    """
    Нижняя граница требования должна быть выше порога, по которому
    detect_truncation признаёт главу недописанной, — иначе движок просит
    то, что сам засчитает как провал.
    """
    from engine.pipeline_config import MIN_CHAPTER_WORDS, MIN_ACCEPTABLE_WORDS
    assert MIN_CHAPTER_WORDS > MIN_ACCEPTABLE_WORDS


def test_built_prompt_moves_with_the_constant(monkeypatch):
    """
    Отличает подстановку от литерала с тем же значением.

    Тест выше («в промпте есть 2500-3000») проходит и когда число вписано
    руками — он проверяет совпадение, а не источник. Фальсификация это
    показала: возврат литерала с прежним значением набор не уронил.
    Здесь константа подменяется и промпт пересобирается: литерал за ней
    не поедет.
    """
    import tempfile
    from pathlib import Path
    import engine.db_core as dbc
    import engine.pipeline_config as cfg

    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "vol.db")
    dbc.init_db()
    monkeypatch.setattr(cfg, "MIN_CHAPTER_WORDS", 2777)

    from engine.db import create_project, get_project
    from engine.state_prompts import build_prompt
    pid = create_project("Объём", "детектив")
    for mode in ("quick", "quality", "master"):
        text = build_prompt(pid, 2, mode, get_project(pid))
        assert "2777" in text, f"{mode}: объём не взят из константы"
        # Строгая половина проверки. Без неё тест удовлетворяется ОДНОЙ
        # подстановкой: при живой самопроверке «написано ли уже N слов»
        # число 2777 попадало в промпт, даже когда требование к объёму
        # оставалось литералом. Прежнее значение после подмены исчезнуть
        # обязано целиком.
        assert "2500" not in text, (
            f"{mode}: прежнее число осталось в промпте — часть требования "
            "вписана литералом, а не подставлена")
