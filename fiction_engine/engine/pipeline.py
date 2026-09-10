"""
Pipeline: Генерация → Критик → Редактор → Судья → решение.

Этот файл — оркестратор. Не содержит бизнес-логики:
  - Сборка контекста  → pipeline_context.py
  - Шаги pipeline     → pipeline_steps.py
  - Дрейф голоса      → pipeline_drift.py
"""

from dataclasses import dataclass
from typing import Callable

from .api import call_model
from .db import (get_state, get_last_chapters_content, get_api_key,
                  create_pipeline_run, save_pipeline_iteration,
                  finish_pipeline_run, get_pipeline_run, get_pipeline_iterations,
                  get_prep_context, log_error)
from .unified_engine import build_engine_context
from .auto_router import auto_route
from .cognitive_memory import get_cognitive_context
from .error_policy import error_boundary, handle_error, ErrorLevel, PipelineError
from .chapter_analyzer import analyze_chapter_deep, format_analysis_for_prompt
from .logger import get_logger
from .pipeline_config import PipelineConfig, STANDARD, CONTINUE, get_preset
from .pipeline_context import build_context
from .pipeline_steps import (
    step_generate, step_drift_check, step_chapter_analysis,
    step_edit, step_critique, step_judge,
    SYS_CRITIC, SYS_EDITOR, SYS_JUDGE,
)

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


def _get_resolver_model(fallback_model: str) -> str:
    try:
        from .db import get_conn
        with get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='resolver_model'"
            ).fetchone()
        if row and row["value"]:
            return row["value"]
    except Exception as e:
        handle_error("_get_resolver_model", e, level=ErrorLevel.RECOVERABLE)
    return fallback_model


def _make_module_resolver(model_value: str):
    resolver_model = _get_resolver_model(model_value)
    def api_call_fn(prompt: str) -> str:
        return _call(resolver_model,
                     "Ты помощник писателя. Отвечай только валидным JSON без пояснений.",
                     prompt, max_tokens=200)
    return api_call_fn


def _make_model_caller(model_value: str):
    caller_model = _get_resolver_model(model_value)
    def caller(prompt: str) -> str:
        return _call(caller_model, "Ты помощник писателя. Отвечай точно и кратко.",
                     prompt, max_tokens=400)
    return caller


# ─── Системный промпт генератора ──────────────────────────────────────────────

def _build_sys_generator(genre_text: str = "") -> str:
    try:
        from .unified_engine import detect_genre
        genre_key    = detect_genre(genre_text) if genre_text else None
        genre_family = genre_key.split("_")[0] if genre_key else None
    except Exception as e:
        handle_error("_build_sys_generator", e, level=ErrorLevel.RECOVERABLE)
        genre_family = None

    identity_map = {
        "fantasy":   "автор коммерческого фэнтези",
        "detective": "автор детективной прозы",
        "thriller":  "автор психологического триллера",
        "horror":    "автор хоррора",
        "scifi":     "автор научной фантастики",
        "romance":   "автор романтической прозы",
        "realism":   "автор реалистической прозы",
    }
    identity = identity_map.get(genre_family, "профессиональный автор коммерческой прозы")
    return (
        f"Ты — {identity} на русском языке.\n"
        "Пишешь художественный текст высокого качества. Строго следуешь инструкциям промпта.\n"
        "ТРЕБОВАНИЕ К ОБЪЁМУ: глава должна быть 2500-3000 слов. "
        "Если глава короче 2000 слов — это провал задания. Пиши полные развёрнутые сцены.\n"
        "ЗАПРЕЩЕНО АБСОЛЮТНО: длинное тире (—) в авторской речи, описаниях, ремарках. "
        "Длинное тире допустимо ТОЛЬКО внутри прямой речи персонажей для обозначения реплики. "
        "В авторском тексте используй запятые, точки, двоеточия — но не тире.\n"
        "Возвращаешь только текст главы — без заголовков, комментариев и пояснений."
    )


# SYS_GENERATOR не инициализируется глобально — жанр неизвестен на старте.
# _build_sys_generator() вызывается в _execute_steps с реальным жанром проекта.
# Это устраняет бессмысленную константу без жанра которая создавала путаницу.


