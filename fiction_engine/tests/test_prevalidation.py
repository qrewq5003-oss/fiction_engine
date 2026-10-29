"""test_prevalidation.py — prevalidate_chapter"""
import json
import pytest
from unittest.mock import patch


def _validate(project_id, llm_response):
    from engine.prevalidation import prevalidate_chapter
    empty_state = {"global_state":"","plot_matrix":"","memory_graph":""}
    with patch("engine.prevalidation.state_for_chapter", return_value=empty_state),\
         patch("engine.prevalidation.get_prep",     return_value={}),\
         patch("engine.prevalidation.get_weighted_promises", return_value=""),\
         patch("engine.prevalidation.check_structural_monotony", return_value=None),\
         patch("engine.prevalidation.call_model",   return_value=llm_response),\
         patch("engine.prevalidation._get_api_keys",
               return_value={"anthropic":"k","openai":"k","nano":"k",
                             "gemini":"k","deepseek":"k"}):
        return prevalidate_chapter(project_id, chapter_num=3,
                                   task="написать главу", model_value="model:v1")


class TestPrevalidateChapter:
    def test_returns_dict(self, project_id):
        r = _validate(project_id, json.dumps(
            {"ok":True,"blocking":[],"warnings":[],"suggestions":[]}))
        assert isinstance(r, dict)

    def test_ok_true_from_llm(self, project_id):
        r = _validate(project_id, json.dumps(
            {"ok":True,"blocking":[],"warnings":[],"suggestions":[]}))
        assert r.get("ok") is True
        assert r.get("blocking",[]) == []

    def test_ok_false_with_blocking(self, project_id):
        resp = json.dumps({"ok":False,
            "blocking":[{"issue":"противоречие","detail":"детали","fix":"исправь"}],
            "warnings":[],"suggestions":[]})
        r = _validate(project_id, resp)
        assert r.get("ok") is False
        assert len(r.get("blocking",[])) >= 1

    def test_non_json_does_not_crash(self, project_id):
        r = _validate(project_id, "не JSON ответ")
        assert isinstance(r, dict)

    def test_prompt_has_future_plans_and_full_schedule(self, project_id):
        """Запрет сцены сверяется с планами следующих глав и расписанием мира
        (гл.9 «Последнего рейса»: «никого не отпускать с борта» при пикнике в гл.10)."""
        from engine.prevalidation import prevalidate_chapter
        world = "Теплоход. " + "х" * 1700 + " Расписание: четверг — пикник на берегу Ахтубы."
        seen = {}

        def fake_call(model, system, prompt, **kw):
            seen["prompt"] = prompt
            return json.dumps({"blocking": [], "warnings": [], "suggestions": []})
        empty_state = {"global_state": "", "plot_matrix": "", "memory_graph": ""}
        with patch("engine.prevalidation.state_for_chapter", return_value=empty_state),\
             patch("engine.prevalidation.get_prep", return_value={"world": world}),\
             patch("engine.prevalidation.get_weighted_promises", return_value=""),\
             patch("engine.prevalidation.check_structural_monotony", return_value=None),\
             patch("engine.run_ahead.get_future", return_value="- гл.4: пикник на берегу"),\
             patch("engine.prevalidation.call_model", side_effect=fake_call),\
             patch("engine.prevalidation._get_api_keys", return_value={}):
            prevalidate_chapter(project_id, chapter_num=3, task="никого не отпускать с борта",
                                model_value="model:v1")
        p = seen["prompt"]
        assert "ПЛАНЫ СЛЕДУЮЩИХ ГЛАВ" in p and "гл.4: пикник на берегу" in p
        assert "пикник на берегу Ахтубы" in p
        assert "спорит с расписанием" in p and "читатель раньше не видел" in p and "вне этой главы" in p

    def test_result_has_warnings_key(self, project_id):
        r = _validate(project_id, json.dumps(
            {"ok":True,"blocking":[],"warnings":[{"issue":"замечание","detail":"x"}],
             "suggestions":[]}))
        assert isinstance(r.get("warnings",[]), list)
