"""test_prevalidation.py — prevalidate_chapter"""
import json
import pytest
from unittest.mock import patch


def _validate(project_id, llm_response):
    from engine.prevalidation import prevalidate_chapter
    empty_state = {"global_state":"","plot_matrix":"","memory_graph":""}
    with patch("engine.prevalidation.get_state",    return_value=empty_state),\
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

    def test_result_has_warnings_key(self, project_id):
        r = _validate(project_id, json.dumps(
            {"ok":True,"blocking":[],"warnings":[{"issue":"замечание","detail":"x"}],
             "suggestions":[]}))
        assert isinstance(r.get("warnings",[]), list)
