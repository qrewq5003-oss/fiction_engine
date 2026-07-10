"""Blueprint: главы, экспорт, L3."""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, Response
from engine.db import get_chapter, get_chapters, save_chapter, get_api_key
from .helpers import get_current_project, get_cheap_model, after_chapter_saved

bp = Blueprint("chapters", __name__)


@bp.route("/chapter/upload", methods=["POST"])
def chapter_upload():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("main.index"))
    number = request.form.get("number", type=int)
    title  = request.form.get("title", "").strip()
    file   = request.files.get("file")
    text   = request.form.get("text", "").strip()
    if file and file.filename:
        content = file.read().decode("utf-8", errors="replace")
    elif text:
        content = text
    else:
        flash("Нужен файл или текст", "error")
        return redirect(url_for("main.index"))
    if not number:
        flash("Укажи номер главы", "error")
        return redirect(url_for("main.index"))
    save_chapter(current["id"], number, content, title)
    flash(f"Глава {number} сохранена ({len(content.split())} слов)", "success")
    return redirect(url_for("main.index"))


@bp.route("/chapter/<int:num>/view")
def chapter_view(num):
    current = get_current_project()
    if not current:
        return redirect(url_for("main.index"))
    ch = get_chapter(current["id"], num)
    return render_template("chapter.html", chapter=ch, current=current)


