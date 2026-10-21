"""
Библия серии: места, вещи, время с историей; противоречие не перезаписывает.
"""
import json


def _e(name, attr, value, changed="", kind="место"):
    return {"kind": kind, "name": name, "attr": attr, "value": value, "changed": changed}


def test_record_history_and_conflict(project_id):
    from engine.series_bible import conflicts, current, history, record
    r = record(project_id, [_e("квартира Ларионовой", "этаж", "второй")], 3)
    assert len(r["added"]) == 1
    # То же значение — ничего
    assert record(project_id, [_e("Квартира Ларионовой", "Этаж", "второй")], 4) == \
        {"added": [], "changed": [], "conflicts": []}
    # Другое значение без события — противоречие, текущее не меняется
    r = record(project_id, [_e("квартира Ларионовой", "этаж", "третий")], 5)
    assert r["conflicts"][0]["was"] == "второй"
    assert [x["value"] for x in current(project_id)] == ["второй"]
    # Событие сюжета — законное изменение, прежняя запись в истории
    r = record(project_id, [_e("квартира Ларионовой", "этаж", "пятый", "переехала к сестре")], 7)
    assert r["changed"][0]["was"] == "второй"
    assert [x["value"] for x in current(project_id)] == ["пятый"]
    vals = [(h["chapter_num"], h["value"], h["status"]) for h in history(project_id, "квартира ларионовой", "этаж")]
    assert vals == [(3, "второй", "введено"), (5, "третий", "противоречие"), (7, "пятый", "изменено")]
    assert len(conflicts(project_id, 5)) == 1


def test_block_puts_focus_first_and_marks_change(project_id):
    from engine.series_bible import author_set, bible_block, record
    record(project_id, [_e("квартира Ларионовой", "этаж", "второй"),
                        _e("шарф Лаптева", "цвет", "красно-чёрный", kind="вещь")], 3)
    author_set(project_id, "вещь", "шарф Лаптева", "где", "у Веры", 6, "Вера изъяла его")
    b = bible_block(project_id, "Вера приходит к Лаптеву, на нём шарф")
    lines = b.splitlines()
    assert lines[0].startswith("БИБЛИЯ СЕРИИ") and "шарф Лаптева" in lines[1]
    assert "у Веры (с гл.6: Вера изъяла его)" in b and "квартира Ларионовой — этаж: второй" in b


def test_analysis_bible_goes_through_merge(project_id):
    from engine.db_state import merge_analysis_into_state
    from engine.series_bible import current
    raw = json.dumps({"bible": [_e("контора Гордеева", "этаж", "второй")]}, ensure_ascii=False)
    assert merge_analysis_into_state(project_id, raw, 3)["changed"]
    raw = json.dumps({"bible": [_e("контора Гордеева", "этаж", "пятый")]}, ensure_ascii=False)
    res = merge_analysis_into_state(project_id, raw, 4)
    assert res["bible_conflicts"] and any("Противоречие с библией" in f["field"] for f in res["fields"])
    assert [x["value"] for x in current(project_id)] == ["второй"]


def test_analysis_prompt_lists_known_entities(project_id):
    from engine.series_bible import known_for_analysis, record
    from engine.state import _build_analysis_prompt
    record(project_id, [_e("квартира Ларионовой", "этаж", "второй")], 3)
    p = _build_analysis_prompt(4, {"global_state": "", "plot_matrix": "", "memory_graph": ""},
                               "текст", None, known_for_analysis(project_id))
    assert "место: квартира Ларионовой: этаж — второй" in p and '"bible"' in p


