"""
Вход по паролю и защита от CSRF (ROADMAP, этап 5.1 и 5.3).
"""
import re

import pytest


@pytest.fixture
def app_csrf(monkeypatch):
    from web.app import app
    monkeypatch.setitem(app.config, "FE_CSRF", True)
    monkeypatch.delenv("FE_PASSWORD", raising=False)
    return app


def _token(client) -> str:
    html = client.get("/").get_data(as_text=True)
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


def test_post_without_token_rejected(app_csrf):
    c = app_csrf.test_client()
    r = c.post("/api/keys/save", json={"provider": "nano_gpt", "key": "sk-evil-000000000000"})
    assert r.status_code == 403
    from engine.db_settings import get_api_key
    assert get_api_key("nano_gpt") is None


def test_post_with_header_or_form_token_passes(app_csrf):
    c = app_csrf.test_client()
    tok = _token(c)
    r = c.post("/api/keys/save", json={"provider": "nano_gpt", "key": "sk-good-000000000000"},
               headers={"X-CSRF-Token": tok})
    assert r.status_code == 200
    r = c.post("/project/new", data={"name": "Проект", "genre": "детектив", "csrf_token": tok})
    assert r.status_code in (200, 302)


def test_token_from_other_session_rejected(app_csrf):
    alien = _token(app_csrf.test_client())
    c = app_csrf.test_client()
    _token(c)
    r = c.post("/api/keys/delete", json={"provider": "nano_gpt"}, headers={"X-CSRF-Token": alien})
    assert r.status_code == 403


def test_every_post_form_gets_token():
    """Формы в шаблонах получают поле csrf_token скриптом base.html."""
    from pathlib import Path
    base = (Path(__file__).parent.parent / "web" / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'name="csrf-token"' in base and "X-CSRF-Token" in base and "'submit'" in base


def test_password_required_when_set(app_csrf, monkeypatch):
    monkeypatch.setenv("FE_PASSWORD", "верный-пароль")
    c = app_csrf.test_client()
    r = c.get("/")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert c.get("/api/keys/status").status_code == 401
    page = c.get("/login").get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
    assert c.post("/login", data={"password": "не тот", "csrf_token": tok}).status_code == 200
    assert c.get("/").status_code == 302
    r = c.post("/login?next=//evil.example", data={"password": "верный-пароль", "csrf_token": tok})
    assert r.status_code == 302 and r.headers["Location"] == "/"
    assert c.get("/").status_code == 200


def test_program_token_skips_session(app_csrf, monkeypatch):
    from web.security import api_token
    c = app_csrf.test_client()
    r = c.post("/api/keys/save", json={"provider": "nano_gpt", "key": "sk-plan-000000000000"},
               headers={"X-FE-Token": api_token()})
    assert r.status_code == 200
    assert c.post("/api/keys/save", json={"provider": "nano_gpt", "key": "x" * 20},
                  headers={"X-FE-Token": "чужой"}).status_code == 403
    monkeypatch.setenv("FE_PASSWORD", "пароль-сервера")
    import hashlib
    want = hashlib.sha256("fiction-engine-api:пароль-сервера".encode()).hexdigest()
    assert api_token() == want                 # так же считает планировщик
    assert c.get("/api/keys/status", headers={"X-FE-Token": want}).status_code == 200


def test_refuses_network_host_without_password(monkeypatch):
    from web.security import check_host
    monkeypatch.delenv("FE_PASSWORD", raising=False)
    assert check_host("127.0.0.1") is None and check_host("localhost") is None
    assert "FE_PASSWORD" in check_host("0.0.0.0")
    assert check_host("100.64.1.2")             # адрес Tailscale — тоже сеть
    monkeypatch.setenv("FE_PASSWORD", "x")
    assert check_host("0.0.0.0") is None


def test_main_exits_without_password(monkeypatch):
    import web.app as wa
    monkeypatch.setenv("FE_HOST", "0.0.0.0")
    monkeypatch.delenv("FE_PASSWORD", raising=False)
    monkeypatch.setattr(wa.app, "run", lambda **k: pytest.fail("сервер поднялся без пароля"))
    with pytest.raises(SystemExit) as e:
        wa.main()
    assert "FE_PASSWORD" in str(e.value)


def test_session_cookie_not_shared_with_planner():
    """Планировщик на том же 127.0.0.1: общий cookie «session» затирал сессию FE."""
    from pathlib import Path
    from web.app import app
    planner = (Path(__file__).resolve().parents[2] / "planner" / "web" / "security.py").read_text(encoding="utf-8")
    m = re.search(r'SESSION_COOKIE_NAME"\] = "(\w+)"', planner)
    assert m and app.config["SESSION_COOKIE_NAME"] not in ("session", m.group(1))
