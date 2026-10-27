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
            "token": self.headers.get("X-FE-Token"),
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

        # Импорт связывает проект; описание остаётся авторским — копия State
        # в нём устаревала с первой же главы
        from engine.db import get_project
        p = get_project(project_id)
        assert p["fe_project_id"] == 7
        assert p["description"] == "описание"

    def test_import_drops_old_state_copy(self, client, project_id, fake_fe):
        from engine.db import get_project, update_project
        update_project(project_id, "Тестовый", "детектив", "СОСТОЯНИЕ МИРА:\nстарое")
        fake_fe.responses["/api/project/context"] = (200, {"project": {"id": 7, "genre": "хоррор"}})
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        assert client.post("/api/fe/import/7").status_code == 200
        assert get_project(project_id)["description"] == ""

    def test_ai_assist_knows_book_and_neighbours(self, client, project_id, fake_fe):
        from engine.db import create_scene, get_acts, set_fe_project, update_scene
        act = get_acts(project_id)[0]["id"]
        a, b, c = (create_scene(project_id, act) for _ in range(3))
        update_scene(a, {"title": "Обвал", "what_happens": "подвал рушится"})
        update_scene(c, {"title": "Больница"})
        set_fe_project(project_id, 7)
        fake_fe.responses["/api/project/context"] = (200, {
            "last_chapter": 1, "story_so_far": "ПАМЯТЬ СЕРИИ: Томаш погиб",
            "plot_matrix": "ГДЕ_СЕЙЧАС: больница", "global_state": "Лукаш ранен"})
        fake_fe.responses["/api/inline_call"] = (200, {"ok": True, "result": "x"})
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        client.post("/api/ai/assist", json={"scene_id": b, "action": "next",
                                            "model": "deepseek_direct::deepseek-chat",
                                            "scene": {"title": "Скорая"}})
        prompt = next(r for r in fake_fe.received if r["path"] == "/api/inline_call")["body"]["prompt"]
        assert "Томаш погиб" in prompt and "ГДЕ_СЕЙЧАС" in prompt and "написано глав: 1" in prompt
        assert "СЦЕНА ДО: Обвал — подвал рушится" in prompt and "СЦЕНА ПОСЛЕ: Больница" in prompt
        assert prompt.index("=== ЭТА СЦЕНА ===") > prompt.index("=== КНИГА")

    def test_ai_assist_sees_day_and_hold_from_card(self, client, project_id, fake_fe):
        """День и «Пока не раскрывать» карточки — в задании помощи, даже если окно их не
        прислало: приписка просит «не переносить время», а времени модель не видела (разбор 26.10)."""
        from engine.db import create_scene, update_scene
        sid = create_scene(project_id)
        update_scene(sid, {"title": "Причал", "day": "пятница", "time_of_day": "Утро",
                           "hold": "кто звонил в 2:14"})
        fake_fe.responses["/api/inline_call"] = (200, {"ok": True, "result": "x"})
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        client.post("/api/ai/assist", json={"scene_id": sid, "action": "rewrite",
                                            "model": "deepseek_direct::deepseek-chat",
                                            "scene": {"title": "Причал"}})
        prompt = next(r for r in fake_fe.received if r["path"] == "/api/inline_call")["body"]["prompt"]
        assert "Когда: пятница, утро" in prompt and "Пока не раскрывать: кто звонил в 2:14" in prompt
        assert "толкований не пиши" in prompt

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

    def test_unlinked_project_does_not_send_to_open_fe_book(self, client, project_id, fake_fe):
        """Проект без связи с книгой FE план не отправляет: раньше он уходил в книгу,
        открытую в FE сейчас (разбор 21.10). Без номера главы — 400, а не глава 1."""
        from engine.db import create_scene
        sid = create_scene(project_id)
        with client.session_transaction() as sess:
            sess["project_id"] = project_id

        data = json.loads(client.post("/api/export/send", json={"scene_ids": [sid], "chapter_num": 4}).data)
        assert data["sent"] is False and "не связан" in data["error"] and data["prompt"]
        assert not [r for r in fake_fe.received if "director_note" in r["path"]]
        assert client.post("/api/export/send", json={"scene_ids": [sid]}).status_code == 400


class TestCallsCarryToken:
    """
    Fiction Engine без сессии пускает только с X-FE-Token
    (fiction_engine/web/security.py) — каждый запрос планировщика его несёт.
    """

    def test_every_call_has_token(self, client, project_id, fake_fe, monkeypatch):
        monkeypatch.setenv("FE_PASSWORD", "пароль-fe")
        from engine.db import create_scene
        sid = create_scene(project_id)
        fake_fe.responses["/api/inline_call"] = (200, {"ok": True, "result": "x"})
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
            sess["planner_auth"] = True       # FE_PASSWORD — и пароль планировщика
        client.get("/api/status")
        client.get("/api/fe/projects")
        client.post("/api/fe/import/7")
        client.post("/api/ai/assist", json={"scene_id": sid, "action": "develop",
                                            "model": "deepseek_direct::deepseek-chat"})
        client.post("/api/export/send", json={"scene_ids": [sid], "chapter_num": 4})
        # Шесть: после импорта проект связан, и AI-помощь сперва берёт у FE книгу
        assert len(fake_fe.received) == 6
        import hashlib
        want = hashlib.sha256("fiction-engine-api:пароль-fe".encode()).hexdigest()
        assert all(r["token"] == want for r in fake_fe.received), fake_fe.received

    def test_token_file_when_no_password(self, tmp_path, monkeypatch):
        from web.blueprints.api_bp import _fe_headers
        monkeypatch.delenv("FE_PASSWORD", raising=False)
        monkeypatch.setenv("FE_API_TOKEN_FILE", str(tmp_path / "api_token"))
        assert _fe_headers() == {}
        (tmp_path / "api_token").write_text("токен-файла\n")
        assert _fe_headers() == {"X-FE-Token": "токен-файла"}


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

    def test_export_reports_not_sent_when_fe_down(self, client, project_id, monkeypatch):
        # Проект связан с книгой: иначе тест проверял ветку «не связан», а ветка
        # «FE недоступен» не проверялась ни разу (разбор планировщика 21.10)
        from engine.db import create_scene, set_fe_project
        set_fe_project(project_id, 7)
        sid = create_scene(project_id)
        monkeypatch.setenv("FE_URL", "http://127.0.0.1:1")
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        data = json.loads(client.post("/api/export/send",
                                      json={"scene_ids": [sid], "chapter_num": 1}).data)
        assert data["sent"] is False and "недоступен" in data["error"]
        assert data["prompt"], "промпт для ручного копирования обязан вернуться"


