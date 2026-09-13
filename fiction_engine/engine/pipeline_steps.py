"""
pipeline_steps.py — исполнители отдельных шагов pipeline.

Каждая функция отвечает за один шаг: generate / edit / critique / judge.
Не знает о цикле pipeline — только о своей задаче.

Улучшения v2:
  - step_critique получает контекст проекта (logical_gaps, opened_promises, жанр)
  - step_judge получает историю оценок → числа становятся осмысленными
  - SYS_CRITIC параметризован жанром → хоррор/детектив/романс оцениваются по-разному
"""

from .api import call_model
from .db import save_pipeline_iteration
from .error_policy import handle_error, ErrorLevel
from .logger import get_logger

log = get_logger(__name__)


# ─── R05: Анализ ритма предложений ───────────────────────────────────────────

def analyze_sentence_rhythm(text: str) -> dict:
    """
    R05: Программный подсчёт распределения длин предложений.
    Норма и границы — в pipeline_config (RHYTHM_TARGET, RHYTHM_RANGE,
    RHYTHM_SHORT_MAX, RHYTHM_LONG_MIN). Там же их берёт промпт генерации:
    до 13.09.2026 норму знал только критик, и генератора судили по
    правилу, которого он не видел.
    Возвращает статистику и строку-вывод для промпта критика.
    """
    import re
    sentences = [s.strip() for s in re.split(r'[.!?…]+', text) if len(s.strip()) > 3]
    if not sentences:
        return {"ok": True, "hint": ""}

    lengths = [len(s.split()) for s in sentences]
    total = len(lengths)

    from .pipeline_config import (RHYTHM_SHORT_MAX, RHYTHM_LONG_MIN,
                                  RHYTHM_TARGET, RHYTHM_RANGE)
    short  = sum(1 for l in lengths if l < RHYTHM_SHORT_MAX)
    medium = sum(1 for l in lengths if RHYTHM_SHORT_MAX <= l <= RHYTHM_LONG_MIN)
    long_  = sum(1 for l in lengths if l > RHYTHM_LONG_MIN)

    pct_short  = round(short  / total * 100)
    pct_medium = round(medium / total * 100)
    pct_long   = round(long_  / total * 100)

    # Целевые диапазоны
    ok_short  = RHYTHM_RANGE["short"][0]  <= pct_short  <= RHYTHM_RANGE["short"][1]
    ok_medium = RHYTHM_RANGE["medium"][0] <= pct_medium <= RHYTHM_RANGE["medium"][1]
    ok_long   = RHYTHM_RANGE["long"][0]   <= pct_long   <= RHYTHM_RANGE["long"][1]

    issues = []
    if not ok_short:
        if pct_short < RHYTHM_RANGE["short"][0]:
            issues.append(f"мало коротких предложений ({pct_short}%, цель {RHYTHM_TARGET["short"]}%) — текст монотонен")
        else:
            issues.append(f"слишком много коротких предложений ({pct_short}%, цель 30%) — рубленый ритм")
    if not ok_long:
        if pct_long < RHYTHM_RANGE["long"][0]:
            issues.append(f"мало длинных предложений ({pct_long}%, цель {RHYTHM_TARGET["long"]}%) — нет дыхания")
        else:
            issues.append(f"слишком много длинных предложений ({pct_long}%, цель {RHYTHM_TARGET["long"]}%) — тяжело читать")

    hint = ""
    if issues:
        hint = (
            f"РИТМ ПРЕДЛОЖЕНИЙ (R05): короткие {pct_short}% / средние {pct_medium}% / длинные {pct_long}% "
            f"(цель {RHYTHM_TARGET["short"]}/{RHYTHM_TARGET["medium"]}/{RHYTHM_TARGET["long"]}). Проблемы: {'; '.join(issues)}."
        )
    else:
        hint = (
            f"РИТМ ПРЕДЛОЖЕНИЙ (R05): короткие {pct_short}% / средние {pct_medium}% / длинные {pct_long}% — норма."
        )

    return {
        "short": pct_short, "medium": pct_medium, "long": pct_long,
        "ok": not issues, "issues": issues, "hint": hint
    }


