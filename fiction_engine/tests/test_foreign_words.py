#!/usr/bin/env python3
"""
Английские вставки в русской главе (engine/foreign_words.py).

Зачем. 21 из 32 глав GLM-5.3 в A/B-замерах содержали вставки вроде
«kissed her», «laid off», «СегодняLate», «под.controlем». Судьи их не
видят, читатель видит сразу. Все примеры ниже — из реальных глав.
"""

import json
import sys
from unittest.mock import MagicMock, patch

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

from engine.foreign_words import (fix_foreign_words, foreign_words,  # noqa: E402
                                  sentences_with_foreign)


class Model:
    """Заглушка корректора: отвечает по очереди заданными словарями."""

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, model, system, user, max_tokens=None, prefill=""):
        self.prompts.append(user)
        a = self.answers.pop(0) if self.answers else {}
        if isinstance(a, Exception):
            raise a
        return a if isinstance(a, str) else json.dumps(a, ensure_ascii=False)


# ─── Поиск ───────────────────────────────────────────────────────────────────

class TestDetect:
    def test_whole_words_and_glued(self):
        text = ("Олег поставил чашку, kissed her in макушку. СегодняLate она встала. "
                "Он держал её под.controlем весь разговор.")
        assert foreign_words(text) == ["kissed", "her", "in", "СегодняLate", "controlем"]

    def test_mixed_script_word(self):
        """Латинская «y» в кириллическом слове — тоже вставка."""
        assert foreign_words("каретка машинкy звякнула") == ["машинкy"]

    def test_not_foreign(self):
        text = "Глава XIV. План B не сработал. Обычный русский текст."
        assert foreign_words(text) == []

    def test_words_from_prompt_are_allowed(self):
        """Автор сам назвал корабль «Nostromo» — это не сбой модели."""
        text = "На борту Nostromo погас свет, footsteps."
        assert foreign_words(text, allowed="Корабль: Nostromo, экипаж 7") == ["footsteps"]

    def test_dot_inside_is_not_sentence_end(self):
        """Точка без пробела — не граница: иначе корректор получит обрубок."""
        text = "Щека дёргалась, и он держал её под.controlем весь разговор. Потом ушёл."
        (a, b), = sentences_with_foreign(text)
        assert text[a:b] == "Щека дёргалась, и он держал её под.controlем весь разговор."

    def test_one_span_per_sentence(self):
        text = "Первая фраза чистая. Тут twice и footsteps сразу! Абзац.\nЕщё kitchen тут"
        spans = sentences_with_foreign(text)
        assert [text[a:b] for a, b in spans] == ["Тут twice и footsteps сразу!", "Ещё kitchen тут"]


# ─── Замена ──────────────────────────────────────────────────────────────────

TEXT = ("Начало главы. Олег сварил кофе, kissed her in макушку и ушёл. "
        "Середина без ошибок. Механизм ракушки, eighth по счёту от края.")


class TestFix:
    def test_only_bad_sentences_are_replaced(self):
        model = Model({"1": "Олег сварил кофе, поцеловал её в макушку и ушёл.",
                       "2": "Механизм ракушки, восьмой по счёту от края."})
        out, fixed = fix_foreign_words(TEXT, "m", model)
        assert out == ("Начало главы. Олег сварил кофе, поцеловал её в макушку и ушёл. "
                       "Середина без ошибок. Механизм ракушки, восьмой по счёту от края.")
        assert fixed == ["kissed", "her", "in", "eighth"]
        assert "Середина без ошибок" not in model.prompts[0], "чистые фразы модели не уходят"

    def test_replacement_with_latin_is_rejected(self):
        model = Model({"1": "Олег сварил кофе, kissed её в макушку и ушёл.",
                       "2": "Механизм ракушки, восьмой по счёту от края."},
                      {})
        out, fixed = fix_foreign_words(TEXT, "m", model)
        assert "kissed her in макушку" in out, "плохая замена не принимается"
        assert "восьмой" in out and fixed == ["eighth"]

    def test_rewrite_instead_of_fix_is_rejected(self):
        """Замена вдвое длиннее — это переписывание, а не перевод слова."""
        long = "Олег сварил кофе и, " + "долго глядя в окно, " * 6 + "поцеловал её в макушку."
        model = Model({"1": long, "2": "Механизм ракушки, восьмой по счёту от края."}, {})
        out, _ = fix_foreign_words(TEXT, "m", model)
        assert long not in out and "kissed" in out

    def test_second_pass_takes_leftovers(self):
        model = Model({"2": "Механизм ракушки, восьмой по счёту от края."},
                      {"1": "Олег сварил кофе, поцеловал её в макушку и ушёл."})
        out, fixed = fix_foreign_words(TEXT, "m", model)
        assert not foreign_words(out)
        assert len(model.prompts) == 2
        assert "eighth" not in model.prompts[1], "второй проход — только остатки"

    def test_retry_after_pass_that_fixed_nothing(self):
        """Первый ответ вернул ту же латиницу — это не повод сдаваться."""
        model = Model({"1": "Олег сварил кофе, kissed её в макушку и ушёл."},
                      {"1": "Олег сварил кофе, поцеловал её в макушку и ушёл.",
                       "2": "Механизм ракушки, восьмой по счёту от края."})
        out, fixed = fix_foreign_words(TEXT, "m", model)
        assert not foreign_words(out) and len(model.prompts) == 2

    def test_passes_are_bounded(self):
        model = Model(*[{}] * 10)
        out, _ = fix_foreign_words(TEXT, "m", model)
        assert out == TEXT and len(model.prompts) == 3

    def test_model_error_keeps_text(self):
        out, fixed = fix_foreign_words(TEXT, "m", Model(*[RuntimeError("503")] * 3))
        assert out == TEXT and fixed == []

    def test_garbage_answer_keeps_text(self):
        out, fixed = fix_foreign_words(TEXT, "m", Model("не JSON вовсе"))
        assert out == TEXT and fixed == []

    def test_clean_text_makes_no_call(self):
        model = Model()
        out, fixed = fix_foreign_words("Чистый текст.", "m", model)
        assert out == "Чистый текст." and not model.prompts


# ─── В генерации ─────────────────────────────────────────────────────────────

FULL = "Она закрыла дверь и села у окна. " * 400


def test_run_generation_cleans_and_warns(project_id):
    from engine.pipeline import run_generation
    chapter = FULL + "Олег сварил кофе, kissed her in макушку и ушёл."
    fix = json.dumps({"1": "Олег сварил кофе, поцеловал её в макушку и ушёл."},
                     ensure_ascii=False)
    replies = iter([chapter, fix])
    with patch("engine.pipeline._call", side_effect=lambda *a, **k: next(replies, "{}")):
        res = run_generation({"id": project_id, "genre": "детектив"}, 1, "quick", "m::x", "Задача.")
    assert res["text"].endswith("поцеловал её в макушку и ушёл.")
    assert "Исправлены английские вставки (3)" in res["warning"]


def test_pipeline_generate_step_cleans():
    from engine.pipeline_steps import step_generate
    chapter = FULL + "Механизм ракушки, eighth по счёту от края."
    replies = iter([chapter, '{"1": "Механизм ракушки, восьмой по счёту от края."}'])
    results: dict = {}
    with patch("engine.pipeline_steps.save_pipeline_iteration") as saved:
        step_generate(1, 1, 3, "задача", "ПРОМПТ", "m", "sys",
                      lambda *a, **k: next(replies), results)
    assert results["generated_text"].endswith("восьмой по счёту от края.")
    assert "eighth" in results["foreign_words"]
    assert saved.call_args.args[-1] == results["generated_text"]
