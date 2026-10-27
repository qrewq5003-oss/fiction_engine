"""
state_prompts.py — сборка промптов для генерации глав.

Отделено от state.py (анализ и CRUD) для снижения CC и MI.
Голос НЕ добавляется здесь — он добавляется в _build_context (pipeline.py),
чтобы избежать дублирования в финальном контексте.
"""

import re
from collections import Counter


# Потолки State в промпте — общие с конвейером (pipeline_context)
from .pipeline_context import (MEMORY_RAW_MAX_CHARS, PLOT_RAW_MAX_CHARS,  # noqa: E402
                               STATE_RAW_MAX_CHARS, note_header)


def _trunc(text: str, limit: int) -> str:
    """Уложить текст в лимит: начало и конец, середина — «[…]», по границам слов.

    Резали хвост: у «Фона» State 23 000 знаков при пороге 12 000 — «Детали
    серии» в конце раздела линий и свежие герои выпадали целиком (разбор 21.10).
    """
    if len(text) <= limit:
        return text
    head_n, tail_n = limit * 2 // 5, limit - limit * 2 // 5 - 5
    head, tail = text[:head_n], text[-tail_n:]
    hb = max(head.rfind(' '), head.rfind('\n'))
    tb = min((i for i in (tail.find(' '), tail.find('\n')) if i >= 0), default=0)
    head = head[:hb].rstrip() if hb > head_n // 2 else head
    tail = tail[tb:].lstrip() if tb < tail_n // 2 else tail
    return f"{head}\n[…]\n{tail}"


def build_prompt(project_id: int, chapter_num: int, mode: str, project: dict) -> str:
    """
    Собрать базовый промпт для генерации главы.
    mode: 'quick' | 'quality' | 'master'
    """
    from .db import get_director_note, get_director_note_source, get_last_update, parse_structured_state
    from .db_state import state_for_chapter

    # State на момент главы и «контекст для следующей» — из применённого анализа
    # прошлой главы. Раньше — State конца книги и последний анализ любой главы,
    # а маркер старого текстового формата в JSON-анализах не находился: вместо
    # «где закончилась прошлая глава» всегда шла заглушка (разбор 21.10)
    state = state_for_chapter(project_id, chapter_num)
    last_update = get_last_update(project_id, before_chapter=chapter_num)

    next_context = _extract_next_context(last_update)
    genre = project.get("genre", "[жанр]")
    name  = project.get("name", "[серия]")

    director_note = get_director_note(project_id, chapter_num)
    # Герои «в этой главе» — названные в плане, а не первые четыре State: у
    # гл.12 «Последнего рейса» шёл мёртвый Зыков и не было троих из плана (разбор 26.10)
    structured = parse_structured_state(state)
    char_prefill = _build_char_prefill(structured, director_note or "")
    note_source = get_director_note_source(project_id, chapter_num)

    template = {"quick": _quick_prompt, "quality": _quality_prompt}.get(mode, _master_prompt)
    prompt = template(chapter_num, genre, name, state, next_context, char_prefill, director_note,
                      note_source=note_source)

    # Тон главы: его раздел и ритм. Строка ритма отсылает к разделу «ТОН ГЛАВЫ»,
    # а в шаблоне его не было — он приходил только с блоком движка (разбор 26.10)
    from .db import get_chapter_tone
    from .genre_mix import load_chapter_tone_section, project_secondary_key, tone_rhythm_note
    tone = get_chapter_tone(project_id, chapter_num)
    note = tone_rhythm_note(tone)
    section = load_chapter_tone_section(tone, project_secondary_key(project)) if tone else ""
    prompt = prompt.replace(RHYTHM_SLOT, f"{section}\n\n{note}".strip())
    return re.sub(r"\n{3,}", "\n\n", prompt)


