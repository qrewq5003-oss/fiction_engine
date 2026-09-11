#!/usr/bin/env python3
"""
Режиссёрская заметка: что записано под номером N, под ним же и читается.

Найдено прогоном 2026-09-12. Веб-слой не переводил номер: POST
/api/director_note/N/save клал заметку под ключ «после главы N», а
генерация главы N читает «после главы N-1». Пара save(N) → get(N) не
замыкалась никогда — заметка молча доставалась СЛЕДУЮЩЕЙ главе.

Видно это было прямо в интерфейсе: после сохранения generate.html
показывает тост «запусти генерацию главы N снова» и тут же зовёт
loadDirectorNote(N) — то есть пишет и читает один номер. Блок с
заметкой не появлялся, и объяснения этому не было.

Для кнопки «Продолжить главу» последствий два, и второе хуже первого:
инструкции критику и судье («это вторая часть, не снижать оценку за
отсутствие завязки») до них не доходили; а в промпт СЛЕДУЮЩЕЙ главы
попадало «КОНЕЦ ПЕРВОЙ ЧАСТИ… Продолжай отсюда» — указание продолжать
предыдущую главу вместо начала новой.

Проверяется свойство, а не случай: круг замыкается, и заметка доходит
до настоящего промпта. Любой будущий маршрут с тем же номером в двух
направлениях обязан вести себя так же.
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())
sys.modules["openai"].OpenAI = MagicMock()


@pytest.fixture
def client(monkeypatch):
    import engine.db_core as dbc
    monkeypatch.setattr(dbc, "DB_PATH", Path(tempfile.mkdtemp()) / "fe.db")
    from engine.db_core import init_db
    init_db()
    from web.app import app
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    return app.test_client()


@pytest.fixture
def project(client):
    from engine.db import create_project, set_active_project, save_chapter
    pid = create_project("Круг", "детектив")
    set_active_project(pid)
    save_chapter(pid, 1, "Текст первой главы. " * 60, "Глава 1")
    save_chapter(pid, 2, "Текст второй главы. " * 60, "Глава 2")
    return pid


# ─── Круг замыкается ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("num", [1, 2, 3, 7])
def test_note_saved_for_chapter_is_read_back_for_the_same_chapter(client, project, num):
    """Один номер в адресе — один смысл, в обе стороны."""
    note = f"ЗАМЕТКА-ДЛЯ-ГЛАВЫ-{num}"
    assert client.post(f"/api/director_note/{num}/save",
                       json={"note": note}).status_code == 200
    got = client.get(f"/api/director_note/{num}").get_json()["note"]
    assert got == note, f"сохранено под {num}, а под {num} не читается"


def test_note_does_not_leak_into_the_next_chapter(client, project):
    """
    Ровно тот дефект: заметка для главы 2 не должна оказаться у главы 3.
    Без этой проверки перевод номера можно «починить» сдвигом в другую
    сторону и снова разъехаться.
    """
    client.post("/api/director_note/2/save", json={"note": "ТОЛЬКО-ДЛЯ-ГЛАВЫ-2"})
    assert client.get("/api/director_note/3").get_json()["note"] is None
    assert client.get("/api/director_note/1").get_json()["note"] is None


# ─── Заметка доходит до промпта ───────────────────────────────────────────────

def test_saved_note_reaches_the_prompt_of_that_chapter(client, project):
    """
    Круг в API — половина дела. Заметка существует ради промпта, и
    проверяется она там же: собранным промптом настоящей главы.
    """
    from engine.db import get_project
    from engine.state_prompts import build_prompt
    mark = "МЕТКА-ПОПАЛА-В-ПРОМПТ"
    client.post("/api/director_note/3/save", json={"note": mark})
    prompt = build_prompt(project, 3, "quick", get_project(project))
    assert mark in prompt, "заметка не дошла до промпта своей главы"


def test_note_of_another_chapter_stays_out_of_the_prompt(client, project):
    from engine.db import get_project
    from engine.state_prompts import build_prompt
    client.post("/api/director_note/2/save", json={"note": "ЧУЖАЯ-ГЛАВЕ-3-МЕТКА"})
    prompt = build_prompt(project, 3, "quick", get_project(project))
    assert "ЧУЖАЯ-ГЛАВЕ-3-МЕТКА" not in prompt


# ─── Перезапись и границы ─────────────────────────────────────────────────────

def test_second_save_replaces_the_first(client, project):
    client.post("/api/director_note/2/save", json={"note": "первая"})
    client.post("/api/director_note/2/save", json={"note": "вторая"})
    assert client.get("/api/director_note/2").get_json()["note"] == "вторая"


def test_empty_note_is_refused(client, project):
    assert client.post("/api/director_note/2/save", json={"note": "  "}).status_code == 400


def test_chapter_zero_is_refused(client, project):
    """Главы начинаются с 1: ноль означал бы ключ -1 и тихую потерю."""
    assert client.post("/api/director_note/0/save", json={"note": "x"}).status_code == 400


def test_first_chapter_works(client, project):
    """Граница: для главы 1 ключ равен 0 — он допустим и читается."""
    client.post("/api/director_note/1/save", json={"note": "для первой"})
    assert client.get("/api/director_note/1").get_json()["note"] == "для первой"


# ─── Движок пишет по своему соглашению и не ломается ──────────────────────────

def test_engine_convention_is_untouched(client, project):
    """
    Слой БД остаётся прежним: save_director_note принимает «после главы».
    Так его зовёт engine/director_note.py, закончив главу N, — и эта
    заметка достаётся главе N+1. Перевод сделан в веб-слое, а не здесь.
    """
    from engine.db import save_director_note, get_director_note
    save_director_note(project, 5, "после пятой")
    assert get_director_note(project, 6) == "после пятой"
    assert get_director_note(project, 5) is None