# ─── Жанровые расширения критика ─────────────────────────────────────────────

_GENRE_CRITIC_LENS = {
    "horror": """
ЖАНРОВЫЙ ФОКУС — ХОРРОР:
- Нарастает ли дред? Страх должен накапливаться, а не объясняться.
- Правило потери: герой должен что-то терять в каждой сцене.
- Не описывается ли монстр/угроза слишком подробно (объяснение убивает страх)?
- Есть ли момент «безопасности перед бурей» — ложное успокоение?""",

    "detective": """
ЖАНРОВЫЙ ФОКУС — ДЕТЕКТИВ:
- Информационная асимметрия: что знает читатель vs что знает протагонист?
- Получает ли читатель все улики для самостоятельного вывода?
- Нет ли дешёвых совпадений или удобных случайностей?
- Двигается ли расследование вперёд или топчется на месте?""",

    "romance": """
ЖАНРОВЫЙ ФОКУС — РОМАНС:
- Двигаются ли отношения? Вперёд или назад — оба варианта хороши, стагнация нет.
- Есть ли эмоциональный риск для хотя бы одного персонажа?
- Сексуальное/романтическое напряжение создаётся через действие, не описание?
- Нет ли «томных взглядов» и других готовых клише близости?""",

    "thriller": """
ЖАНРОВЫЙ ФОКУС — ТРИЛЛЕР:
- Тиканье часов: читатель понимает цену промедления?
- Каждая сцена сжимает петлю или добавляет новый уровень угрозы?
- Протагонист в постоянной опасности или слишком комфортен?
- Нет ли информации которую автор придерживает нечестно (не интрига, а обман)?""",

    "fantasy": """
ЖАНРОВЫЙ ФОКУС — ФЭНТЕЗИ:
- Правила мира последовательны? Магия работает по своим законам?
- Мир ощущается живым или только декорацией?
- Нет ли deus ex machina — способностей которые появляются только когда нужны?
- Ставки ощутимы или абстрактны («судьба мира» без личного измерения)?""",

    "scifi": """
ЖАНРОВЫЙ ФОКУС — НФ:
- Идея работает на историю или история на идею?
- Технология/наука интегрирована в поведение персонажей, а не просто описана?
- Нет ли info-dump — экспозиции через лекцию?
- Мир экстраполирован последовательно или только там где удобно?""",
}

_GENRE_CRITIC_DEFAULT = """
ЖАНРОВЫЙ ФОКУС:
- Соответствует ли глава жанровому контракту серии?
- Выполняет ли она главную функцию жанра (страх/загадка/напряжение/отношения)?"""