class TestSeriesBibleLink:
    """План главы и библия серии идут в связанный проект Fiction Engine."""

    def _link(self, client, project_id, fake_fe, fe_pid=7):
        fake_fe.responses["/api/project/context"] = (200, {"project": {"id": fe_pid, "genre": "детектив"}})
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        assert client.post(f"/api/fe/import/{fe_pid}").status_code == 200

    def test_import_remembers_fe_project(self, client, project_id, fake_fe):
        from engine.db import get_project
        self._link(client, project_id, fake_fe)
        assert get_project(project_id)["fe_project_id"] == 7

    def test_export_sends_plan_with_scene_facts(self, client, project_id, fake_fe):
        from engine.db import create_scene, update_scene
        self._link(client, project_id, fake_fe)
        sid = create_scene(project_id)
        update_scene(sid, {"title": "Допрос", "location": "контора на Литейном", "time_of_day": "вечер",
                           "characters": "Вера, Лаптев"})
        fake_fe.responses["/api/chapter_plan/4/save"] = (200, {"ok": True, "facts": 3})
        resp = client.post("/api/export/send", json={"scene_ids": [sid], "chapter_num": 4})
        data = json.loads(resp.data)
        assert data["sent"] is True and data["facts"] == 3
        req = next(r for r in fake_fe.received if r["path"] == "/api/chapter_plan/4/save")
        assert req["body"]["pid"] == 7 and "Допрос" in req["body"]["note"]
        assert {(f["attr"], f["value"]) for f in req["body"]["facts"]} == {
            ("место", "контора на Литейном"), ("время", "вечер"), ("кто", "Вера, Лаптев")}

    def test_export_sends_board_ahead_for_run_ahead_guard(self, client, project_id, fake_fe):
        """Сцены доски после плана главы — в FE полем future (сторожу забеганий), без заметок сцены."""
        from engine.db import create_scene, get_acts, set_chapter_scenes, update_scene
        self._link(client, project_id, fake_fe)
        a1, a2 = (a["id"] for a in get_acts(project_id)[:2])
        past, now, nxt, later, empty = (create_scene(project_id, a) for a in (a1, a1, a1, a2, a2))
        update_scene(past, {"title": "Пальто", "what_happens": "Варя находит пальто"})
        set_chapter_scenes(project_id, 3, [past])
        update_scene(now, {"title": "Кофейня", "what_happens": "Гоша врёт про 16-е"})
        update_scene(nxt, {"title": "Признание", "what_happens": "Гоша признаётся, что фондом занимался Марат",
                           "hold": "Марата прямо не обвинять", "notes": "черновик: может, в 15-ю?"})
        update_scene(later, {"title": "Финал", "what_happens": "Марат задержан"})
        fake_fe.responses["/api/chapter_plan/4/save"] = (200, {"ok": True, "facts": 0})
        client.post("/api/export/send", json={"scene_ids": [now], "chapter_num": 4})
        req = next(r for r in fake_fe.received if r["path"] == "/api/chapter_plan/4/save")
        future = req["body"]["future"]
        assert future.splitlines() == [
            "- дальше «Признание»: Гоша признаётся, что фондом занимался Марат (пока не раскрывать: Марата прямо не обвинять)",
            "- дальше «Финал»: Марат задержан"]
        assert "черновик" not in future and "Пальто" not in future and "Кофейня" not in future

    def test_bible_proxy_uses_linked_pid(self, client, project_id, fake_fe):
        self._link(client, project_id, fake_fe)
        fake_fe.responses["/api/bible"] = (200, {"facts": [], "conflicts": [], "history": []})
        assert json.loads(client.get("/api/fe/bible").data)["facts"] == []
        assert any(r["path"] == "/api/bible?pid=7" for r in fake_fe.received)
        client.post("/api/fe/bible/set", json={"kind": "место", "name": "квартира", "attr": "этаж",
                                               "value": "второй", "reason": "правка"})
        req = next(r for r in fake_fe.received if r["path"] == "/api/bible/set")
        assert req["body"]["pid"] == 7 and req["body"]["value"] == "второй"

    def test_unlinked_project_is_told_to_import(self, client, project_id):
        with client.session_transaction() as sess:
            sess["project_id"] = project_id
        r = client.get("/api/fe/bible")
        assert r.status_code == 400 and "импортируй" in json.loads(r.data)["error"]
        assert "не связан" in client.get("/bible").get_data(as_text=True)
