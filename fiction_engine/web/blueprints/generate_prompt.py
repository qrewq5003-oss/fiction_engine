#!/usr/bin/env python3
"""
Промпт, подготовка и точечная правка.

Выделено из generate_bp.py: файл дорос до 905 строк и держал
четыре несвязанные темы сразу. Блупринт остаётся общим — bp
импортируется из generate_bp, поэтому имена endpoint'ов не
меняются и url_for в шаблонах продолжает работать.
"""

import re

from flask import render_template, request, jsonify, redirect, url_for, flash
from engine.db import (get_chapters, get_api_key,
                       get_prep, save_prep, PREP_SECTIONS)
from engine.api import get_all_models_flat
from engine.state import build_prompt   # используется в /prompt/generate


from .generate_bp import bp
from .helpers import (get_current_project)


@bp.route("/prompt")
def prompt_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
    models = get_all_models_flat()
    chapters = get_chapters(current["id"])
    return render_template("prompt.html", current=current, models=models, chapters=chapters)


@bp.route("/prompt/generate", methods=["POST"])
def prompt_generate():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    chapter_num = request.json.get("chapter_num")
    mode = request.json.get("mode", "quick")
    if not chapter_num:
        return jsonify({"error": "Нужен номер главы"}), 400
    try:
        prompt = build_prompt(current["id"], chapter_num, mode, current)
        return jsonify({"ok": True, "prompt": prompt})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/prep")
def prep_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
    prep = get_prep(current["id"])
    return render_template("prep.html", current=current, prep=prep, sections=PREP_SECTIONS)


@bp.route("/prep/save", methods=["POST"])
def prep_save():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    section = request.json.get("section", "").strip()
    content = request.json.get("content", "")
    if section not in PREP_SECTIONS:
        return jsonify({"error": "Неизвестная секция"}), 400
    save_prep(current["id"], section, content)
    return jsonify({"ok": True})


@bp.route("/api/prep/size")
def prep_size():
    current = get_current_project()
    if not current:
        return jsonify({"chars": 0})
    from engine.db import get_prep_context
    chars = len(get_prep_context(current["id"]))
    from engine.pipeline_config import PREP_WARN_CHARS
    warn = chars > PREP_WARN_CHARS
    return jsonify({"chars": chars, "warning": warn,
                    "message": f"{chars} символов" + (
                        f" — больше {PREP_WARN_CHARS // 1000} тыс.: уходит писателю в каждой главе "
                        f"целиком, дорого и рассеивает внимание" if warn else "")})


@bp.route("/edit")
def edit_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
    models = get_all_models_flat()
    chapters = get_chapters(current["id"])
    from engine.scene_editor import EDIT_MODES
    return render_template("edit.html", current=current, models=models,
                           chapters=chapters, edit_modes=EDIT_MODES)


@bp.route("/edit/run", methods=["POST"])
def edit_run():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    text        = data.get("text", "").strip()
    mode        = data.get("mode", "cliches")
    model_value = data.get("model")
    custom      = data.get("custom", "").strip()
    if not text or not model_value:
        return jsonify({"error": "Нужны text и model"}), 400
    if not get_api_key(model_value.split("::")[0]):
        return jsonify({"error": "Нет API ключа"}), 400
    try:
        from engine.scene_editor import edit_scene
        result = edit_scene(current["id"], text, mode, model_value, custom)
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _plot_fragment(plot_text: str, chapter_num: int) -> str:
    """
    Строки «Сюжета» про эту главу: с её номера, до 16 строк. Номер — отдельным
    числом: раньше «1» находилось в «2016» и в «11», и кнопка брала не тот кусок.
    """
    import re
    num = re.compile(rf"(?<!\d){chapter_num}(?!\d)")
    relevant: list[str] = []
    for line in plot_text.split("\n"):
        if not relevant and num.search(line):
            relevant.append(line)
        elif relevant:
            relevant.append(line)
        if len(relevant) > 15:
            break
    return "\n".join(relevant)


# Приписки модели после самого промта: «Примечание: в заголовке опечатка…»
# («Ночная смена», 20.10) — кнопка вставляла их в задачу, и они уходили писателю
_NOTE_LINE = re.compile(r"^\s*(?:-{3,}|\*{0,2}(?:Примечани|Комментари|Пояснени))", re.IGNORECASE)


def _without_model_notes(text: str) -> str:
    lines = text.strip().splitlines()
    for i, line in enumerate(lines):
        if i and _NOTE_LINE.match(line):
            return "\n".join(lines[:i]).strip()
    return text.strip()


def _open_promises(l3: dict, chapter_num: int) -> str:
    """Незакрытые обещания главы — текстом, на момент этой главы. Раньше уходил
    список Python целиком, с закрытыми и «resolved_chapter» поздних глав (разбор 21.10)."""
    from engine.pipeline import open_promises_of
    return "; ".join(open_promises_of(l3, chapter_num)) or "нет"