def _build_sys_critic(genre: str = "") -> str:
    """
    Строит SYS_CRITIC с жанровой вставкой.

    Ключи _GENRE_CRITIC_LENS английские (detective, fantasy, horror…), а
    жанр проекта хранится по-русски («городское фэнтези»). Простое
    .lower().split("_") давало 'городское фэнтези' — промах по таблице и
    молчаливый откат на нейтральную линзу, то есть жанровый фокус критика
    не применялся ни к одному русскоязычному проекту.
    Нормализуем тем же detect_genre, что и остальной движок:
    'детектив' → 'detective_classic' → 'detective'.
    """
    from .unified_engine import detect_genre

    raw = (genre or "").lower()
    genre_key = (detect_genre(raw) or raw).split("_")[0]
    genre_lens = _GENRE_CRITIC_LENS.get(genre_key, _GENRE_CRITIC_DEFAULT)

    return f"""Ты — строгий литературный редактор. Анализируешь текст главы и выявляешь конкретные проблемы.

Оцениваешь по 5 критериям (каждый 0-10):
1. ГОЛОС — уникальность стиля, отсутствие ИИ-клише
2. СТРУКТУРА — темп, крюк, финал, движение
3. ПЕРСОНАЖИ — достоверность, физика эмоций, не называть эмоцию напрямую
4. СЦЕНЫ — конкретность деталей, атмосфера
5. ДИАЛОГ — естественность, подтекст
{genre_lens}

Перед оценкой проверь по чеклисту сцены (Scene Health):
- Меняет ли глава состояние персонажа/мира/отношений? (если нет — структурная проблема)
- Причинно-следственная связь сохранена? (события вытекают друг из друга)
- Эмоциональная цель сцены ясна читателю?
- Есть сенсорный якорь (деталь создающая присутствие)?
- Нет избыточных повторов (те же мысли/действия дважды)?
Нарушения чеклиста фиксируй в СТРУКТУРЕ и СЦЕНАХ.

Запрещённые паттерны которые снижают оценку:
"сердце сжалось", "внутри что-то оборвалось", "холод пробежал по спине",
"время остановилось", "тишина была оглушительной", "танцующие языки пламени",
тире как драматическая пауза, многоточие для значительности,
называть эмоцию напрямую вместо физики тела.

Формат ответа — строго:
ГОЛОС: [0-10] — [1-2 предложения конкретной критики]
СТРУКТУРА: [0-10] — [1-2 предложения]
ПЕРСОНАЖИ: [0-10] — [1-2 предложения]
СЦЕНЫ: [0-10] — [1-2 предложения]
ДИАЛОГ: [0-10] — [1-2 предложения]
ИТОГ: [0-50]
ГЛАВНЫЕ ПРОБЛЕМЫ:
- [конкретная проблема с цитатой из текста]
- [конкретная проблема с цитатой]
- [конкретная проблема]
ЧТО ИСПРАВИТЬ В ПЕРВУЮ ОЧЕРЕДЬ:
[2-3 конкретных действия для редактора]"""


# ─── Редактор и судья (без изменений в системных ролях) ──────────────────────

SYS_CRITIC = _build_sys_critic()  # алиас для обратной совместимости — без жанра

SYS_EDITOR = """Ты — профессиональный редактор и автор. Получаешь оригинальный текст главы и критику редактора.
Переписываешь текст исправляя все указанные проблемы. Сохраняешь сюжет и персонажей.
ЗАПРЕЩЕНО: длинное тире (—) в авторской речи, описаниях, ремарках. Только в прямой речи персонажей.
Возвращаешь только переработанный текст — без комментариев."""

SYS_JUDGE = """Ты — главный редактор серии. Сравниваешь два варианта текста и выносишь финальный вердикт.

Оцениваешь финальный вариант по тем же 5 критериям (0-10 каждый).

Формат ответа — строго:
ГОЛОС: [0-10]
СТРУКТУРА: [0-10]
ПЕРСОНАЖИ: [0-10]
СЦЕНЫ: [0-10]
ДИАЛОГ: [0-10]
ИТОГ: [0-50]
УЛУЧШЕНИЯ: [что стало лучше после редактуры — конкретно]
ОСТАТОК: [что ещё можно улучшить]
ВЕРДИКТ: [ПРИНЯТЬ / НА ДОРАБОТКУ]
ПРАВИЛО ВЕРДИКТА: ПРИНЯТЬ только если ИТОГ ≥ 40 И каждый из 5 критериев ≥ 7 И ни одного нарушения Scene Health чеклиста. Если хоть одно условие не выполнено — НА ДОРАБОТКУ. Не делай исключений.
ОБОСНОВАНИЕ: [1-2 предложения с конкретными числами — почему ПРИНЯТЬ или НА ДОРАБОТКУ]"""

# Системная роль для continuity check — лёгкая, без литературной оценки
_SYS_CONTINUITY_INNER = (
    "Ты — редактор серии, специализирующийся на непрерывности повествования. "
    "Ищешь только конкретные, явные нарушения фактов серии в новой главе. "
    "Не стилистику, не предположения — только то что явно противоречит "
    "установленным фактам. Отвечаешь только валидным JSON без пояснений."
)