def _extract_next_context(last_update: dict | None) -> str:
    """Извлечь блок контекста для следующей главы из последнего обновления."""
    if not last_update:
        return ""
    # JSON-анализ и старый текстовый формат — общим разбором (state._extract_next_context)
    from .state import _extract_next_context as from_analysis
    return from_analysis(last_update.get("raw_analysis", "") or "")


def _build_char_prefill(structured: dict, focus: str = "") -> str:
    """
    Строит строку для автозаполнения блока ПЕРСОНАЖИ В ЭТОЙ ГЛАВЕ
    из структурированного State Engine.
    focus — план или заметка к главе: герои, названные в нём, идут первыми
    (до шести); никого не назвал — первые четыре, как раньше.
    Если ### ИМЯ паттерна нет — использует фолбэк-парсер свободного текста.
    Если state пустой — возвращает пустую строку (убираем бесполезный шаблон).
    """
    chars = structured.get("characters", {})
    char_names = structured.get("char_names", [])

    if char_names:
        f = focus.lower()
        named = [n for n in char_names if any(w in f for w in n.lower().split() if len(w) > 2)]
        if named:
            return _prefill_from_structured(chars, named, limit=6)
        return _prefill_from_structured(chars, char_names)

    raw_state = structured.get("raw", {})
    global_text = raw_state.get("global_state", "").strip() if raw_state else ""
    if not global_text or len(global_text) < 20:
        return ""

    return _prefill_from_freeform(global_text)


def _prefill_from_structured(chars: dict, char_names: list, limit: int = 4) -> str:
    """Строит prefill из структурированных данных персонажей."""
    lines = []
    for name in char_names[:limit]:
        ch = chars.get(name, {})
        parts = []
        if ch.get("state"):    parts.append(ch["state"])
        if ch.get("location"): parts.append(f"локация: {ch['location']}")
        if ch.get("goal"):     parts.append(f"цель: {ch['goal']}")
        desc = ". ".join(parts) if parts else ""
        if desc:
            lines.append(f"{name}: {desc}")
    return "\n".join(lines)


_EXCLUDE_WORDS = {
    "Его", "Её", "Они", "Она", "Оно", "Это", "Так", "Вот", "Там", "Тут",
    "Всё", "Уже", "Ещё", "Нет", "Да", "Но", "Как", "Что", "Где", "Когда",
    "Если", "Потому", "Также", "При", "Главный", "Главная", "Первый",
    "Первая", "Новый", "Новая", "Старый", "Старая", "Большой", "Другой",
    "Другая", "Такой", "Такая", "Сам", "Сама", "Один", "Одна", "Весь", "Вся",
}


def _prefill_from_freeform(global_text: str) -> str:
    """Фолбэк: извлекает имена из свободного текста state."""
    candidates = re.findall(r"\b([А-ЯЁ][а-яё]{2,12})\b", global_text)
    counts = Counter(candidates)
    freeform_names = []
    for w, c in counts.items():
        if w in _EXCLUDE_WORDS or len(w) < 3:
            continue
        if c >= 2 or re.search(rf"\b{w}\s+[а-яё]", global_text):
            freeform_names.append(w)
    freeform_names = freeform_names[:4]

    if not freeform_names:
        return ""

    lines = []
    sentences = re.split(r"[.!?]", global_text)
    for name in freeform_names:
        desc = ""
        for s in sentences:
            if name in s:
                desc = s.strip()[:120]
                break
        if desc:
            lines.append(f"{name}: {desc}")
    return "\n".join(lines)


