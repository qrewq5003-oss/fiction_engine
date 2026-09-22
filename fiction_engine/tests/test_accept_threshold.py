#!/usr/bin/env python3
"""
Порог принятия главы.

Было: ИТОГ >= 40 и каждый критерий >= 7. Этого не брал никто — ни одна
глава ни разу, ни у одной из 19 моделей. Вердикт «НА ДОРАБОТКУ»
выдавался ВСЕГДА и потому не значил ничего.

Новые числа выбраны не по медиане, а по разделяющей способности: порог
должен принимать целую главу и отвергать испорченную. Замер 14.09 на
нарочно испорченных текстах (перемешанные абзацы, перевёрнутый порядок,
дублированный кусок):

    порог   проходят настоящие   протекают испорченные
      25         11 из 15              10 из 15     ← бессмыслен
      28         10 из 15               2 из 15
      30          7 из 15               2 из 15     ← выбран
      32          2 из 15               2 из 15     ← режет живое
      40          0 из 15               0 из 15     ← прежний

30 стоит выше медианы настоящих текстов (29): «ПРИНЯТЬ» значит «лучше
обычного», а не «как обычно».
"""

import sys
from unittest.mock import MagicMock, patch

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

MODEL = "anthropic_direct::test"


def _reply(voice, structure, characters, scenes, dialog, total):
    return (f"ГОЛОС: {voice}/10 — ок\n"
            f"СТРУКТУРА: {structure}/10 — ок\n"
            f"ПЕРСОНАЖИ: {characters}/10 — ок\n"
            f"СЦЕНЫ: {scenes}/10 — ок\n"
            f"ДИАЛОГ: {dialog}/10 — ок\n"
            f"ИТОГ: {total}/50\n"
            f"ГЛАВНЫЕ ПРОБЛЕМЫ:\n- что-то\n")


def _verdict(monkeypatch, scores, total):
    import engine.pipeline_tasks as pt
    monkeypatch.setattr(pt, "_call", lambda *a, **k: _reply(*scores, total))
    return pt.score_text("Глава. " * 300, "детектив", MODEL)["verdict"]


class TestThresholdIsReachable:
    def test_middling_chapter_is_not_accepted(self, monkeypatch):
        """
        Глава из живого прогона 22.09: все критерии по 6, сумма 30 — ровно
        медиана настоящих текстов. Середину принимать незачем: «ПРИНЯТЬ»
        должно значить «заметно лучше обычного», а не «как обычно».
        """
        assert _verdict(monkeypatch, (6, 6, 6, 6, 6), 30) == "НА ДОРАБОТКУ"

    def test_good_chapter_is_accepted(self, monkeypatch):
        """Лучший текст замера: 37 из 50."""
        assert _verdict(monkeypatch, (8, 7, 7, 7, 8), 37) == "ПРИНЯТЬ"

    def test_bar_stands_above_the_median(self):
        """
        Смысл планки. Медиана настоящих глав на калиброванном судье — 29.
        Порог, стоящий на медиане, означает «не хуже обычного» и потому
        ничего не значит.
        """
        from engine.pipeline_config import ACCEPT_TOTAL
        MEASURED_MEDIAN = 29
        assert ACCEPT_TOTAL > MEASURED_MEDIAN + 3, (
            f"порог {ACCEPT_TOTAL} слишком близок к медиане {MEASURED_MEDIAN}: "
            "«ПРИНЯТЬ» будет значить «как обычно»")

    def test_weak_chapter_is_rejected_by_total(self, monkeypatch):
        """glm-4.7 из замера: 25 баллов — ниже порога."""
        assert _verdict(monkeypatch, (5, 5, 5, 5, 5), 25) == "НА ДОРАБОТКУ"

    def test_chapter_with_one_collapsed_criterion_is_rejected(self, monkeypatch):
        """
        Llama из замера: итог 16, сцены 2. Планка отдельного критерия
        существует ровно для этого — не пускать главу, где одно свойство
        провалено начисто, даже если сумма набрана остальными.
        """
        assert _verdict(monkeypatch, (7, 7, 7, 2, 7), 30) == "НА ДОРАБОТКУ"

    def test_shuffled_text_score_is_rejected(self, monkeypatch):
        """Перемешанные абзацы давали в замере около 20 баллов."""
        assert _verdict(monkeypatch, (5, 3, 4, 4, 4), 20) == "НА ДОРАБОТКУ"