# ─── Шаги ────────────────────────────────────────────────────────────────────

def step_generate(run_id: int, iteration: int, chapter_num: int,
                  generation_prompt: str, full_prompt: str,
                  model_gen: str, sys_generator: str,
                  call_fn, results: dict,
                  prefill: str = "") -> None:
    """
    Шаг генерации текста.
    Пишет в results: generated_text, stage.
    prefill — начало ответа модели для продолжения главы.
    """
    from .chapter_analyzer import analyze_chapter_deep, format_analysis_for_prompt

    gen_text = call_fn(model_gen, sys_generator, full_prompt, prefill=prefill) if prefill else call_fn(model_gen, sys_generator, full_prompt)
    save_pipeline_iteration(run_id, iteration, "generate", model_gen,
                             generation_prompt, gen_text)
    results["generated_text"] = gen_text
    results["stage"]          = "generate"

    _flag_truncation(gen_text, results, f"step_generate (ch{chapter_num})")


def step_drift_check(project_id: int, chapter_num: int,
                     gen_text: str, model_critic: str,
                     call_fn, results: dict) -> None:
    """Проверка дрейфа голоса — RECOVERABLE, не блокирует."""
    try:
        from .pipeline_drift import check_voice_drift, should_check_drift
        if not should_check_drift(project_id, chapter_num):
            return
        drift = check_voice_drift(project_id, chapter_num, gen_text, model_critic, call_fn)
        if drift and drift.get("warning"):
            results["drift_warning"] = drift["warning"]
            results["drift_score"]   = drift.get("score")
    except Exception as e:
        handle_error(f"step_drift_check ({project_id}, ch{chapter_num})", e,
                     level=ErrorLevel.RECOVERABLE)


def step_chapter_analysis(project_id: int, chapter_num: int,
                           gen_text: str, model_critic: str,
                           call_fn, results: dict) -> None:
    """Когнитивный анализ главы — RECOVERABLE, фоновый."""
    try:
        from .chapter_analyzer import analyze_chapter_deep, format_analysis_for_prompt
        analysis = analyze_chapter_deep(
            project_id, chapter_num, gen_text,
            lambda p: call_fn(model_critic, "", p)
        )
        if analysis and analysis.analysis_quality != "failed":
            block = format_analysis_for_prompt(analysis)
            if block:
                results["chapter_analysis_block"] = block
            if analysis.logical_gaps:
                results["logical_gaps"] = analysis.logical_gaps
            if analysis.opened_promises:
                results["opened_promises"] = analysis.opened_promises
            # Сохраняем opening/closing type для трекинга структурных паттернов
            if hasattr(analysis, "opening_type") and analysis.opening_type:
                results["opening_type"] = analysis.opening_type
            if hasattr(analysis, "closing_type") and analysis.closing_type:
                results["closing_type"] = analysis.closing_type
    except Exception as e:
        handle_error(f"step_chapter_analysis ({project_id}, ch{chapter_num})", e,
                     level=ErrorLevel.RECOVERABLE)

    # ── Авто-очередь State Engine (IDEA 1) ───────────────────────────────────
    # Ставим State Engine update в pending-очередь без блокировки pipeline.
    # Пользователь видит бейдж «N обновлений State Engine» и применяет одним кликом.
    try:
        from .state import queue_state_update_from_analysis
        queue_state_update_from_analysis(
            project_id, chapter_num, gen_text,
            call_fn=lambda p: call_fn(model_critic, "", p),
        )
    except Exception as e:
        handle_error(
            f"step_chapter_analysis queue_state ({project_id}, ch{chapter_num})",
            e, level=ErrorLevel.RECOVERABLE,
        )


