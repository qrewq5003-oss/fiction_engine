"""
Fiction Engine — веб-интерфейс.
app.py регистрирует blueprints и держит только:
  - главную страницу
  - проекты (create/switch/delete)
  - настройки / API ключи
  - общие API-роуты (models, chapters, engine)
  - stats
"""

import os
import sys
from pathlib import Path
# Пакет ставится через `pip install -e .` (см. setup.sh), поэтому
# engine и web импортируются штатно — подмешивать пути не нужно.

# Загружаем .env если есть (python-dotenv опционален)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from engine.db import (init_db, create_project, get_projects, get_project,
                        set_active_project, get_active_project_id,
                        save_chapter, get_chapters, get_chapter,
                        get_state, update_state, save_api_key, get_api_key,
                        get_all_api_keys, save_state_update, mark_update_applied,
                        get_pending_updates, get_prep, save_prep, PREP_SECTIONS,
                        get_generation_history, get_generation_by_id,
                        init_generation_history)
from engine.api import get_all_models_flat, MODELS
from engine.state import analyze_chapter, build_prompt

app = Flask(__name__)

# Глава читается в память целиком (chapters.py, state_bp.py). Без лимита
# один большой файл кладёт процесс. 32 МБ — с большим запасом на любой роман.
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

# ─── Secret Key ───────────────────────────────────────────────────────────────
_secret = os.environ.get("FLASK_SECRET_KEY", "")
if not _secret:
    import secrets as _secrets
    _secret = _secrets.token_hex(32)
    import logging as _logging
    _logging.warning(
        "FLASK_SECRET_KEY не задан — используется случайный ключ. "
        "Сессии сбросятся при перезапуске. "
        "Задайте переменную окружения FLASK_SECRET_KEY для стабильной работы."
    )
app.secret_key = _secret
del _secret


# ─── Хелпер ──────────────────────────────────────────────────────────────────

def get_current_project():
    pid = get_active_project_id()
    return get_project(pid) if pid else None


# ─── Регистрация blueprints ──────────────────────────────────────────────────

from web.blueprints.chapters  import bp as chapters_bp
from web.blueprints.state_bp  import bp as state_bp
from web.blueprints.voice_bp  import bp as voice_bp
from web.blueprints.ideas_bp  import bp as ideas_bp
from web.blueprints.knowledge_bp import bp as knowledge_bp
from web.blueprints.generate_bp import bp as generate_bp

app.register_blueprint(chapters_bp)
app.register_blueprint(state_bp)
app.register_blueprint(voice_bp)
app.register_blueprint(ideas_bp)
app.register_blueprint(knowledge_bp)
app.register_blueprint(generate_bp)


# ─── Главная ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    projects = get_projects()
    current  = get_current_project()
    chapters = get_chapters(current["id"]) if current else []
    pending  = get_pending_updates(current["id"]) if current else []
    return render_template("index.html", projects=projects, current=current,
                           chapters=chapters, pending_updates=pending)


# ─── Проекты ─────────────────────────────────────────────────────────────────

@app.route("/project/new", methods=["POST"])
def project_new():
    name  = request.form.get("name", "").strip()
    genre = request.form.get("genre", "").strip()
    if not name:
        flash("Название обязательно", "error")
        return redirect(url_for("index"))
    try:
        pid = create_project(name, genre)
        set_active_project(pid)
        flash(f"Проект «{name}» создан", "success")
    except Exception as e:
        flash(f"Ошибка: {e}", "error")
    return redirect(url_for("index"))


@app.route("/project/<int:pid>/switch")
def project_switch(pid):
    set_active_project(pid)
    p = get_project(pid)
    flash(f"Переключился на «{p['name']}»", "success")
    return redirect(url_for("index"))


@app.route("/project/<int:pid>/delete", methods=["POST"])
def project_delete(pid):
    from engine.db import delete_project
    p = get_project(pid)
    name = p["name"] if p else f"#{pid}"
    delete_project(pid)
    flash(f"Проект «{name}» удалён", "info")
    projects = get_projects()
    if projects:
        set_active_project(projects[0]["id"])
    return redirect(url_for("index"))


# ─── Статистика ───────────────────────────────────────────────────────────────

@app.route("/stats")
def stats_page():
    current = get_current_project()
    if not current:
        flash("Сначала выбери проект", "error")
        return redirect(url_for("index"))
    chapters = get_chapters(current["id"])
    total_words = sum(ch["word_count"] or 0 for ch in chapters)
    return render_template("stats.html", current=current,
                           chapters=chapters, total_words=total_words)


# ─── Настройки ────────────────────────────────────────────────────────────────

@app.route("/settings")
def settings_page():
    models = get_all_models_flat()
    from engine import __version__
    return render_template("settings.html", models=models, version=__version__)


