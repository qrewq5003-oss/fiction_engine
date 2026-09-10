#!/usr/bin/env python3
"""
test_routes_smoke.py — каждая GET-страница отвечает, а не падает в 500.

Зачем отдельный файл. Все страницы, требующие проекта, начинались с

    if not current:
        return redirect(url_for("main.index"))

но блупринта «main» в Fiction Engine нет: главная объявлена прямо на app
(web/app.py: @app.route("/")), её endpoint — «index». Имя «main.index»
приехало из планировщика, где такой блупринт есть. В результате
/generate, /pipeline, /state и ещё десяток страниц отдавали 500 вместо
редиректа — ровно то, что видел бы пользователь при первом запуске,
когда проекта ещё нет.

Ни один из 858 тестов этого не ловил: они дёргают функции и API-роуты,
а не обходят страницы. Этот файл обходит.
"""

import sys
import tempfile
import pathlib
from unittest.mock import MagicMock

import pytest

for _mod in ["openai", "anthropic"]:
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


def _make_client(with_project: bool):
    import engine.db_core as dbc
    dbc.DB_PATH = pathlib.Path(tempfile.mkdtemp()) / "smoke.db"
    from engine.db_core import init_db
    init_db()

    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "smoke-secret"

    if with_project:
        from engine.db import create_project, set_active_project
        set_active_project(create_project("Смоук", "детектив"))

    import logging
    logging.disable(logging.CRITICAL)
    return app, app.test_client()


def _get_pages(app):
    """Все GET-маршруты без параметров, кроме /api/* и служебных."""
    pages = []
    for rule in app.url_map.iter_rules():
        if "GET" not in (rule.methods or set()):
            continue
        path = str(rule)
        if rule.arguments or path.startswith(("/api/", "/static")):
            continue
        pages.append(path)
    return sorted(set(pages))


@pytest.mark.parametrize("with_project", [False, True],
                         ids=["без проекта", "с проектом"])
def test_no_page_returns_500(with_project):
    app, client = _make_client(with_project)
    broken = []
    for path in _get_pages(app):
        resp = client.get(path, follow_redirects=False)
        if resp.status_code >= 500:
            broken.append((path, resp.status_code))
    assert not broken, f"страницы падают: {broken}"


def test_redirect_target_resolves_without_project():
    """
    Страница, требующая проекта, обязана вести на существующий endpoint.
    Именно здесь ломался url_for («main.index»): BuildError → 500.
    """
    app, client = _make_client(with_project=False)
    resp = client.get("/generate", follow_redirects=False)
    assert resp.status_code in (301, 302), resp.status_code
    assert resp.headers["Location"].endswith("/")

    followed = client.get("/generate", follow_redirects=True)
    assert followed.status_code == 200


def test_index_endpoint_is_not_blueprint_scoped():
    """Главная объявлена на app, значит её endpoint — «index», без префикса."""
    app, _ = _make_client(with_project=False)
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    assert "index" in endpoints
    assert "main.index" not in endpoints
