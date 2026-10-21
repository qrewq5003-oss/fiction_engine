"""
Режиссёрская заметка — короткая инструкция движка самому себе
о том как подходить к следующей главе.

Не пересказ событий (это L3).
Не режим (это выбор пользователя).
Установка на тон, темп, подход — то что редактор написал бы на полях.
"""
from typing import Callable

PROMPT = """Ты — редактор. Ты только что прочитал главу художественного текста.

Напиши себе заметку для следующей главы: 2-3 коротких предложения.
Не пересказывай что произошло — это уже записано.
Пиши только о том КАК подходить к следующей: тон, темп, что держать, чего не делать.

Примеры хороших заметок:
"Он ещё не переварил. Не торопить реакцию. Тишина важнее действия."
"Отношения сломаны но оба делают вид. Диалог должен быть про другое."
"Напряжение на пике — следующая сцена разрядка, но не облегчение."

Примеры плохих заметок:
"Произошло предательство, нужно показать последствия." — это пересказ
"Писать в мастер режиме с высоким стандартом." — это не установка

КОНЕЦ ГЛАВЫ (последние 800 символов):
{chapter_tail}

ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:
{global_state}

Заметка (2-3 предложения, только суть):"""


def generate_director_note(
    project_id: int,
    chapter_num: int,
    chapter_text: str,
    state: dict,
    api_call_fn: Callable[..., str],
) -> str | None:
    """
    Сгенерировать режиссёрскую заметку после сохранения главы.
    Сохраняет в БД и возвращает текст заметки.
    """
    try:
        # Заметка к следующей главе уже есть — план из планировщика или
        # запись автора: не перезаписывать (сохранение было безусловным)
        from engine.db import get_director_note
        if get_director_note(project_id, chapter_num + 1):
            return None
        tail = chapter_text[-800:].strip()
        # Герои конца главы, а не первые 400 знаков State: там были только
        # второстепенные, добавленные позже (разбор 21.10)
        from engine.pipeline_context import extract_relevant_state
        global_state = extract_relevant_state(state, tail, before_chapter=chapter_num + 1)[:1500]

        prompt = PROMPT.format(
            chapter_tail=tail,
            global_state=global_state,
        )

        note = api_call_fn(prompt)
        if not note or len(note.strip()) < 10:
            return None

        note = note.strip()

        from engine.db import save_director_note
        save_director_note(project_id, chapter_num, note, source="auto")

        return note

    except Exception:
        return None
