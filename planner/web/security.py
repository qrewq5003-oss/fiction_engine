"""
security.py — вход по паролю и защита от CSRF, как в Fiction Engine
(fiction_engine/web/security.py).

Вход. Пароль — PLANNER_PASSWORD, а если его нет, FE_PASSWORD: обычно оба
приложения открывают вместе и одним паролем. Пароль задан — без входа не
открывается ни одна страница, кроме /login. Не на петле (PLANNER_HOST не
127.0.0.1 / localhost / ::1) без пароля планировщик не запускается: через
него видны проекты Fiction Engine и пишутся планы глав.

CSRF. Чужая страница в том же браузере может отправить запрос на
http://127.0.0.1:5001 и удалить сцену. Поэтому запрос, меняющий данные
(не GET / HEAD / OPTIONS), несёт токен сессии: заголовок X-CSRF-Token
(apiPost в base.html добавляет его сам) или поле csrf_token формы.
"""

from __future__ import annotations

import hmac
import os
import secrets

from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def password() -> str:
    return os.environ.get("PLANNER_PASSWORD") or os.environ.get("FE_PASSWORD", "")


def check_host(host: str) -> str | None:
    """Почему нельзя запускаться на этом адресе, или None."""
    if host not in LOOPBACK and not password():
        return (f"PLANNER_HOST={host} открывает планировщик сети, а входа нет: "
                f"задайте PLANNER_PASSWORD или FE_PASSWORD.")
    return None


def allowed_request_host(host_header: str) -> bool:
    """
    Имя в Host — петля или из PLANNER_TRUSTED_HOSTS (через запятую). Защита от
    DNS rebinding, как в Fiction Engine (web/security.allowed_request_host):
    чужое имя, перепривязанное на 127.0.0.1, — отказ. Вне петли без списка
    не действует (там нужен пароль).
    """
    import os
    name = (host_header or "").strip().lower()
    if name.startswith("["):
        name = name[1:].split("]")[0]
    elif name.count(":") == 1:
        name = name.split(":")[0]
    extra = {h.strip().lower() for h in os.environ.get("PLANNER_TRUSTED_HOSTS", "").split(",") if h.strip()}
    if os.environ.get("PLANNER_HOST", "127.0.0.1") not in LOOPBACK and not extra:
        return True
    return name in LOOPBACK or name in extra


def safe_next(nxt: str | None) -> str:
    """
    Куда вернуть после входа: только свой путь. Управляющие символы и обратный
    слеш вырезаются ДО проверки: «/<табуляция>/evil.example» проходил проверку, а
    браузер, выкинув табуляцию, шёл на //evil.example (разбор планировщика 21.10).
    """
    from urllib.parse import urlsplit
    s = "".join(ch for ch in str(nxt or "") if ch >= " " and ch != "\x7f").replace("\\", "/")
    parts = urlsplit(s)
    if not s.startswith("/") or s.startswith("//") or parts.scheme or parts.netloc:
        return "/"
    return s


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _same(a: str | None, b: str | None) -> bool:
    # Байты, а не строки: compare_digest на строке с кириллицей падает
    return bool(a and b) and hmac.compare_digest(str(a).encode(), str(b).encode())


_LOGIN_PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Вход — Планировщик</title>
<style>body{background:#0f0f13;color:#e2e2f0;font-family:system-ui,sans-serif;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0}form{background:#1a1a22;
border:1px solid #2e2e3e;border-radius:10px;padding:28px;width:min(320px,90vw)}input{width:100%;
box-sizing:border-box;padding:10px;margin:12px 0;background:#22222e;color:#e2e2f0;border:1px solid
#2e2e3e;border-radius:6px}button{width:100%;padding:10px;background:#7c6af7;color:#fff;border:0;
border-radius:6px;cursor:pointer}.err{color:#f87171;font-size:14px}</style></head><body>
<form method="POST"><div>Планировщик</div>
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="password" name="password" placeholder="Пароль" autofocus required>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<button type="submit">Войти</button></form></body></html>"""


def init_security(app: Flask) -> None:
    # PLANNER_CSRF=False — только для тестов, которые шлют POST без сессии
    app.config.setdefault("PLANNER_CSRF", True)
    # Своё имя cookie: Fiction Engine на том же 127.0.0.1, а cookie порт не
    # различают — общий «session» приложения затирали друг другу
    app.config["SESSION_COOKIE_NAME"] = "planner_session"
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.route("/login", methods=["GET", "POST"])
    def login():
        error = ""
        if request.method == "POST":
            if _same(request.form.get("password"), password()):
                session.clear()
                session["planner_auth"] = True
                session.permanent = True
                nxt = request.args.get("next") or "/"
                # Только свой путь — не уводить на чужой сайт после входа
                return redirect(safe_next(nxt))
            error = "Неверный пароль"
        return render_template_string(_LOGIN_PAGE, error=error)

    @app.before_request
    def _host_guard():
        if not allowed_request_host(request.host):
            return jsonify({"error": "запрос на чужое имя хоста отклонён: открывайте планировщик по "
                                     "127.0.0.1 или localhost (в сети — PLANNER_TRUSTED_HOSTS)"}), 403
        return None

    @app.before_request
    def _same_project():
        """
        Запрос для проекта, который сейчас не открыт, — 409. Проект — в общей
        сессии браузера: вкладка, открытая для одной книги, после переключения
        в другой вкладке писала в другую (разбор планировщика 21.10). Страница
        шлёт X-Planner-Project; без него — как раньше.
        """
        want = (request.headers.get("X-Planner-Project") or "").strip()
        if not want or request.method in SAFE_METHODS:
            return None
        if str(session.get("project_id") or "") != want:
            return jsonify({"error": "Страница открыта для другого проекта — в другой вкладке открыт "
                                     "другой. Обновите страницу.", "project_mismatch": True}), 409
        return None

    @app.before_request
    def _guard():
        if password() and not session.get("planner_auth") and request.endpoint not in ("login", "static"):
            if request.method in SAFE_METHODS and not request.path.startswith("/api/"):
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return jsonify({"error": "нужен вход"}), 401
        if request.method not in SAFE_METHODS and app.config["PLANNER_CSRF"]:
            sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not _same(sent, session.get("csrf")):
                return jsonify({"error": "запрос отклонён: нет токена CSRF — обновите страницу"}), 403
        return None
