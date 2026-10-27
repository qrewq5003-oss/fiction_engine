"""Импорт главы на доску: разбивка текста на сцены, порядок глав в акте, связи для графа."""
import json

import pytest

from tests.test_fe_calls import fake_fe  # noqa: F401 — фикстура заглушки FE

ANSWER = {
    "scenes": [
        {"title": "Причал", "location": "пристань", "day": "пятница", "time_of_day": "утро",
         "characters": "Вера, паромщик", "what_happens": "Вера находит записку.", "emotion": "тревога"},
        {"title": "Каюта", "location": "паром", "time_of_day": "сумерки",
         "characters": "Вера", "what_happens": "Вера читает записку.", "emotion": "страх"},
        {"title": "", "what_happens": ""},
    ],
    "links": [
        {"from": 1, "to": 2, "type": "cause", "label": "записка"},
        {"from": "S{old}", "to": 1, "type": "cause", "label": "звонок"},
        {"from": 1, "to": 1, "type": "cause"},                 # на себя
        {"from": 2, "to": 7, "type": "cause"},                 # нет такой сцены
        {"from": "S99999", "to": 1, "type": "cause"},          # не с этой доски
        {"from": 1, "to": 2, "type": "дружба"},                # нет такого типа
    ],
}


def _answer(old_id: int) -> str:
    return "Вот разметка:\n```json\n" + json.dumps(ANSWER, ensure_ascii=False).replace("{old}", str(old_id)) + "\n```"


def test_parse_keeps_only_what_is_recognised():
    from engine.chapter_import import parse
    got = parse(_answer(5), {5})
    assert [s["title"] for s in got["scenes"]] == ["Причал", "Каюта"]
    assert got["scenes"][0]["time_of_day"] == "Утро"
    assert got["scenes"][1]["time_of_day"] == ""        # «сумерки» нет в списке времени суток
    assert [(l["from"], l["to"]) for l in got["links"]] == [(["new", 0], ["new", 1]), (["board", 5], ["new", 0])]


def test_parse_rejects_garbage():
    from engine.chapter_import import parse
    with pytest.raises(ValueError):
        parse("не знаю", set())
    with pytest.raises(ValueError):
        parse('{"scenes": []}', set())


def test_board_block_only_earlier_chapters():
    from engine.chapter_import import board_block
    b = board_block([{"id": 1, "chapter_num": 1, "title": "Пролог"}, {"id": 2, "chapter_num": 3, "title": "Позже"},
                     {"id": 3, "chapter_num": None, "title": "План"}], 2)
    assert "S1" in b and "S2" not in b and "S3" not in b


def test_insert_position_follows_chapters():
    from engine.chapter_import import insert_position
    act = [{"chapter_num": 1}, {"chapter_num": None}, {"chapter_num": 4}]
    assert insert_position(act, 2) == 1
    assert insert_position(act, 5) == 3
    assert insert_position([{"chapter_num": 4}], 2) == 0
    assert insert_position([{"chapter_num": None}], 2) == 1


def test_import_chapter_order_and_links(project_id):
    from engine.db import get_acts, get_links, get_scenes, import_chapter
    act = get_acts(project_id)[0]["id"]
    ch1 = import_chapter(project_id, act, 1, [{"title": "Пролог"}], [])
    ch3 = import_chapter(project_id, act, 3, [{"title": "Финал"}], [])
    ids = import_chapter(project_id, act, 2, [{"title": "А", "time_of_day": "Ночь"}, {"title": "Б"}],
                         [{"from": ["new", 0], "to": ["new", 1], "type": "cause", "label": "x"},
                          {"from": ["board", ch1[0]], "to": ["new", 0], "type": "mirror", "label": ""},
                          {"from": ["board", 99999], "to": ["new", 0], "type": "cause", "label": ""}])
    seq = sorted((s for s in get_scenes(project_id) if s["act_id"] == act), key=lambda s: s["position"])
    assert [s["title"] for s in seq] == ["Пролог", "А", "Б", "Финал"]
    assert {s["chapter_num"] for s in seq if s["id"] in ids} == {2}
    assert seq[1]["time_of_day"] == "Ночь"
    assert {(l["from_id"], l["to_id"], l["link_type"]) for l in get_links(project_id)} == {
        (ids[0], ids[1], "cause"), (ch1[0], ids[0], "mirror")}
    assert ch3


