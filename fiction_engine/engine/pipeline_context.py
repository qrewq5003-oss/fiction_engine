"""
pipeline_context.py — сборка контекста для генерации.

Ответственность: State, KB, L3, голос, символы, эталоны, движок.
Не знает о шагах pipeline и API-вызовах.
"""

from .db import (get_state, get_last_chapters_content, get_api_key,
                 get_project, get_active_voice, get_symbols_context,
                 kb_search, kb_get_auto_inject, get_exemplars)
from .cognitive_memory import get_cognitive_context
from .unified_engine import build_engine_context
from .error_policy import handle_error, ErrorLevel
from .logger import get_logger

log = get_logger(__name__)


# ─── Голос ────────────────────────────────────────────────────────────────────

def build_consolidated_voice(active_voice: dict | None,
                              last_chapters: list,
                              mode: str) -> str:
    lines = []

    if active_voice and active_voice.get("profile") and mode in ("quality", "master"):
        profile_short = active_voice["profile"][:500].strip()
        lines.append(f"ГОЛОСОВОЙ ПРОФИЛЬ ({active_voice['name']}):\n{profile_short}")

    if last_chapters:
        sample_size = {"quick": 700, "quality": 400, "master": 300}.get(mode, 500)
        lines.append("ГОЛОС — ЭТАЛОН (последние главы):")
        for ch in last_chapters:
            lines.append(f"[Гл.{ch['number']}]: {ch['content'][:sample_size].strip()}")

    if mode == "master" and active_voice and active_voice.get("source"):
        try:
            from .peak_finales import get_peak_finale
            peak = get_peak_finale(active_voice["source"])
            if peak:
                lines.append(peak)
        except Exception as e:
            handle_error("build_consolidated_voice peak_finale", e, level=ErrorLevel.RECOVERABLE)

    if not lines:
        return ("ГОЛОС — ЭТАЛОН:\n"
                "[Вставь 3-5 предложений из предыдущей главы — эталон голоса]")

    return "\n\n".join(lines)


# ─── Релевантный State ────────────────────────────────────────────────────────

def extract_relevant_state(state: dict, prompt_text: str,
                           api_call_fn=None) -> str:
    import re
    from .db import parse_structured_state_smart

    structured  = parse_structured_state_smart(state, api_call_fn)
    prompt_lower = prompt_text.lower()

    char_names = structured["char_names"]
    relevant   = [
        n for n in char_names
        if any(w in prompt_lower for w in n.lower().split() if len(w) > 2)
    ] or char_names[:4]

    lines = []
    for name in relevant:
        ch    = structured["characters"].get(name, {})
        block = [f"## {name}"]
        if ch.get("state"):    block.append(f"Состояние: {ch['state']}")
        if ch.get("location"): block.append(f"Локация: {ch['location']}")
        if ch.get("goal"):     block.append(f"Цель: {ch['goal']}")
        if ch.get("knows"):    block.append(f"Знает: {ch['knows']}")
        if ch.get("ignores"):  block.append(f"Не знает: {ch['ignores']}")
        lines.append("\n".join(block))

    world = structured["world"]
    if world.get("moment"):    lines.append(f"МОМЕНТ: {world['moment']}")
    if world.get("threat"):    lines.append(f"УГРОЗА: {world['threat']}")
    if world.get("forbidden"): lines.append(f"⚠ НЕЛЬЗЯ: {world['forbidden']}")

    plot = structured["plot"]
    if plot.get("next"):     lines.append(f"СЛЕДУЮЩИЙ ШАГ: {plot['next']}")
    if plot.get("must_not"): lines.append(f"ПОМНИ: {plot['must_not']}")

    if lines:
        return "\n\n".join(lines)

    # Fallback — сырой текст
    raw_global = state.get("global_state", "")
    raw_plot   = state.get("plot_matrix", "")
    blocks     = re.split(r'\n(?=##)', raw_global)
    relevant_blocks = [
        b for b in blocks if b.strip() and (
            not re.match(r'##+ (.+)', b.strip()) or
            any(w in prompt_lower
                for w in (re.match(r'##+ (.+)', b.strip()).group(1).lower().split())
                if len(w) > 2)
        )
    ]
    result = "\n".join(relevant_blocks) if relevant_blocks else raw_global[:600]
    return result + f"\n\nАКТИВНЫЕ ЛИНИИ:\n{raw_plot[:400]}"


# ─── KB блок ─────────────────────────────────────────────────────────────────

def _build_kb_block(project_id: int, task_text: str) -> str:
    try:
        kb_articles = list(kb_get_auto_inject(project_id))
        if task_text:
            seen = {a["id"] for a in kb_articles}
            kb_articles += [a for a in kb_search(project_id, task_text, max_results=2)
                            if a["id"] not in seen]
        if not kb_articles:
            return ""
        budget, parts = 3000, []
        for art in kb_articles[:4]:
            chunk = f"[{art['title']}]\n{art['content'][:budget]}"
            parts.append(chunk)
            budget -= len(chunk)
            if budget <= 0:
                break
        return "\nБАЗА ЗНАНИЙ:\n" + "\n---\n".join(parts) + "\n"
    except Exception as e:
        handle_error(f"_build_kb_block ({project_id})", e, level=ErrorLevel.RECOVERABLE)
        return ""


