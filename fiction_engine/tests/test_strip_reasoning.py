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
