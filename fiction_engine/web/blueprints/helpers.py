"""
Общие хелперы для всех blueprints.

Правило: этот файл не импортирует _call, _build_*, _make_* из pipeline.
Только публичные функции engine-слоя.
"""
from typing import TYPE_CHECKING

from engine.db import get_project, get_active_project_id, get_conn

if TYPE_CHECKING:
    from werkzeug.datastructures import FileStorage


def get_current_project() -> dict | None:
    pid = get_active_project_id()
    if pid:
        return get_project(pid)
    return None


def log_web_error(context: str, exc: Exception, **ctx: object) -> None:
    """
    Записать ошибку web-слоя, не прерывая обработку запроса.

    Нужен потому, что дополнительные шаги после сохранения главы (L3,
    дрейф голоса, режиссёрская заметка, авто-оценка) некритичны: их отказ
    не должен ронять запрос. Но и молчать нельзя — именно так три
    функциональных бага прожили в проекте незамеченными.
    """
    try:
        from engine.logger import get_logger
        get_logger("web").error(context, exc, **ctx)
    except Exception:
        # Логирование — последнее, что может отказать; дальше некуда
        pass


def attachment_header(filename: str) -> str:
    """
    Значение Content-Disposition для скачивания файла с любым именем.

    Заголовки HTTP кодируются в latin-1. Имя проекта по-русски, вставленное
    как есть, роняло ответ на реальном сервере (UnicodeEncodeError) —
    тестовый клиент Flask заголовки не кодирует и этого не видел.
    Поэтому имя идёт дважды (RFC 6266 / RFC 5987): ASCII-замена для старых
    клиентов и точное имя в UTF-8 в filename*.
    """
    import re
    from urllib.parse import quote
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_") or "export"
    fallback = f"{ascii_stem}.{ext}" if ext else ascii_stem
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename, safe='')}"


UPLOAD_EXTENSIONS = (".txt", ".docx")


def read_uploaded_text(file: "FileStorage") -> str:
    """
    Текст загруженного .txt или .docx.

    Загрузка главы раньше декодировала любой файл как UTF-8: .docx — это
    zip-архив, и в главу молча сохранялся мусор. Неподдерживаемый формат —
    ValueError, а не догадка.
    """
    name = (file.filename or "").lower()
    if name.endswith(".txt"):
        return file.read().decode("utf-8", errors="replace")
    if name.endswith(".docx"):
        import io
        import docx
        document = docx.Document(io.BytesIO(file.read()))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())
    raise ValueError("Поддерживаются только .txt и .docx")


def get_cheap_model(fallback_model: str) -> str:
    """Вернуть resolver_model из настроек или fallback."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='resolver_model'"
            ).fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception as e:
        log_web_error("get_cheap_model: не прочитать resolver_model", e)
    return fallback_model


def _get_scorer_model(fallback: str) -> str:
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='scorer_model'"
            ).fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception as e:
        log_web_error("_get_scorer_model: не прочитать scorer_model", e)
    return fallback


def after_chapter_saved(project_id: int, chapter_num: int, text: str, model_value: str) -> dict:
    """
    Единый pipeline после сохранения главы:
      1. L3 саммари
      2. Дрейф голоса
      3. Режиссёрская заметка
      4. Авто-оценка

    Возвращает dict с результатами (не кидает исключений).
    """
    # Аннотация обязательна: без неё тип выводится по первому
    # присваиванию (bool), и последующая запись строки — ошибка типов
    result: dict[str, object] = {}
    cheap  = get_cheap_model(model_value)

    # 1. L3
    try:
        from engine.pipeline import generate_l3
        summary = generate_l3(project_id, chapter_num, text, cheap)
        result["l3_generated"] = summary is not None
    except Exception:
        result["l3_generated"] = False

    # 2. Дрейф голоса
    try:
        from engine.pipeline import auto_drift_check_if_needed
        drift = auto_drift_check_if_needed(project_id, chapter_num, text, model_value)
        if drift and drift.get("warning"):
            result["drift_warning"] = drift["warning"]
            result["drift_score"]   = drift.get("score")
    except Exception as e:
        log_web_error("после сохранения: проверка дрейфа голоса", e,
                      project_id=project_id, chapter_num=chapter_num)

    # 3. Режиссёрская заметка
    try:
        from engine.pipeline import generate_director_note_for_chapter
        note = generate_director_note_for_chapter(project_id, chapter_num, text, cheap)
        if note:
            result["director_note"] = note
    except Exception as e:
        log_web_error("после сохранения: режиссёрская заметка", e,
                      project_id=project_id, chapter_num=chapter_num)

    # 4. Авто-оценка
    try:
        scorer_model = _get_scorer_model(model_value)
        if scorer_model:
            score = _auto_score_chapter(project_id, chapter_num, text, scorer_model)
            if score is not None:
                result["auto_score"] = score
    except Exception as e:
        log_web_error("после сохранения: авто-оценка главы", e,
                      project_id=project_id, chapter_num=chapter_num)

    return result


def _auto_score_chapter(project_id: int, chapter_num: int,
                         text: str, scorer_model: str) -> float | None:
    """
    Оценить главу через pipeline.score_text и сохранить в chapter_scores.
    Возвращает итоговый балл или None при ошибке.
    """
    from engine.db import get_api_key, get_project, save_chapter_score
    from engine.pipeline import score_text

    provider = scorer_model.split("::")[0] if "::" in scorer_model else ""
    if not get_api_key(provider):
        return None

    project = get_project(project_id)
    from engine.unified_engine import project_genre_key
    genre   = project_genre_key(project) or ""

    try:
        details = score_text(text, genre, scorer_model)
        save_chapter_score(project_id, chapter_num, details)
        return details.get("total")
    except Exception:
        return None
