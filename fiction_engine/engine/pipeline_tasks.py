"""
pipeline_tasks.py — самостоятельные операции над главой.

Генерация, оценка, саммари, разбор голоса, символы, обещания. Всё это
вызывается поодиночке, вне цикла критик/редактор/судья, поэтому живёт
отдельно от оркестратора. Выделено из pipeline.py — см. pipeline_llm.
"""

from .engine_loaders_core import ANTICLICHE_HEADER, VOICE_CHECK_HEADER
from .error_policy import (handle_error, ErrorLevel)


# ─── Проксирование через pipeline ─────────────────────────────────────────────
#
# Имена ниже разрешаются на модуле pipeline В МОМЕНТ ВЫЗОВА, а не при импорте.
# Так подмена engine.pipeline.<имя> в тестах продолжает действовать:
# engine.pipeline._call патчится в 85 местах, и связывание при импорте
# сделало бы эти подмены бесполезными.

def _via_pipeline(name):
    def _proxy(*args, **kwargs):
        from . import pipeline
        return getattr(pipeline, name)(*args, **kwargs)
    _proxy.__name__ = name
    return _proxy


_call                = _via_pipeline("_call")
call_json            = _via_pipeline("call_json")
get_prep_context     = _via_pipeline("get_prep_context")
_build_context       = _via_pipeline("_build_context")
_make_model_caller   = _via_pipeline("_make_model_caller")
_build_sys_generator = _via_pipeline("_build_sys_generator")


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
        ([VOICE_CHECK_HEADER],                      "voice_check"),
        ([ANTICLICHE_HEADER],                       "anticliche"),
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

    if not _ends_finished(text):
        msg = (f"Глава обрывается на полуслове: последняя фраза не закончена "
               f"(«…{_tail_for_message(text)}»).")
        import logging; logging.warning(msg)
        return {"truncated": True, "reason": "mid_sentence", "message": msg}

    if word_count < MIN_ACCEPTABLE_WORDS:
        msg = (f"Глава короче требуемого: {word_count} слов "
               f"(промпт требует ~{TARGET_CHAPTER_WORDS}).")
        import logging; logging.warning(msg)
        return {"truncated": True, "reason": "short", "message": msg}

    return {"truncated": False, "reason": "", "message": ""}


# Чем может законно кончаться глава: знак конца фразы, закрывающая кавычка
# или скобка. Разметку и пробелы снимаем перед проверкой.
_TERMINAL_CHARS = ".!?…»\"'”’)]"
_TRAILING_NOISE = " \t\r\n*_~`#-–—"


def _ends_finished(text: str) -> bool:
    """
    Кончается ли текст законченной фразой.

    Отдельная проверка, потому что ни один другой рубеж этого не ловит.
    Провайдер сообщает stop — значит модель закончила сама. Объём в норме.
    А судья к обрыву слеп: проверка 14.09 на пяти главах, срез в одной и
    той же точке (75% текста), разная только граница —

        оригинал              структура 6.4
        обрыв на полуслове    структура 6.4  (+0.0)
        обрыв в предложении   структура 6.2  (-0.2)

    при разбросе 0.8. Глава, оборванная посреди слова, получает ту же
    оценку, что целая; один текст даже вырос с 6 до 8.

    Завершённость — свойство арифметическое, и проверять его надо
    арифметикой, а не спрашивать у языковой модели.
    """
    tail = (text or "").rstrip(_TRAILING_NOISE)
    return bool(tail) and tail[-1] in _TERMINAL_CHARS


