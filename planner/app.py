"""
app.py — планировщик истории.
Запуск: python app.py
Порт: 5001
"""
from flask import Flask, redirect, url_for, session, request, jsonify, render_template
import os
from pathlib import Path

# Окружение FE (fiction_engine/.env): FE_PASSWORD оттуда — и токен вызовов FE, и
# вход. Без него при заданном пароле все вызовы планировщика к FE получали 401
# (разбор 21.10). Своё .env планировщика — важнее
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    load_dotenv(Path(__file__).parent.parent / "fiction_engine" / ".env")
except ImportError:
    pass

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")


def _session_secret() -> str:
    """
    Ключ подписи сессий. Константа в коде — публичный ключ (подделка cookie).
    Порядок: SECRET_KEY, FLASK_SECRET_KEY (так он называется в .env FE), иначе
    постоянный файл PLANNER_SECRET_FILE (~/fiction_engine/planner_secret.key).
    Раньше без SECRET_KEY ключ был новым при каждом запуске: после перезапуска
    открытые карточки получали отказ, а автосохранение теряло правки молча
    (разбор планировщика 21.10).
    """
    env = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
    if env:
        return env
    import secrets
    path = Path(os.environ.get("PLANNER_SECRET_FILE") or Path.home() / "fiction_engine" / "planner_secret.key")
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_hex(32)
    path.write_text(key, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:                 # Windows: права NTFS, chmod ничего не даёт
        pass
    return key


app.secret_key = _session_secret()

# Вход по паролю и CSRF — web/security.py
from web.security import check_host, init_security
init_security(app)


@app.template_filter("local")
def local_time(value, n: int = 16) -> str:
    """Время из базы (UTC, «YYYY-MM-DD HH:MM:SS») — в местном: показывалось в UTC
    без пометки, принятая в 13:51 глава значилась в 10:51 (разбор 21.10)."""
    from datetime import datetime, timezone
    s = str(value or "")
    try:
        t = datetime.strptime(s[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return s[:n]
    return t.astimezone().strftime("%Y-%m-%d %H:%M:%S")[:n]

# ─── Init DB ─────────────────────────────────────────────────────────────────
from engine.db import init_db
init_db()

# ─── Blueprints ───────────────────────────────────────────────────────────────
from web.blueprints.main_bp   import bp as main_bp
from web.blueprints.scene_bp  import bp as scene_bp
from web.blueprints.api_bp    import bp as api_bp

app.register_blueprint(main_bp)
app.register_blueprint(scene_bp)
app.register_blueprint(api_bp)

# ─── Текущий проект ──────────────────────────────────────────────────────────
# Выбирается до обработчика, а не при отрисовке шаблона. Раньше первый проект
# подставлялся только в контекст шаблона: в новой сессии панель показывала
# проект выбранным, а «Доска» уводила на список проектов — маршруты читают
# session["project_id"], который ещё не был задан.
@app.before_request
def ensure_current_project():
    # Только страницы: запросы /api/ идут со страницы, где проект уже выбран,
    # а часть из них доказанно не обращается к базе (tests/test_ownership.py)
    if request.path.startswith(("/api/", "/static/")):
        return
    from engine.db import get_projects, get_project
    pid = session.get("project_id")
    if pid and get_project(pid):
        return
    projects = get_projects()
    if projects:
        session["project_id"] = projects[0]["id"]
    else:
        session.pop("project_id", None)


@app.errorhandler(500)
def _json_500(e):
    """Сбой запроса страницы (/api/…, POST) — JSON с причиной, а не HTML: JS
    показывал «Unexpected token <» (разбор планировщика 21.10)."""
    if request.path.startswith("/api/") or request.method != "GET":
        err = getattr(e, "original_exception", None) or e
        return jsonify({"error": f"сбой сервера: {type(err).__name__}: {str(err)[:200]}"}), 500
    return "Внутренняя ошибка планировщика", 500


@app.context_processor
def inject_globals():
    from engine.db import get_projects, get_project
    current_id = session.get("project_id")
    return {"projects": get_projects(), "current": get_project(current_id) if current_id else None}


@app.route("/")
def index():
    return redirect(url_for("main.board"))


@app.route("/switch/<int:pid>")
def switch_project(pid):
    # Несуществующий проект в сессию не ставить
    from engine.db import get_project
    if get_project(pid):
        session["project_id"] = pid
    return redirect(url_for("main.board"))


if __name__ == "__main__":
    # По умолчанию слушаем только петлю. Для доступа с телефона (Tailscale) —
    # PLANNER_HOST=0.0.0.0 и пароль: без него не на петле не запускаемся.
    host = os.environ.get("PLANNER_HOST", "127.0.0.1")
    port = int(os.environ.get("PLANNER_PORT", "5001"))
    why = check_host(host)
    if why:
        raise SystemExit(why)
    print(f"Планировщик запускается на http://{host}:{port}")
    app.run(debug=False, host=host, port=port)
