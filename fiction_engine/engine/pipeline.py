"""
Pipeline: Генерация → Критик → Редактор → Судья → решение.

Этот файл — оркестратор. Не содержит бизнес-логики:
  - Сборка контекста  → pipeline_context.py
  - Шаги pipeline     → pipeline_steps.py
  - Дрейф голоса      → pipeline_drift.py
"""

from dataclasses import dataclass

from .api import call_model
from .db import (get_api_key, create_pipeline_run, finish_pipeline_run, get_pipeline_run, get_pipeline_iterations, get_prep_context)  # noqa: F401 — get_prep_context берётся прокси из pipeline_tasks
from .error_policy import handle_error, ErrorLevel
from .logger import get_logger
from .pipeline_config import PipelineConfig
from .pipeline_steps import (step_generate, step_drift_check, step_chapter_analysis, step_edit, step_critique, step_judge)

log = get_logger(__name__)


# ─── Конфигурация шагов ───────────────────────────────────────────────────────

@dataclass
class PipelineStep:
    name: str
    enabled: bool = True


DEFAULT_PIPELINE: list[PipelineStep] = [
    PipelineStep("generate"),
    PipelineStep("critique"),
    PipelineStep("judge"),
]

PIPELINE_WITH_EDIT: list[PipelineStep] = [
    PipelineStep("edit"),
    PipelineStep("critique"),
    PipelineStep("judge"),
]

# Pipeline с пре-валидацией задачи перед генерацией.
# Добавляет один LLM-вызов (дешёвая модель) но ловит противоречия до трат на генерацию.
PIPELINE_WITH_PREVALIDATE: list[PipelineStep] = [
    PipelineStep("prevalidate"),
    PipelineStep("generate"),
    PipelineStep("critique"),
    PipelineStep("judge"),
]


# ─── API-обёртки ─────────────────────────────────────────────────────────────


def _get_keys():
    return {
        "anthropic": get_api_key("anthropic_direct"),
        "nano":      get_api_key("nano_gpt"),
        "openai":    get_api_key("openai_direct"),
        "gemini":    get_api_key("gemini_direct"),
        "deepseek":  get_api_key("deepseek_direct"),
    }


def _call(model_value: str, system: str, user: str,
          max_tokens: int = 6000, prefill: str = "") -> str:
    keys = _get_keys()
    return call_model(model_value, system, user,
                      anthropic_key=keys["anthropic"],
                      nano_key=keys["nano"],
                      openai_key=keys["openai"],
                      gemini_key=keys["gemini"],
                      deepseek_key=keys["deepseek"],
                      max_tokens=max_tokens,
                      prefill=prefill)


def call_llm(model_value: str, system: str, user: str,
             max_tokens: int = 6000, prefill: str = "") -> str:
    """
    Публичный сырой вызов модели — санкционированная точка входа для web-слоя.

    Существует потому, что web иногда нужен именно одиночный вызов
    (проверка непрерывности, генерация промпта по кнопке), а не целый
    шаг пайплайна. Раньше blueprints импортировали приватный _call,
    что ломало границу слоёв (см. check_architecture.py).

    Для структурированных ответов используй call_json.
    """
    return _call(model_value, system, user, max_tokens=max_tokens, prefill=prefill)


