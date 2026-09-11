#!/usr/bin/env python3
"""
Промпт, подготовка и точечная правка.

Выделено из generate_bp.py: файл дорос до 905 строк и держал
четыре несвязанные темы сразу. Блупринт остаётся общим — bp
импортируется из generate_bp, поэтому имена endpoint'ов не
меняются и url_for в шаблонах продолжает работать.
"""

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
    return jsonify({"chars": chars, "warning": chars > 8000,
                    "message": f"{chars} символов" + (" — возможно превышение" if chars > 8000 else "")})


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
                f"НЕЗАКРЫТЫЕ ЛИНИИ: {prev_l3.get('promises', '')}"
            )

        # 3. State Engine — current character states
        state = get_state(project_id)
        state_text = state.get("content", "").strip()[:1500] if state else ""

        # 4. Get model
        from engine.db import get_setting
        model_value = get_setting("model") or ""
        if not model_value:
            return jsonify({"error": "Не задана модель в настройках"}), 400

        # 5. Build LLM prompt
        sys_prompt = (
            "Ты — литературный ассистент. Помогаешь автору составить промт для генерации главы. "
            "Анализируешь контекст серии и создаёшь структурированный черновик промта. "
            "Пишешь лаконично и конкретно — автор сам доработает детали."
        )

        context_parts = []
        if plot_text:
            # Extract relevant chapter plan
            lines = plot_text.split('\n')
            relevant = []
            capture = False
            for line in lines:
                if f"{chapter_num}" in line or f"Гл.{chapter_num}" in line or f"Глава {chapter_num}" in line:
                    capture = True
                if capture:
                    relevant.append(line)
                    if len(relevant) > 15:
                        break
            if relevant:
                context_parts.append(f"ПЛАН СЕРИИ (фрагмент про гл.{chapter_num}):\n" + "\n".join(relevant))
            else:
                context_parts.append(f"ПЛАН СЕРИИ:\n{plot_text[:1000]}")

        if prev_l3_text:
            context_parts.append(f"САММАРИ ПРЕДЫДУЩЕЙ ГЛАВЫ:\n{prev_l3_text}")

        if state_text:
            context_parts.append(f"ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:\n{state_text[:800]}")

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
        result = call_llm(model_value, sys_prompt, user_prompt, max_tokens=600)

        if not result or len(result.strip()) < 50:
            return jsonify({"error": "Модель вернула пустой ответ"}), 500

        return jsonify({"ok": True, "prompt": result.strip()})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
