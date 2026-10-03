"""
Блок движка в генераторе пайплайна.

С первого коммита шаг generate собирал контекст по умолчанию: QUICK, без
модели и без задачи. Генератор не видел контракта жанра, а судья того же
пайплайна проверял главу именно по нему.
"""
from unittest.mock import patch

from engine.pipeline import PIPELINE_ENGINE_MODE, PipelineStep, run_pipeline_step

CHAPTER = "Он вошёл в комнату и сел у окна. " * 400


def _run(project_id, build):
    from engine.db_narrative import create_pipeline_run
    run_id = create_pipeline_run(project_id, 1, "m", "m", "m", "m")
    with patch("engine.pipeline._build_context", side_effect=build), \
         patch("engine.pipeline._call", return_value=CHAPTER):
        return run_pipeline_step(
            run_id=run_id, iteration=1, project_id=project_id, chapter_num=1,
            generation_prompt="Глава 1. Допрос в участке.",
            model_gen="deepseek::chat", model_critic="m::m",
            model_editor="m::m", model_judge="m::m",
            steps=[PipelineStep("generate")])


def test_generate_builds_quality_context_for_generator_model(project_id):
    seen = {}

    def build(project_id, chapter_num, base_prompt, mode="quick",
              model_value="", task_text=""):
        seen.update(mode=mode, model_value=model_value, task_text=task_text)
        return base_prompt

    _run(project_id, build)
    assert PIPELINE_ENGINE_MODE == "quality"
    assert seen == {"mode": "quality", "model_value": "deepseek::chat",
                    "task_text": "Глава 1. Допрос в участке."}


def test_oversized_context_is_trimmed_and_reported(project_id):
    from engine.pipeline_config import context_char_budget
    huge = "x" * (context_char_budget("deepseek::chat") + 1000)
    sent = []
    with patch("engine.pipeline.step_generate",
               side_effect=lambda *a, **k: sent.append(a[4])):
        res = _run(project_id, lambda *a, **k: huge)
    assert len(sent[0]) <= context_char_budget("deepseek::chat")
    assert res["context_trimmed"].startswith("Контекст обрезан")