# ─── Exemplar блок ────────────────────────────────────────────────────────────

def _build_exemplar_block(project_id: int) -> str:
    try:
        exemplars = get_exemplars(project_id)
        if not exemplars:
            return ""
        budget, parts = 1200, []
        for ex in exemplars[:2]:
            chunk = ex["text"][:budget]
            label = f"[{ex['label']}]\n" if ex.get("label") else ""
            parts.append(label + chunk)
            budget -= len(chunk)
            if budget <= 0:
                break
        if not parts:
            return ""
        return (
            "\nЭТАЛОНЫ ГОЛОСА (пиши в этом стиле — не копируй, улавливай):\n"
            + "\n---\n".join(parts) + "\n"
        )
    except Exception as e:
        handle_error(f"_build_exemplar_block ({project_id})", e, level=ErrorLevel.RECOVERABLE)
        return ""


# ─── Engine контекст ─────────────────────────────────────────────────────────

def _build_engine_block(project: dict, mode: str, model_value: str,
                         task_text: str, api_call_fn) -> str:
    if not project:
        return ""
    try:
        from .auto_router import route_by_keywords
        genre_key        = project.get("genre", "")
        pre_selected     = None
        resolver_fn      = api_call_fn

        if mode == "master" and task_text:
            kw_modules, confidence = route_by_keywords(task_text, genre_key)
            if confidence >= 2:
                pre_selected = kw_modules
                resolver_fn  = None

        return build_engine_context(
            genre_key,
            mode,
            model_value=model_value,
            include_dialectics=(mode == "master"),
            task_text=task_text,
            api_call_fn=resolver_fn,
            pre_selected_modules=pre_selected,
        )
    except Exception as e:
        handle_error("_build_engine_block", e, level=ErrorLevel.RECOVERABLE)
        return ""


# ─── Главная функция сборки ───────────────────────────────────────────────────

def build_context(project_id: int, chapter_num: int, base_prompt: str,
                  mode: str = "quick", model_value: str = "",
                  task_text: str = "", api_call_fn=None) -> str:
    """
    Собрать полный контекст для генерации главы.

    Порядок блоков:
      base_prompt → голос → эталоны → KB → L3 → prep → engine → символы → state
    """
    state   = get_state(project_id)
    last    = get_last_chapters_content(project_id, n=2)
    project = get_project(project_id)

    from .db import get_prep_context
    prep = get_prep_context(project_id)

    voice_block    = build_consolidated_voice(get_active_voice(project_id), last, mode)
    exemplar_block = _build_exemplar_block(project_id)
    kb_block       = _build_kb_block(project_id, task_text)
    l3_ctx         = get_cognitive_context(project_id, before_chapter=chapter_num)
    l3_block       = f"\n{l3_ctx}\n" if l3_ctx else ""
    prep_block     = f"\nПОДГОТОВКА АВТОРА:\n{prep}\n" if prep else ""
    engine_ctx     = _build_engine_block(project, mode, model_value, task_text, api_call_fn)
    engine_block   = f"\n{engine_ctx}\n" if engine_ctx else ""
    symbols_ctx    = get_symbols_context(project_id)
    symbols_block  = f"\n{symbols_ctx}\n" if symbols_ctx else ""

    # ── Монотонность структуры (IDEA 4) ──────────────────────────────────────
    # Если последние N глав открываются/закрываются одним паттерном —
    # предупреждаем модель до генерации, чтобы она сделала что-то другое.
    monotony_block = ""
    try:
        from .db import check_structural_monotony
        monotony_warning = check_structural_monotony(project_id, before_chapter=chapter_num)
        if monotony_warning:
            monotony_block = f"\nСТРУКТУРНОЕ ПРЕДУПРЕЖДЕНИЕ:\n{monotony_warning}\nИспользуй другой тип открытия/закрытия главы.\n"
    except Exception as e:
        handle_error("build_context monotony_check", e, level=ErrorLevel.RECOVERABLE)

    # State — только если не задан явно в промпте
    state_markers = [
        "ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ", "СОСТОЯНИЕ МИРА",
        "АКТИВНЫЕ СЮЖЕТНЫЕ ЛИНИИ", "АКТИВНЫЕ ЛИНИИ",
    ]
    if any(m in base_prompt for m in state_markers):
        state_block = ""
    else:
        smart_state = extract_relevant_state(state, base_prompt, api_call_fn)
        state_block = f"\nСОСТОЯНИЕ ПЕРСОНАЖЕЙ:\n{smart_state}\n"

    # ── ChapterAnalysis предыдущей главы — замыкаем петлю ────────────────────
    # logical_gaps и opened_promises из анализа предыдущей главы
    # попадают в контекст генерации следующей.
    prev_analysis_block = ""
    if chapter_num > 1:
        try:
            from .db import get_chapter_analysis
            from .chapter_analyzer import format_analysis_for_prompt, ChapterAnalysis
            prev_data = get_chapter_analysis(project_id, chapter_num - 1)
            if prev_data:
                prev_analysis = ChapterAnalysis(
                    project_id=project_id,
                    chapter_num=chapter_num - 1,
                    arc_progress=prev_data.get("arc_progress", {}),
                    opened_promises=prev_data.get("opened_promises", []),
                    logical_gaps=prev_data.get("logical_gaps", []),
                    conflict_score=prev_data.get("conflict_score", 0.0),
                    pacing_note=prev_data.get("pacing_note", ""),
                )
                formatted = format_analysis_for_prompt(prev_analysis)
                if formatted:
                    prev_analysis_block = f"\n{formatted}\n"
        except Exception as e:
            handle_error("build_context prev_chapter_analysis", e,
                         level=ErrorLevel.RECOVERABLE)

    full_context = f"""{base_prompt}

---
КОНТЕКСТ СЕРИИ:

{voice_block}
{exemplar_block}
{kb_block}
{l3_block}
{prep_block}
{monotony_block}{prev_analysis_block}{engine_block}
{symbols_block}{state_block}"""

    # ── Debug: сохранить промпт в файл для верификации ────────────────────────
    # Включается через env-переменную FICTION_DEBUG=1
    # или через настройку БД: settings key='debug_prompts' value='1'
    _maybe_save_debug_prompt(project_id, chapter_num, mode, full_context)

    return full_context


