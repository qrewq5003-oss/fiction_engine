"""test_pipeline_config.py — engine/pipeline_config.py (StepConfig, PipelineConfig, presets)"""
import pytest


class TestStepConfig:
    def test_valid_names_accepted(self):
        from engine.pipeline_config import StepConfig
        for n in ("generate", "edit", "critique", "judge"):
            assert StepConfig(n).name == n

    def test_invalid_name_raises(self):
        from engine.pipeline_config import StepConfig
        with pytest.raises(ValueError, match="Неизвестный шаг"):
            StepConfig("unknown_step")

    def test_default_model_roles(self):
        from engine.pipeline_config import StepConfig
        assert StepConfig("generate").default_model_role == "gen"
        assert StepConfig("edit").default_model_role    == "editor"
        assert StepConfig("critique").default_model_role == "critic"
        assert StepConfig("judge").default_model_role   == "judge"

    def test_explicit_model_role_overrides(self):
        from engine.pipeline_config import StepConfig
        assert StepConfig("judge", model_role="nano").default_model_role == "nano"

    def test_enabled_true_by_default(self):
        from engine.pipeline_config import StepConfig
        assert StepConfig("generate").enabled is True

    def test_round_trip_to_dict_from_dict(self):
        from engine.pipeline_config import StepConfig
        s  = StepConfig("edit", enabled=False, max_tokens=3000)
        s2 = StepConfig.from_dict(s.to_dict())
        assert s2.name == "edit" and s2.enabled is False and s2.max_tokens == 3000


class TestPipelineConfig:
    def _cfg(self):
        from engine.pipeline_config import PipelineConfig, StepConfig
        return PipelineConfig(steps=[
            StepConfig("generate"),
            StepConfig("critique"),
            StepConfig("judge", enabled=False),
        ])

    def test_enabled_steps_excludes_disabled(self):
        names = [s.name for s in self._cfg().enabled_steps]
        assert "generate" in names and "critique" in names and "judge" not in names

    def test_step_names_only_enabled(self):
        cfg = self._cfg()
        assert "generate" in cfg.step_names and "critique" in cfg.step_names

    def test_has_step_true_for_enabled(self):
        assert self._cfg().has_step("generate") is True

    def test_has_step_false_for_disabled(self):
        assert self._cfg().has_step("judge") is False   # disabled

    def test_has_step_false_for_missing(self):
        assert self._cfg().has_step("edit") is False

    def test_get_step_returns_regardless_of_enabled(self):
        step = self._cfg().get_step("judge")  # disabled but still findable
        assert step is not None and step.name == "judge"

    def test_get_step_none_for_missing(self):
        assert self._cfg().get_step("nonexistent") is None

    def test_with_step_disabled_is_immutable(self):
        from engine.pipeline_config import STANDARD
        new = STANDARD.with_step_disabled("judge")
        assert new is not STANDARD                          # new object
        orig = STANDARD.get_step("judge")
        assert orig is None or orig.enabled is True         # original unchanged

    def test_with_step_disabled_actually_disables(self):
        from engine.pipeline_config import STANDARD
        new = STANDARD.with_step_disabled("judge")
        j = new.get_step("judge")
        assert j is not None and j.enabled is False

    def test_to_dict_from_dict_round_trip(self):
        from engine.pipeline_config import STANDARD
        d = STANDARD.to_dict()
        r = STANDARD.__class__.from_dict(d)
        assert r.max_iterations == STANDARD.max_iterations
        assert r.score_threshold == STANDARD.score_threshold
        assert len(r.steps)      == len(STANDARD.steps)

    def test_to_pipeline_steps_length(self):
        from engine.pipeline_config import STANDARD
        result = STANDARD.to_pipeline_steps()
        assert isinstance(result, list) and len(result) == len(STANDARD.steps)


class TestGetPreset:
    def test_all_standard_presets(self):
        from engine.pipeline_config import get_preset
        for name in ("quick","standard","deep","continue","auto_improve","critique_only"):
            assert get_preset(name) is not None

    def test_unknown_raises_value_error(self):
        from engine.pipeline_config import get_preset
        with pytest.raises(ValueError, match="Неизвестный пресет"):
            get_preset("does_not_exist_xyz")

    def test_quick_has_no_active_judge(self):
        from engine.pipeline_config import get_preset
        assert get_preset("quick").has_step("judge") is False

    def test_deep_has_active_edit(self):
        from engine.pipeline_config import get_preset
        edit = get_preset("deep").get_step("edit")
        assert edit is not None and edit.enabled is True

    def test_standard_threshold_sensible(self):
        from engine.pipeline_config import get_preset
        t = get_preset("standard").score_threshold
        assert 0 < t < 50

    def test_critique_only_generate_disabled(self):
        from engine.pipeline_config import get_preset
        gen = get_preset("critique_only").get_step("generate")
        assert gen is not None and gen.enabled is False


class TestListPresets:
    def test_returns_list_with_enough_presets(self):
        from engine.pipeline_config import list_presets
        result = list_presets()
        assert isinstance(result, list) and len(result) >= 5

    def test_each_item_has_required_keys(self):
        from engine.pipeline_config import list_presets
        for p in list_presets():
            for k in ("id","description","steps","max_iter"):
                assert k in p, f"key '{k}' missing in {p}"

    def test_standard_and_quick_present(self):
        from engine.pipeline_config import list_presets
        ids = {p["id"] for p in list_presets()}
        assert "standard" in ids and "quick" in ids