def _tail_for_message(text: str, n: int = 40) -> str:
    return (text or "").rstrip()[-n:]


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

    # Замер ритма КРИТИКУ НЕ ПЕРЕДАЁТСЯ — сознательно.
    #
    # Он передавался под заголовком «ДАННЫЕ АНАЛИЗА» прямо перед текстом
    # главы, и критик исправно называл ритм главной проблемой. Замер
    # 14.09.2026 на шести текстах: с подсказкой претензия про ритм в 5
    # случаях из 5, без подсказки — 0 из 5. Сто процентов этих претензий
    # были нашими собственными.
    #
    # Заслоняло оно вот что (те же тексты, тот же судья, без подсказки):
    #   «Глава — это не сцена, а экспозиция, переодетая в сцену»
    #   «Отсутствие сценического момента»
    #   «Обрыв на полуслове — "Ты опозда" без закрытия кавычки»
    # То есть ровно структуру и сцены — два критерия, стоявшие ниже всех.
    #
    # Ритм при этом с оценкой не связан: по 17 текстам r = +0.42, то есть
    # чем БОЛЬШЕ коротких предложений, тем выше оценка. Чинить его ради
    # баллов бессмысленно, и это проверено двумя закрытыми этапами.
    #
    # Сам замер никуда не делся: он возвращается в результате и доступен
    # автору. Он арифметический и в языковой модели не нуждается.
    from .pipeline_config import (CRITIC_TEXT_LIMIT, ACCEPT_TOTAL,
                                  ACCEPT_MIN_CRITERION)
    prompt = f"Глава:\n\n{text[:CRITIC_TEXT_LIMIT]}"

    raw = _call(model_value, sys_critic, prompt, max_tokens=1200)

    # Парсим структурированный ответ критика
    from .pipeline_llm import parse_criterion

    def extract_score(label):
        return parse_criterion(raw, label)

    voice      = extract_score("ГОЛОС")
    structure  = extract_score("СТРУКТУРА")
    characters = extract_score("ПЕРСОНАЖИ")
    scenes     = extract_score("СЦЕНЫ")
    dialog     = extract_score("ДИАЛОГ")

    from .pipeline_llm import parse_score
    total = parse_score(raw) or float(sum([voice, structure, characters, scenes, dialog]))

    # Главная проблема — первый пункт из ГЛАВНЫЕ ПРОБЛЕМЫ.
    # Разбор общий: своя выемка требовала дефис сразу на следующей строке
    # и не совпадала ни разу — критик пишет «## ГЛАВНЫЕ ПРОБЛЕМЫ:», пустую
    # строку и «**1. ...**».
    from .pipeline_llm import parse_first_item
    main_issue = parse_first_item(raw, "ГЛАВНЫЕ ПРОБЛЕМЫ")

    return {
        "voice":      voice,
        "structure":  structure,
        "characters": characters,
        "scenes":     scenes,
        "dialog":     dialog,
        "total":      total,
        "verdict":    ("ПРИНЯТЬ"
                       if total >= ACCEPT_TOTAL
                       and min(voice, structure, characters, scenes, dialog) >= ACCEPT_MIN_CRITERION
                       else "НА ДОРАБОТКУ"),
        "main_issue": main_issue,
        "rhythm":     rhythm,
        "raw":        raw,
    }


def _l3_summary_budget() -> int:
    from .l3_memory import SUMMARY_MAX_TOKENS
    return SUMMARY_MAX_TOKENS


def generate_l3(project_id: int, chapter_num: int,
                text: str, model_value: str) -> object:
    from .l3_memory import generate_l3_summary, SUMMARY_MAX_TOKENS
    return generate_l3_summary(project_id, chapter_num, text,
                                _make_model_caller(model_value, SUMMARY_MAX_TOKENS))


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
    from .pipeline_config import VOICE_TEXT_LIMIT
    SYS = "Ты литературный редактор. Оцени соответствие текста голосовому профилю."
    prompt = (
        f"ПРОФИЛЬ:\n{voice_profile[:800]}\n\n"
        f"ТЕКСТ:\n{text[:VOICE_TEXT_LIMIT]}\n\n"
        "ОЦЕНКА: X/10\n\nСОВПАДАЕТ:\n-\n\nНЕ СОВПАДАЕТ:\n-\n\nИСПРАВИТЬ:\n-"
    )
    result      = _call(model_value, SYS, prompt, max_tokens=800)
    score_match = re.search(r'ОЦЕНКА:\s*(\d+)/10', result)
    return {"analysis": result, "score": int(score_match.group(1)) if score_match else None}


def find_symbols_in_chapter(chapter_text: str, existing_names: list[str],
                             model_value: str) -> dict:
    from .pipeline_config import SYMBOLS_TEXT_LIMIT, SYMBOLS_MAX_TOKENS
    known  = ', '.join(existing_names) if existing_names else 'нет'
    SYS    = "Ты редактор-аналитик. Ищешь символы в тексте. Только JSON."
    prompt = (
        f"Найди символы в главе. УЖЕ ИЗВЕСТНЫ: {known}\n"
        f"ТЕКСТ:\n{chapter_text[:SYMBOLS_TEXT_LIMIT]}\n"
        '{"found":[{"name":"...","type":"...","context":"...","potential_meaning":"...","is_new":true}],"note":"..."}'
    )
    result = call_json(model_value, SYS, prompt, max_tokens=SYMBOLS_MAX_TOKENS)

    # Форма ответа не гарантирована: модель возвращает то объект с "found",
    # то сразу список символов. Веб-слой делает `{"ok": True, **result}` —
    # на списке это TypeError и пятисотка пользователю. Приводим к одной
    # форме здесь, а не надеемся на дисциплину модели.
    if isinstance(result, list):
        return {"found": result, "note": ""}
    if not isinstance(result, dict):
        return {"found": [], "note": "модель вернула неожиданную форму ответа"}
    result.setdefault("found", [])
    return result


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
        # Тот же бюджет, что и у одиночной генерации: пакет делает ровно то же.
        api_call_fn=_make_model_caller(model_value, _l3_summary_budget()),
        chapter_nums=chapter_nums,
        progress_callback=progress_callback,
    )


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
