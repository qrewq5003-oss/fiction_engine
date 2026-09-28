#!/usr/bin/env python3
"""
Короткая глава дописывается вторым вызовом (extend_short_chapter).

Зачем. Модель заканчивает главу сама, законченной фразой, но короче
требуемого: A/B 27.09 — 10 глав из 16 ниже 2500 слов, минимум 1698.
Движок только показывал баннер. Теперь недостающий объём дописывается,
но не в тех случаях, где дописывание навредит: обрыв на полуслове,
режим «Продолжение главы», глава и так в норме.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

from engine.pipeline_config import (CONTINUATION_MARKER, EXTEND_MIN_ADD,  # noqa: E402
                                    MIN_CHAPTER_WORDS, PROSE_MAX_TOKENS,
                                    TARGET_CHAPTER_WORDS, extension_prompt,
                                    extension_words)
from engine.pipeline_tasks import extend_short_chapter  # noqa: E402

SHORT = "Она закрыла дверь и села у окна. " * 250          # 1750 слов
FULL = "Она закрыла дверь и села у окна. " * 400           # 2800 слов
MORE = "Шаги остановились у двери не сразу. " * 200


class Recorder:
    def __init__(self, reply=MORE):
        self.calls, self.reply = [], reply

    def __call__(self, model, system, user, max_tokens=None, prefill=""):
        self.calls.append({"user": user, "max_tokens": max_tokens})
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _extend(text, user="ПРОМПТ ГЛАВЫ", call=None, stop="stop"):
    call = call or Recorder()
    with patch("engine.api.get_last_stop_reason", return_value=stop):
        out, note = extend_short_chapter(text, "m", "sys", user, call)
    return out, note, call


def test_short_finished_chapter_is_extended():
    out, note, call = _extend(SHORT)
    assert len(call.calls) == 1
    assert out.startswith(SHORT.rstrip()) and out.endswith(MORE.strip())
    assert "1750 →" in note
    sent = call.calls[0]
    assert sent["user"].startswith("ПРОМПТ ГЛАВЫ"), "продолжению нужен исходный промпт главы"
    assert SHORT.strip() in sent["user"]
    assert sent["max_tokens"] == PROSE_MAX_TOKENS


def test_full_chapter_untouched():
    out, note, call = _extend(FULL)
    assert out == FULL and not note and not call.calls


def test_cut_mid_sentence_untouched():
    """Обрыв на полуслове — другой случай: там кнопка продолжения с хвостом."""
    text = SHORT + "И тогда он сказал, что"
    out, note, call = _extend(text)
    assert out == text and not call.calls


def test_max_tokens_stop_untouched():
    out, _, call = _extend(SHORT, stop="max_tokens")
    assert out == SHORT and not call.calls


def test_continuation_mode_untouched():
    """Вторая часть главы по кнопке «Продолжить» и должна быть короче."""
    out, _, call = _extend(SHORT, user=f"⚠️ {CONTINUATION_MARKER} — …")
    assert out == SHORT and not call.calls


def test_call_error_keeps_written_text():
    out, note, _ = _extend(SHORT, call=Recorder(RuntimeError("503")))
    assert out == SHORT and not note


def test_empty_continuation_keeps_written_text():
    out, note, _ = _extend(SHORT, call=Recorder("  "))
    assert out == SHORT and not note


def test_extension_words_target_the_top():
    assert extension_words(1750) == TARGET_CHAPTER_WORDS - 1750
    assert extension_words(2450) == 550
    assert extension_words(2950) == EXTEND_MIN_ADD


def test_extension_prompt_says_last_paragraph_is_not_the_end():
    p = extension_prompt(SHORT)
    assert "1750 слов" in p and "не финал" in p and SHORT.strip() in p


def test_ui_continue_note_carries_the_marker():
    """Кнопка «Продолжить главу» пишет director note с маркером — по нему
    движок узнаёт вторую часть главы и не дописывает её до полной."""
    html = (Path(__file__).resolve().parents[1] / "web/templates/generate.html").read_text(encoding="utf-8")
    assert CONTINUATION_MARKER in html


def test_run_generation_extends_and_warns(project_id):
    from engine.pipeline import run_generation
    replies = iter([SHORT, MORE])
    with patch("engine.pipeline._call", side_effect=lambda *a, **k: next(replies, "{}")), \
         patch("engine.api.get_last_stop_reason", return_value="stop"):
        res = run_generation({"id": project_id, "genre": "детектив"}, 1, "quick", "m::x", "Задача.")
    assert res["text"].endswith(MORE.strip())
    assert res["word_count"] > MIN_CHAPTER_WORDS
    assert not res["truncated"]
    assert "дописана" in res["warning"]


def test_pipeline_generate_step_extends():
    """Второй путь генерации — шаг generate пайплайна."""
    from engine.pipeline_steps import step_generate
    results: dict = {}
    replies = iter([SHORT, MORE])

    def call_fn(model, system, user, max_tokens=None, prefill=""):
        return next(replies)

    with patch("engine.pipeline_steps.save_pipeline_iteration") as saved, \
         patch("engine.api.get_last_stop_reason", return_value="stop"):
        step_generate(1, 1, 3, "задача", "ПРОМПТ ГЛАВЫ", "m", "sys", call_fn, results)
    assert results["generated_text"].endswith(MORE.strip())
    assert "дописана" in results["extended"]
    assert saved.call_args.args[-1] == results["generated_text"], "в историю — дописанный текст"
    assert results["truncated"] is False
