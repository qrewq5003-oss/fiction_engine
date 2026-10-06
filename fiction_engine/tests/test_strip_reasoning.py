"""
Рассуждения «думающих» моделей не должны попадать в текст главы.

Замер 06.10: у MiMo v2.5 Pro глава начиналась с «</thought>» — открывающий
тег провайдер съел, закрывающий остался. Блоки снимались только в JSON.
"""
from unittest.mock import patch

from engine.pipeline_tasks import strip_reasoning

CHAPTER = "Она закрыла дверь и села у окна. " * 40


def test_full_block_removed():
    t, ch = strip_reasoning("<think>план сцены</think>\n" + CHAPTER)
    assert ch and t == CHAPTER.strip() and "план" not in t


def test_orphan_close_at_start_cuts_reasoning():
    t, ch = strip_reasoning("рассуждаю о сцене…</thought> " + CHAPTER)
    assert ch and t.startswith("Она закрыла") and "рассуждаю" not in t


def test_orphan_close_deep_in_text_removes_only_tag():
    """Глубоко в тексте тег — не граница рассуждения: главу не теряем."""
    t, ch = strip_reasoning(CHAPTER + "</thought>" + CHAPTER)
    assert ch and "</thought>" not in t and t.count("Она закрыла") == 80


def test_clean_text_untouched():
    t, ch = strip_reasoning(CHAPTER)
    assert not ch and t == CHAPTER          # без тегов — байт в байт


def test_run_generation_strips_and_warns(project_id):
    from engine.pipeline import run_generation
    raw = "<thinking>сначала улики</thinking>" + "Он вошёл в комнату и сел у окна. " * 400
    with patch("engine.pipeline._call", return_value=raw):
        res = run_generation({"id": project_id, "genre": "детектив"}, 1, "quick", "m::x", "Задача.")
    assert "<thinking>" not in res["text"] and "сначала улики" not in res["text"]
    assert "рассуждений модели" in res["warning"]


# ─── Сигналы по тексту главы (engine/text_signals.py) ────────────────────────

def test_signals_quiet_on_most_real_chapters():
    """На главах трёх генераторов панели сигнал получают меньше половины."""
    import json
    from pathlib import Path
    from engine.text_signals import chapter_signals
    bench = Path(__file__).resolve().parents[2] / "bench"
    chs = [c["text"] for p in ("base-pool-2026-10-05.json", "base-pool-kimi-2026-10-06.json",
                               "base-pool-deepseek-2026-10-06.json")
           for c in json.loads((bench / p).read_text(encoding="utf-8"))["chapters"]]
    flagged = sum(bool(chapter_signals(t)) for t in chs)
    assert len(chs) == 64 and flagged < len(chs) / 2


def test_signals_find_similes_cliche_and_repeats():
    from engine.text_signals import chapter_signals
    text = ("Свет падал словно вода, и тени лежали будто ковёр. " * 20
            + "Она почувствовала страх и вышла. " + "Он смотрел на стену. " * 60
            + "Коридор тянулся долго. " * 5 + "Лестница скрипела. " * 30)
    sig = " ".join(chapter_signals(text))
    assert "Сравнений «словно / будто»" in sig
    assert "Штамп эмоции" in sig and "почувствовала страх" in sig


def test_signals_ignore_names():
    """Имя пишется с заглавной — его повтор не сигналит."""
    from engine.text_signals import chapter_signals
    text = ("Михаил пришёл. Потом Михаил сел. Михаил молчал. Тишина стояла в комнате. " * 40)
    assert not any("михаил" in s.lower() for s in chapter_signals(text))


def test_run_generation_reports_signals(project_id):
    from engine.pipeline import run_generation
    chapter = "Свет падал словно вода, и тени лежали будто ковёр в комнате. " * 300
    with patch("engine.pipeline._call", return_value=chapter):
        res = run_generation({"id": project_id, "genre": "детектив"}, 1, "quick", "m::x", "Задача.")
    assert "словно / будто" in res["warning"]
