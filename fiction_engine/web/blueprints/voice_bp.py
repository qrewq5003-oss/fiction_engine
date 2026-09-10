"""Blueprint: голос, символы."""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from engine.db import get_chapter, get_chapters, get_api_key
from engine.api import get_all_models_flat
from .helpers import get_current_project

bp = Blueprint("voice", __name__)


@bp.route("/voice")
def voice_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
    from engine.db import get_voice_profiles, init_voice_tables
    from engine.voice_profiles import get_author_voices
    init_voice_tables()
    profiles = get_voice_profiles(current["id"])
    author_voices = get_author_voices()
    models = get_all_models_flat()
    return render_template("voice.html", current=current,
                           profiles=profiles, author_voices=author_voices, models=models)


@bp.route("/voice/analyze", methods=["POST"])
def voice_analyze():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    text = data.get("text", "").strip()
    model_value = data.get("model")
    if not text:
        return jsonify({"error": "Нет текста"}), 400
    if not get_api_key(model_value.split("::")[0]):
        return jsonify({"error": "Нет API ключа"}), 400
    try:
        from engine.scene_editor import analyze_voice
        return jsonify({"ok": True, "analysis": analyze_voice(text, model_value)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/voice/save", methods=["POST"])
def voice_save():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    name = data.get("name", "").strip()
    profile = data.get("profile", "").strip()
    if not name or not profile:
        return jsonify({"error": "Нужны name и profile"}), 400
    from engine.db import save_voice_profile
    pid = save_voice_profile(current["id"], name, profile,
                             data.get("samples", ""), data.get("source", "custom"))
    return jsonify({"ok": True, "id": pid})


@bp.route("/voice/activate", methods=["POST"])
def voice_activate():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db import set_active_voice
    set_active_voice(current["id"], (request.json or {}).get("id"))
    return jsonify({"ok": True})


@bp.route("/voice/delete", methods=["POST"])
def voice_delete():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    profile_id = (request.json or {}).get("id")
    if not profile_id:
        return jsonify({"error": "Нет id"}), 400
    from engine.db import delete_voice_profile
    delete_voice_profile(profile_id)
    return jsonify({"ok": True})


@bp.route("/voice/check", methods=["POST"])
def voice_check():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    text = data.get("text", "").strip()
    model_value = data.get("model")
    if not text:
        return jsonify({"error": "Нет текста"}), 400
    from engine.db import get_active_voice
    active_voice = get_active_voice(current["id"])
    if not active_voice:
        return jsonify({"error": "Нет активного голосового профиля"}), 400
    if not get_api_key(model_value.split("::")[0]):
        return jsonify({"error": "Нет API ключа"}), 400
    try:
        from engine.pipeline import analyze_voice_match
        data = analyze_voice_match(active_voice["profile"], text, model_value)
        return jsonify({"ok": True, "analysis": data["analysis"], "score": data["score"],
                        "voice_name": active_voice["name"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/voice/import_author", methods=["POST"])
def voice_import_author():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    source = (request.json or {}).get("source", "")
    from engine.voice_profiles import get_author_voice_by_source
    from engine.db import save_voice_profile
    voice = get_author_voice_by_source(source)
    if not voice:
        return jsonify({"error": "Голос не найден"}), 404
    pid = save_voice_profile(current["id"], voice["name"], voice["profile"],
                             voice["samples"], voice["source"])
    return jsonify({"ok": True, "id": pid})


# ─── Символы ─────────────────────────────────────────────────────────────────

@bp.route("/symbols")
def symbols_page():
    current = get_current_project()
    if not current:
        return redirect(url_for("index"))
    from engine.db import get_symbols
    symbols = get_symbols(current["id"])
    chapters = get_chapters(current["id"])
    return render_template("symbols.html", project=current, symbols=symbols, chapters=chapters)


@bp.route("/symbols/add", methods=["POST"])
def symbols_add():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    from engine.db import save_symbol
    sid = save_symbol(current["id"], data.get("name",""), data.get("symbol_type","предмет"),
                      data.get("introduced_ch",1), data.get("initial_meaning",""),
                      data.get("related_chars",""), data.get("notes",""))
    return jsonify({"ok": True, "id": sid})


@bp.route("/symbols/appearance", methods=["POST"])
def symbols_appearance():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    from engine.db import add_symbol_appearance
    add_symbol_appearance(data.get("symbol_id"), data.get("chapter"),
                          data.get("context",""), data.get("meaning",""))
    return jsonify({"ok": True})


@bp.route("/symbols/planned", methods=["POST"])
def symbols_planned():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    from engine.db import add_symbol_planned
    add_symbol_planned(data.get("symbol_id"), data.get("chapter",0),
                       data.get("how",""), data.get("meaning",""))
    return jsonify({"ok": True})


@bp.route("/symbols/delete", methods=["POST"])
def symbols_delete():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    from engine.db import delete_symbol
    delete_symbol((request.json or {}).get("id"))
    return jsonify({"ok": True})


@bp.route("/symbols/analyze", methods=["POST"])
def symbols_analyze():
    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет проекта"}), 400
    data = request.json or {}
    chapter_num = data.get("chapter_num")
    model_value = data.get("model")
    if not chapter_num or not model_value:
        return jsonify({"error": "Нужны chapter_num и model"}), 400
    if not get_api_key(model_value.split("::")[0]):
        return jsonify({"error": "Нет API ключа"}), 400
    ch = get_chapter(current["id"], chapter_num)
    if not ch:
        return jsonify({"error": "Глава не найдена"}), 404
    from engine.db import get_symbols
    existing_names = [s["name"] for s in get_symbols(current["id"])]
    SYS = "Ты редактор-аналитик. Ищешь символы в тексте. Только JSON."
    prompt = f"""Найди символы в главе. УЖЕ ИЗВЕСТНЫ: {', '.join(existing_names) or 'нет'}
ТЕКСТ:\n{ch['content'][:3000]}
{{"found":[{{"name":"...","type":"...","context":"...","potential_meaning":"...","is_new":true}}],"note":"..."}}"""
    try:
        from engine.pipeline import find_symbols_in_chapter
        result = find_symbols_in_chapter(ch["content"], existing_names, model_value)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
