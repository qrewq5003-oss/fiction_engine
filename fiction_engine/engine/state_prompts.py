"""
state_prompts.py — сборка промптов для генерации глав.

Отделено от state.py (анализ и CRUD) для снижения CC и MI.
Голос НЕ добавляется здесь — он добавляется в _build_context (pipeline.py),
чтобы избежать дублирования в финальном контексте.
"""

import re
from collections import Counter


def _trunc(text: str, limit: int) -> str:
    """Обрезать текст по лимиту символов, не разрывая слово на середине."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = max(cut.rfind(' '), cut.rfind('\n'))
    return cut[:boundary].rstrip() if boundary > limit // 2 else cut


def build_prompt(project_id: int, chapter_num: int, mode: str, project: dict) -> str:
    """
    Собрать базовый промпт для генерации главы.
    mode: 'quick' | 'quality' | 'master'
    """
    from .db import get_state, get_last_update, parse_structured_state, get_director_note

    state = get_state(project_id)
    last_update = get_last_update(project_id)

    next_context = _extract_next_context(last_update)
    genre = project.get("genre", "[жанр]")
    name  = project.get("name", "[серия]")

    structured = parse_structured_state(state)
    char_prefill = _build_char_prefill(structured)
    director_note = get_director_note(project_id, chapter_num)

    if mode == "quick":
        return _quick_prompt(chapter_num, genre, name, state, next_context, char_prefill, director_note)
    elif mode == "quality":
        return _quality_prompt(chapter_num, genre, name, state, next_context, char_prefill, director_note)
    else:
        return _master_prompt(chapter_num, genre, name, state, next_context, char_prefill, director_note)


def _extract_next_context(last_update: dict | None) -> str:
    """Извлечь блок контекста для следующей главы из последнего обновления."""
    if not last_update:
        return ""
    raw = last_update.get("raw_analysis", "")
    marker = "=== КОНТЕКСТ ДЛЯ СЛЕДУЮЩЕЙ ГЛАВЫ ==="
    if marker not in raw:
        return ""
    return raw.split(marker)[-1].strip()


def _build_char_prefill(structured: dict) -> str:
    """
    Строит строку для автозаполнения блока ПЕРСОНАЖИ В ЭТОЙ ГЛАВЕ
    из структурированного State Engine.
    Если ### ИМЯ паттерна нет — использует фолбэк-парсер свободного текста.
    Если state пустой — возвращает пустую строку (убираем бесполезный шаблон).
    """
    chars = structured.get("characters", {})
    char_names = structured.get("char_names", [])

    if char_names:
        return _prefill_from_structured(chars, char_names)

    raw_state = structured.get("raw", {})
    global_text = raw_state.get("global_state", "").strip() if raw_state else ""
    if not global_text or len(global_text) < 20:
        return ""

    return _prefill_from_freeform(global_text)


def _prefill_from_structured(chars: dict, char_names: list) -> str:
    """Строит prefill из структурированных данных персонажей."""
    lines = []
    for name in char_names[:4]:
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
    return """ЖЁСТКИЕ ЗАПРЕТЫ — ИИ-КЛИШЕ:
Эмоциональные: "сердце сжалось", "внутри что-то оборвалось", "холод пробежал по спине", "время остановилось", "земля ушла из-под ног", "тень улыбки", "в глазах мелькнуло"
Описательные: "танцующие языки пламени", "тишина была оглушительной", "напряжение было осязаемым"
Типографские: тире как пауза перед важным словом → разбей на два предложения; многоточие для значительности → покажи действием; абзац-одиночка не чаще раза в главе; "что-то изменилось" → назвать конкретно что
Нарративные: погода = настроение, мудрость/урок в конце сцены, "он не знал что...", зеркало для описания внешности
Диалоговые: "нам надо поговорить", "обещай что не рассердишься"
- Называть эмоцию напрямую — только через физику тела и действие
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
        return ("ЖАНРОВЫЕ ПРАВИЛА:\n"
                "- Детектив: все лгут — ищи зачем, не что\n"
                "- Нуар: мрачный тон без оправданий, горькие победы\n"
                "- Диалог: минимум атрибуции, подтекст важнее текста\n")
    if any(w in g for w in ["триллер", "thriller"]):
        return ("ЖАНРОВЫЕ ПРАВИЛА:\n"
                "- Напряжение не провисает ни в одном абзаце\n"
                "- Протагонист активен: принимает решения, не только реагирует\n"
                "- Каждая глава заканчивается хуже чем началась\n")
    if any(w in g for w in ["хоррор", "horror", "ужасы"]):
        return ("ЖАНРОВЫЕ ПРАВИЛА:\n"
                "- Страх через ощущения, не через называние\n"
                "- Угроза нарастает постепенно — не взрыв в начале\n"
                "- Что-то теряется в каждой главе\n")
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