def test_generator_and_continuity_get_bible(project_id):
    from unittest.mock import patch
    from engine.continuity_checker import _build_series_facts
    from engine.pipeline_context import build_context
    from engine.series_bible import record
    record(project_id, [_e("квартира Ларионовой", "этаж", "второй")], 3)
    with patch("engine.pipeline_context.build_consolidated_voice", return_value=""), \
         patch("engine.pipeline_context._build_exemplar_block", return_value=""), \
         patch("engine.pipeline_context._build_kb_block", return_value=""), \
         patch("engine.pipeline_context._build_engine_block", return_value=""), \
         patch("engine.pipeline_context.get_symbols_context", return_value=""), \
         patch("engine.pipeline_context.extract_relevant_state", return_value=""), \
         patch("engine.db.get_prep_context", return_value=""), \
         patch("engine.pipeline_context._maybe_save_debug_prompt", return_value=None):
        ctx = build_context(project_id, 4, "Задача главы")
    assert "БИБЛИЯ СЕРИИ" in ctx and "квартира Ларионовой — этаж: второй" in ctx
    assert "квартира Ларионовой" in _build_series_facts(project_id, 4)


def test_refinement_is_not_a_conflict(project_id):
    """Ложные противоречия замера 14.10 — уточнения, а не смена факта."""
    from engine.series_bible import current, history, record
    record(project_id, [_e("тайник", "где", "в полу, под ковром, в кабинете")], 4)
    r = record(project_id, [_e("тайник", "где", "в полу кабинета под ковром, крышка люка — половица")], 5)
    assert r["conflicts"] == []
    assert current(project_id)[0]["value"].startswith("в полу кабинета")
    assert [h["status"] for h in history(project_id, "тайник", "где")] == ["введено", "уточнено"]
    record(project_id, [_e("Кирпичный переулок", "дом", "15, квартира 8")], 4)
    assert record(project_id, [_e("Кирпичный переулок", "дом", "15")], 5)["conflicts"] == []
    # Числа и порядковые расходятся — противоречие
    record(project_id, [_e("контора", "этаж", "второй")], 3)
    assert record(project_id, [_e("контора", "этаж", "третий")], 4)["conflicts"]


def test_short_word_value_refined(project_id):
    """«ФАП» → «ФАП, холодильная камера» — уточнение (книга 18.10); «ФАП» → «ДК» — нет."""
    from engine.series_bible import record, same_or_refined
    record(project_id, [_e("сцена 1", "место", "ФАП", kind="событие")], 4)
    assert record(project_id, [_e("сцена 1", "место", "ФАП, холодильная камера", kind="событие")], 4)["conflicts"] == []
    assert not same_or_refined("ФАП", "ДК")
    assert not same_or_refined("на юге", "на севере")


def test_floor_from_any_attr_catches_real_conflict(project_id):
    """Замер 14.10, deepseek без библии: «адрес: …, 5 этаж» в гл.3 и «этаж: четвёртый» в гл.6."""
    from engine.series_bible import current, record
    record(project_id, [_e("квартира вдовы Ларионовой", "адрес", "набережная Мойки, дом с лепниной, 5 этаж")], 3)
    assert {(r["attr"], r["value"]) for r in current(project_id)} >= {("этаж", "5-й")}
    r = record(project_id, [_e("квартира вдовы Ларионовой", "этаж", "четвёртый")], 6)
    assert r["conflicts"] and r["conflicts"][0]["was"] == "5-й"
    # «третий» и «3-й» — одно и то же, «окно: третий этаж» — тот же этаж
    record(project_id, [_e("дом Ирины", "окно", "третий этаж, тёплый жёлтый свет")], 3)
    assert record(project_id, [_e("дом Ирины", "этаж", "третий, окно справа")], 4)["conflicts"] == []
    assert record(project_id, [_e("дом Ирины", "адрес", "канал Грибоедова, пятый этаж")], 5)["conflicts"]


def test_place_aliases_merge_events_do_not(project_id):
    from engine.series_bible import current, record
    record(project_id, [_e("квартира вдовы Ларионовой", "этаж", "второй")], 3)
    r = record(project_id, [_e("дом Ларионовой", "этаж", "третий")], 4)
    assert r["conflicts"] and r["conflicts"][0]["name"] == "квартира вдовы Ларионовой"
    # Разные события с похожими именами — разные: ложные противоречия замера
    record(project_id, [_e("звонок Гордеева", "время", "около пяти часов", kind="событие")], 4)
    assert record(project_id, [_e("звонок Гордееву", "время", "17:02", kind="событие")], 5)["conflicts"] == []
    assert len([r for r in current(project_id) if r["kind"] == "событие"]) == 2


