"""
security.py — вход по паролю и защита от CSRF (ROADMAP, этап 5.1 и 5.3).

Вход. FE_PASSWORD задан — без входа не открывается ни одна страница, кроме
/login. Не на петле (FE_HOST не 127.0.0.1 / localhost / ::1) без пароля
приложение не запускается: в БД лежат ключи провайдеров.

CSRF. Чужая страница в том же браузере может отправить форму на
http://127.0.0.1:5000 — и удалить проект или подменить ключ. Поэтому любой
запрос, меняющий данные (не GET / HEAD / OPTIONS), несёт токен сессии:
заголовок X-CSRF-Token (fetch в base.html добавляет его сам) или поле
csrf_token формы. Без токена — 403.

Программы на той же машине (planner) вместо сессии шлют заголовок
X-FE-Token: sha256 от FE_PASSWORD (token_from_password), если он задан, иначе содержимое файла
~/fiction_engine/api_token (создаётся с правами 600, путь — FE_API_TOKEN_FILE).
Браузер сам такой заголовок не добавляет, поэтому CSRF через него невозможен.

Маршрут /login и сам вход — без пароля; файл api_token тесты кладут во
временную папку (FE_API_TOKEN_FILE в conftest).
"""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

from flask.typing import ResponseReturnValue
from flask import Flask, jsonify, redirect, render_template_string, request, session, url_for

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def password() -> str:
    return os.environ.get("FE_PASSWORD", "")


def api_token_file() -> Path:
    return Path(os.environ.get("FE_API_TOKEN_FILE")
                or Path.home() / "fiction_engine" / "api_token")


def token_from_password(pw: str) -> str:
    """
    Токен из пароля. Не сам пароль: заголовок HTTP — латиница-1, а пароль
    может быть русским. Планировщик считает так же (planner, _fe_headers).
    """
    import hashlib
    return hashlib.sha256(("fiction-engine-api:" + pw).encode()).hexdigest()


def api_token() -> str:
    """Токен для программ на этой машине: из пароля, если он задан, иначе файл."""
    if password():
        return token_from_password(password())
    from engine.secret_store import private_file
    return private_file(api_token_file(), lambda: secrets.token_urlsafe(32).encode()).decode()


def check_host(host: str) -> str | None:
    """Почему нельзя запускаться на этом адресе, или None."""
    if host not in LOOPBACK and not password():
        return (f"FE_HOST={host} открывает приложение сети, а входа нет: задайте FE_PASSWORD "
                f"(в БД лежат ключи провайдеров).")
    return None


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def _same(a: str | None, b: str | None) -> bool:
    # Байты, а не строки: compare_digest на строке с кириллицей падает
    return bool(a and b) and hmac.compare_digest(str(a).encode(), str(b).encode())


_LOGIN_PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Вход — Fiction Engine</title>
<style>body{background:#0f0f13;color:#e2e2f0;font-family:system-ui,sans-serif;display:flex;
align-items:center;justify-content:center;min-height:100vh;margin:0}form{background:#1a1a22;
border:1px solid #2e2e3e;border-radius:10px;padding:28px;width:min(320px,90vw)}input{width:100%;
box-sizing:border-box;padding:10px;margin:12px 0;background:#22222e;color:#e2e2f0;border:1px solid
#2e2e3e;border-radius:6px}button{width:100%;padding:10px;background:#7c6af7;color:#fff;border:0;
border-radius:6px;cursor:pointer}.err{color:#f87171;font-size:14px}</style></head><body>
<form method="POST"><div>Fiction Engine</div>
<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
<input type="password" name="password" placeholder="Пароль" autofocus required>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
<button type="submit">Войти</button></form></body></html>"""


def init_security(app: Flask) -> None:
    # FE_CSRF=0 — только для тестов движка, которые шлют POST без сессии
    app.config.setdefault("FE_CSRF", os.environ.get("FE_CSRF", "1") != "0")
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.route("/login", methods=["GET", "POST"])
    def login() -> ResponseReturnValue:
        error = ""
        if request.method == "POST":
            if _same(request.form.get("password"), password()):
                session.clear()
                session["fe_auth"] = True
                session.permanent = True
                nxt = request.args.get("next") or "/"
                # Только свой путь — не уводить на чужой сайт после входа
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
            error = "Неверный пароль"
        return render_template_string(_LOGIN_PAGE, error=error)

    @app.before_request
    def _guard() -> ResponseReturnValue | None:
        if _same(request.headers.get("X-FE-Token"), api_token()):
            return None                      # программа на этой машине
        if password() and not session.get("fe_auth") and request.endpoint not in ("login", "static"):
            if request.method in SAFE_METHODS and not request.path.startswith("/api/"):
                return redirect(url_for("login", next=request.full_path.rstrip("?")))
            return jsonify({"error": "нужен вход"}), 401
        if request.method not in SAFE_METHODS and app.config["FE_CSRF"]:
            sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
            if not _same(sent, session.get("csrf")):
                return jsonify({"error": "запрос отклонён: нет токена CSRF — обновите страницу"}), 403
        return None