def _director_block(note: str | None) -> str:
    if not note:
        return ""
    return f"ЗАМЕТКА ДЛЯ ЭТОЙ ГЛАВЫ (от редактора после предыдущей):\n{note}\n\n"


# ─── Шаблоны промптов ─────────────────────────────────────────────────────────

def _quick_prompt(num, genre, name, state, next_context, char_prefill="", director_note=None):
    genre_id = _genre_identity(genre)
    genre_rules = _genre_rules(genre)
    return f"""# ПРОМПТ: QUICK — Глава {num} / {name}
# Режим: черновик, высокий темп

## ═══ СИСТЕМНЫЙ ПРОМПТ ═══

Ты пишешь {genre_id} на русском языке. Жанр: {genre}.

{_cliche_block()}

{genre_rules}
ОБЪЁМ: СТРОГО 2500-3000 слов. Короче — провал задания. Пиши полную главу.

СТРУКТУРА (2500-3000 слов):
- Первые 200-300 слов: крюк, без предисловий, сразу в действие
- Середина 60%: каждый абзац двигает вперёд — ситуацию или персонажа
- Последние 200-300 слов: поворот или клиффхэнгер

ТЕМП:
- Экшн/напряжение: короткие предложения (5-10 слов)
- Описание/рефлексия: средние (10-20 слов)
- Нет длинных описательных блоков в середине сцены действия

ЗАПРЕЩЕНО:
- Длинное тире (—) в авторской речи, описаниях и ремарках — в диалогах допустимо для обозначения реплики

---

## ═══ ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ ═══

Напиши главу {num}.

КОНТЕКСТ ИЗ ПРЕДЫДУЩЕЙ ГЛАВЫ:
{next_context if next_context else "[заполни: 2-3 предложения где закончилась прошлая глава]"}

ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:
{_trunc(state['global_state'], 900)}

АКТИВНЫЕ СЮЖЕТНЫЕ ЛИНИИ:
{_trunc(state['plot_matrix'], 600)}

ПЕРСОНАЖИ В ЭТОЙ ГЛАВЕ:
{char_prefill}

{_director_block(director_note)}ЗАДАЧА ГЛАВЫ (одно конкретное предложение):
[например: "Кира узнаёт что наставник знал о предательстве"]

СЦЕНЫ:
1. [Место. Что происходит. Чем заканчивается — 2 предложения]
2. [То же]

ТОНАЛЬНОСТЬ: [напряжённая / тихая / экшн / эмоциональная]
ЗАКАНЧИВАЕТСЯ НА: [клиффхэнгер / тихий финал / открытый вопрос]

Объём: СТРОГО 2500-3000 слов (считай абзацы — их должно быть 15-20). Пиши главу целиком без комментариев и без объяснений.
"""