def _flag_truncation(text: str, results: dict, where: str) -> None:
    """
    Отметить в results, что текст не дописан.

    Обрыв по потолку виден только сразу после вызова модели: дальше по
    пайплайну обрезанный текст неотличим от законченного. Флаг доходит до
    интерфейса, чтобы предложить продолжение кнопкой, а не ждать пока
    автор сам заметит обрыв на полуслове.
    """
    try:
        from .pipeline import detect_truncation
        cut = detect_truncation(text, len(text.split()))
        if cut["truncated"]:
            results["truncation_warning"] = cut["message"]
            results["truncated"]  = True
            results["cut_reason"] = cut["reason"]
        else:
            results["truncated"] = False
    except Exception as e:
        handle_error(f"{where}: проверка обрыва", e, level=ErrorLevel.RECOVERABLE)


def step_edit(run_id: int, iteration: int, generation_prompt: str,
              previous_text: str, previous_critique: str,
              model_editor: str, call_fn, results: dict) -> None:
    """
    Шаг редактуры: правит текст по критике.

    Берёт текст и критику ТЕКУЩЕЙ итерации, если они есть, и только иначе —
    предыдущей. До 13.09.2026 он смотрел лишь на предыдущую, поэтому на
    первом проходе не запускался никогда: критик называл конкретные
    проблемы, и никто их не правил, пока автор не нажмёт «продолжить».
    Штатным результатом движка был черновик с диагнозом, а не текст.

    Порядок шагов в профиле DEEP уже был верным
    (generate → critique → edit → judge) — не хватало только того, чтобы
    редактор видел, что сделали два шага перед ним.
    """
    text     = results.get("generated_text") or previous_text
    critique = results.get("critique") or previous_critique
    if not (text and critique):
        return
    rhythm_hint = (results.get("sentence_rhythm") or {}).get("hint", "")
    edit_prompt = (
        f"ОРИГИНАЛЬНЫЙ ТЕКСТ:\n{text}\n\n"
        f"КРИТИКА РЕДАКТОРА:\n{critique}\n\n"
        + (f"ЗАМЕРЕНО: {rhythm_hint}\n\n" if rhythm_hint else "")
        + "Перепиши текст, исправив все указанные проблемы. Сохрани сюжет и персонажей."
    )
    edited_text = call_fn(model_editor, SYS_EDITOR, edit_prompt)
    save_pipeline_iteration(run_id, iteration, "edit", model_editor,
                             generation_prompt, edited_text)
    results["generated_text"] = edited_text
    results["stage"]          = "edit"
    _flag_truncation(edited_text, results, "step_edit")