def test_split_takes_chapter_from_linked_fe_and_saves_nothing(client, project_id, fake_fe):  # noqa: F811
    from engine.db import create_scene, get_scenes, set_fe_project, update_scene
    set_fe_project(project_id, 7)
    old = create_scene(project_id)
    update_scene(old, {"title": "Звонок"})
    from engine.db import set_chapter_scenes
    set_chapter_scenes(project_id, 1, [old])
    fake_fe.responses["/api/chapter/2/text"] = (200, {"text": "Вера пришла на пристань. " * 50})
    fake_fe.responses["/api/inline_call"] = (200, {"ok": True, "result": _answer(old)})
    with client.session_transaction() as sess:
        sess["project_id"] = project_id
    r = client.post("/api/chapter_import/split", json={"chapter_num": 2, "model": "nano_gpt::x"}).get_json()
    assert r["ok"] and len(r["scenes"]) == 2 and r["already"] == 0
    assert r["links"][1]["from_title"] == "Звонок"
    got = {x["path"].split("?")[0]: x for x in fake_fe.received}
    assert "pid=7" in got["/api/chapter/2/text"]["path"]
    prompt = got["/api/inline_call"]["body"]["prompt"]
    assert f"S{old} (гл.1): Звонок" in prompt and "Вера пришла на пристань" in prompt
    assert len(get_scenes(project_id)) == 1                     # предложение, не запись


def test_split_needs_text_without_link(client, project_id):
    with client.session_transaction() as sess:
        sess["project_id"] = project_id
    r = client.post("/api/chapter_import/split", json={"chapter_num": 1, "model": "m"})
    assert r.status_code == 400 and "вставь текст" in r.get_json()["error"]


def test_save_route(client, project_id):
    from engine.db import create_project, get_acts, get_links, get_scenes
    with client.session_transaction() as sess:
        sess["project_id"] = project_id
    act = get_acts(project_id)[0]["id"]
    r = client.post("/api/chapter_import/save", json={
        "chapter_num": 4, "act_id": act,
        "scenes": [{"title": "А", "notes": "не из полей разбивки", "project_id": 999}, {"title": "Б"}],
        "links": [{"from": ["new", 0], "to": ["new", 1], "type": "cause"}, {"from": "мусор"}]}).get_json()
    assert r["ok"] and len(r["ids"]) == 2
    sc = {s["title"]: s for s in get_scenes(project_id)}
    assert sc["А"]["chapter_num"] == 4 and sc["А"]["notes"] == "" and sc["А"]["project_id"] == project_id
    assert len(get_links(project_id)) == 1
    # Чужой акт — отказ
    other_act = get_acts(create_project("Чужой"))[0]["id"]
    assert client.post("/api/chapter_import/save", json={
        "chapter_num": 1, "act_id": other_act, "scenes": [{"title": "x"}]}).status_code in (403, 404)


def test_board_has_import_button(client, project_id):
    with client.session_transaction() as sess:
        sess["project_id"] = project_id
    html = client.get("/board").get_data(as_text=True)
    assert "Импорт главы" in html and "const BOARD_CHAPTERS = []" in html


def test_prompt_asks_facts_and_shows_board_link():
    """«Что происходит» — фактами, без толкований (карточка уходит писателю планом);
    образец связи — со сцены доски, а не «1 → 2» соседних сцен (разбор формулировок 26.10)."""
    from engine.chapter_import import PROMPT
    assert "без толкований" in PROMPT and '"from": "S<id>"' in PROMPT
    assert '"from": 1, "to": 2' not in PROMPT and "противоречит" not in PROMPT