def _quality_prompt(num, genre, name, state, next_context, char_prefill="", director_note=None):
    genre_id = _genre_identity(genre)
    genre_rules = _genre_rules(genre)
    return f"""# ПРОМПТ: QUALITY — Глава {num} / {name}
# Режим: важная глава, поворот, кульминация

## ═══ СИСТЕМНЫЙ ПРОМПТ ═══

Ты пишешь {genre_id} на русском языке. Жанр: {genre}. Высокий стандарт.

{_cliche_block()}

{genre_rules}
ЗАПРЕЩЕНО:
- Объяснять эмоцию после того как она показана действием или деталью
- Называть что символизирует образ или деталь
- Финал с выводом, резюме или прямым называнием смысла
- Называть внутреннее состояние персонажа если оно уже видно через действие
- Длинное тире (—) в авторской речи, описаниях и ремарках — в диалогах допустимо для обозначения реплики

ПОСЛЕДНЯЯ СТРОКА — конкретный образ или физическое действие, не вывод.

ОБЯЗАТЕЛЬНО:
- Каждая сцена меняет знание / отношения / ситуацию
- Первое предложение без вводных конструкций, сразу в действие
- Последнее предложение несёт вес — читатель унесёт его с собой

СТРУКТУРА (2500-3000 слов):
Крюк [150-200] → Нарастание [300-400] → Пик [200-300] → Спад/последствие [300-400] → Финал [150-200]

---

## ═══ ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ ═══

Напиши главу {num}. Тип: [кульминация / поворот / эмоциональная / тихая после кульминации]

КОНТЕКСТ:
{next_context if next_context else "[заполни: что произошло в последних 1-2 главах]"}

СОСТОЯНИЕ МИРА:
{_trunc(state['global_state'], 900)}

АКТИВНЫЕ ЛИНИИ:
{_trunc(state['plot_matrix'], 600)}

ЧТО ПЕРСОНАЖИ ЗНАЮТ:
{_trunc(state['memory_graph'], 450)}

ПЕРСОНАЖИ НА СТАРТЕ ГЛАВЫ:
{char_prefill}

{_director_block(director_note)}ЗАДАЧА ГЛАВЫ (одно предложение, конкретно):
[]

ЧТО МЕНЯЕТСЯ К КОНЦУ:
[]

СЦЕНА 1 [~1000 слов]:
Место: []
Персонажи: []
Что происходит: []
Чем заканчивается: []

СЦЕНА 2 [~1000 слов]:
Место: []
Что происходит: []
Финал главы: [клиффхэнгер / тихий удар / открытый вопрос]

ТОНАЛЬНОСТЬ: []
ДОМИНИРУЮЩЕЕ ОЩУЩЕНИЕ (одно слово): [предательство / одиночество / надежда которая рушится / ...]

Объём: СТРОГО 2500-3000 слов (25-35 абзацев). Пиши целиком. Без комментариев.
"""


def _master_prompt(num, genre, name, state, next_context, char_prefill="", director_note=None):
    genre_id = _genre_identity(genre)
    genre_rules = _genre_rules(genre)
    return f"""# ПРОМПТ: MASTER — Глава {num} / {name}

## ═══ СИСТЕМНЫЙ ПРОМПТ ═══

Ты пишешь {genre_id} на русском языке. Жанр: {genre}. Высший стандарт письма — каждая деталь работает, ничего лишнего.

{genre_rules}
═══ СОСТОЯНИЕ МИРА ═══

{state['global_state']}

Что персонажи знают:
{_trunc(state['memory_graph'], 650)}

Открытые линии:
{_trunc(state['plot_matrix'], 600)}

{_cliche_block()}

ДОПОЛНИТЕЛЬНО ЗАПРЕЩЕНО:
- Объяснять эмоцию после того как она показана
- Называть что символизирует деталь или образ
- Объяснять что "означает" происходящее — читатель понимает сам
- Монолог антагониста объясняющий мотивацию
- Финал с резюме, моралью или прямым выводом
- Длинное тире (—) в авторской речи, описаниях и ремарках — в диалогах допустимо для обозначения реплики

ОБЯЗАТЕЛЬНО:
- Последняя строка — конкретный образ или действие, не вывод
- Физика момента: что ощущает тело, что слышит, что видит — конкретно
- Если что-то "значит" — пусть читатель сам это поймёт

СТРУКТУРА (2500-3000 слов):
Вход [100-150] → Нарастание [600-700] → Кульминация [300-400] → Последствие [400-500]

---

## ═══ ПОЛЬЗОВАТЕЛЬСКИЙ ПРОМПТ ═══

Напиши главу {num}.

ЧТО ПРИВЕЛО К ЭТОМУ МОМЕНТУ:
{next_context if next_context else "[заполни: 3-5 предложений, только факты]"}

{_director_block(director_note)}ЧТО ЧИТАТЕЛЬ ЖДЁТ:
[]

ПЕРСОНАЖИ НА СТАРТЕ ГЛАВЫ:
{char_prefill}

СЦЕНА 1 [~900 слов]:
Место: [конкретно, с одной атмосферной деталью]
Кто: []
Динамика: [кто контролирует ситуацию и как меняется]
Финал сцены: []

СЦЕНА 2 — КУЛЬМИНАЦИЯ [~700 слов]:
Выбор или действие: []
Цена: [что теряется]

СЦЕНА 3 — ПОСЛЕДСТВИЕ [~700 слов]:
Как выглядит мир после: []
Последняя строка: [клиффхэнгер / закрытие / образ]

ЯКОРНЫЕ ДЕТАЛИ (должны быть в главе):
- []

ПОСЛЕ ЭТОЙ ГЛАВЫ НЕВОЗМОЖНО:
[]

Объём: СТРОГО 2500-3000 слов (25-35 абзацев). Пиши целиком. Без предисловий.
"""