def step_critique(run_id: int, iteration: int, chapter_num: int,
                  model_critic: str, call_fn, results: dict,
                  previous_text: str = "",
                  project_id: int = 0,
                  genre: str = "") -> None:
    """
    Шаг критического анализа.

    Улучшения v2:
    - SYS_CRITIC строится с жанровой вставкой
    - В промпт добавляется контекст проекта: logical_gaps и opened_promises
      из results (уже заполнены step_chapter_analysis)
    """
    import re

    current_text    = results.get("generated_text", previous_text or "")
    sys_critic      = _build_sys_critic(genre)

    # ── Контекст проекта для критика (ключевое улучшение) ──────────────────
    # logical_gaps и opened_promises попадают в results из step_chapter_analysis.
    # Критик теперь знает что висит незакрытым и может указать: «Марина в этой
    # главе принимает решение которое противоречит её цели из главы 7».
    context_blocks = []

    logical_gaps = results.get("logical_gaps", [])
    if logical_gaps:
        gaps_text = "; ".join(str(g) for g in logical_gaps[:5])
        context_blocks.append(f"ЛОГИЧЕСКИЕ РАЗРЫВЫ (из анализа):\n{gaps_text}")

    opened_promises = results.get("opened_promises", [])
    if opened_promises:
        promises_text = "; ".join(str(p) for p in opened_promises[:5])
        context_blocks.append(f"ОТКРЫТЫЕ ОБЕЩАНИЯ (висят незакрытыми):\n{promises_text}")

    # Дополнительно: загрузить накопленные gaps из прошлых глав (не только текущей)
    if project_id and chapter_num > 1:
        try:
            from .db import get_all_logical_gaps
            past_gaps = get_all_logical_gaps(project_id, before_chapter=chapter_num)
            if past_gaps:
                past_text = "; ".join(
                    f"гл.{g['chapter_num']}: {g['gaps'][0]}"
                    for g in past_gaps[:3] if g.get("gaps")
                )
                if past_text:
                    context_blocks.append(
                        f"НЕЗАКРЫТЫЕ РАЗРЫВЫ ИЗ ПРОШЛЫХ ГЛАВ:\n{past_text}"
                    )
        except Exception as e:
            handle_error(f"step_critique load past gaps ({project_id})", e,
                         level=ErrorLevel.RECOVERABLE)

    # ── Continuity check — кросс-главная проверка непрерывности ────────────
    # Отдельный LLM-вызов: «вот факты серии, вот новая глава — найди нарушения».
    # Запускается только если есть ≥2 прошлых глав с данными.
    if project_id and chapter_num >= 3:
        try:
            from .continuity_checker import check_continuity, format_continuity_for_prompt
            violations = check_continuity(
                project_id, chapter_num, current_text,
                api_call_fn=lambda p: call_fn(model_critic, _SYS_CONTINUITY_INNER, p, max_tokens=600),
            )
            if violations:
                continuity_block = format_continuity_for_prompt(violations)
                if continuity_block:
                    context_blocks.insert(0, continuity_block)  # Первым — самое важное
                results["continuity_violations"] = violations
        except Exception as e:
            handle_error(f"step_critique continuity_check ({project_id}, ch{chapter_num})", e,
                         level=ErrorLevel.RECOVERABLE)

    # ── R05: программный анализ ритма предложений ──────────────────────────
    try:
        rhythm = analyze_sentence_rhythm(current_text)
        if rhythm.get("hint"):
            context_blocks.append(rhythm["hint"])
        results["sentence_rhythm"] = rhythm
    except Exception as e:
        handle_error("step_critique r05_rhythm", e, level=ErrorLevel.RECOVERABLE)

    if context_blocks:
        project_context = "\n\n".join(context_blocks)
        critique_prompt = (
            f"КОНТЕКСТ ПРОЕКТА (используй для оценки персонажей и логики):\n"
            f"{project_context}\n\n"
            f"---\n\n"
            f"Глава {chapter_num}:\n\n{current_text}"
        )
    else:
        critique_prompt = f"Глава {chapter_num}:\n\n{current_text}"

    critique  = call_fn(model_critic, sys_critic, critique_prompt, max_tokens=2000)

    from .pipeline_llm import parse_score
    critic_score = parse_score(critique)

    save_pipeline_iteration(run_id, iteration, "critique", model_critic,
                             current_text, critique, score=critic_score)
    results["critique"]     = critique
    results["critic_score"] = critic_score


