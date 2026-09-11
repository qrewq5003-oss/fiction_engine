"""
Обращения к Fiction Engine ИСПОЛНЯЮТСЯ, а не только присутствуют в коде.

Поводом стала дыра, которую не поймали 55 зелёных тестов: хелпер
`_fe_base_url()` вызывался в шести местах и не был определён вовсе.
Все обращения падали с NameError, и четыре из пяти маскировались под
«Fiction Engine не запущен» — NameError тоже Exception, а вокруг стоял
широкий перехват.

Прежние проверки не могли этого увидеть в принципе:
  • тест статуса ждал `fe_server: false` — сломанный код даёт ровно то же,
    он не отличает «FE не поднят» от «код не работает»;
  • контрактный тест на стороне FE вычитывал адреса регуляркой по
    исходникам: он сверяет строковые литералы с маршрутами, но ни разу
    не исполняет код планировщика.

Здесь поднимается настоящий HTTP-сервер-заглушка, FE_URL указывает на
него, и проверяется, что запрос ДОШЁЛ: метод, путь, тело.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


class _Recorder(BaseHTTPRequestHandler):
    """Записывает пришедшие запросы и отвечает заготовленным."""

    received: list = []
    responses: dict = {}

    def _reply(self, method: str) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        _Recorder.received.append({
            "method": method,
            "path": self.path,
            "body": json.loads(body) if body else None,
        })
        status, payload = _Recorder.responses.get(
            self.path.split("?")[0], (200, {"ok": True}))
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply("GET")

    def do_POST(self):
        self._reply("POST")

    def log_message(self, *args):
        pass                      # не засорять вывод тестов


@pytest.fixture
def fake_fe(monkeypatch):
    """Заглушка Fiction Engine на случайном порту; FE_URL смотрит на неё."""
    _Recorder.received = []
    _Recorder.responses = {}
    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    monkeypatch.setenv("FE_URL", f"http://{host}:{port}")
    yield _Recorder
    server.shutdown()
    server.server_close()


class TestBaseUrl:
    def test_helper_exists_and_reads_env(self, monkeypatch):
        """Именно этой проверки не хватало: функция должна существовать."""
        from web.blueprints.api_bp import _fe_base_url
        monkeypatch.setenv("FE_URL", "http://example.test:9000/")
        assert _fe_base_url() == "http://example.test:9000"

    def test_default_is_loopback(self, monkeypatch):
        from web.blueprints.api_bp import _fe_base_url
        monkeypatch.delenv("FE_URL", raising=False)
        assert _fe_base_url() == "http://127.0.0.1:5000"


class TestCallsReachFe:
    """Каждое обращение к FE должно реально уходить по сети."""

    def test_status_queries_keys(self, client, fake_fe):
        fake_fe.responses["/api/keys/status"] = (200, {"anthropic_direct": "sk-…"})
        data = json.loads(client.get("/api/status").data)
        paths = [r["path"] for r in fake_fe.received]
        assert "/api/keys/status" in paths, f"запрос не ушёл: {paths}"
        assert data["fe_server"] is True
        assert data["keys"]["anthropic"] is True

    def test_fe_projects_proxied(self, client, fake_fe):
        fake_fe.responses["/api/projects/list"] = (
            200, {"projects": [{"id": 1, "name": "Серия", "genre": "детектив"}]})
        data = json.loads(client.get("/api/fe/projects").data)
        assert "/api/projects/list" in [r["path"] for r in fake_fe.received]
        assert data["projects"][0]["name"] == "Серия"

    def test_import_requests_specific_project(self, client, project_id, fake_fe):
        fake_fe.responses["/api/project/context"] = (200, {
            "project": {"id": 7, "name": "Серия FE", "genre": "хоррор"},
            "global_state": "## ПЕРСОНАЖИ\nМарк жив",
            "plot_matrix": "СТАТУС: завязка",
            "active_promises": ["найти убийцу"],
        })
        with client.session_transaction() as sess:
            sess["project_id"] = project_id

        resp = client.post("/api/fe/import/7")
        assert resp.status_code == 200, resp.data
        req = next(r for r in fake_fe.received if r["path"].startswith("/api/project/context"))
        assert "pid=7" in req["path"], f"номер проекта не передан: {req['path']}"

        from engine.db import get_project
        assert "найти убийцу" in get_project(project_id)["description"]

    def test_ai_assist_calls_inline(self, client, project_id, fake_fe):
        from engine.db import create_scene
        sid = create_scene(project_id)
        fake_fe.responses["/api/inline_call"] = (200, {"ok": True, "result": "развитие сцены"})
        with client.session_transaction() as sess:
            sess["project_id"] = project_id

        resp = client.post("/api/ai/assist", json={
            "scene_id": sid, "action": "develop", "model": "deepseek_direct::deepseek-chat"})
        assert resp.status_code == 200, resp.data
        req = next(r for r in fake_fe.received if r["path"] == "/api/inline_call")
        assert req["method"] == "POST"
        assert req["body"]["prompt"], "промпт не передан"
        assert json.loads(resp.data)["result"] == "развитие сцены"

    def test_export_sends_note_with_chapter(self, client, project_id, fake_fe):
        from engine.db import create_scene
        sid = create_scene(project_id)
        with client.session_transaction() as sess:
            sess["project_id"] = project_id

        resp = client.post("/api/export/send",
                           json={"scene_ids": [sid], "chapter_num": 4})
        assert resp.status_code == 200
        assert json.loads(resp.data)["sent"] is True, "экспорт молча не дошёл"
        req = next(r for r in fake_fe.received if "director_note" in r["path"])
        assert req["path"] == "/api/director_note/4/save"
        assert req["body"]["note"], "текст плана не передан"


class TestFailuresAreDistinguishable:
    """
    Отказ FE и поломка кода не должны выглядеть одинаково.

    Прежде любой NameError внутри обработчика превращался в
    «Fiction Engine недоступен», и отличить одно от другого было нельзя.
    """

    def test_fe_refusal_is_not_reported_as_downtime(self, client, project_id, fake_fe):
        """
        «Нет API ключа» — это отказ FE, а не его отсутствие. Раньше любой
        ответ с кодом ошибки схлопывался в «Fiction Engine недоступен»,
        и автор видел не ту причину.
        """
        from engine.db import create_scene
        sid = create_scene(project_id)
        fake_fe.responses["/api/inline_call"] = (
            400, {"error": "Нет API ключа для deepseek_direct"})
        with client.session_transaction() as sess:
            sess["project_id"] = project_id

        resp = client.post("/api/ai/assist", json={
            "scene_id": sid, "action": "develop",
            "model": "deepseek_direct::deepseek-chat"})
        assert resp.status_code == 400, "отказ подменён кодом недоступности"
        text = json.loads(resp.data)["error"]
        assert "ключ" in text.lower(), text
        assert "недоступен" not in text.lower(), text

    def test_model_hint_matches_fe_provider_names(self):
        """
        Подсказка в интерфейсе должна называть провайдера так же, как FE.
        Было «deepseek::…», а FE ищет ключ по «deepseek_direct» — автор
        вводил показанное и получал «Нет API ключа».
        """
        from pathlib import Path as _P
        html = (_P(__file__).resolve().parents[1] / "web" / "templates" / "scene.html")
        text = html.read_text(encoding="utf-8")
        known = ("anthropic_direct", "openai_direct", "gemini_direct",
                 "deepseek_direct", "nano_gpt")
        import re
        for hint in re.findall(r'placeholder="([\w\-]+::[^"]+)"', text):
            provider = hint.split("::")[0]
            assert provider in known, f"подсказка {hint!r}: FE не знает провайдера {provider!r}"

    def test_status_without_fe(self, client, monkeypatch):
        monkeypatch.setenv("FE_URL", "http://127.0.0.1:1")   # заведомо закрыт
        data = json.loads(client.get("/api/status").data)
        assert data["fe_server"] is False and data["has_keys"] is False

    def test_export_reports_not_sent_when_fe_down(self, client, project_id, monkeypatch):
        from engine.db import create_scene
        sid = create_scene(project_id)
        monkeypatch.setenv("FE_URL", "http://127.0.0.1:1")
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        data = json.loads(client.post("/api/export/send",
                                      json={"scene_ids": [sid], "chapter_num": 1}).data)
        assert data["sent"] is False
        assert data["prompt"], "промпт для ручного копирования обязан вернуться"
