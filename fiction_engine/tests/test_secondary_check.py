"""
Проверка второй линии книги после вердикта судьи (engine/secondary_check.py).
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

JUDGMENT = ("ГОЛОС: 8\nСТРУКТУРА: 8\nПЕРСОНАЖИ: 8\nСЦЕНЫ: 8\nДИАЛОГ: 8\n"
            "ИТОГ: 40\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: хорошо")


def _line_answer(scores, present="да"):
    return json.dumps({"present": present, "answers": [
        {"q": i, "quote": "…", "score": s} for i, s in enumerate(scores, 1)]}, ensure_ascii=False)


def test_family_only_for_measured_genres():
    from engine.secondary_check import line_family
    assert line_family("romance_contemporary") == "romance"
    assert line_family("horror_gothic") == "horror"
    assert line_family("thriller_spy") == "thriller"
    assert line_family("fantasy_dark") is None          # набор не прошёл с одним судьёй
    assert line_family("detective_noir") is None
    assert line_family("romance") is None               # тон «Романтика», не жанр
    assert line_family(None) is None


def test_check_line_scores_and_weak_questions():
    from engine.secondary_check import LINE_QUESTIONS, check_line
    res = check_line("глава", "romance_contemporary", "Романтика",
                     lambda p: _line_answer([0, 1, 0, 2, 1]))
    assert res == {"present": True, "score": 4.0, "failed": True,
                   "weak": [LINE_QUESTIONS["romance"]["Q"][0], LINE_QUESTIONS["romance"]["Q"][2]]}
    ok = check_line("глава", "romance_contemporary", "Романтика", lambda p: _line_answer([2, 2, 1, 2, 2]))
    assert ok["failed"] is False and ok["score"] == 9.0


def test_absent_line_is_not_a_failure():
    from engine.secondary_check import check_line
    res = check_line("глава", "horror_gothic", "Готика", lambda p: _line_answer([], present="нет"))
    assert res == {"present": False, "score": None, "failed": False, "weak": []}


def test_unparsed_or_partial_answer_is_none():
    from engine.secondary_check import check_line
    assert check_line("глава", "horror_gothic", "Готика", lambda p: "не знаю") is None
    assert check_line("глава", "horror_gothic", "Готика", lambda p: _line_answer([2, 2])) is None


def test_questions_match_measured_sets():
    """Вопросы в движке — те же, что прошли замер (tools/secondary_line/families.py)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "secondary_line"))
    from families import FAMILIES
    from engine.secondary_check import LINE_QUESTIONS
    for fam, v in LINE_QUESTIONS.items():
        assert v["Q"] == FAMILIES[fam]["Q"], fam


def _judge(project_id, line_reply):
    from engine.db_projects import set_project_genre_key, set_project_genre_secondary
    from engine.db import create_pipeline_run
    from engine.pipeline_steps import step_judge
    set_project_genre_key(project_id, "detective_classic")
    set_project_genre_secondary(project_id, "romance_contemporary")
    run_id = create_pipeline_run(project_id, chapter_num=3, model_gen="m", model_critic="m",
                                 model_editor="m", model_judge="m")
    results = {"generated_text": "Вера поняла, что влюблена.", "critique": "критика"}

    def call(model, system, prompt, max_tokens=0):
        return line_reply if "второй жанр" in prompt and "present" in prompt else JUDGMENT
    with patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_judge(run_id, 1, 3, "m", call, results, project_id=project_id)
    return results


def test_failed_line_turns_accept_into_rework(project_id):
    from engine.pipeline_llm import parse_verdict
    r = _judge(project_id, _line_answer([0, 1, 0, 1, 1]))
    assert r["verdict"] == "НА ДОРАБОТКУ"
    assert "ВТОРАЯ ЛИНИЯ" in r["judgment"] and parse_verdict(r["judgment"]) == "НА ДОРАБОТКУ"
    assert r["secondary_line"]["failed"] is True


def test_living_line_keeps_verdict(project_id):
    r = _judge(project_id, _line_answer([2, 2, 2, 1, 2]))
    assert r["verdict"] == "ПРИНЯТЬ" and "ВТОРАЯ ЛИНИЯ" not in r["judgment"]
    assert r["secondary_line"]["score"] == 9.0


def test_set_verdict_rewrites_the_line():
    from engine.pipeline_llm import parse_verdict, set_verdict
    t = set_verdict(JUDGMENT, "НА ДОРАБОТКУ")
    assert parse_verdict(t) == "НА ДОРАБОТКУ" and t.count("ВЕРДИКТ:") == 1
    assert parse_verdict(set_verdict("ВЕРДИКТ: [ПРИНЯТЬ]", "НА ДОРАБОТКУ")) == "НА ДОРАБОТКУ"
    assert parse_verdict(set_verdict("без вердикта", "ПРИНЯТЬ")) == "ПРИНЯТЬ"