def _execute_steps(
    steps: list[PipelineStep],
    run_id: int, iteration: int,
    project_id: int, chapter_num: int,
    generation_prompt: str,
    model_gen: str, model_critic: str,
    model_editor: str, model_judge: str,
    previous_text: str | None = None,
    previous_critique: str | None = None,
    prefill: str = "",
) -> dict:
    results       = {"iteration": iteration}
    enabled_steps = [s for s in steps if s.enabled]

    # Загружаем проект один раз — жанр нужен нескольким шагам.
    # _genre инициализируется здесь чтобы judge не падал с NameError
    # если запускается без предшествующего шага critique.
    _genre = ""
    try:
        from .db import get_project
        _proj  = get_project(project_id)
        _genre = _proj.get("genre", "") if _proj else ""
    except Exception as e:
        handle_error("_execute_steps get_project", e, level=ErrorLevel.RECOVERABLE)

    for step in enabled_steps:
        if step.name == "generate":
            from .state import strip_empty_placeholders
            clean_prompt = strip_empty_placeholders(generation_prompt)
            full_prompt  = _build_context(project_id, chapter_num, clean_prompt)
            sys_gen      = _build_sys_generator(_genre)

            step_generate(run_id, iteration, chapter_num, generation_prompt,
                          full_prompt, model_gen, sys_gen, _call, results,
                          prefill=prefill)
            gen_text = str(results.get("generated_text", "") or "")
            step_drift_check(project_id, chapter_num,
                             gen_text, model_critic, _call, results)
            step_chapter_analysis(project_id, chapter_num,
                                  gen_text, model_critic, _call, results)

        elif step.name == "edit":
            step_edit(run_id, iteration, generation_prompt,
                      previous_text, previous_critique,
                      model_editor, _call, results)

        elif step.name == "critique":
            step_critique(run_id, iteration, chapter_num,
                          model_critic, _call, results, previous_text or "",
                          project_id=project_id, genre=_genre)

        elif step.name == "prevalidate":
            # Пре-валидация задачи перед генерацией — non-blocking.
            # Добавляет prevalidation_warnings в results, не останавливает pipeline.
            try:
                from .prevalidation import prevalidate_chapter
                pv = prevalidate_chapter(project_id, chapter_num,
                                          generation_prompt, model_critic)
                if not pv.get("ok", True):
                    results["prevalidation_warnings"] = pv.get("blocking", [])
                elif pv.get("warnings"):
                    results["prevalidation_warnings"] = pv.get("warnings", [])
            except Exception as e:
                handle_error("pipeline prevalidate", e, level=ErrorLevel.RECOVERABLE)

        elif step.name == "judge":
            step_judge(run_id, iteration, chapter_num,
                       model_judge, _call, results, previous_text or "",
                       project_id=project_id, genre_key=_genre)

    return results


def run_pipeline_step(
    run_id: int, iteration: int,
    project_id: int, chapter_num: int,
    generation_prompt: str,
    model_gen: str, model_critic: str,
    model_editor: str, model_judge: str,
    previous_text: str = None,
    previous_critique: str = None,
    steps: list[PipelineStep] | None = None,
    prefill: str = "",
) -> dict:
    if steps is None:
        steps = PIPELINE_WITH_EDIT if (previous_text and previous_critique) else DEFAULT_PIPELINE
    return _execute_steps(
        steps=steps, run_id=run_id, iteration=iteration,
        project_id=project_id, chapter_num=chapter_num,
        generation_prompt=generation_prompt,
        model_gen=model_gen, model_critic=model_critic,
        model_editor=model_editor, model_judge=model_judge,
        previous_text=previous_text, previous_critique=previous_critique,
        prefill=prefill,
    )


def _resolve_pipeline_steps(
    steps: list[PipelineStep] | None,
    config: PipelineConfig | None,
) -> list[PipelineStep] | None:
    """
    Определяет итоговый список шагов с учётом настройки prevalidation_enabled.

    Если steps и config не переданы — читаем настройку из БД.
    Если prevalidation_enabled=true → используем PIPELINE_WITH_PREVALIDATE.
    Иначе → DEFAULT_PIPELINE (выбирается в run_pipeline_step).

    Это единственное место где решается "валидировать ли по умолчанию".
    """
    if config is not None:
        return config.to_pipeline_steps()
    if steps is not None:
        return steps
    # steps и config не переданы — смотрим настройку
    try:
        from .db import get_setting
        if get_setting("prevalidation_enabled") == "true":
            return list(PIPELINE_WITH_PREVALIDATE)
    except Exception as e:
        handle_error("_resolve_pipeline_steps", e, level=ErrorLevel.RECOVERABLE)
    return None  # run_pipeline_step выберет DEFAULT_PIPELINE


