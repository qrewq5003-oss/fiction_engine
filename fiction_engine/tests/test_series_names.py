"""
Имена с отчествами в серии: сигнал, когда отчество у того же имени меняется,
и реестр отчеств для генератора.

Замер 11.10 (bench/ab-series-details-2026-10-11.json): после деталей серии
чаще всего остаётся одно — Ирина Андреевна в следующей главе становится
Борисовной. Так во всех сериях детектива, у любого генератора.
"""
from unittest.mock import patch

CH3 = ("Ирина Андреевна открыла сейф. Аркадий Павлович молчал. — Аркадию Павловичу "
       "виднее, — сказала Ирина. Вера кивнула.")
CH4 = ("Утром Ирина Борисовна принесла папку. Аркадий Павлович ждал у окна. "
       "Ирина положила папку на стол.")


def test_mentions_fold_cases_and_forms():
    from engine.text_signals import name_mentions
    got = name_mentions("Аркадий Павлович ушёл. Звали Аркадием Павловичем, иногда "
                        "Аркадий Палыч, а за глаза Павла Сергеевича — Павел Сергеич. "
                        "Ирине Андреевне было некогда.")
    keys = {(k, p) for k, p, _, _ in got}
    assert (("м", "аркад"), "павл") in keys and len({p for k, p in keys if k[1] == "аркад"}) == 1
    assert (("м", "павл"), "серге") in keys and len({k for k, _ in keys if k[1] == "павл"}) == 1
    assert (("ж", "ирин"), "андре") in keys


def test_sentence_start_is_not_a_name():
    from engine.text_signals import name_mentions
    assert name_mentions("Вчера Павлович не пришёл. вчера было тихо, вчера и сегодня.") == []


def test_signal_when_patronymic_changes():
    from engine.text_signals import series_signals
    sig = series_signals(CH4, [{"number": 3, "content": CH3}])
    ours = [s for s in sig if "Отчество" in s]
    assert len(ours) == 1
    assert "«Ирина Андреевна» в главе 3" in ours[0] and "«Ирина Борисовна»" in ours[0]


def test_no_signal_for_same_patronymic_or_two_namesakes():
    from engine.text_signals import series_signals
    same = "Ирине Андреевне не спалось. Аркадий Павлович позвонил."
    assert not [s for s in series_signals(same, [{"number": 3, "content": CH3}]) if "Отчество" in s]
    # Оба отчества в новой главе — скорее два человека с одним именем
    both = "Ирина Андреевна и Ирина Борисовна вышли вместе."
    assert not [s for s in series_signals(both, [{"number": 3, "content": CH3}]) if "Отчество" in s]


def test_series_names_keeps_first_patronymic_in_nominative():
    from engine.text_signals import series_names
    names = series_names([{"number": 3, "content": "Аркадию Павловичу позвонили. Аркадий Павлович встал."},
                          {"number": 4, "content": CH4}])
    assert names == ["Аркадий Павлович", "Ирина Борисовна"]
    names = series_names([{"number": 3, "content": CH3}, {"number": 4, "content": CH4}])
    assert "Ирина Андреевна" in names and "Ирина Борисовна" not in names


def test_generator_and_continuity_get_names(project_id):
    from engine.continuity_checker import _build_series_facts
    from engine.db import save_chapter
    from engine.pipeline_context import build_context
    save_chapter(project_id, 3, CH3, "Глава 3")
    with patch("engine.pipeline_context.build_consolidated_voice", return_value=""), \
         patch("engine.pipeline_context._build_exemplar_block", return_value=""), \
         patch("engine.pipeline_context._build_kb_block", return_value=""), \
         patch("engine.pipeline_context._build_engine_block", return_value=""), \
         patch("engine.pipeline_context.get_symbols_context", return_value=""), \
         patch("engine.pipeline_context.extract_relevant_state", return_value=""), \
         patch("engine.db.get_prep_context", return_value=""), \
         patch("engine.pipeline_context._maybe_save_debug_prompt", return_value=None):
        ctx = build_context(project_id, 4, "Задача главы")
    assert "ИМЕНА СЕРИИ" in ctx and "Ирина Андреевна, Аркадий Павлович" in ctx
    assert "Ирина Андреевна" in _build_series_facts(project_id, 4)