@app.route("/api/keys/status")
def api_keys_status():
    from engine.db import get_conn
    with get_conn() as conn:
        rows = conn.execute("SELECT provider, api_key FROM api_keys").fetchall()
    result = {}
    for r in rows:
        k = r["api_key"]
        result[r["provider"]] = k[:8] + "\u00b7" * 8 + k[-4:] if len(k) > 12 else "***"
    return jsonify(result)


@app.route("/api/keys/save", methods=["POST"])
def api_keys_save():
    data = request.json or {}
    provider = data.get("provider", "").strip()
    key = data.get("key", "").strip()
    if not provider or not key:
        return jsonify({"error": "provider и key обязательны"}), 400
    save_api_key(provider, key)
    return jsonify({"ok": True})


@app.route("/api/keys/delete", methods=["POST"])
def api_keys_delete():
    from engine.db import get_conn
    provider = (request.json or {}).get("provider", "").strip()
    if not provider:
        return jsonify({"error": "provider обязателен"}), 400
    with get_conn() as conn:
        conn.execute("DELETE FROM api_keys WHERE provider=?", (provider,))
    return jsonify({"ok": True})


@app.route("/api/scorer/model", methods=["GET"])
def scorer_model_get():
    from engine.db import get_conn
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='scorer_model'").fetchone()
        return jsonify({"model": row["value"] if row else ""})
    except Exception:
        return jsonify({"model": ""})


@app.route("/api/scorer/model", methods=["POST"])
def scorer_model_set():
    from engine.db import get_conn
    model = (request.json or {}).get("model", "")
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('scorer_model',?)", (model,))
    return jsonify({"ok": True})


@app.route("/api/resolver/model", methods=["GET"])
def resolver_model_get():
    from engine.db import get_conn
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='resolver_model'").fetchone()
        return jsonify({"model": row["value"] if row else ""})
    except Exception:
        return jsonify({"model": ""})


@app.route("/api/resolver/model", methods=["POST"])
def resolver_model_set():
    from engine.db import get_conn
    model = (request.json or {}).get("model", "")
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('resolver_model',?)", (model,))
    return jsonify({"ok": True})


@app.route("/api/settings/prevalidation", methods=["GET"])
def prevalidation_get():
    from engine.db import get_setting
    return jsonify({"enabled": get_setting("prevalidation_enabled") == "true"})


@app.route("/api/settings/prevalidation", methods=["POST"])
def prevalidation_set():
    from engine.db import get_conn
    enabled = bool((request.json or {}).get("enabled", False))
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key,value) VALUES ('prevalidation_enabled',?)",
            ("true" if enabled else "false",)
        )
    return jsonify({"ok": True, "enabled": enabled})


# ─── NanoGPT ─────────────────────────────────────────────────────────────────

