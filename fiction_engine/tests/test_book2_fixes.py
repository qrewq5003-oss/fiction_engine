"""Книга на Sonnet 18.10: повтор L3 при браке JSON, «Пока не раскрывать» в плане."""
import json

TEXT = "Анна поднялась на галерею маяка и долго смотрела на воду. " * 10
GOOD = json.dumps({"events": "Анна на маяке.", "characters": "", "conflicts": "", "promises": [], "mood": "тихо"},
                  ensure_ascii=False)


def test_l3_retries_once_on_broken_json(project_id):
    from engine.l3_memory import generate_l3_summary
    answers = ['{"events": "Анна на маяке", "characters": ', GOOD]
    calls = []
    res = generate_l3_summary(project_id, 12, TEXT, lambda p: (calls.append(p), answers[len(calls) - 1])[1])
    assert res and res["events"] == "Анна на маяке." and len(calls) == 2


def test_l3_no_retry_when_cut_by_token_limit(project_id, monkeypatch):
    import engine.api as api
    from engine.l3_memory import generate_l3_summary
    monkeypatch.setattr(api, "get_last_stop_reason", lambda: "max_tokens")
    calls = []
    assert generate_l3_summary(project_id, 12, TEXT, lambda p: (calls.append(p), '{"events": "обрыв')[1]) is None
    assert len(calls) == 1


def test_plan_items_ignore_hold_block():
    from engine.plan_check import plan_items
    plan = ("ПЛАН ГЛАВЫ 4\n\nСЦЕНА 1: Холодильная камера\n  Что происходит: осмотр тела\n\n"
            "СЦЕНА 2: Калоши\n  Что происходит: калоши с ромбом\n\n"
            "ПОКА НЕ РАСКРЫВАТЬ (в этой главе читатель этого ещё не узнаёт):\n- связь Кравец с журналом")
    items = plan_items(plan)
    assert len(items) == 2 and not any("Кравец" in i for i in items)