def test_event_date_time_weekday(project_id):
    from engine.series_bible import facets, record
    assert facets("событие", "дата и время", "17 ноября, 19:00") == {"дата": "17 ноября", "время": "19:00"}
    assert facets("событие", "время", "среда, 21:10") == {"день недели": "среда"}
    assert facets("событие", "дата", "двадцать пятое декабря") == {}       # сам признак — дата
    assert facets("событие", "когда", "двадцать пятое декабря")["дата"] == "25 декабря"
    # Время чужого действия — не время события
    assert facets("событие", "присутствие Куприка", "у люка до ~21:45") == {}
    # «вторник» и «пятно» — не порядковые
    assert facets("место", "вид", "пятно у двери во вторник") == {}
    record(project_id, [_e("встреча у вдовы", "дата", "среда, четвёртое декабря", kind="событие")], 5)
    r = record(project_id, [_e("встреча у вдовы", "время", "четверг, вечер", kind="событие")], 6)
    assert [c["attr"] for c in r["conflicts"]] == ["день недели"]


def test_description_conflicts_only_on_marks(project_id):
    """«Фон» 19.10: описания места спорили словами — «столик у окна» и «у стены»; спорят только метки."""
    from engine.series_bible import current, record
    record(project_id, [_e("кофейня «Зерно»", "вид", "столик у окна, видны трамваи")], 2)
    r = record(project_id, [_e("кофейня «Зерно»", "вид", "столик у стены, зеркало над стойкой")], 10)
    assert r["conflicts"] == []
    assert current(project_id)[0]["value"] == "столик у окна, видны трамваи; столик у стены, зеркало над стойкой"
    # Цвет — метка: «синяя» и «голубая» спорят
    record(project_id, [_e("куртка Ольги", "вид", "синяя, на кармане бейдж", kind="вещь")], 2)
    assert record(project_id, [_e("куртка Ольги", "вид", "голубая, с бейджем", kind="вещь")], 13)["conflicts"]
    # Этаж в описании — тоже метка
    record(project_id, [_e("кабинет Беловой", "обстановка", "каб. 214, второй этаж, кактус")], 13)
    assert record(project_id, [_e("кабинет Беловой", "обстановка", "каб. 214, настольная лампа")], 17)["conflicts"] == []
    assert record(project_id, [_e("кабинет Беловой", "обстановка", "каб. 215, лампа")], 18)["conflicts"]
    # Не описание — по-прежнему строго
    record(project_id, [_e("кусачки", "где", "в пакете", kind="вещь")], 2)
    assert record(project_id, [_e("кусачки", "где", "на кухонном столе", kind="вещь")], 3)["conflicts"]


def test_description_join_is_capped(project_id):
    from engine.series_bible import DESCRIPTION_MAX, current, record
    for ch in range(1, 30):
        record(project_id, [_e("двор", "вид", f"на скамейке сидит кто-то в куртке, вариант номер {'а' * ch}")], ch)
    v = current(project_id)[0]["value"]
    assert len(v) <= DESCRIPTION_MAX and v.endswith("а" * 29)


def test_same_night_is_not_a_conflict(project_id):
    """План: «четверг, 27 ноября, ночь», глава: «пятница, 28 ноября, 0:58» — одна ночь."""
    from engine.series_bible import record, same_night
    ev = "событие"
    record(project_id, [_e("сцена 3", "время", "четверг, 27 ноября, ночь", kind=ev)], 21)
    r = record(project_id, [_e("сцена 3", "время", "пятница, 28 ноября, ночь, 0:58–1:38", kind=ev)], 21)
    assert r["conflicts"] == []
    record(project_id, [_e("сцена 2", "время", "пятница, 28 ноября, ночь", kind=ev)], 23)
    assert record(project_id, [_e("сцена 2", "время", "ночь с 28 на 29 ноября, квартира", kind=ev)], 23)["conflicts"] == []
    assert record(project_id, [_e("сцена 2", "время", "суббота, 29 ноября, около 2:10", kind=ev)], 23)["conflicts"] == []
    assert same_night("30 ноября, ночь", "1 декабря, 0:40")
    # Не ночь, сдвиг на два дня, день недели против даты — противоречие
    assert not same_night("четверг, 27 ноября, вечер", "пятница, 28 ноября, 19:00")
    assert not same_night("четверг, 27 ноября, ночь", "суббота, 29 ноября, 1:00")
    assert not same_night("четверг, 27 ноября, ночь", "пятница, 27 ноября, 1:00")
    record(project_id, [_e("сцена 5", "время", "среда, ночь", kind=ev)], 5)
    assert record(project_id, [_e("сцена 5", "время", "пятница, 1:00", kind=ev)], 5)["conflicts"]