def _maybe_save_debug_prompt(project_id: int, chapter_num: int,
                              mode: str, prompt: str) -> None:
    """
    Сохраняет итоговый промпт в ~/fiction_engine/prompts_debug/
    если включён debug-режим.

    Включить: Settings → debug_prompts = 1
    Или: export FICTION_DEBUG=1 перед запуском.

    Имя файла: debug_{project_id}_ch{chapter_num}_{mode}_{timestamp}.txt
    Содержит маркеры блоков и размеры для аудита контекста.
    """
    import os
    debug_on = os.environ.get("FICTION_DEBUG", "0") == "1"
    if not debug_on:
        try:
            from .db import get_setting
            debug_on = get_setting("debug_prompts") == "1"
        except Exception as e:
            handle_error("не прочитать флаг debug_prompts", e,
                         level=ErrorLevel.RECOVERABLE)
    if not debug_on:
        return

    try:
        from pathlib import Path
        from datetime import datetime

        debug_dir = Path.home() / "fiction_engine" / "prompts_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"debug_p{project_id}_ch{chapter_num}_{mode}_{ts}.txt"
        out = debug_dir / fname

        # Заголовок с метаданными
        lines = [
            f"# PROMPT DEBUG — project={project_id} chapter={chapter_num} mode={mode}",
            f"# Saved: {datetime.now().isoformat()}",
            f"# Total chars: {len(prompt)}",
            f"# Estimated tokens: ~{len(prompt) // 4}",
            "",
            "# ── БЛОКИ (наличие) ─────────────────────────────────────────────",
        ]
        blocks = {
            "ГОЛОСОВОЙ ПРОФИЛЬ":          "voice_profile",
            "ГОЛОС — ЭТАЛОН":             "voice_samples",
            "ЭТАЛОНЫ":                    "exemplars",
            "БАЗА ЗНАНИЙ":                "knowledge_base",
            "КОГНИТИВНАЯ ПАМЯТЬ":         "cognitive_memory",
            "ПОДГОТОВКА АВТОРА":          "prep",
            "ПРАВИЛА ЖАНРА":              "engine_genre_rules",
            "ПОДЖАНР — обязательно":      "engine_subgenre_labels",
            "ЧИТАТЕЛЬСКИЙ КОНТРАКТ":      "engine_contract",
            "АНТИКЛИШЕ":                  "engine_anticliche",
            "Обещания сюжета":            "cognitive_promises",
            "СИМВОЛИКА":                  "symbolism",
            "СОСТОЯНИЕ ПЕРСОНАЖЕЙ":       "state",
            "АНАЛИЗ ГЛАВЫ":               "prev_chapter_analysis",
            "СТРУКТУРНОЕ ПРЕДУПРЕЖДЕНИЕ": "monotony_warning",
            "[ТЕХНИКА:":                  "writing_core",
            "ХУКИ И КОНЦОВКИ":            "pattern_lib",
        }
        for label, name in blocks.items():
            present = "✓" if label in prompt else "✗"
            lines.append(f"#   {present} {name} ({label!r})")

        lines += ["", "# ── ПОЛНЫЙ ПРОМПТ ───────────────────────────────────────────────", ""]
        lines.append(prompt)

        out.write_text("\n".join(lines), encoding="utf-8")
        log.debug(f"Debug prompt saved: {out}", project_id=project_id, chapter_num=chapter_num)
    except Exception as e:
        log.debug(f"Debug prompt save failed: {e}")