def step_judge(run_id: int, iteration: int, chapter_num: int,
               model_judge: str, call_fn, results: dict,
               previous_text: str = "",
               project_id: int = 0,
               genre_key: str = "") -> None:
    """
    Шаг финального вердикта.

    Улучшения v2:
    - Судья получает историю оценок проекта → «38/50 — выше среднего»
      вместо бессмысленного числа в вакууме.
    """
    import re

    current_text = results.get("generated_text", previous_text or "")
    critique     = results.get("critique", "")

    # ── История оценок для контекста судьи ──────────────────────────────────
    score_context = ""
    if project_id:
        try:
            from .db import get_judge_score_history, format_score_history
            history      = get_judge_score_history(project_id, n=10)
            score_context = format_score_history(history, chapter_num)
        except Exception as e:
            handle_error(f"step_judge score_history ({project_id})", e,
                         level=ErrorLevel.RECOVERABLE)

    if previous_text and previous_text != current_text:
        judge_prompt = (
            f"ИСХОДНЫЙ ВАРИАНТ:\n{previous_text}\n\n"
            f"ПЕРЕРАБОТАННЫЙ ВАРИАНТ:\n{current_text}\n\n"
            f"КРИТИКА НА ПЕРЕРАБОТАННЫЙ ВАРИАНТ:\n{critique}\n\n"
            "Вынеси финальный вердикт."
        )
    else:
        judge_prompt = (
            f"ТЕКСТ ГЛАВЫ {chapter_num}:\n{current_text}\n\n"
            f"КРИТИКА:\n{critique}\n\n"
            "Вынеси финальный вердикт."
        )

    # Добавляем историю оценок и calibration hint в системную роль судьи
    sys_judge = SYS_JUDGE
    if score_context:
        sys_judge = SYS_JUDGE + f"\n\nИСТОРИЯ ОЦЕНОК ПРОЕКТА: {score_context}"

    # ── Жанровый чеклист из 10_VALIDATION ───────────────────────────────────
    try:
        from .engine_loaders import _load_validation_checklist
        checklist = _load_validation_checklist(genre_key or None)
        if checklist:
            sys_judge += f"\n\n{checklist}"
    except Exception as e:
        handle_error(f"step_judge validation_checklist", e, level=ErrorLevel.RECOVERABLE)

    # ── Читательский контракт жанра ──────────────────────────────────────────
    # validation_checklist — технические критерии (ритм, структура, клише).
    # genre_contract — что жанр обещает читателю (HEA в романсе, раскрытый
    # убийца в детективе, объяснение угрозы в хорроре). Оба нужны судье.
    # Контракт уже идёт в промпт генерации (unified_engine, quality/master),
    # судья должен проверять то же самое на выходе.
    if genre_key:
        try:
            from .engine_loaders import _load_genre_contract
            contract = _load_genre_contract(genre_key)
            if contract:
                sys_judge += (
                    f"\n\n{contract}"
                    "\n\nПри вынесении ВЕРДИКТ проверь: выполнены ли "
                    "обязательные пункты контракта? Нарушение контракта — "
                    "основание для НА ДОРАБОТКУ независимо от prose score."
                )
        except Exception as e:
            handle_error(f"step_judge genre_contract ({genre_key})", e,
                         level=ErrorLevel.RECOVERABLE)

    # ── Calibration hint: «ты обычно завышаешь на +3.2» ─────────────────
    if project_id:
        try:
            from .db_chapters import get_judge_calibration_hint
            cal_hint = get_judge_calibration_hint(project_id)
            if cal_hint:
                sys_judge += f"\n\nКАЛИБРОВКА: {cal_hint}"
        except Exception as e:
            handle_error(f"step_judge calibration_hint ({project_id})", e,
                         level=ErrorLevel.RECOVERABLE)

    # ── Проектный порог принятия (IDEA 5) ────────────────────────────────────
    if project_id:
        try:
            from .db_chapters import get_project_accept_threshold, format_project_threshold_hint
            threshold_data = get_project_accept_threshold(project_id)
            threshold_hint = format_project_threshold_hint(threshold_data)
            if threshold_hint:
                sys_judge += f"\n\n{threshold_hint}"
        except Exception as e:
            handle_error(f"step_judge threshold_hint ({project_id})", e,
                         level=ErrorLevel.RECOVERABLE)

    judgment = call_fn(model_judge, sys_judge, judge_prompt, max_tokens=2000)

    from .pipeline_llm import parse_score, parse_verdict
    judge_score = parse_score(judgment)
    verdict     = parse_verdict(judgment)

    save_pipeline_iteration(run_id, iteration, "judge", model_judge,
                             current_text, judgment,
                             score=judge_score, verdict=verdict)
    results["judgment"]    = judgment
    results["judge_score"] = judge_score
    results["verdict"]     = verdict