@app.route("/api/nano/models")
def api_nano_models():
    import urllib.request, json as _json
    key = get_api_key("nano_gpt")
    if not key:
        return jsonify({"error": "no_key"}), 400
    try:
        req = urllib.request.Request(
            "https://nano-gpt.com/api/v1/models",
            headers={"Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = _json.loads(resp.read())
        models = [m["id"] for m in data.get("data", [])]
        return jsonify({"ok": True, "models": models, "count": len(models)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── UNIFIED ENGINE ───────────────────────────────────────────────────────────

@app.route("/api/engine/status")
def engine_status():
    from engine.unified_engine import engine_available, get_engine_path, get_all_genre_options
    available = engine_available()
    return jsonify({"available": available, "path": str(get_engine_path()),
                    "genres": get_all_genre_options() if available else []})


@app.route("/api/engine/modules")
def engine_modules():
    current = get_current_project()
    mode  = request.args.get("mode", "quick")
    model = request.args.get("model", "")
    if not current:
        return jsonify({"modules": []})
    from engine.unified_engine import (get_active_modules, detect_genre,
                                        engine_available, get_token_budget)
    if not engine_available():
        return jsonify({"modules": [], "available": False})
    genre = current.get("genre", "")
    modules = get_active_modules(genre, mode)
    genre_key = detect_genre(genre)
    budget = get_token_budget(model)
    return jsonify({"available": True, "genre_key": genre_key, "mode": mode,
                    "modules": modules, "token_budget": budget,
                    "engine_char_budget": int(budget * 4 * 0.35)})


@app.route("/api/engine/path", methods=["POST"])
def engine_set_path():
    from engine.db import get_conn
    path = (request.json or {}).get("path", "").strip()
    if not path:
        return jsonify({"error": "Нужен путь"}), 400
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('unified_engine_path',?)", (path,))
    from engine.unified_engine import engine_available
    return jsonify({"ok": True, "available": engine_available()})


# ─── Общие API ────────────────────────────────────────────────────────────────

@app.route("/api/models")
def api_models():
    return jsonify(get_all_models_flat())


@app.route("/api/chapters")
def api_chapters():
    current = get_current_project()
    if not current:
        return jsonify([])
    return jsonify(get_chapters(current["id"]))


@app.route("/api/batch_l3", methods=["POST"])
def api_batch_l3():
    """
    Пакетная генерация L3-саммари — SSE streaming.

    Тело запроса (JSON):
        {
            "model":        "..."         (обязательно),
            "chapter_nums": [1, 2, 3]    (опционально; null = все главы)
        }

    Возвращает Server-Sent Events:
        data: {"type": "progress", "current": 2, "total": 14, "chapter_num": 3}
        data: {"type": "done",     "generated": [...], "skipped": [...], "failed": [...]}
        data: {"type": "error",    "message": "..."}
    """
    import json as _json
    import threading
    from engine.pipeline import run_batch_l3

    current = get_current_project()
    if not current:
        return jsonify({"error": "Нет активного проекта"}), 400

    data         = request.get_json(silent=True) or {}
    model_value  = data.get("model", "").strip()
    chapter_nums = data.get("chapter_nums")

    if not model_value:
        return jsonify({"error": "Укажите model"}), 400

    project_id = current["id"]

    def stream():
        try:
            progress_events: list[tuple[int, int, int]] = []

            def _cb(current_idx: int, total: int, chapter_num: int) -> None:
                progress_events.append((current_idx, total, chapter_num))

            result_holder: dict = {}
            error_holder:  dict = {}

            def _run() -> None:
                try:
                    result_holder["result"] = run_batch_l3(
                        project_id=project_id,
                        model_value=model_value,
                        chapter_nums=chapter_nums,
                        progress_callback=_cb,
                    )
                except Exception as exc:
                    error_holder["error"] = str(exc)

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()

            import time
            sent = 0
            while thread.is_alive() or sent < len(progress_events):
                while sent < len(progress_events):
                    idx, total, ch_num = progress_events[sent]
                    evt = _json.dumps({
                        "type":        "progress",
                        "current":     idx + 1,
                        "total":       total,
                        "chapter_num": ch_num,
                    })
                    yield f"data: {evt}\n\n"
                    sent += 1
                if thread.is_alive():
                    time.sleep(0.1)

            if error_holder:
                yield f"data: {_json.dumps({'type': 'error', 'message': error_holder['error']})}\n\n"
            else:
                res = result_holder.get("result", {})
                yield f"data: {_json.dumps({'type': 'done', **res})}\n\n"

        except Exception as exc:
            import json as _j
            yield f"data: {_j.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return app.response_class(
        stream(),
        mimetype="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ─── Валидация движка при первом запросе (работает и под gunicorn) ────────────

_engine_validated = False

@app.before_request
def _validate_engine_once() -> None:
    """
    Проверяет пути движка один раз — при первом HTTP-запросе.
    Срабатывает независимо от способа запуска: python app.py, gunicorn, uWSGI.
    """
    global _engine_validated
    if _engine_validated:
        return
    _engine_validated = True

    import logging
    log = logging.getLogger(__name__)
    try:
        from engine.engine_loaders import validate_engine_paths
        check = validate_engine_paths()
        if not check["ok"]:
            log.error(
                "Fiction Engine: критические файлы не найдены: %s. Путь: %s",
                check["missing_critical"], check["engine_path"],
            )
        elif check["missing_optional"]:
            log.warning("Fiction Engine: опциональные файлы отсутствуют: %s",
                        check["missing_optional"])
    except Exception as exc:
        log.warning("Engine validation failed: %s", exc)


# ─── Запуск ──────────────────────────────────────────────────────────────────

def main() -> None:
    """
    Точка входа команды fiction-engine-web.

    Вынесена из блока __main__, чтобы работать и через установленный
    пакет, и при запуске файлом напрямую.
    """
    init_db()
    # validate_engine_paths вызывается автоматически при первом запросе
    # через @before_request хук _validate_engine_once — работает при любом запуске.
    # По умолчанию только петля: аутентификации нет, а в БД лежат API-ключи.
    # Выставить наружу — осознанно через FE_HOST=0.0.0.0.
    host = os.environ.get("FE_HOST", "127.0.0.1")
    port = int(os.environ.get("FE_PORT", "5000"))
    print(f"Fiction Engine запускается на http://{host}:{port}")
    if host == "0.0.0.0":
        print("  ВНИМАНИЕ: слушаем все интерфейсы без аутентификации — "
              "в БД хранятся API-ключи.")
    app.run(debug=False, host=host, port=port)


if __name__ == "__main__":
    main()