@bp.route("/api/prompt-assist", methods=["POST"])
def prompt_assist():
    """Ассистент промта: собирает контекст и генерирует черновик промта для главы."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет активного проекта"}), 400

    data = request.json or {}
    chapter_num = data.get("chapter_num")
    if not chapter_num:
        return jsonify({"error": "Укажи номер главы"}), 400

    project_id = current["id"]

    try:
        from engine.db import get_l3_summary
        from engine.db_settings import get_prep
        from engine.db_state import get_state

        # 1. Plan for this chapter from plot section
        prep = get_prep(project_id)
        plot_text = prep.get("plot", "").strip()

        # 2. L3 summary of previous chapter
        prev_l3 = get_l3_summary(project_id, chapter_num - 1) if chapter_num > 1 else None
        prev_l3_text = ""
        if prev_l3:
            prev_l3_text = (
                f"СОБЫТИЯ гл.{chapter_num-1}: {prev_l3.get('events', '')}\n"
                f"ПЕРСОНАЖИ: {prev_l3.get('characters', '')}\n"
                f"КОНФЛИКТЫ: {prev_l3.get('conflicts', '')}\n"
                f"НАСТРОЕНИЕ: {prev_l3.get('mood', '')}\n"
                f"НЕЗАКРЫТЫЕ ЛИНИИ: {_open_promises(prev_l3, int(chapter_num))}"
            )

        # 3. State Engine — персонажи и сюжет. Раньше читался ключ «content»,
        # которого у State нет, — ассистент не видел State никогда
        # State на момент главы (db_state.state_for_chapter)
        from engine.db_state import state_for_chapter
        state = state_for_chapter(project_id, int(chapter_num)) or {}
        # Герои плана и замысла главы, а не первые 3000 знаков State: у «Фона»
        # это 13 % State, и главной героини в них не было (разбор 21.10)
        from engine.db import get_director_note as _note
        from engine.pipeline_context import extract_relevant_state
        focus = "\n".join(x for x in (_note(project_id, chapter_num) or "", plot_text[:2000]) if x)
        state_text = extract_relevant_state(state, focus, before_chapter=int(chapter_num))[:6000]

        # 4. Модель — выбранная на странице генерации
        from web.blueprints.helpers import pick_model
        model_value = pick_model(data.get("model", ""))
        if not model_value:
            return jsonify({"error": "Нет модели с ключом: выбери модель в поле «Модель»"}), 400

        # 5. Build LLM prompt
        sys_prompt = (
            "Ты — литературный ассистент. Помогаешь автору составить промт для генерации главы. "
            "Анализируешь контекст серии и создаёшь структурированный черновик промта. "
            "Пишешь лаконично и конкретно — автор сам доработает детали."
        )

        # План главы из планировщика (тот, что уйдёт писателю). Раньше кнопка
        # его не видела и сочиняла главу от крючка прошлой: «Ночная смена»
        # (20.10) — подвал и новая свидетельница вместо плана, в последней
        # главе новый крючок вместо развязки; писатель получал две разные главы
        from engine.db import get_director_note
        chapter_plan = (get_director_note(project_id, chapter_num) or "").strip()

        context_parts = []
        if chapter_plan:
            context_parts.append("ПЛАН ГЛАВЫ (писатель получит его отдельно, целиком):\n" + chapter_plan)
            if plot_text:
                context_parts.append(f"ЗАМЫСЕЛ КНИГИ:\n{plot_text[:1000]}")
        elif plot_text:
            relevant = _plot_fragment(plot_text, chapter_num)
            if relevant:
                context_parts.append(f"ПЛАН СЕРИИ (фрагмент про гл.{chapter_num}):\n" + relevant)
            else:
                context_parts.append(f"ПЛАН СЕРИИ:\n{plot_text[:1000]}")

        if prev_l3_text:
            context_parts.append(f"САММАРИ ПРЕДЫДУЩЕЙ ГЛАВЫ:\n{prev_l3_text}")

        if state_text:
            context_parts.append(f"ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:\n{state_text}")

        if chapter_plan:
            # Задача — направление поверх плана, а не его пересказ: время, место и
            # порядок сцен писатель уже получает, а вторая копия плана с другими
            # словами спорит с первой
            user_prompt = (
                "\n\n---\n\n".join(context_parts) +
                f"\n\n---\n\nСоставь черновик задачи для Главы {chapter_num} поверх плана главы.\n"
                "Не пересказывай план: не переноси время, даты, места, порядок и состав сцен. "
                "Не добавляй событий, улик и персонажей, которых нет в плане и прошлых главах. "
                "Не раскрывай того, что план велит пока не раскрывать.\n\n"
                "Формат строго такой:\n"
                f"Гл.{chapter_num} — [НАЗВАНИЕ ЗАГЛАВНЫМИ]\n\n"
                "ЗАДАЧА: [одно-два предложения — что эта глава делает с читателем]\n\n"
                "ТОНАЛЬНОСТЬ: [2-3 слова]\n"
                "ЗАКАНЧИВАЕТСЯ НА: [то, чем кончается последняя сцена плана]\n\n"
                "Не добавляй объяснений — только сам промт."
            )
        else:
            user_prompt = (
                "\n\n---\n\n".join(context_parts) +
                f"\n\n---\n\nСоставь черновик промта для Главы {chapter_num}.\n\n"
                "Формат строго такой:\n"
                f"Гл.{chapter_num} — [НАЗВАНИЕ ЗАГЛАВНЫМИ]\n\n"
                "ЗАДАЧА: [одно предложение — что должна сделать эта глава с читателем]\n\n"
                "СЦЕНЫ:\n"
                "1. [Локация — краткое описание]\n"
                "2. [Локация — краткое описание]\n"
                "3. [Локация — краткое описание]\n\n"
                "ТОНАЛЬНОСТЬ: [2-3 слова]\n"
                "ЗАКАНЧИВАЕТСЯ НА: [крючок или состояние]\n\n"
                "Не добавляй объяснений — только сам промт."
            )

        # 6. Call LLM
        from engine.pipeline import call_llm
        result = _without_model_notes(call_llm(model_value, sys_prompt, user_prompt, max_tokens=600) or "")

        if len(result) < 50:
            return jsonify({"error": "Модель вернула пустой ответ"}), 500

        return jsonify({"ok": True, "prompt": result, "with_plan": bool(chapter_plan)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
