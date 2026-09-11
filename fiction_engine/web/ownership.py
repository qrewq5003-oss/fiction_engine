"""
Принадлежность объектов активному проекту.

Большинство маршрутов Fiction Engine работают от `chapter_num` и сами
разрешают его внутри активного проекта — там вопроса не возникает. Но
часть принимает СКВОЗНЫЕ идентификаторы: номер генерации и номер запуска
pipeline уникальны на всю базу. Такие маршруты брали их из запроса как
есть, и объекты другого проекта были доступны:

    GET  /api/generation/<id>        отдавал чужой текст главы
    POST /api/generation/<id>/delete удалял чужую генерацию
    GET  /pipeline/<run_id>/history  показывал чужие итерации
    POST /pipeline/reject            менял статус чужого запуска

Проектов у одного пользователя много, и перепутать их легко: достаточно
открыть старую вкладку или перейти по ссылке из истории браузера после
переключения проекта.

Проверки собраны здесь, чтобы новый обработчик брал готовую, а не
изобретал свою: поимённые заплатки в планировщике как раз и привели к
тому, что закрыли три случая из одиннадцати.
"""

from flask import jsonify


def active_pid() -> int | None:
    from engine.db import get_active_project_id
    return get_active_project_id()


def owned_generation(gen_id: int | None) -> dict | None:
    """Запись истории генераций активного проекта — или None."""
    from engine.db import get_generation_by_id
    gen = get_generation_by_id(gen_id) if gen_id is not None else None
    pid = active_pid()
    return gen if gen and pid and gen.get("project_id") == pid else None


def owned_run(run_id: int | None) -> dict | None:
    """Запуск pipeline активного проекта — или None."""
    from engine.db import get_pipeline_run
    run = get_pipeline_run(run_id) if run_id is not None else None
    pid = active_pid()
    return run if run and pid and run["project_id"] == pid else None


def deny(what: str = "Объект") -> tuple:
    """Единый отказ: не раскрываем, существует ли объект в другом проекте."""
    return jsonify({"error": f"{what} не найден в текущем проекте"}), 404
