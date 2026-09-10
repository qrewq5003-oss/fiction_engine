"""
Общие хелперы для всех blueprints.

Правило: этот файл не импортирует _call, _build_*, _make_* из pipeline.
Только публичные функции engine-слоя.
"""
from engine.db import get_project, get_active_project_id, get_conn


def get_current_project():
    pid = get_active_project_id()
    if pid:
        return get_project(pid)
    return None


def get_cheap_model(fallback_model: str) -> str:
    """Вернуть resolver_model из настроек или fallback."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='resolver_model'"
            ).fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass
    return fallback_model


def _get_scorer_model(fallback: str) -> str:
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='scorer_model'"
            ).fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception:
        pass
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
    except Exception:
        pass

    # 3. Режиссёрская заметка
    try:
        from engine.pipeline import generate_director_note_for_chapter
        note = generate_director_note_for_chapter(project_id, chapter_num, text, cheap)
        if note:
            result["director_note"] = note
    except Exception:
        pass

    # 4. Авто-оценка
    try:
        scorer_model = _get_scorer_model(model_value)
        if scorer_model:
            score = _auto_score_chapter(project_id, chapter_num, text, scorer_model)
            if score is not None:
                result["auto_score"] = score
    except Exception:
        pass

    return result


def _auto_score_chapter(project_id: int, chapter_num: int,
                         text: str, scorer_model: str):
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
    genre   = project.get("genre", "") if project else ""

    try:
        details = score_text(text, genre, scorer_model)
        save_chapter_score(project_id, chapter_num, details)
        return details.get("total")
    except Exception:
        return None
