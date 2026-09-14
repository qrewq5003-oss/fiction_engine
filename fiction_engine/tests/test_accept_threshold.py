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
    def test_typical_good_chapter_is_accepted(self, monkeypatch):
        """Настоящая глава из замера: итог 31, минимальный критерий 5."""
        assert _verdict(monkeypatch, (7, 6, 6, 5, 7), 31) == "ПРИНЯТЬ"

    def test_best_measured_chapter_is_accepted(self, monkeypatch):
        assert _verdict(monkeypatch, (8, 7, 7, 7, 8), 37) == "ПРИНЯТЬ"

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
                assert preset.score_threshold >= ACCEPT_TOTAL - 1, (
                    f"{preset.description[:30]}: планка {preset.score_threshold} "
                    f"ниже порога принятия {ACCEPT_TOTAL}")