def parse_score(text: str) -> float:
    import re
    m = re.search(r'ИТОГ:\s*(\d+(?:\.\d+)?)', text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    scores = re.findall(r'(?:ГОЛОС|СТРУКТУРА|ПЕРСОНАЖИ|СЦЕНЫ|ДИАЛОГ):\s*(\d+)', text, re.IGNORECASE)
    return sum(float(s) for s in scores) if scores else 0.0


def parse_verdict(text: str) -> str:
    import re
    m = re.search(r'ВЕРДИКТ:\s*(ПРИНЯТЬ|НА ДОРАБОТКУ)', text, re.IGNORECASE)
    return m.group(1).upper() if m else "НА ДОРАБОТКУ"


# ─── Контекст — делегируем ────────────────────────────────────────────────────

def _build_context(project_id: int, chapter_num: int, base_prompt: str,
                   mode: str = "quick", model_value: str = "",
                   task_text: str = "") -> str:
    """Обёртка для обратной совместимости."""
    api_call_fn = _make_module_resolver(model_value) if mode == "master" else None
    return build_context(project_id, chapter_num, base_prompt,
                         mode, model_value, task_text, api_call_fn)


def _build_consolidated_voice(active_voice, last_chapters, mode):
    from .pipeline_context import build_consolidated_voice
    return build_consolidated_voice(active_voice, last_chapters, mode)


def _extract_relevant_state(state, prompt_text):
    from .pipeline_context import extract_relevant_state
    return extract_relevant_state(state, prompt_text)


# ─── Выполнение шагов ─────────────────────────────────────────────────────────

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


# ─── Публичный API pipeline ───────────────────────────────────────────────────

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


# ─── Voice Drift — делегируем ─────────────────────────────────────────────────

def check_voice_drift(project_id: int, chapter_num: int,
                      chapter_text: str, model_value: str) -> dict:
    from .pipeline_drift import check_voice_drift as _drift
    return _drift(project_id, chapter_num, chapter_text, model_value, _call)


def auto_drift_check_if_needed(project_id: int, chapter_num: int,
                                chapter_text: str, model_value: str) -> dict | None:
    from .pipeline_drift import should_check_drift
    if not should_check_drift(project_id, chapter_num):
        return None
    return check_voice_drift(project_id, chapter_num, chapter_text, model_value)


# ─── Публичный API — web-слой ─────────────────────────────────────────────────

def _truncate_context_by_blocks(context: str,
                                 max_chars: int = 360_000) -> tuple[str, list[str]]:
    """
    Обрезает контекст до max_chars удаляя наименее важные блоки целиком.
    Порядок удаления: exemplars → kb → writing_core → pattern_lib → symbolism
    → voice_check → engine_anticliche → prev_analysis → l3 (частично)

    Возвращает (обрезанный текст, список удалённых блоков).
    Всегда сохраняет: base_prompt, voice, state, engine_rules, prep.
    """
    if len(context) <= max_chars:
        return context, []

    # Маркеры блоков в порядке удаления (наименее важные — первые)
    # Каждый элемент: (список возможных маркеров, имя блока)
    DROP_ORDER = [
        (["ЭТАЛОНЫ", "ГОЛОС — ЭТАЛОН"],           "exemplars"),
        (["БАЗА ЗНАНИЙ"],                           "kb"),
        (["[ТЕХНИКА:", "ТЕХНИКА ПИСЬМА"],           "writing_core"),
        (["ХУКИ И КОНЦОВКИ", "ПАТТЕРНЫ СИТУАЦИЙ"], "pattern_lib"),
        (["СИМВОЛИКА", "СИМВОЛЫ СЕРИИ"],            "symbolism"),
        (["ГОЛОС — ПРОВЕРКА", "VOICE CHECK"],       "voice_check"),
        (["АНТИКЛИШЕ", "ЗАПРЕЩЁННЫЕ ПАТТЕРНЫ"],    "anticliche"),
        (["АНАЛИЗ ГЛАВЫ"],                          "prev_analysis"),
    ]

    result = context
    removed = []

    for markers, name in DROP_ORDER:
        if len(result) <= max_chars:
            break
        # Ищем первый из возможных маркеров
        idx = -1
        for marker in markers:
            pos = result.find(marker)
            if pos >= 0:
                idx = pos
                break
        if idx < 0:
            continue
        # Находим конец блока
        end_patterns = ["\n\n---", "\n\n\n"]
        end_idx = len(result)
        for pat in end_patterns:
            pos = result.find(pat, idx + 10)
            if pos > 0:
                end_idx = min(end_idx, pos)
        result = result[:idx] + result[end_idx:]
        removed.append(name)

    # Если всё ещё слишком большой — обрезаем L3 (оставляем первые 50%)
    if len(result) > max_chars:
        l3_marker = "КОГНИТИВНАЯ ПАМЯТЬ"
        idx = result.find(l3_marker)
        if idx >= 0:
            l3_end = result.find("\n\n\n", idx + 100)
            if l3_end > idx:
                l3_block = result[idx:l3_end]
                result = result[:idx] + l3_block[:len(l3_block)//2] + "...[обрезано]\n" + result[l3_end:]
                removed.append("l3_partial")

    # Последний резерв — грубая обрезка
    if len(result) > max_chars:
        result = result[:max_chars]
        removed.append("hard_cut")

    return result, removed


def detect_truncation(text: str, word_count: int) -> dict:
    """
    Понять, дописана ли глава, и вернуть разбор для интерфейса.

    Возвращает {"truncated": bool, "reason": str, "message": str}:
      reason="max_tokens" — жёсткий обрыв: провайдер сообщил, что упёрся
                            в потолок. Текст оборван буквально на полуслове.
      reason="short"      — модель закончила сама, но объём заметно ниже
                            требуемого промптом.
      reason=""           — всё в порядке.

    Раньше здесь стоял порог в 800 слов при требовании 2500+ — глава,
    обрезанная вдвое, проходила молча. И признак обрыва был только текстом
    в предупреждении: интерфейс не мог на него среагировать кнопкой.
    """
    from .api import get_last_stop_reason
    from .pipeline_config import MIN_ACCEPTABLE_WORDS, TARGET_CHAPTER_WORDS

    if get_last_stop_reason() in ("max_tokens", "length"):
        msg = (f"Глава оборвана: ответ упёрся в потолок max_tokens. "
               f"Написано {word_count} слов из ~{TARGET_CHAPTER_WORDS}.")
        import logging; logging.warning(msg)
        return {"truncated": True, "reason": "max_tokens", "message": msg}

    if word_count < MIN_ACCEPTABLE_WORDS:
        msg = (f"Глава короче требуемого: {word_count} слов "
               f"(промпт требует ~{TARGET_CHAPTER_WORDS}).")
        import logging; logging.warning(msg)
        return {"truncated": True, "reason": "short", "message": msg}

    return {"truncated": False, "reason": "", "message": ""}


def describe_truncation(text: str, word_count: int) -> str:
    """Текстовая обёртка над detect_truncation — для мест, где нужна строка."""
    return detect_truncation(text, word_count)["message"]


def run_generation(project: dict, chapter_num: int, mode: str,
                   model_value: str, task: str) -> dict:
    # get_prep_context уже импортирован на уровне модуля (строка 17).
    # Повторный локальный импорт перекрывал его и делал функцию
    # неподменяемой в тестах — патч engine.pipeline.get_prep_context
    # не действовал, и проверка «Подготовка большая» никогда не срабатывала.
    from .state import build_prompt, strip_empty_placeholders

    project_id = project["id"]
    genre      = project.get("genre", "")
    sys_prompt = _build_sys_generator(genre)

    prep_chars = len(get_prep_context(project_id))
    warning    = f"Подготовка большая ({prep_chars} символов)." if prep_chars > 8000 else None

    # Защита: если task содержит полный промпт (случайно вставили шаблон),
    # очищаем его — иначе промпт дублируется в контексте.
    if task.lstrip().startswith("# ПРОМПТ:") or "═══ СИСТЕМНЫЙ ПРОМПТ ═══" in task:
        import warnings
        warnings.warn("run_generation: task содержит полный промпт — очищаем.")
        task = ""
        warning = (warning or "") + " ⚠ В поле 'Задача главы' был вставлен полный промпт — он очищен. Укажи конкретную задачу для главы."

    base_prompt    = build_prompt(project_id, chapter_num, mode, project)
    full_prompt    = strip_empty_placeholders(f"{base_prompt}\n\n---\nЗАДАЧА ГЛАВЫ:\n{task}")
    context_prompt = _build_context(project_id, chapter_num, full_prompt,
                                    mode, model_value, task_text=task)

    from .pipeline_config import (PROSE_MAX_TOKENS, MIN_ACCEPTABLE_WORDS,
                                  estimate_tokens, TARGET_CHAPTER_WORDS)

    if estimate_tokens(context_prompt) > 90_000:
        context_prompt, truncated = _truncate_context_by_blocks(context_prompt)
        if truncated:
            warning = (warning or "") + f" Контекст обрезан: удалены блоки {truncated}."

    text = _call(model_value, sys_prompt, context_prompt, max_tokens=PROSE_MAX_TOKENS)
    if not text or not text.strip():
        raise RuntimeError("Модель вернула пустой ответ.")
    word_count = len(text.split())
    if len(text.strip()) < 100:
        raise RuntimeError(f"Слишком короткий ответ: {text[:200]}")

    cut = detect_truncation(text, word_count)
    if cut["truncated"]:
        warning = (warning or "") + " " + cut["message"]

    # ── Фоновый анализ главы — замыкаем петлю для следующей генерации ────────
    # RECOVERABLE — не блокирует возврат результата при ошибке.
    # Результат сохраняется в БД и читается в build_context следующей главы.
    try:
        from .pipeline_steps import step_chapter_analysis
        results: dict = {}
        step_chapter_analysis(project_id, chapter_num, text, model_value,
                               lambda m, s, p: _call(m, s, p), results)
    except Exception as e:
        handle_error("run_generation chapter_analysis", e, level=ErrorLevel.RECOVERABLE)

    return {
        "text":      text,
        "warning":   warning,
        "truncated": cut["truncated"],
        "cut_reason": cut["reason"],
        "word_count": word_count,
    }


def call_json(model_value: str, system: str, prompt: str,
              max_tokens: int = 2000) -> dict:
    import json, re

    raw = _call(model_value, system, prompt, max_tokens=max_tokens)

    # 1. Прямой парсинг
    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        pass

    # 2. Убрать <think>...</think> (DeepSeek R1)
    raw_no_think = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
    # Убрать markdown-блоки
    cleaned = re.sub(r'```(?:json)?\s*', '', raw_no_think).strip().rstrip('`').strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Найти JSON по балансу скобок (устойчиво к тексту вокруг)
    start = raw.find('{')
    if start != -1:
        depth, end, in_str, escape = 0, -1, False, False
        for i, ch in enumerate(raw[start:], start):
            if escape:
                escape = False; continue
            if ch == '\\' and in_str:
                escape = True; continue
            if ch == '"':
                in_str = not in_str; continue
            if not in_str:
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1; break
        if end != -1:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass

    raise ValueError(f"Модель не вернула корректный JSON. Ответ: {raw[:300]}")


def score_text(text: str, genre: str, model_value: str) -> dict:
    """
    Оценка текста главы через тот же SYS_CRITIC что использует основной пайплайн.
    Возвращает dict с ключами: voice, structure, characters, scenes, dialog,
    total (0-50), verdict, main_issue, rhythm.

    Раньше: примитивный JSON-промпт с 4 критериями и захардкоженным примером.
    Теперь: полный SYS_CRITIC с жанровой линзой + R05 анализ ритма.
    """
    import re
    from .pipeline_steps import _build_sys_critic, analyze_sentence_rhythm

    sys_critic = _build_sys_critic(genre)

    # R05: программный анализ ритма — передаём как факт, не просим угадывать
    rhythm = analyze_sentence_rhythm(text)
    rhythm_hint = rhythm.get("hint", "")

    prompt_parts = []
    if rhythm_hint:
        prompt_parts.append(f"ДАННЫЕ АНАЛИЗА:\n{rhythm_hint}")
    prompt_parts.append(f"Глава:\n\n{text[:4000]}")
    prompt = "\n\n---\n\n".join(prompt_parts)

    raw = _call(model_value, sys_critic, prompt, max_tokens=1200)

    # Парсим структурированный ответ критика
    def extract_score(label):
        m = re.search(rf"{label}:\s*(\d+)", raw, re.IGNORECASE)
        return int(m.group(1)) if m else 0

    voice      = extract_score("ГОЛОС")
    structure  = extract_score("СТРУКТУРА")
    characters = extract_score("ПЕРСОНАЖИ")
    scenes     = extract_score("СЦЕНЫ")
    dialog     = extract_score("ДИАЛОГ")

    m_total = re.search(r"ИТОГ:\s*(\d+(?:\.\d+)?)", raw)
    total   = float(m_total.group(1)) if m_total else float(sum([voice, structure, characters, scenes, dialog]))

    # Главная проблема — первый пункт из ГЛАВНЫЕ ПРОБЛЕМЫ
    main_issue = ""
    m_problems = re.search(r"ГЛАВНЫЕ ПРОБЛЕМЫ:\s*\n-\s*(.+)", raw)
    if m_problems:
        main_issue = m_problems.group(1).strip()

    return {
        "voice":      voice,
        "structure":  structure,
        "characters": characters,
        "scenes":     scenes,
        "dialog":     dialog,
        "total":      total,
        "verdict":    "ПРИНЯТЬ" if total >= 40 and min(voice, structure, characters, scenes, dialog) >= 7 else "НА ДОРАБОТКУ",
        "main_issue": main_issue,
        "rhythm":     rhythm,
        "raw":        raw,
    }


def generate_l3(project_id: int, chapter_num: int,
                text: str, model_value: str) -> object:
    from .l3_memory import generate_l3_summary
    return generate_l3_summary(project_id, chapter_num, text,
                                _make_model_caller(model_value))


def generate_director_note_for_chapter(project_id: int, chapter_num: int,
                                        text: str, model_value: str) -> str | None:
    from .director_note import generate_director_note
    from .db import get_state
    state = get_state(project_id)
    return generate_director_note(
        project_id, chapter_num, text, state, _make_model_caller(model_value)
    )


def analyze_voice_match(voice_profile: str, text: str, model_value: str) -> dict:
    import re
    SYS = "Ты литературный редактор. Оцени соответствие текста голосовому профилю."
    prompt = (
        f"ПРОФИЛЬ:\n{voice_profile[:800]}\n\n"
        f"ТЕКСТ:\n{text[:2000]}\n\n"
        "ОЦЕНКА: X/10\n\nСОВПАДАЕТ:\n-\n\nНЕ СОВПАДАЕТ:\n-\n\nИСПРАВИТЬ:\n-"
    )
    result      = _call(model_value, SYS, prompt, max_tokens=800)
    score_match = re.search(r'ОЦЕНКА:\s*(\d+)/10', result)
    return {"analysis": result, "score": int(score_match.group(1)) if score_match else None}


def find_symbols_in_chapter(chapter_text: str, existing_names: list[str],
                             model_value: str) -> dict:
    known  = ', '.join(existing_names) if existing_names else 'нет'
    SYS    = "Ты редактор-аналитик. Ищешь символы в тексте. Только JSON."
    prompt = (
        f"Найди символы в главе. УЖЕ ИЗВЕСТНЫ: {known}\n"
        f"ТЕКСТ:\n{chapter_text[:3000]}\n"
        '{"found":[{"name":"...","type":"...","context":"...","potential_meaning":"...","is_new":true}],"note":"..."}'
    )
    return call_json(model_value, SYS, prompt, max_tokens=800)


# ─── Публичные обёртки для web-слоя ──────────────────────────────────────────
# Web-слой не должен импортировать _приватные функции или внутренние модули
# (l3_memory, api, narrative_intelligence напрямую). Эти функции — единственная
# точка входа для соответствующих операций.

def run_narrative_analysis(project_id: int, through_chapter: int,
                           model_value: str) -> object:
    """
    Публичная обёртка для narrative_intelligence.analyze_narrative.
    Web-слой вызывает эту функцию вместо импорта _make_model_caller.
    """
    from .narrative_intelligence import analyze_narrative
    return analyze_narrative(project_id, through_chapter, _make_model_caller(model_value))


def get_active_promises_for_project(project_id: int,
                                   through_chapter: int | None = None,
                                   limit: int = 100) -> list[str]:
    """
    Тексты незакрытых обещаний проекта — публичная замена прямому
    импорту l3_memory.normalize_promises / get_active_promises в web-слое.

    through_chapter=None — учитывать все главы.
    Возвращает список строк, готовый к отдаче в JSON.
    """
    from .db_narrative import get_l3_summaries
    from .l3_memory import normalize_promises, get_active_promises

    before = (through_chapter + 1) if through_chapter is not None else 10 ** 9
    summaries = get_l3_summaries(project_id, before_chapter=before, n=limit)

    collected: list[dict] = []
    for s in summaries:
        raw = s.get("promises")
        if not raw:
            continue
        collected.extend(normalize_promises(raw, s.get("chapter_num", 0)))

    return [p.get("text", "") for p in get_active_promises(collected) if p.get("text")]


def run_batch_l3(project_id: int, model_value: str,
                 chapter_nums: list[int] | None = None,
                 progress_callback=None) -> dict:
    """
    Публичная обёртка для l3_memory.batch_generate_l3.
    Web-слой вызывает эту функцию вместо импорта из l3_memory и api.

    Возвращает {"generated": [...], "skipped": [...], "failed": [...]}.
    """
    from .l3_memory import batch_generate_l3
    return batch_generate_l3(
        project_id=project_id,
        api_call_fn=_make_model_caller(model_value),
        chapter_nums=chapter_nums,
        progress_callback=progress_callback,
    )
