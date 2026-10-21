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

# Блок движка для генератора пайплайна. QUICK, а не QUALITY, хотя судья
# проверяет главу по контракту жанра: замер 03.10 (bench/ab-pipeline-mode-
# 2026-10-03.json, 4 жанра × 2 прогона) — оценка 7.72 против 7.69 при шуме
# 0.44, контракт и без него выполнен на 9–10 из 10. QUALITY добавлял
# ~25 тыс. символов к каждому вызову без измеримой пользы.
PIPELINE_ENGINE_MODE = "quick"


# ─── Конфигурация шагов ───────────────────────────────────────────────────────

@dataclass
class PipelineStep:
    name: str
    enabled: bool = True
    # Бюджет ответа. None — взять по имени шага из pipeline_config.
    # Раньше поля не было вовсе, и объявленный в StepConfig бюджет
    # терялся при конверсии: глава обрывалась на 6000 токенах.
    max_tokens: int | None = None


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

# Первый проход С РЕДАКТУРОЙ: критика применяется сразу, а не ждёт,
# пока автор нажмёт «продолжить».
#
# Без него штатный результат движка — черновик с диагнозом: критик
# называет конкретные проблемы, и никто их не правит. Замер 19 моделей
# 13.09.2026: ни одна глава не прошла порог принятия, а двенадцать
# главных претензий из четырнадцати — про ритм, который переписыванием
# как раз исправляется (Kimi K2.5: 59% коротких → 14%).
#
# Стоит одного дополнительного вызова модели на прогон. Поэтому набором
# по умолчанию становится только после замера — см. ROADMAP_TEXT.md,
# этап 2.
PIPELINE_GENERATE_AND_EDIT: list[PipelineStep] = [
    PipelineStep("generate"),
    PipelineStep("critique"),
    PipelineStep("edit"),
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

# «Мастерская» с выключенными критиком и судьёй — прежняя страница
# «Генерация»: только писатель. Разбор и оценку можно запросить потом
# (REVIEW_ONLY по готовому тексту).
WRITER_ONLY: list[PipelineStep] = [PipelineStep("generate")]
REVIEW_ONLY: list[PipelineStep] = [PipelineStep("critique"), PipelineStep("judge")]
ENGINE_MODES = ("quick", "quality", "master")


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
    engine_mode: str | None = None,
) -> dict:
    results: dict = {"iteration": iteration}
    engine_mode = engine_mode if engine_mode in ENGINE_MODES else PIPELINE_ENGINE_MODE
    enabled_steps = [s for s in steps if s.enabled]

    # Загружаем проект один раз — жанр нужен нескольким шагам.
    # _genre инициализируется здесь чтобы judge не падал с NameError
    # если запускается без предшествующего шага critique.
    _genre = ""
    try:
        from .db import get_project
        _proj  = get_project(project_id)
        from .unified_engine import project_genre_key
        _genre = project_genre_key(_proj) or ""
    except Exception as e:
        handle_error("_execute_steps get_project", e, level=ErrorLevel.RECOVERABLE)

    for step in enabled_steps:
        # Бюджет ответа этого шага. Шаговые функции зовут call_fn без
        # max_tokens, поэтому раньше действовало умолчание call_model
        # (6000) — глава обрывалась на 2100 словах при требовании 2500.
        from .pipeline_config import step_token_budget
        _budget = step.max_tokens or step_token_budget(step.name)

        def _budgeted(_b=_budget, _op=step.name):
            # Обёртка, а не замена: внутри зовётся модульный _call по имени,
            # поэтому подмена в тестах (monkeypatch pipeline._call) работает
            # как раньше. Шаговые функции вызывают call_fn без max_tokens —
            # бюджет подставляется здесь.
            def call(model_value, system, user, max_tokens=None, prefill=""):
                # Метка шага ставится в контекст, а не передаётся аргументом:
                # десятки тестов подменяют _call своими заглушками с прежней
                # сигнатурой, и лишний параметр их ломает.
                from .api import set_current_operation
                set_current_operation(_op)
                try:
                    return _call(model_value, system, user,
                                 max_tokens=max_tokens or _b, prefill=prefill)
                finally:
                    set_current_operation("")
            return call

        step_call = _budgeted()

        if step.name == "generate":
            from .state import strip_empty_placeholders
            clean_prompt = strip_empty_placeholders(generation_prompt)
            from .engine_issues import collect_engine_issues, engine_issues_note
            with collect_engine_issues() as issues:
                # Режим, модель и задача передаются явно. Раньше блок здесь
                # собирался по умолчанию: бюджет модели «default», а без
                # задачи не подбирались разделы ремесла и паттерны сцен.
                full_prompt = _build_context(project_id, chapter_num, clean_prompt,
                                             engine_mode, model_gen,
                                             task_text=clean_prompt)
            if issues:
                results["engine_issues"] = engine_issues_note(issues)
            from .pipeline_config import context_char_budget
            max_context = context_char_budget(model_gen)
            if len(full_prompt) > max_context:
                full_prompt, trimmed = _truncate_context_by_blocks(
                    full_prompt, max_chars=max_context)
                if trimmed:
                    results["context_trimmed"] = f"Контекст обрезан: удалены блоки {trimmed}."
            sys_gen      = _build_sys_generator(_genre)

            step_generate(run_id, iteration, chapter_num, generation_prompt,
                          full_prompt, model_gen, sys_gen, step_call, results,
                          prefill=prefill)
            gen_text = str(results.get("generated_text", "") or "")
            gen_text, cross = _continuity_pass(run_id, iteration, project_id, chapter_num,
                                               gen_text, model_gen, step_call, results)
            # Повторы относительно прошлых глав проекта — сигнал автору
            from .text_signals import previous_chapters, project_echo_signals, series_signals
            series = (series_signals(gen_text, previous_chapters(project_id, chapter_num)) + cross
                      + project_echo_signals(project_id, gen_text))
            if series:
                results["text_signals"] = list(results.get("text_signals") or []) + series
            step_drift_check(project_id, chapter_num,
                             gen_text, model_critic, step_call, results, model_gen=model_gen)
            step_chapter_analysis(project_id, chapter_num,
                                  gen_text, model_critic, step_call, results)

        elif step.name == "edit":
            step_edit(run_id, iteration, generation_prompt,
                      previous_text, previous_critique,
                      model_editor, step_call, results, model_judge=model_judge,
                      project_id=project_id, chapter_num=chapter_num)
            # Редактор переписывает главу целиком, и проверенный текст
            # перестаёт быть проверенным: у автора 17.10 «Кратохвил» вместо
            # Вавры, «одиннадцать в подвале» вместо двенадцати и «под
            # обезболом» появились только на кругах редактуры, после
            # проверки первого текста
            edited = str(results.get("generated_text", "") or "")
            if edited:
                _continuity_pass(run_id, iteration, project_id, chapter_num,
                                 edited, model_editor, step_call, results)

        elif step.name == "critique":
            step_critique(run_id, iteration, chapter_num,
                          model_critic, step_call, results, previous_text or "",
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
                       model_judge, step_call, results, previous_text or "",
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
    engine_mode: str | None = None,
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
        prefill=prefill, engine_mode=engine_mode,
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
    writer_only: bool = False,
    engine_mode: str | None = None,
) -> dict:
    with log.context(project_id=project_id, chapter_num=chapter_num) as ctx:
        ctx.info("pipeline start", model=model_gen)

    run_id = create_pipeline_run(project_id, chapter_num,
                                  model_gen, model_critic, model_editor, model_judge)
    resolved_steps = list(WRITER_ONLY) if writer_only else _resolve_pipeline_steps(steps, config)

    result = run_pipeline_step(
        run_id=run_id, iteration=1,
        project_id=project_id, chapter_num=chapter_num,
        generation_prompt=generation_prompt,
        model_gen=model_gen, model_critic=model_critic,
        model_editor=model_editor, model_judge=model_judge,
        steps=resolved_steps,
        prefill=prefill,
        engine_mode=engine_mode,
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

    # Судья пристрастен к тексту генератора (Claude судит Claude) — сказать
    # автору. После авто-цикла: он подменяет result
    from .pipeline_config import judge_bias_warning
    bias = judge_bias_warning(model_gen, model_judge)
    if bias:
        result["judge_warning"] = bias
    return result


def preview_writer_prompt(project: dict, chapter_num: int, task: str,
                          engine_mode: str | None = None, model_gen: str = "") -> dict:
    """Промпт писателя целиком, как его соберёт шаг generate (для «👁 Промпт писателя»)."""
    from .state import strip_empty_placeholders
    from .unified_engine import project_genre_key
    mode = engine_mode if engine_mode in ENGINE_MODES else PIPELINE_ENGINE_MODE
    clean = strip_empty_placeholders(task)
    prompt = _build_context(project["id"], chapter_num, clean, mode, model_gen, task_text=clean)
    system = _build_sys_generator(project_genre_key(project) or "")
    return {"prompt": prompt, "system": system, "chars": len(prompt) + len(system)}


def _continuity_pass(run_id, iteration: int, project_id: int, chapter_num: int,
                     text: str, model_gen: str, call, results: dict) -> tuple[str, list[str]]:
    """
    Сверка главы с прошлыми и, если выбран правщик, правка на месте —
    отдельной итерацией, чтобы в истории прогона был виден и текст до правки.
    → (текст, сигналы автору). Проверяющий не выбран — текст как был.
    """
    from .continuity_checker import continuity_fix_model, cross_check_and_fix
    continuity: dict = {}
    fixed, cross = cross_check_and_fix(project_id, chapter_num, text, model_gen, call,
                                       report=continuity)
    if continuity:
        results["continuity"] = continuity
    if fixed != text:
        from .db import save_pipeline_iteration
        save_pipeline_iteration(run_id, iteration, "continuity_fix", continuity_fix_model(),
                                "", fixed)
        results["generated_text"] = fixed
    return fixed, cross


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
    from .pipeline_config import judge_bias_warning
    bias = judge_bias_warning(run["model_gen"], run["model_judge"])
    if bias:
        result["judge_warning"] = bias
    return result


TEXT_STAGES = ("generate", "continuity_fix", "edit")


def pipeline_rounds(iters: list[dict]) -> list[dict]:
    """
    Круги запуска: текст круга (последний из генерации, правки, сверки) и
    оценка судьи этого текста. Круг без нового текста (переоценка) судит
    прежний текст. [{round, text, score, verdict}] по порядку кругов.
    """
    rounds: dict[int, dict] = {}
    text = ""
    for it in sorted(iters, key=lambda i: (i["iteration"], i.get("id") or 0)):
        r = rounds.setdefault(it["iteration"], {"round": it["iteration"], "text": text,
                                                "score": None, "verdict": ""})
        if it["stage"] in TEXT_STAGES and it.get("output_text"):
            text = r["text"] = it["output_text"]
        elif it["stage"] == "judge" and it.get("score"):
            r["score"], r["verdict"] = it["score"], it.get("verdict") or ""
    return [r for r in rounds.values() if r["text"]]


PLAN_SLACK = 2      # баллов судьи, которые уступаются кругу с более полным планом


def best_round(rounds: list[dict]) -> dict | None:
    """
    Лучший круг: «ПРИНЯТЬ» выше доработки, затем балл судьи; при равенстве —
    более поздний. «Фон» (19.10): в главах 10, 21, 22 правка снижала оценку
    (32 «ПРИНЯТЬ» → 29), а «Принять» брал последний круг.

    План: круг, чей текст сверен с планом (r["plan"], plan_check.
    attach_round_checks) и закрывает его полнее, берётся, если вердикт тот же,
    а балл ниже не больше чем на PLAN_SLACK. Пункт «нет» весит больше любого
    числа «частично». Дымовая книга (19.10, гл.1): круг 1 — 33, два пункта
    «частично»; круг 2 — 31, план целиком; брался круг 1, закрытое правкой
    терялось. Текст лучшего по баллу круга не сверен — сравнивать не с чем.
    """
    judged = [r for r in rounds if r["score"]]
    if not judged:
        return None
    top = max(judged, key=lambda r: (r["verdict"] == "ПРИНЯТЬ", r["score"], r["round"]))
    if not top.get("plan"):
        return top
    def gaps(r):
        return r["plan"]["missing"], r["plan"]["partial"]
    near = [r for r in judged if r.get("plan") and gaps(r) < gaps(top)
            and (r["verdict"] == "ПРИНЯТЬ") == (top["verdict"] == "ПРИНЯТЬ")
            and r["score"] >= top["score"] - PLAN_SLACK]
    return min(near, key=lambda r: (gaps(r), -r["score"], -r["round"])) if near else top


def round_of_text(rounds: list[dict], text: str) -> dict | None:
    """Круг, чей текст принимается; None — автор правил текст вручную."""
    return next((r for r in reversed(rounds) if text and r["text"] == text), None)


def accept_pipeline(run_id: int, final_text: str = ""):
    run = get_pipeline_run(run_id)
    if not run:
        return
    finish_pipeline_run(run["project_id"], run_id, "accepted")
    # Строки калибровки судьи здесь больше не пишутся (20.10): «Принять» писал
    # оценку автора, равную оценке судьи, — затирал настоящую оценку автора
    # главы, и судья всегда слышал «твои оценки точны (+0.0)». Калибровка — только
    # из оценок автора (ideas_bp); принятые запуски и так в pipeline_runs.


def reanalyze_accepted(project_id: int, chapter_num: int, run_id: int, final_text: str) -> bool:
    """
    Анализ главы (разрывы, обещания, причинные цепи, тип зачина и концовки —
    chapter_analysis) — заново по принятому тексту, если он не черновик первого
    круга. True — анализ переписан.

    Анализ делается один раз, по черновику (step_chapter_analysis в круге 1), а
    принимается часто круг правки. «Ночная смена» (20.10): правка гл.1 убрала
    ошибку «мы с тобой вдвоём в палате», а в анализе она осталась, и критик гл.3
    упрекал главу «нерешённым разрывом из гл.1». Анализ читают писатель следующей
    главы, проверка непрерывности и предупреждение о монотонности.
    """
    rounds = pipeline_rounds(get_pipeline_iterations(run_id))
    if not (rounds and (final_text or "").strip()) or rounds[0]["text"].strip() == final_text.strip():
        return False
    run = get_pipeline_run(run_id) or {}
    model = run.get("model_critic") or run.get("model_gen")
    if not model:
        return False
    from .chapter_analyzer import analyze_chapter_deep
    analysis = analyze_chapter_deep(project_id, chapter_num, final_text, lambda p: _call(model, "", p))
    return analysis.analysis_quality != "failed"


def reject_pipeline(run_id: int):
    run = get_pipeline_run(run_id)
    if not run:
        return
    finish_pipeline_run(run["project_id"], run_id, "rejected")

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
    get_active_promises_for_project, get_story_so_far, run_batch_l3,
    check_voice_drift, auto_drift_check_if_needed,
    detect_truncation, describe_truncation, extend_short_chapter,
    clean_foreign_words, strip_reasoning,
    _truncate_context_by_blocks,
)