# ─── План против текста (разбор 21.10) ───────────────────────────────────────

def _plan(project_id, chapter, facts):
    from web.app import app
    app.config.update(TESTING=True, FE_CSRF=False)
    return app.test_client().post(f"/api/chapter_plan/{chapter}/save", json={
        "pid": project_id, "note": f"ПЛАН ГЛАВЫ {chapter}", "facts": facts}).get_json()


def _cur(project_id, before=None):
    from engine.series_bible import current
    return {(r["name"], r["attr"]): r["value"] for r in current(project_id, before)}


def test_plan_reexport_replaces_old_plan_keeps_author_edit(project_id):
    """«Фон», гл.20: после перепланирования «Анонс» (старый план) оставался рядом со «Сделкой»."""
    from engine.series_bible import author_set
    author_set(project_id, "место", "Квартира Лавровых", "этаж", "пятый", 3, "правка автора")
    _plan(project_id, 20, [{"kind": "событие", "name": "глава 20, сцена 3: Анонс", "attr": "место", "value": "комната Вари"}])
    _plan(project_id, 20, [{"kind": "событие", "name": "глава 20, сцена 3: Сделка", "attr": "место", "value": "комната Вари"}])
    cur = _cur(project_id)
    assert ("глава 20, сцена 3: Сделка", "место") in cur and ("глава 20, сцена 3: Анонс", "место") not in cur
    assert cur[("Квартира Лавровых", "этаж")] == "пятый"


def test_text_wins_over_plan_not_over_author_edit(project_id):
    """«Фон», гл.23: «пятница, ночь (план)» оставалась фактом при «субботе, 2:10» в тексте."""
    from engine.series_bible import author_set, bible_block, record
    _plan(project_id, 23, [{"kind": "событие", "name": "глава 23, сцена 3: Без экрана", "attr": "место",
                            "value": "квартира Лавровых"}])
    author_set(project_id, "предмет", "Термос Лёвы", "цвет", "серебристый", 21, "правка автора")
    out = record(project_id, [{"kind": "событие", "name": "глава 23, сцена 3: Без экрана", "attr": "место",
                               "value": "двор у гаражей"},
                              {"kind": "предмет", "name": "Термос Лёвы", "attr": "цвет", "value": "зелёный"}], 23)
    cur = _cur(project_id)
    assert cur[("глава 23, сцена 3: Без экрана", "место")] == "двор у гаражей" and len(out["changed"]) == 1
    # Правка автора вручную — канон: расхождение остаётся противоречием
    assert cur[("Термос Лёвы", "цвет")] == "серебристый" and len(out["conflicts"]) == 1
    assert "в плане «квартира Лавровых»" in bible_block(project_id, before_chapter=24)


def test_block_for_rewritten_chapter_keeps_earlier_value(project_id):
    """Факт, уточнённый поздней главой, для переписываемой ранней главы — значение до неё, а не пропуск."""
    from engine.series_bible import bible_block, record
    record(project_id, [{"kind": "место", "name": "Подсобка", "attr": "замок", "value": "навесной"}], 5)
    record(project_id, [{"kind": "место", "name": "Подсобка", "attr": "замок", "value": "кодовый",
                         "changed": "заменили после кражи"}], 20)
    assert "навесной" in bible_block(project_id, before_chapter=12)
    assert "кодовый" in bible_block(project_id, before_chapter=21)