@bp.route("/export/txt")
def export_txt():
    current = get_current_project()
    if not current:
        return redirect(url_for("main.index"))
    chapters = get_chapters(current["id"])
    lines = []
    for ch in chapters:
        full = get_chapter(current["id"], ch["number"])
        lines.append(f"=== Глава {ch['number']} ===\n\n{full['content']}\n\n")
    return Response("\n".join(lines), mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment;filename={current['name']}.txt"})


@bp.route("/export/chapter/<int:num>/txt")
def export_chapter_txt(num):
    current = get_current_project()
    if not current:
        return redirect(url_for("main.index"))
    ch = get_chapter(current["id"], num)
    if not ch:
        flash("Глава не найдена", "error")
        return redirect(url_for("main.index"))
    return Response(ch["content"], mimetype="text/plain",
                    headers={"Content-Disposition": f"attachment;filename=chapter_{num}.txt"})




@bp.route("/export/docx")
def export_docx():
    """Экспорт всех глав в один DOCX файл."""
    current = get_current_project()
    if not current:
        return redirect(url_for("main.index"))
    chapters = get_chapters(current["id"])
    if not chapters:
        flash("Нет глав для экспорта", "error")
        return redirect(url_for("main.index"))

    try:
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        import io

        doc = Document()

        # Стиль документа
        style = doc.styles["Normal"]
        style.font.name = "Georgia"
        style.font.size = Pt(12)

        # Заголовок книги
        title_p = doc.add_paragraph()
        title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_p.add_run(current["name"])
        run.font.size = Pt(24)
        run.bold = True

        if current.get("genre"):
            sub_p = doc.add_paragraph()
            sub_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            sub_run = sub_p.add_run(current["genre"])
            sub_run.font.size = Pt(12)
            sub_run.italic = True

        doc.add_page_break()

        for ch in chapters:
            full = get_chapter(current["id"], ch["number"])
            if not full or not full.get("content"):
                continue

            # Заголовок главы
            h = doc.add_paragraph()
            h.alignment = WD_ALIGN_PARAGRAPH.CENTER
            hr = h.add_run(f"Глава {ch['number']}" +
                          (f": {ch['title']}" if ch.get("title") else ""))
            hr.font.size = Pt(16)
            hr.bold = True

            doc.add_paragraph()  # отступ

            # Текст главы — разбиваем по абзацам
            for para_text in full["content"].split("\n"):
                p = doc.add_paragraph(para_text)
                p.paragraph_format.first_line_indent = Inches(0.3)

            doc.add_page_break()

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        safe_name = current["name"].replace(" ", "_")
        return Response(
            buf.read(),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment;filename={safe_name}.docx"}
        )
    except ImportError:
        flash("Установи python-docx: pip install python-docx", "error")
        return redirect(url_for("main.index"))
    except Exception as e:
        flash(f"Ошибка экспорта: {e}", "error")
        return redirect(url_for("main.index"))


@bp.route("/api/chapters/search")
def chapters_search():
    """Поиск по тексту всех глав."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"results": []})

    chapters = get_chapters(current["id"])
    results = []
    q_lower = q.lower()

    for ch in chapters:
        full = get_chapter(current["id"], ch["number"])
        if not full or not full.get("content"):
            continue
        content = full["content"]
        content_lower = content.lower()

        # Найти все вхождения с контекстом
        pos = 0
        matches = []
        while True:
            idx = content_lower.find(q_lower, pos)
            if idx == -1:
                break
            # Вырезать контекст: 100 символов до и после
            start = max(0, idx - 100)
            end = min(len(content), idx + len(q) + 100)
            snippet = content[start:end].replace("\n", " ")
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet = snippet + "..."
            matches.append(snippet)
            pos = idx + len(q)
            if len(matches) >= 3:  # максимум 3 совпадения на главу
                break

        if matches:
            results.append({
                "chapter_num": ch["number"],
                "chapter_title": ch.get("title") or f"Глава {ch['number']}",
                "matches": matches,
                "count": len(matches)
            })

    return jsonify({"results": results, "query": q, "total": len(results)})


@bp.route("/api/continuity/check", methods=["POST"])
def continuity_check():
    """Проверить главу на нарушения непрерывности."""
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    chapter_num = data.get("chapter_num")
    text = data.get("text", "").strip()
    model_value = data.get("model", "")

    if not chapter_num or not text:
        return jsonify({"error": "Нужны chapter_num и text"}), 400
    if not model_value:
        try:
            from engine.db import get_conn
            with get_conn() as conn:
                row = conn.execute("SELECT value FROM settings WHERE key='last_model'").fetchone()
            model_value = row["value"] if row else ""
        except Exception:
            pass
    if not model_value:
        return jsonify({"error": "Не задана модель"}), 400

    try:
        from engine.continuity_checker import check_continuity
        from engine.pipeline import _call as llm_call
        import functools

        def api_fn(prompt):
            return llm_call(model_value,
                           "Ты редактор серии. Ищешь нарушения непрерывности. Только JSON.",
                           prompt, max_tokens=600)

        violations = check_continuity(current["id"], chapter_num, text, api_fn)
        return jsonify({"ok": True, "violations": violations, "count": len(violations)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── L3 ──────────────────────────────────────────────────────────────────────

@bp.route("/api/l3/status")
def l3_status():
    current = get_current_project()
    if not current:
        return jsonify({"summaries": []})
    from engine.db import get_l3_status
    return jsonify({"summaries": get_l3_status(current["id"])})


@bp.route("/api/l3/<int:chapter_num>")
def l3_get(chapter_num):
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db import get_l3_summary
    return jsonify({"summary": get_l3_summary(current["id"], chapter_num)})


@bp.route("/api/l3/<int:chapter_num>/generate", methods=["POST"])
def l3_generate(chapter_num):
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    ch = get_chapter(current["id"], chapter_num)
    if not ch:
        return jsonify({"error": "Глава не найдена"}), 404
    model_value = (request.json or {}).get("model", "")
    if not model_value:
        try:
            from engine.db import get_conn
            with get_conn() as conn:
                row = conn.execute("SELECT value FROM settings WHERE key='last_model'").fetchone()
            model_value = row["value"] if row else ""
        except Exception:
            pass
    if not model_value:
        return jsonify({"error": "Не задана модель"}), 400
    from engine.pipeline import generate_l3
    summary = generate_l3(current["id"], chapter_num, ch["content"],
                          get_cheap_model(model_value))
    if not summary:
        return jsonify({"error": "Не удалось сгенерировать саммари"}), 500
    return jsonify({"ok": True, "summary": summary})


@bp.route("/api/l3/<int:chapter_num>/delete", methods=["POST"])
def l3_delete(chapter_num):
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db import delete_l3_summary
    delete_l3_summary(current["id"], chapter_num)
    return jsonify({"ok": True})