class TestThresholdHasOneSource:
    """
    Порог стоял в двух местах разными числами: 40 в правиле вердикта и
    38 в профилях пайплайна. Копии в этом проекте уже расходились дважды
    (абзацы, ритм), поэтому здесь проверяется именно единственность
    источника, а не конкретное значение.
    """

    def test_judge_prompt_states_the_same_numbers_as_the_code(self):
        from engine.pipeline_steps import SYS_JUDGE
        from engine.pipeline_config import ACCEPT_TOTAL, ACCEPT_MIN_CRITERION
        assert f"ИТОГ ≥ {ACCEPT_TOTAL}" in SYS_JUDGE
        assert f"критериев ≥ {ACCEPT_MIN_CRITERION}" in SYS_JUDGE

    def test_no_stale_forty_left_in_the_judge_prompt(self):
        from engine.pipeline_steps import SYS_JUDGE
        assert "ИТОГ ≥ 40" not in SYS_JUDGE

    def test_verdict_follows_the_constant_when_it_moves(self, monkeypatch):
        """Проверка проверки: сдвинули константу — вердикт обязан сдвинуться."""
        import engine.pipeline_config as cfg
        import engine.pipeline_tasks as pt
        monkeypatch.setattr(cfg, "ACCEPT_TOTAL", 45)
        monkeypatch.setattr(pt, "_call", lambda *a, **k: _reply(7, 7, 7, 7, 7, 35))
        assert pt.score_text("Глава. " * 300, "детектив", MODEL)["verdict"] == "НА ДОРАБОТКУ"

    def test_pipeline_presets_are_not_above_the_accept_bar(self):
        """
        Профили пайплайна сами решают, когда прекращать итерации. Если их
        планка выше порога принятия, пайплайн будет крутиться после того,
        как глава уже признана годной.
        """
        from engine.pipeline_config import ACCEPT_TOTAL, QUICK, STANDARD, DEEP
        for preset in (QUICK, STANDARD, DEEP):
            if preset.score_threshold < 900:      # 999 = «никогда не принимать»
                assert preset.score_threshold >= ACCEPT_TOTAL, (
                    f"{preset.description[:30]}: планка {preset.score_threshold} "
                    f"ниже порога принятия {ACCEPT_TOTAL}")


# ─── Правило вердикта: судья и код говорят одно ──────────────────────────────
#
# Числа свели к константам 14.09, а ТЕКСТ правила остался разным — и это
# оказалось важнее чисел. У судьи стояло третье условие, которого в коде
# нет: «и ни одного нарушения Scene Health чеклиста».
#
# Замер 15.09, шесть глав: судья сказал «НА ДОРАБОТКУ» во всех шести,
# включая оценки 36, 32 и 31 при пороге 30. То есть починка порога (этап 4)
# закрыла путь score_text и не тронула путь судьи.
#
# Цена выше неверной надписи: авто-цикл повторов слушает именно судью —
# `verdict == "НА ДОРАБОТКУ"` крутит edit → critique → judge, по три вызова
# модели за круг, на вердикте, который не может стать положительным.
#
# Scene Health при этом уже учтён: критику сказано «Нарушения чеклиста
# фиксируй в СТРУКТУРЕ и СЦЕНАХ». Гейт считал их второй раз, да ещё
# абсолютным вето.

