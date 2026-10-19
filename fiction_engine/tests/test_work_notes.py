"""Рабочие заметки модели без тегов в тексте главы (книга «Фон», гл.21, 19.10)."""
from unittest.mock import patch

CHAPTER = "\n\n".join(f"Абзац {i}. Варя смотрела на экран и считала кадры, Лёва варил суп." for i in range(300))
DRAFT = "Звонок прозвенел в 13:02. Марат стоял у двери с термосом."
NOTES = ("Write scene 2 (~1000 words). Varya in loft, Gosha waits.\n"
         "Hmm, Marat visited Varya at 13:02 and was there till about 13:19.\n"
         "Write final cleanly.")
LEAK = DRAFT + "\n\n" + NOTES + CHAPTER


def test_detects_notes_and_takes_text_after_them():
    from engine.pipeline_tasks import after_work_notes, work_note_lines
    lines = work_note_lines(LEAK)
    assert len(lines) == 2                         # «Write final cleanly.» склеено с главой — не заметка
    assert after_work_notes(LEAK, lines) == CHAPTER.strip()


def test_ordinary_chapter_with_english_line_untouched():
    from engine.pipeline_tasks import work_note_lines
    text = CHAPTER + "\n\nnightowl_52: молодец\n\n— Okay, let me just check this one thing, — сказал Гоша в камеру."
    assert work_note_lines(text) == []
    assert work_note_lines("Just an English story about a lighthouse keeper and his notes.") == []


def _run(answers):
    from engine.pipeline_steps import step_generate
    calls, results = [], {}

    def call(model, system, prompt, **kw):
        calls.append(prompt)
        return answers.pop(0)
    with patch("engine.pipeline_steps.save_pipeline_iteration"), \
         patch("engine.pipeline.extend_short_chapter", side_effect=lambda t, *a, **k: (t, "")), \
         patch("engine.pipeline.clean_foreign_words", side_effect=lambda t, *a, **k: (t, [])), \
         patch("engine.chapter_analyzer.analyze_chapter_deep", return_value=None):
        step_generate(1, 1, 21, "Глава 21", "ПРОМПТ", "m", "sys", call, results)
    return results, calls


def test_generate_retries_once_and_takes_clean_retry():
    results, calls = _run([LEAK, CHAPTER])
    assert len(calls) == 2 and results["generated_text"] == CHAPTER
    assert results["work_notes"] == 2 and results["work_notes_fixed"] == "повтор генерации"


def test_generate_falls_back_to_text_after_notes():
    results, calls = _run([LEAK, LEAK])
    assert len(calls) == 2 and results["generated_text"] == CHAPTER.strip()
    assert results["work_notes_fixed"] == "текст после заметок"


def test_generate_warns_when_nothing_clean():
    body = "\n\n".join(f"Абзац {i}. Варя смотрела на экран и считала кадры." for i in range(60))
    short = body + "\n\n" + NOTES + "\n\nКороткий хвост: меньше, чем нужно на главу."
    results, _ = _run([short, short])
    assert "рабочие заметки" in results["warning"] and results["generated_text"] == short