def strip_empty_placeholders(prompt: str) -> str:
    """
    Убирает пустые плейсхолдеры [] из промпта перед отправкой модели.
    Сохраняет [] с содержимым: [например: ...], [клиффхэнгер / ...].
    Убирает осиротевшие заголовки полей значение которых было удалено.
    Вызывается в generate/run — НЕ в /prompt/generate.
    """
    KEEP_HEADERS = {
        'СЦЕНА', '═══',
        # Контекстные заголовки — нельзя удалять даже если следующая строка ## ...
        'ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ', 'АКТИВНЫЕ СЮЖЕТНЫЕ ЛИНИИ',
        'СОСТОЯНИЕ МИРА', 'АКТИВНЫЕ ЛИНИИ', 'КОНТЕКСТ ИЗ ПРЕДЫДУЩЕЙ ГЛАВЫ',
    }
    # '#' убран из SECTION_MARKERS: ## Заголовки внутри стейта — валидный контент,
    # не признак осиротевшего заголовка
    SECTION_MARKERS = {'Объём', 'объём', '---', 'СЦЕНА', 'SCENE'}

    lines = prompt.splitlines()
    p1 = _remove_empty_placeholder_lines(lines)
    p2 = _remove_orphaned_headers(p1, KEEP_HEADERS, SECTION_MARKERS)

    text = '\n'.join(p2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def _remove_empty_placeholder_lines(lines: list[str]) -> list[str]:
    result = []
    for line in lines:
        s = line.strip()
        if re.match(r'^[^[]{2,}:\s*\[\]$', s):
            continue
        if s in ('[]', '- []'):
            continue
        result.append(line)
    return result


def _remove_orphaned_headers(
    lines: list[str],
    keep_headers: set,
    section_markers: set,
) -> list[str]:
    result = []
    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(r'^[^[:\n]{3,}:$', s):
            if any(k in s for k in keep_headers):
                result.append(line)
                continue
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            ns = lines[j].strip() if j < len(lines) else ''
            orphaned = (
                not ns
                or re.match(r'^[^[:\n]{3,}:$', ns)
                or any(ns.startswith(m) for m in section_markers)
                or re.match(r'^СЦЕНА\s+\d', ns)
            )
            if orphaned:
                continue
        result.append(line)
    return result


# ─── Блоки промптов ───────────────────────────────────────────────────────────

def _cliche_block() -> str:
    # Без «ЖЁСТКИХ ЗАПРЕТОВ»: штамп — замена, а не угроза; «эмоцию — только через
    # физику тела» читалось наоборот и звало жесты-реакции (разбор формулировок 26.10)
    return """ИИ-ШТАМПЫ — заменяй своим:
Эмоциональные: "сердце сжалось", "внутри что-то оборвалось", "холод пробежал по спине", "время остановилось", "земля ушла из-под ног", "тень улыбки", "в глазах мелькнуло"
Описательные: "танцующие языки пламени", "тишина была оглушительной", "напряжение было осязаемым"
Типографские: тире как пауза перед важным словом → разбей на два предложения; многоточие для значительности → покажи действием; абзац-одиночка не чаще раза в главе; "что-то изменилось" → назвать конкретно что
Нарративные: погода = настроение, мудрость/урок в конце сцены, "он не знал что...", зеркало для описания внешности
Диалоговые: "нам надо поговорить", "обещай что не рассердишься"
- Эмоцию не называй словом: покажи поступком или деталью
- Финальное предложение с абстрактным обобщением → конкретный образ или действие"""


def _genre_identity(genre: str) -> str:
    """Определить идентификацию жанра по тексту."""
    g = genre.lower()
    if any(w in g for w in ["фэнтези", "fantasy"]):
        return "коммерческое фэнтези"
    if any(w in g for w in ["нуар", "noir", "детектив", "detective"]):
        return "детектив"
    if any(w in g for w in ["триллер", "thriller"]):
        return "триллер"
    if any(w in g for w in ["хоррор", "horror", "ужасы", "ужас"]):
        return "хоррор"
    if any(w in g for w in ["фантастика", "sci-fi", "scifi", "нф", "киберпанк"]):
        return "научную фантастику"
    if any(w in g for w in ["романтика", "роман", "romance"]):
        return "романтическую прозу"
    if any(w in g for w in ["реализм", "проза", "сага"]):
        return "реалистическую прозу"
    return "коммерческую прозу"


def _genre_rules(genre: str) -> str:
    """Жанро-специфичные правила для промпта."""
    g = genre.lower()
    if any(w in g for w in ["нуар", "noir", "детектив"]):
        # «Мрачный тон» — только нуару: любой детектив получал его (разбор базы 26.10)
        noir = any(w in g for w in ["нуар", "noir"])
        # «Детектив: все лгут» убрано: то же точнее говорит правило разговора
        # (своя цель, причина не отдавать сведения), а абсолют спорил с cozy
        return ("ЖАНРОВЫЕ ПРАВИЛА:\n"
                + ("- Нуар: мрачный тон без оправданий, горькие победы\n" if noir else "")
                + "- Диалог: минимум атрибуции, подтекст важнее текста\n")
    if any(w in g for w in ["триллер", "thriller"]):
        # Абсолюты «ни в одном абзаце», «каждая глава» спорили с планом (разбор 26.10)
        return ("ЖАНРОВЫЕ ПРАВИЛА:\n"
                "- Протагонист активен: принимает решения, не только реагирует\n"
                "- Как правило, глава кончается для героя хуже, чем началась; развязка книги — по плану\n")
    if any(w in g for w in ["хоррор", "horror", "ужасы"]):
        return ("ЖАНРОВЫЕ ПРАВИЛА:\n"
                "- Страх через ощущения, не через называние\n"
                "- Угроза нарастает постепенно — не взрыв в начале\n"
                "- Угроза чего-то стоит героям\n")
    if any(w in g for w in ["романтика", "роман", "romance"]):
        return ("ЖАНРОВЫЕ ПРАВИЛА:\n"
                "- Химия показана, не объявлена\n"
                "- Каждая глава двигает отношения вперёд или назад\n"
                "- HEA/HFN — контракт с читателем, не опция\n")
    if any(w in g for w in ["реализм", "проза"]):
        return ("ЖАНРОВЫЕ ПРАВИЛА:\n"
                "- Финал без морали — читатель делает выводы сам\n"
                "- Событие может быть малым, эмоциональный вес — огромным\n"
                "- Диалог мимо: говорят об одном, думают о другом\n")
    return ""


def _director_block(note: str | None, source: str | None = None) -> str:
    """Заметка к главе под заголовком по источнику (pipeline_context.note_header)."""
    if not note:
        return ""
    from .plan_check import plan_writer_lines
    end = plan_writer_lines(note)
    return f"{note_header(source)}\n{note}\n\n" + (f"{end}\n\n" if end else "")


def _has_scene_plan(note: str | None) -> bool:
    """У главы план со сценами: скелет «СЦЕНЫ» и меню финала шаблона с ним спорят —
    кнопка без плана так сочиняла свою главу рядом с планом (CHANGELOG 20.10)."""
    from .plan_check import plan_end_line
    return bool(note and plan_end_line(note))


# ─── Шаблоны промптов ─────────────────────────────────────────────────────────

# ─── Объём главы ──────────────────────────────────────────────────────────────
#
# Все три промпта просят 2500-3000 слов одной формулировкой. Два решения
# внутри неё стоят на замерах 2026-09-12 (Claude Haiku 4.5 и Sonnet 4.6,
# один и тот же сюжет, бюджет 11730 токенов — в него ни разу не упёрлись,
# stop_reason всегда 'end_turn'):
#
#   голый запрос «2500-3000 слов»                 1599 слов
#   + разбивка на три сцены в одном вызове        1668
#   + самопроверка «написано ли уже 2500?»        1925   ← +20%
#   то же на sonnet-4-6                           2598   ← цель взята
#
# 1. САМОПРОВЕРКА добавлена во все три. Из проверенных формулировок она
#    единственная дала прирост; разбивка на сцены — нет.
#
# 2. ЧИСЛА АБЗАЦЕВ нет (27.10). В сентябре 15-20 и 25-35 выровняли, но
#    модели пишут 58-86 абзацев по 20-30 слов и подсказку игнорируют, а с
#    голосом автора («абзац — до пяти предложений») 25-35 спорило.
#
# Настоящая причина недобора в другом и промптом не лечится: модели
# систематически недодают по объёму. Haiku упирается около 1900-2000 за
# вызов, как ни проси; сильные модели (Опус, Sonnet 5.5 с самопроверкой)
# берут объём сами, короткую законченную главу движок дописывает.

def _scene_words(weights, i: int) -> int:
    """
    Слова i-й сцены. Считаются от требования к объёму, а не вписаны руками.

    Прежние числа не сходились с требованием: 900+700+700=2300 в master и
    1000+1000=2000 в quality при «СТРОГО 2500-3000 слов». Модель следует
    расписанному по сценам, а не общему требованию.
    """
    from .pipeline_config import scene_word_budget
    return scene_word_budget(weights)[i]


def _volume_block() -> str:
    """Требование к объёму — из pipeline_config, не литералом."""
    from .pipeline_config import volume_rule_for_prompt
    return volume_rule_for_prompt()


def _volume_check() -> str:
    from .pipeline_config import volume_check_for_prompt
    return volume_check_for_prompt()


def _detail_block() -> str:
    """Правило о деталях — из pipeline_config, не копией (см. историю с ритмом)."""
    from .pipeline_config import detail_rule_for_prompt
    return detail_rule_for_prompt()


def _rhythm_block() -> str:
    """
    Правило ритма — то же, по которому текст потом оценивают.

    До 13 сентября 2026 генератору его не показывали ни в одном режиме:
    в quick стояло противоположное («Экшн/напряжение: короткие предложения
    5-10 слов»), в quality про ритм не было ни слова, в master одно
    упоминание. Критик при этом считал распределение арифметикой и снижал
    оценку. Двенадцать главных претензий из четырнадцати в замере 19
    моделей — именно про это.

    Берётся из pipeline_config, а не переписывается здесь: копия разошлась
    бы, как разошлось число абзацев.

    С 27.10 общей нормы 30/50/20 писателю нет: инструкция ни разу не сдвинула
    ритм (64 % → 68 %), спорила со стилем серии, а в авторской речи коротких и так
    29–52 % — норма «по всей главе» считала реплики (разбор 26.10). Здесь — место:
    build_prompt ставит в него ритм тона главы, если он задан, иначе убирает.
    Рубленые куски находит код и отдаёт редактору (text_signals.short_runs).
    """
    return RHYTHM_SLOT


RHYTHM_SLOT = "⟦РИТМ ГЛАВЫ⟧"


def _em_dash() -> str:
    """Правило автора о тире — из pipeline_config, одно на всех."""
    from .pipeline_config import EM_DASH_RULE
    return EM_DASH_RULE


def _dialogue_block() -> str:
    """Правило разговора — из pipeline_config, как ритм и детали."""
    from .pipeline_config import dialogue_rule_for_prompt
    return dialogue_rule_for_prompt()


def _structure_block() -> str:
    """Правило структуры главы — из pipeline_config, как ритм и детали."""
    from .pipeline_config import structure_rule_for_prompt
    return structure_rule_for_prompt()


def _quick_prompt(num, genre, name, state, next_context, char_prefill="", director_note=None,
                  note_source=None):
    genre_id = _genre_identity(genre)
    genre_rules = _genre_rules(genre)
    # С планом со сценами скелет сцен и меню финала не выводятся: конец задаёт план
    skeleton = "" if _has_scene_plan(director_note) else """СЦЕНЫ:
1. [Место. Что происходит. Чем заканчивается — 2 предложения]
2. [То же]

ТОНАЛЬНОСТЬ: [напряжённая / тихая / экшн / эмоциональная]
ЗАКАНЧИВАЕТСЯ НА: [событие или состояние героя — не вывод]

"""
    # Без «Режим: черновик, высокий темп» (QUICK — основной режим, темп задаёт тон
    # главы), «провала задания» и объёма трижды; детали и ритм — по разу (были дважды)
    return f"""# ПРОМПТ: QUICK — Глава {num} / {name}

## ═══ СИСТЕМНЫЙ ПРОМПТ ═══

Ты пишешь {genre_id} на русском языке. Жанр: {genre}.

{_cliche_block()}

{genre_rules}
СТРУКТУРА:
- Первые 200-300 слов: крюк, без предисловий, сразу в действие
- Нет длинных описательных блоков в середине сцены действия
- Конец — последняя сцена плана или задачи; крючок, если его просит стиль, — внутри неё

ЗАПРЕЩЕНО:
- {_em_dash()}

---

## ═══ ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ ═══

Напиши главу {num}.

КОНТЕКСТ ИЗ ПРЕДЫДУЩЕЙ ГЛАВЫ:
{next_context if next_context else "[заполни: 2-3 предложения где закончилась прошлая глава]"}

ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:
{_trunc(state['global_state'], STATE_RAW_MAX_CHARS)}

АКТИВНЫЕ СЮЖЕТНЫЕ ЛИНИИ:
{_trunc(state['plot_matrix'], PLOT_RAW_MAX_CHARS)}

ПЕРСОНАЖИ В ЭТОЙ ГЛАВЕ:
{char_prefill}

{_director_block(director_note, note_source)}ЗАДАЧА ГЛАВЫ (одно конкретное предложение):
[например: "Кира узнаёт что наставник знал о предательстве"]

{skeleton}{_detail_block()}

{_rhythm_block()}

{_dialogue_block()}

{_structure_block()}

Объём: {_volume_block()}. {_volume_check()} Пиши главу целиком без комментариев и без объяснений.
"""


def _quality_prompt(num, genre, name, state, next_context, char_prefill="", director_note=None,
                    note_source=None):
    genre_id = _genre_identity(genre)
    genre_rules = _genre_rules(genre)
    skeleton = "" if _has_scene_plan(director_note) else f"""СЦЕНА 1 [~{_scene_words((1,1), 0)} слов]:
Место: []
Персонажи: []
Что происходит: []
Чем заканчивается: []

СЦЕНА 2 [~{_scene_words((1,1), 1)} слов]:
Место: []
Что происходит: []
Финал главы: [событие или состояние героя — не вывод]

"""
    # Без подписи режима и «Высокого стандарта», без трёх лишних формулировок
    # финала и чисел частей (сумма 1100–1500 при 2500–3000; модель следует
    # расписанному по частям — pipeline_config.scene_word_budget)
    return f"""# ПРОМПТ: QUALITY — Глава {num} / {name}

## ═══ СИСТЕМНЫЙ ПРОМПТ ═══

Ты пишешь {genre_id} на русском языке. Жанр: {genre}.

{_cliche_block()}

{genre_rules}
ЗАПРЕЩЕНО:
- Объяснять эмоцию после того как она показана действием или деталью
- Называть что символизирует образ или деталь
- Финал с выводом, резюме или прямым называнием смысла
- {_em_dash()}

ОБЯЗАТЕЛЬНО:
- Каждая сцена меняет знание / отношения / ситуацию
- Первое предложение без вводных конструкций, сразу в действие

СТРУКТУРА: крюк → нарастание → пик → последствие → конец главы

---

## ═══ ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ ═══

Напиши главу {num}. Тип: [кульминация / поворот / эмоциональная / тихая после кульминации]

КОНТЕКСТ:
{next_context if next_context else "[заполни: что произошло в последних 1-2 главах]"}

СОСТОЯНИЕ МИРА:
{_trunc(state['global_state'], STATE_RAW_MAX_CHARS)}

АКТИВНЫЕ ЛИНИИ:
{_trunc(state['plot_matrix'], PLOT_RAW_MAX_CHARS)}

ЧТО ПЕРСОНАЖИ ЗНАЮТ:
{_trunc(state['memory_graph'], MEMORY_RAW_MAX_CHARS)}

ПЕРСОНАЖИ НА СТАРТЕ ГЛАВЫ:
{char_prefill}

{_director_block(director_note, note_source)}ЗАДАЧА ГЛАВЫ (одно предложение, конкретно):
[]

ЧТО МЕНЯЕТСЯ К КОНЦУ:
[]

{skeleton}ТОНАЛЬНОСТЬ: []
ДОМИНИРУЮЩЕЕ ОЩУЩЕНИЕ (одно слово): [предательство / одиночество / надежда которая рушится / ...]

{_detail_block()}

{_rhythm_block()}

{_dialogue_block()}

{_structure_block()}

Объём: {_volume_block()}. {_volume_check()} Пиши целиком. Без комментариев.
"""


def _master_prompt(num, genre, name, state, next_context, char_prefill="", director_note=None,
                   note_source=None):
    genre_id = _genre_identity(genre)
    genre_rules = _genre_rules(genre)
    skeleton = "" if _has_scene_plan(director_note) else f"""СЦЕНА 1 [~{_scene_words((9,7,7), 0)} слов]:
Место: [конкретно, через деталь, которую персонаж задевает или ощущает]
Кто: []
Динамика: [кто контролирует ситуацию и как меняется]
Финал сцены: []

СЦЕНА 2 — КУЛЬМИНАЦИЯ [~{_scene_words((9,7,7), 1)} слов]:
Выбор или действие: []
Цена: [что теряется]

СЦЕНА 3 — ПОСЛЕДСТВИЕ [~{_scene_words((9,7,7), 2)} слов]:
Как выглядит мир после: []
Последняя строка: [событие или состояние героя — не вывод]

"""
    # Без «высшего стандарта» (так само приложение описывает плохую установку —
    # director_note), дублей и чисел частей, не сходившихся с объёмом и сценами
    return f"""# ПРОМПТ: MASTER — Глава {num} / {name}

## ═══ СИСТЕМНЫЙ ПРОМПТ ═══

Ты пишешь {genre_id} на русском языке. Жанр: {genre}.

{genre_rules}
═══ СОСТОЯНИЕ МИРА ═══

{state['global_state']}

Что персонажи знают:
{_trunc(state['memory_graph'], MEMORY_RAW_MAX_CHARS)}

Открытые линии:
{_trunc(state['plot_matrix'], PLOT_RAW_MAX_CHARS)}

{_cliche_block()}

ДОПОЛНИТЕЛЬНО ЗАПРЕЩЕНО:
- Объяснять эмоцию после того как она показана
- Называть что символизирует деталь или образ
- Объяснять что "означает" происходящее — читатель понимает сам
- Монолог антагониста объясняющий мотивацию
- Финал с резюме, моралью или прямым выводом
- {_em_dash()}

ОБЯЗАТЕЛЬНО:
- Место и вещи — через то, что персонаж трогает, слышит, видит, конкретно

СТРУКТУРА: вход → нарастание → кульминация → последствие

---

## ═══ ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ ═══

Напиши главу {num}.

ЧТО ПРИВЕЛО К ЭТОМУ МОМЕНТУ:
{next_context if next_context else "[заполни: 3-5 предложений, только факты]"}

{_director_block(director_note, note_source)}ЧТО ЧИТАТЕЛЬ ЖДЁТ:
[]

ПЕРСОНАЖИ НА СТАРТЕ ГЛАВЫ:
{char_prefill}

{skeleton}ЯКОРНЫЕ ДЕТАЛИ (должны быть в главе):
- []

ПОСЛЕ ЭТОЙ ГЛАВЫ НЕВОЗМОЖНО:
[]

{_detail_block()}

{_rhythm_block()}

{_dialogue_block()}

{_structure_block()}

Объём: {_volume_block()}. {_volume_check()} Пиши целиком. Без предисловий.
"""
