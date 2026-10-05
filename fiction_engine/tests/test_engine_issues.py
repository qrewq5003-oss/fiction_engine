"""
test_engine_issues.py — сбои базы знаний видны автору (AUDIT_UNIFIED.md, F4).

Загрузчики и сборка блока движка раньше гасили ошибки в пустую строку,
и глава уходила в модель без контракта или всего блока молча.
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from engine.engine_config import GENRE_KEYWORDS
from engine.engine_issues import (collect_engine_issues, engine_issues_note,
                                  note_engine_issue)
from engine.unified_engine import build_engine_context

KB_PATH = Path(__file__).resolve().parents[2] / "UNIFIED_ENGINE_MASTER"


def test_note_outside_collection_is_harmless():
    note_engine_issue("что-то пропало")          # только лог, без исключения


def test_collection_gathers_unique_notes():
    with collect_engine_issues() as issues:
        note_engine_issue("раздел А")
        note_engine_issue("раздел А")
        note_engine_issue("раздел Б")
    assert issues == ["раздел А", "раздел Б"]
    note_engine_issue("после сбора")
    assert issues == ["раздел А", "раздел Б"]


def test_note_text():
    assert engine_issues_note([]) == ""
    note = engine_issues_note(["раздел А", "раздел Б"])
    assert note.startswith("База знаний: раздел А; раздел Б.")


@pytest.mark.parametrize("mode", ("quick", "quality", "master"))
@pytest.mark.parametrize("genre_key", sorted(GENRE_KEYWORDS))
def test_real_base_has_no_issues(genre_key, mode):
    """На настоящей базе сборка не отмечает ни одного пропавшего раздела."""
    assert KB_PATH.is_dir(), f"UNIFIED_ENGINE_MASTER не найден: {KB_PATH}"
    with patch("engine.engine_loaders.get_engine_path", return_value=KB_PATH), \
         collect_engine_issues() as issues:
        block = build_engine_context(genre_key, mode)
    assert block
    assert issues == []


def test_missing_contract_is_reported():
    with patch("engine.engine_loaders.get_engine_path", return_value=KB_PATH), \
         patch("engine.unified_engine._load_genre_contract", return_value=""), \
         collect_engine_issues() as issues:
        build_engine_context("detective_classic", "quality")
    assert issues == ["не собран раздел «читательский контракт» (detective_classic)"]


def test_contract_not_required_in_quick():
    with patch("engine.engine_loaders.get_engine_path", return_value=KB_PATH), \
         patch("engine.unified_engine._load_genre_contract", return_value=""), \
         collect_engine_issues() as issues:
        build_engine_context("detective_classic", "quick")
    assert issues == []


def test_missing_base_is_reported(tmp_path):
    with patch("engine.engine_loaders.get_engine_path",
               return_value=tmp_path / "нет"), \
         collect_engine_issues() as issues:
        assert build_engine_context("detective_classic", "quick") == ""
    assert issues == ["каталог базы знаний не найден, блок движка пуст"]


def test_module_without_prompt_sections_is_reported(tmp_path):
    from engine.engine_loaders_core import load_module
    d = tmp_path / "03_ADVANCED_ENGINES"
    d.mkdir()
    (d / "01_tension_curve.md").write_text("## MINI\nсуть\n", encoding="utf-8")
    with collect_engine_issues() as issues:
        assert load_module(tmp_path, "01_tension_curve", 30) == ""
        assert load_module(tmp_path, "99_nonexistent", 30) == ""
    assert issues == ["в модуле 01_tension_curve нет секции PROMPT:QUICK",
                      "модуль 99_nonexistent не найден"]


def test_contract_without_own_section_is_empty(tmp_path):
    """Чужой контракт хуже пустого: начало файла больше не подставляется (U1)."""
    from engine.engine_config import CONTRACT_MAP
    from engine.engine_loaders_genre import load_genre_contract
    d = tmp_path / "16_GENRE_CONTRACT"
    d.mkdir()
    (d / CONTRACT_MAP["detective"]).write_text(
        "# Контракт\n## НУАР\n<!-- genre: detective_noir -->\nОбязательно: тьма\n"
        "## КЛАССИЧЕСКИЙ\nОбязательно: улики\n", encoding="utf-8")
    # У классического раздел есть, но якоря нет — по русской метке не ищем
    assert load_genre_contract(tmp_path, "detective_classic") == ""
    noir = load_genre_contract(tmp_path, "detective_noir")
    assert "НУАР" in noir and "тьма" in noir and "улики" not in noir and "<!--" not in noir


def test_genre_prompt_without_subgenre_block_is_empty(tmp_path):
    """Без блока поджанра правила семейства больше не подставляются."""
    from engine.engine_loaders_genre import load_genre_prompt
    d = tmp_path / "11_PROMPTS"
    d.mkdir()
    (d / "detective_QUICK.md").write_text(
        "═══ ПРАВИЛА КАЧЕСТВА ═══\nОБЯЗАТЕЛЬНО:\n- улики\n", encoding="utf-8")
    assert load_genre_prompt(tmp_path, "detective_classic", "quick") == ""


def test_run_generation_warns_when_engine_block_fails(project_id):
    from engine.pipeline import run_generation
    chapter = "Он вошёл в комнату и сел у окна. " * 400
    with patch("engine.pipeline._call", return_value=chapter), \
         patch("engine.pipeline_context.build_engine_context",
               side_effect=RuntimeError("битый файл")):
        res = run_generation({"id": project_id, "genre": "детектив"},
                             1, "quick", "m::x", "Задача.")
    assert "База знаний: блок движка не собран: RuntimeError" in res["warning"]


def test_run_generation_quiet_on_real_base(project_id):
    from engine.pipeline import run_generation
    chapter = "Он вошёл в комнату и сел у окна. " * 400
    with patch("engine.pipeline._call", return_value=chapter), \
         patch("engine.engine_loaders.get_engine_path", return_value=KB_PATH):
        res = run_generation({"id": project_id, "genre": "детектив"},
                             1, "quick", "m::x", "Задача.")
    assert "База знаний" not in (res["warning"] or "")
