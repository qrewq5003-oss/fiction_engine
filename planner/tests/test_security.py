"""Вход по паролю и CSRF планировщика (web/security.py)."""

import re

import pytest


@pytest.fixture
def guarded(client):
    """Клиент с включённой проверкой CSRF."""
    import app as planner_app
    planner_app.app.config["PLANNER_CSRF"] = True
    yield client
    planner_app.app.config["PLANNER_CSRF"] = False


def _token(client) -> str:
    html = client.get("/login").get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _login(client, pw, nxt=""):
    return client.post("/login" + nxt, data={"password": pw, "csrf_token": _token(client)})


class TestLogin:
    def test_no_password_no_login(self, client):
        assert client.get("/projects").status_code == 200

    def test_page_redirects_to_login(self, client, monkeypatch):
        monkeypatch.setenv("PLANNER_PASSWORD", "секрет")
        resp = client.get("/board")
        assert resp.status_code == 302 and "/login" in resp.headers["Location"]

    def test_api_answers_401(self, client, monkeypatch):
        monkeypatch.setenv("PLANNER_PASSWORD", "секрет")
        assert client.get("/api/status").status_code == 401

    def test_wrong_password(self, client, monkeypatch):
        monkeypatch.setenv("PLANNER_PASSWORD", "секрет")
        assert "Неверный пароль" in _login(client, "не тот").get_data(as_text=True)
        assert "/login" in client.get("/projects").headers.get("Location", "")

    def test_right_password(self, client, monkeypatch):
        monkeypatch.setenv("PLANNER_PASSWORD", "секрет")
        assert _login(client, "секрет").status_code == 302
        assert client.get("/projects").status_code == 200

    def test_fe_password_used_when_own_not_set(self, client, monkeypatch):
        monkeypatch.setenv("FE_PASSWORD", "общий")
        assert "/login" in client.get("/projects").headers.get("Location", "")
        _login(client, "общий")
        assert client.get("/projects").status_code == 200

    def test_next_only_own_path(self, client, monkeypatch):
        monkeypatch.setenv("PLANNER_PASSWORD", "секрет")
        resp = _login(client, "секрет", "?next=//evil.example")
        assert resp.headers["Location"] in ("/", "http://localhost/")


class TestCsrf:
    def test_post_without_token_rejected(self, guarded):
        resp = guarded.post("/projects/new", json={"name": "П"})
        assert resp.status_code == 403

    def test_post_with_page_token(self, guarded):
        html = guarded.get("/projects").get_data(as_text=True)
        token = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
        resp = guarded.post("/projects/new", json={"name": "П"}, headers={"X-CSRF-Token": token})
        assert resp.status_code == 200 and resp.get_json().get("ok")


class TestHost:
    def test_network_needs_password(self, monkeypatch):
        from web.security import check_host
        monkeypatch.delenv("PLANNER_PASSWORD", raising=False)
        monkeypatch.delenv("FE_PASSWORD", raising=False)
        assert check_host("0.0.0.0")
        assert check_host("127.0.0.1") is None
        monkeypatch.setenv("FE_PASSWORD", "общий")
        assert check_host("0.0.0.0") is None


def test_session_cookie_not_shared_with_fe():
    """Fiction Engine на том же 127.0.0.1: общий cookie «session» затирал его сессию."""
    from app import app
    assert app.config["SESSION_COOKIE_NAME"] == "planner_session"


def test_foreign_host_is_refused(client, monkeypatch):
    """DNS rebinding: чужое имя в Host — отказ (разбор 21.10)."""
    monkeypatch.delenv("PLANNER_TRUSTED_HOSTS", raising=False)
    monkeypatch.delenv("PLANNER_HOST", raising=False)
    assert client.get("/projects", headers={"Host": "evil.example:5001"}).status_code == 403
    assert client.get("/projects", headers={"Host": "127.0.0.1:5001"}).status_code == 200