def start_pipeline(
    project_id: int, chapter_num: int, generation_prompt: str,
    model_gen: str, model_critic: str, model_editor: str, model_judge: str,
    steps: list[PipelineStep] | None = None,
    config: PipelineConfig | None = None,
    prefill: str = "",
) -> dict:
    with log.context(project_id=project_id, chapter_num=chapter_num) as ctx:
        ctx.info("pipeline start", model=model_gen)

    run_id = create_pipeline_run(project_id, chapter_num,
                                  model_gen, model_critic, model_editor, model_judge)
    resolved_steps = _resolve_pipeline_steps(steps, config)

    result = run_pipeline_step(
        run_id=run_id, iteration=1,
        project_id=project_id, chapter_num=chapter_num,
        generation_prompt=generation_prompt,
        model_gen=model_gen, model_critic=model_critic,
        model_editor=model_editor, model_judge=model_judge,
        steps=resolved_steps,
        prefill=prefill,
    )
    result["run_id"] = run_id

    # ── Авто-цикл (IDEA 2): edit→critique→judge при НА ДОРАБОТКУ ─────────────
    max_auto_retries = getattr(config, "max_auto_retries", 0) if config else 0
    if max_auto_retries > 0:
        from .pipeline_config import CONTINUE

        auto_done   = 0
        prev_score  = result.get("judge_score", 0.0)
        continue_steps = _resolve_pipeline_steps(None, CONTINUE)

        while (
            result.get("verdict") == "НА ДОРАБОТКУ"
            and auto_done < max_auto_retries
        ):
            auto_done += 1
            iters = get_pipeline_iterations(run_id)
            next_iter = max((i["iteration"] for i in iters), default=0) + 1

            with log.context(project_id=project_id, chapter_num=chapter_num) as ctx:
                ctx.info(f"pipeline auto-retry {auto_done}/{max_auto_retries}")

            result = run_pipeline_step(
                run_id=run_id, iteration=next_iter,
                project_id=project_id, chapter_num=chapter_num,
                generation_prompt=generation_prompt,
                model_gen=model_gen, model_critic=model_critic,
                model_editor=model_editor, model_judge=model_judge,
                previous_text=result.get("generated_text", ""),
                previous_critique=result.get("critique", ""),
                steps=continue_steps,
            )
            result["run_id"] = run_id

            # Защита от деградации: прерываем если score не растёт
            current_score = result.get("judge_score", 0.0)
            if current_score <= prev_score:
                with log.context(project_id=project_id) as ctx:
                    ctx.info(
                        f"auto-retry прерван: score не улучшился "
                        f"({prev_score} → {current_score})"
                    )
                break
            prev_score = current_score

    return result


def continue_pipeline(
    run_id: int, project_id: int, chapter_num: int,
    generation_prompt: str, previous_text: str, previous_critique: str,
    steps: list[PipelineStep] | None = None,
    config: PipelineConfig | None = None,
) -> dict:
    run   = get_pipeline_run(run_id)
    iters = get_pipeline_iterations(run_id)
    next_iter = max((i["iteration"] for i in iters), default=0) + 1

    with log.context(project_id=project_id, chapter_num=chapter_num) as ctx:
        ctx.info(f"pipeline continue iter={next_iter}")

    resolved_steps = (config.to_pipeline_steps() if config is not None else steps)
    result = run_pipeline_step(
        run_id=run_id, iteration=next_iter,
        project_id=project_id, chapter_num=chapter_num,
        generation_prompt=generation_prompt,
        model_gen=run["model_gen"], model_critic=run["model_critic"],
        model_editor=run["model_editor"], model_judge=run["model_judge"],
        previous_text=previous_text, previous_critique=previous_critique,
        steps=resolved_steps,
    )
    result["run_id"] = run_id
    return result


def accept_pipeline(run_id: int):
    finish_pipeline_run(run_id, "accepted")
    # Записываем judge_score принятой главы для get_project_accept_threshold (IDEA 5).
    # Используется для вычисления проектного стандарта качества.
    try:
        run   = get_pipeline_run(run_id)
        iters = get_pipeline_iterations(run_id)
        # Берём последний judge score из итераций
        judge_iters = [i for i in iters if i.get("stage") == "judge" and i.get("score")]
        if judge_iters and run:
            last_score = judge_iters[-1]["score"]
            from .db_chapters import save_judge_calibration
            # author_score == judge_score при принятии без авторской правки
            save_judge_calibration(
                project_id=run["project_id"],
                chapter_num=run["chapter_num"],
                judge_score=last_score,
                author_score=last_score,
                note="auto_accept",
            )
    except Exception as e:
        handle_error("accept_pipeline threshold_record", e, level=ErrorLevel.RECOVERABLE)


def reject_pipeline(run_id: int):
    finish_pipeline_run(run_id, "rejected")

# ─── Реэкспорт: публичные имена остаются доступны как engine.pipeline.X ───────
#
# Импорт внизу файла — подмодули берут имена отсюда через прокси. Внешние
# импорты вида `from engine.pipeline import run_generation` продолжают
# работать, как и подмены engine.pipeline.<имя> в тестах.

from .pipeline_llm import (          # noqa: E402,F401
    call_json, parse_score, parse_verdict,
    _build_sys_generator, _build_context, _get_resolver_model,
    _make_module_resolver, _make_model_caller,
    _build_consolidated_voice, _extract_relevant_state,
)
from .pipeline_tasks import (        # noqa: E402,F401
    run_generation, score_text, generate_l3,
    generate_director_note_for_chapter, analyze_voice_match,
    find_symbols_in_chapter, run_narrative_analysis,
    get_active_promises_for_project, run_batch_l3,
    check_voice_drift, auto_drift_check_if_needed,
    detect_truncation, describe_truncation, _truncate_context_by_blocks,
)