class TestJudgeRuleMatchesCode:
    def test_judge_rule_states_the_same_conditions(self):
        from engine.pipeline_steps import SYS_JUDGE
        from engine.pipeline_config import ACCEPT_TOTAL, ACCEPT_MIN_CRITERION
        assert f"ИТОГ ≥ {ACCEPT_TOTAL}" in SYS_JUDGE
        assert f"критериев ≥ {ACCEPT_MIN_CRITERION}" in SYS_JUDGE

    def test_judge_has_no_extra_gate(self):
        """
        Третьего условия быть не должно: оно делало вердикт недостижимым
        и считало нарушения Scene Health второй раз.
        """
        from engine.pipeline_steps import SYS_JUDGE
        rule = next(l for l in SYS_JUDGE.splitlines() if "ПРАВИЛО ВЕРДИКТА" in l)
        assert "ни одного нарушения" not in rule, (
            "у судьи снова абсолютное вето по Scene Health — "
            "вердикт станет недостижимым, а авто-цикл будет крутиться впустую")

    def test_rule_is_not_written_into_the_prompt_by_hand(self):
        """
        Отличает подстановку от литерала с теми же числами.

        Тест ниже проверяет функцию `verdict_rule_for_prompt`, а не
        собранный `SYS_JUDGE` — и потому проходит, даже когда правило
        вписано в промпт руками. Фальсификация это показала: литерал с
        теми же числами набор не уронил. Здесь проверяется исходник.
        """
        from pathlib import Path
        src = (Path(__file__).resolve().parents[1] / "engine" / "pipeline_steps.py").read_text(
            encoding="utf-8")
        for line in src.splitlines():
            if "ПРАВИЛО ВЕРДИКТА" in line and "def " not in line and "#" not in line:
                raise AssertionError(
                    f"правило вердикта вписано в pipeline_steps.py литералом: {line.strip()[:90]}")

    def test_rule_comes_from_the_same_source_as_the_code(self, monkeypatch):
        """
        Проверка проверки: сдвинули константу — правило судьи обязано
        сдвинуться. Отличает подстановку от литерала с тем же значением.
        """
        import engine.pipeline_config as cfg
        monkeypatch.setattr(cfg, "ACCEPT_TOTAL", 41)
        rule = cfg.verdict_rule_for_prompt()
        assert "ИТОГ ≥ 41" in rule
        assert "30" not in rule, "прежнее число осталось — часть правила вписана литералом"

    def test_rule_and_code_agree_on_the_same_scores(self, monkeypatch):
        """
        Главное. Прогоняем оба пути по одним и тем же оценкам: расчёт кода
        и правило, которое читает судья. Они обязаны совпасть.
        """
        import re
        import engine.pipeline_tasks as pt
        from engine.pipeline_config import (ACCEPT_TOTAL, ACCEPT_MIN_CRITERION,
                                            verdict_rule_for_prompt)
        rule = verdict_rule_for_prompt()
        total_in_rule = int(re.search(r"ИТОГ ≥ (\d+)", rule).group(1))
        min_in_rule   = int(re.search(r"критериев ≥ (\d+)", rule).group(1))

        cases = [
            ((8, 7, 7, 7, 8), 37, "ПРИНЯТЬ"),
            ((7, 8, 7, 7, 7), 36, "ПРИНЯТЬ"),
            ((6, 6, 6, 6, 6), 30, "НА ДОРАБОТКУ"),   # середина
            ((5, 5, 5, 5, 5), 25, "НА ДОРАБОТКУ"),
            ((9, 9, 9, 2, 9), 38, "НА ДОРАБОТКУ"),   # один провал начисто
        ]
        for scores, total, expected in cases:
            monkeypatch.setattr(pt, "_call", lambda *a, _s=scores, _t=total, **k: _reply(*_s, _t))
            code = pt.score_text("Глава. " * 300, "детектив", MODEL)["verdict"]
            by_rule = ("ПРИНЯТЬ" if total >= total_in_rule and min(scores) >= min_in_rule
                       else "НА ДОРАБОТКУ")
            assert code == by_rule == expected, (
                f"оценки {scores}/{total}: код говорит {code}, "
                f"правило судьи — {by_rule}")


# ─── Пороги и судья идут вместе ──────────────────────────────────────────────
#
# Прежние 30/4 калиброваны на claude-haiku-4-5. 15.09 прямой ключ Anthropic
# исчерпан, судья заменён на kimi-k2.5 и калибровка проведена заново: 15
# настоящих глав против 15 нарочно испорченных.
#
#      итог  критерий   проходят      протекают
#        28      4       7 из 15       3 из 15
#        28      5       6 из 15       1 из 15
#        30      5       4 из 15       0 из 15   ← выбрано
#
# Тридцать у одной модели и тридцать у другой — разные тридцать, поэтому
# судья записан рядом с числами и меняться без перекалибровки не должен.

class TestThresholdTravelsWithItsJudge:
    def test_calibrated_judge_is_declared(self):
        from engine.pipeline_config import CALIBRATED_JUDGE
        assert "::" in CALIBRATED_JUDGE, "судья должен быть с провайдером"

    def test_bench_uses_the_calibrated_judge(self):
        """
        Замер обязан судить тем же судьёй, на котором калиброван порог.
        Своя копия в bench уже расходилась: в выводе стоял порог 40, когда
        движок принимал с 30.
        """
        import sys
        from pathlib import Path
        tools = Path(__file__).resolve().parents[2] / "tools"
        sys.path.insert(0, str(tools))
        import importlib
        bench = importlib.import_module("bench")
        from engine.pipeline_config import CALIBRATED_JUDGE
        assert bench.DEFAULT_JUDGE == CALIBRATED_JUDGE

    # Здесь стоял тест «судья не должен быть anthropic_direct» — он был
    # написан 15.09, когда прямой ключ Anthropic был исчерпан, и закрепил
    # ВРЕМЕННОЕ ОБСТОЯТЕЛЬСТВО как правило проекта. Ключ пополнили 22.09,
    # судья вернулся на claude-sonnet-5 — и тест стал врать: он падал на
    # штатной, обдуманной настройке.
    #
    # Правило, которое действительно нужно стеречь, уже проверено выше:
    # судья объявлен и замер судит тем же судьёй, на котором калиброван
    # порог. Кто именно это — решение владельца, а не инвариант кода.
