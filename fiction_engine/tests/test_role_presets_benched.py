"""
Наборы ролей совпадают с теми, на которых сделаны замеры (pipeline_config.BENCHED_PRESETS).

Тест для того, кто меняет модель в наборе: упал — значит, сначала замеры для
новой модели, потом снимок. Автору книги это не видно.
"""
from engine.pipeline_config import BENCHED_PRESETS, ROLE_PRESETS

WHAT_TO_MEASURE = (
    "Сменилась модель в наборе ролей. Прежде чем обновлять BENCHED_PRESETS, повтори замеры "
    "для новой модели (список — в engine/pipeline_config.py над BENCHED_PRESETS): писатель/редактор — "
    "bench/edit-source-*, судья — bench/judges-*, критик — bench/critics-*, непрерывность — "
    "bench/ab-continuity-*. Своё не судит никто."
)


def test_presets_are_the_benched_ones():
    assert set(ROLE_PRESETS) == set(BENCHED_PRESETS), WHAT_TO_MEASURE
    for name, preset in ROLE_PRESETS.items():
        benched = BENCHED_PRESETS[name]
        assert preset["roles"] == benched["roles"], f"набор «{name}», роли. {WHAT_TO_MEASURE}"
        assert preset["settings"] == benched["settings"], f"набор «{name}», настройки. {WHAT_TO_MEASURE}"


def test_judge_is_never_the_writers_family():
    """Своё не судит никто — правило всех замеров и наборов."""
    from engine.pipeline_config import model_family
    for name, preset in ROLE_PRESETS.items():
        gen = model_family(preset["roles"]["gen"])
        for role in ("judge",):
            assert model_family(preset["roles"][role]) != gen, name
        for key in ("continuity_model", "scorer_model"):
            assert model_family(preset["settings"][key]) != gen, (name, key)
