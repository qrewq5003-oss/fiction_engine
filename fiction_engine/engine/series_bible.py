"""
series_bible.py — библия серии: места, вещи и время событий с историей.

Зачем. Детали серии (до 8 на главу, db_state) не помогли: модель выписывает
то, что ей кажется важным, — плащ, аптеку, машину, — а ломается потом другое.
Этаж квартиры вдовы, который в следующей главе стал третьим, а потом
четвёртым, в детали не попал ни у DeepSeek, ни у Kimi (14.10). Реестр имён
сработал (смен отчества 10 → 0), потому что держит сущность и её атрибут, а не
случайную деталь, и идёт генератору отдельным блоком «пиши ровно так».

Библия — так же: карточки «место / вещь / событие» с атрибутами (этаж, адрес,
вид, чья, где лежит, день, время). Анализ главы дописывает их; уже известные
сущности он получает списком и называет так же.

Запись не перезаписывается никогда. Факт законно меняется по сюжету
(переехала, отдала нож) — новая запись с причиной, прежняя остаётся в
истории. Факт сменился без события — это противоречие: в библию как текущее
значение не идёт, записывается отдельно и становится сигналом автору.
"""

from __future__ import annotations

import datetime
import re

from .db_core import get_conn

KINDS = ("место", "вещь", "событие", "персонаж")
BLOCK_MAX = 40          # строк в блоке генератору
KNOWN_MAX = 60          # сущностей в подсказке анализу


def _ensure() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS series_bible (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL REFERENCES projects(id),
                kind        TEXT NOT NULL,
                name        TEXT NOT NULL,
                attr        TEXT NOT NULL,
                value       TEXT NOT NULL,
                chapter_num INTEGER NOT NULL DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'введено',   -- введено | уточнено | дополнено | изменено | противоречие | автор
                reason      TEXT NOT NULL DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bible_project ON series_bible(project_id)")


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip(" .«»\"")


# Различающие слова: если они расходятся — это другое значение, а не уточнение.
# Порядковые — только с окончанием порядкового: «пятно», «вторник», «четверг»
# порядковыми не считаются. Длинные основы раньше коротких.
_ORD_STEMS = (("одиннадцат", 11), ("двенадцат", 12), ("тринадцат", 13), ("четырнадцат", 14),
              ("пятнадцат", 15), ("шестнадцат", 16), ("семнадцат", 17), ("восемнадцат", 18),
              ("девятнадцат", 19), ("двадцат", 20), ("тридцат", 30), ("перв", 1), ("втор", 2),
              ("трет", 3), ("четверт", 4), ("пят", 5), ("шест", 6), ("седьм", 7), ("восьм", 8),
              ("девят", 9), ("десят", 10))
_ORD_END = r"(?:ый|ий|ой|ая|ое|ую|ого|ому|ом|ые|ых|ым|ыми|ья|ье|ьи|ью|ьего|ьему|ьей|ьем|ьих)"
_ORD = re.compile(r"\b(?:(двадцать|тридцать)\s+)?(" + "|".join(s for s, _ in _ORD_STEMS) + ")" + _ORD_END + r"\b")
_ORD_NUM = dict(_ORD_STEMS)
_COLOR = re.compile(r"\b(бел|черн|красн|син|зелен|желт|сер|коричнев|бур|голуб|розов|фиолет|оранж|рыж|"
                    r"бордов|бежев|золот|серебр)\w*")
_DAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
_DAY = re.compile(r"\b(понедельник|вторник|сред|четверг|пятниц|суббот|воскресень)\w*")
_MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря")
_MONTH = re.compile(r"(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)\w*")


def _ordn(tens: str | None, stem: str) -> int:
    """«двадцать», «пят(ое)» → 25; tens — «двадцать»/«тридцать» или None."""
    return _ORD_NUM[stem] + {"двадцать": 20, "тридцать": 30}.get(tens or "", 0)


def _day(stem: str) -> str:
    return next(d for d in _DAYS if d.startswith(stem))


def _marks(v: str) -> set[str]:
    # Порядковые — числом: «третий» и «3-й» одно и то же
    v = _key(v)
    return (set(re.findall(r"\d+", v)) | {str(_ordn(m.group(1), m.group(2))) for m in _ORD.finditer(v)}
            | {m.group(1) for m in _COLOR.finditer(v)}
            | {_day(m.group(1)) for m in _DAY.finditer(v)})


# ─── Один факт под разными словами ───────────────────────────────────────────
#
# Замер 14.10: этаж дома Ирины записан как «окно: третий этаж», «этаж: третий,
# окно справа» и «адрес: …, третий этаж» — три разных признака, и смена этажа
# под любым из них прошла бы мимо сверки. Признаки сводятся к общему ключу, а
# то, на чём ломается связность (этаж места; дата, время и день недели
# события), достаётся из значения любого признака отдельным фактом.

_ATTR_SYN = (("этаж", re.compile(r"этаж")),
             ("где лежит", re.compile(r"^(где\b|местонахожд|место хранени|хранится)")),
             ("вид", re.compile(r"^(вид|внешн|примет|как выглядит)")),
             ("адрес", re.compile(r"^адрес")))


def attr_key(attr: str) -> str:
    k = _key(attr)
    return next((canon for canon, rx in _ATTR_SYN if rx.search(k)), k)


_FLOOR = re.compile(r"\b(\d+)(?:-?[а-я]{1,3})?\s+этаж|" + _ORD.pattern + r"\s+этаж")
_TIME = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")
_WHEN = re.compile(r"врем|дат|когда|\bдень|\bчас|числ")
_DATE = re.compile(r"\b(?:(\d{1,2})|" + _ORD.pattern + r")\s+" + _MONTH.pattern)


def facets(kind: str, attr: str, value: str) -> dict[str, str]:
    """
    Факты, которые достаются из значения: этаж места; дата, время и день
    недели события. «окно — третий этаж, свет» → {"этаж": "3-й"}. Признак,
    который сам и есть этот факт, не дублируется.
    """
    v, own = _key(value), attr_key(attr)
    out: dict[str, str] = {}
    if kind == "место":
        m = _FLOOR.search(v)
        if m:
            out["этаж"] = f"{m.group(1) or _ordn(m.group(2), m.group(3))}-й"
        elif own == "этаж":
            mo, md = _ORD.search(v), re.search(r"\d+", v)
            if mo or md:
                out["этаж"] = f"{_ordn(mo.group(1), mo.group(2)) if mo else md.group()}-й"
    # Только из признака о времени: «присутствие Куприка: до 21:45» — не время падения
    if kind == "событие" and _WHEN.search(own):
        m = _DATE.search(v)
        if m:
            day = int(m.group(1)) if m.group(1) else _ordn(m.group(2), m.group(3))
            month = next(mo for mo in _MONTHS if mo.startswith(m.group(4)[:3]))
            out["дата"] = f"{day} {month}"
        m = _TIME.search(v)
        if m:
            out["время"] = f"{int(m.group(1)):02d}:{m.group(2)}"
        m = _DAY.search(v)
        if m:
            out["день недели"] = _day(m.group(1))
    return {k: val for k, val in out.items() if k != own}


# ─── Одна сущность под разными именами ───────────────────────────────────────
#
# «дом Ирины» и «квартира Ирины Воробьёвой», «квартира вдовы Ларионовой» и
# «квартира Ларионовой»: главное слово из одной группы и имена собственные
# одного входят в имена другого — это то же место. Только места: у событий и
# вещей так совпадают разные — «звонок Гордеева» и «звонок Гордееву»,
# «покупка билета Лаптева» и «покупка повторного билета Лаптева» (замер 14.10).

_HEAD_GROUPS = ({"дом", "квартир", "подъезд", "жиль"},)


def _head(name: str) -> str:
    w = re.findall(r"[а-яa-z]+", _key(name))
    h = w[0][:7] if w else ""
    return next((min(g) for g in _HEAD_GROUPS if any(h.startswith(x) for x in g)), h)


def _proper(name: str) -> set[str]:
    return {w[:4].lower() for w in re.findall(r"[А-ЯЁA-Z][а-яёa-z]+", name or "")}


def resolve_name(known: list[str], kind_known: dict[str, str], kind: str, name: str) -> str:
    """Имя уже известной сущности, если новое — её другое название; иначе само имя."""
    if kind != "место" or any(_key(k) == _key(name) for k in known):
        return name
    head, prop = _head(name), _proper(name)
    if not prop:
        return name
    hits = [k for k in known if kind_known.get(k) == kind and _head(k) == head and _proper(k)
            and (_proper(k) <= prop or prop <= _proper(k))]
    return hits[0] if len(hits) == 1 else name


def _words(v: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[а-яa-z]{4,}", _key(v))}


def _short_words(v: str) -> set[str]:
    return set(re.findall(r"[а-яa-z]{2,}", _key(v)))


def same_or_refined(old: str, new: str) -> bool:
    """
    Новое значение — то же или уточнение прежнего: «15, квартира 8» → «15»,
    «под ковром» → «в полу кабинета под ковром». Не уточнение — если расходятся
    числа, порядковые, цвета или дни недели («второй» → «третий») или значения
    не пересекаются по смыслу.
    """
    mo, mn = _marks(old), _marks(new)
    if mo and mn and not (mo <= mn or mn <= mo):
        return False
    wo, wn = _words(old), _words(new)
    if not wo or not wn:
        # Значение из коротких слов: «ФАП» → «ФАП, холодильная камера» —
        # уточнение, если все его слова есть в другом (книга на Sonnet 18.10,
        # единственный конфликт библии за 4 главы — ложный)
        so, sn = _short_words(old), _short_words(new)
        if so and sn and (so <= sn or sn <= so):
            return True
        return bool(mo or mn) and (mo <= mn or mn <= mo)
    return len(wo & wn) * 2 >= min(len(wo), len(wn))


_DESCRIPTION_WORDS = 5     # от стольких слов значение — описание, а не одно значение признака


def _content_stems(value: str) -> set[str]:
    return {w.lower().replace("ё", "е")[:5] for w in re.findall(r"[А-Яа-яЁёA-Za-z]{4,}", value or "")}


def complements(old: str, new: str) -> bool:
    """
    Новое значение дополняет прежнее, а не спорит с ним: оба — описания (от
    пяти слов) и не делят ни одного значимого слова. Короткие значения
    («третий» / «пятый», «красный шарф» / «синий шарф») и описания с общими
    словами («белая башня, 84 ступени» / «кирпичная башня, 60 ступеней»)
    сравниваются как раньше — там расхождение и есть противоречие. С числами в
    обоих — уточнение, только если числа те же, а значение подробнее.
    """
    nums_old, nums_new = set(re.findall(r"\d+", old)), set(re.findall(r"\d+", new))
    if nums_old and nums_new:
        # Числа в обоих: те же числа и подробнее — уточнение, а не спор.
        # «1:40, кварцевые» → «без двадцати два (1:40), стекло поцарапано»
        # (книга на Sonnet 18.10 — единственный конфликт библии, ложный).
        # Другое число («1:20», «этаж 5» вместо «этаж 3») — противоречие
        return nums_old <= nums_new and len(new) > len(old)
    if len(old.split()) < _DESCRIPTION_WORDS or len(new.split()) < _DESCRIPTION_WORDS:
        return False
    if nums_old or nums_new:
        return False                     # число только в одном — сравниваем как факты
    return not (_content_stems(old) & _content_stems(new))


# ─── Описание и та же ночь ────────────────────────────────────────────────────
#
# «Фон» (24 главы, 19.10): из 14 противоречий библии настоящее одно — куртка
# синяя, потом голубая. Шесть — описания мест и вещей: «столик у окна, видны
# трамваи» и «столик у стены, зеркало над стойкой» — два взгляда на одну
# кофейню, а не два значения. Четыре — сцена после полуночи: в плане «четверг,
# 27 ноября, ночь», в главе «пятница, 28 ноября, 0:58».

_DESCRIPTIVE = re.compile(r"^(вид|описани|обстановк|интерьер|запах|внутри)")
DESCRIPTION_MAX = 400     # символов в склеенном описании; старые части уходят первыми


def descriptive(attr: str) -> bool:
    """Признак — описание (вид, обстановка, запах), а не одно значение."""
    return bool(_DESCRIPTIVE.search(attr_key(attr)))


def marks_agree(old: str, new: str) -> bool:
    """Метки (числа, порядковые, цвета, дни недели) не расходятся: одних нет или одни входят в другие."""
    mo, mn = _marks(old), _marks(new)
    return not (mo and mn) or mo <= mn or mn <= mo


def _join_description(old: str, new: str) -> str:
    parts = [p for p in re.split(r";\s*", old) if p] + [new]
    while len(parts) > 1 and len("; ".join(parts)) > DESCRIPTION_MAX:
        parts.pop(0)
    return "; ".join(parts)


_NIGHT_HOUR = 6           # время до 6 утра — ещё та ночь


def _when(v: str) -> tuple[int | None, int | None]:
    """(порядковый день года по дате, номер дня недели) — что есть в значении."""
    v = _key(v)
    day = None
    m = _DATE.search(v)
    if m:
        d = int(m.group(1)) if m.group(1) else _ordn(m.group(2), m.group(3))
        mon = next(i for i, mo in enumerate(_MONTHS, 1) if mo.startswith(m.group(4)[:3]))
        try:
            day = datetime.date(2000, mon, d).toordinal()
        except ValueError:
            day = None
    m = _DAY.search(v)
    return day, (_DAYS.index(_day(m.group(1))) if m else None)


def same_night(old: str, new: str, context: str = "") -> bool:
    """
    Одна и та же ночь, названная до полуночи и после: «четверг, 27 ноября, ночь»
    и «пятница, 28 ноября, 0:58». Дата и день недели сдвинуты на один день в
    одну сторону, а в значениях или в исходном тексте — ночь или время до 6 утра.
    """
    text = _key(" ".join((old, new, context)))
    night = "ноч" in text or any(int(h) < _NIGHT_HOUR for h, _ in _TIME.findall(text))
    if not night:
        return False
    (do, wo), (dn, wn) = _when(old), _when(new)
    shifts = []
    if do is not None and dn is not None:
        shifts.append(dn - do)
    if wo is not None and wn is not None:
        shifts.append((wn - wo + 3) % 7 - 3)
    return bool(shifts) and len(set(shifts)) == 1 and abs(shifts[0]) == 1


def _fact_key(name: str, attr: str) -> tuple[str, str]:
    return _key(name), attr_key(attr)


def _rows(project_id: int) -> list[dict]:
    _ensure()
    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM series_bible WHERE project_id=? ORDER BY id", (project_id,))]
    for r in rows:
        r["key"] = "|".join(_fact_key(r["name"], r["attr"]))     # история в интерфейсе
    return rows


def _by_chapter(rows: list[dict]) -> list[dict]:
    """Записи по главе (запись без главы — к последней главе на момент записи), затем по порядку."""
    upto, keyed = 0, []
    for r in rows:                     # rows — по id
        upto = max(upto, r["chapter_num"] or 0)
        keyed.append(((r["chapter_num"] or upto), r["id"], r))
    return [r for *_, r in sorted(keyed, key=lambda x: (x[0], x[1]))]


def current(project_id: int, before_chapter: int | None = None) -> list[dict]:
    """
    Текущие факты: по каждой (сущность, признак) — последняя запись, кроме
    противоречий. before_chapter — на момент перед этой главой: записи поздних
    глав не берутся. Раньше срез делал bible_block уже после выбора последней
    записи, и факт, уточнённый поздней главой, пропадал целиком (переписывание
    гл.20 «Фона» — 5 фактов).
    """
    cur: dict[tuple[str, str], dict] = {}
    # По главе, затем по порядку записи: пересчитанная гл.12 записывается
    # после гл.24 и по порядку записи перебивала бы её значения для конца книги
    # (разбор 21.10). Запись без главы (правка автора) — на момент записи:
    # к последней главе, известной тогда
    for r in _by_chapter(_rows(project_id)):
        if r["status"] == "противоречие":
            continue
        if before_chapter is not None and (r["chapter_num"] or 0) >= before_chapter:
            continue
        cur[_fact_key(r["name"], r["attr"])] = r
    return list(cur.values())


def history(project_id: int, name: str, attr: str) -> list[dict]:
    k = _fact_key(name, attr)
    return [r for r in _rows(project_id) if _fact_key(r["name"], r["attr"]) == k]


def conflicts(project_id: int, chapter_num: int | None = None) -> list[dict]:
    return [r for r in _rows(project_id) if r["status"] == "противоречие"
            and (chapter_num is None or r["chapter_num"] == chapter_num)]


def _add(project_id: int, e: dict, chapter_num: int, status: str, reason: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO series_bible (project_id, kind, name, attr, value, chapter_num, status, reason) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (project_id, e["kind"], e["name"].strip(), e["attr"].strip(), e["value"].strip(),
             chapter_num, status, reason.strip()))


def record(project_id: int, entries: list, chapter_num: int) -> dict:
    """
    Дописать факты главы. entries — [{kind, name, attr, value, changed}]; changed —
    причина по сюжету, если факт изменился. Возвращает {added, changed, conflicts}.
    """
    _ensure()
    facts = current(project_id)
    # Сверка — с фактами на момент главы: факты переписанной гл.12 сверялись
    # со значениями гл.20–24 и писались ложными «противоречиями» (разбор 21.10)
    now = {_fact_key(r["name"], r["attr"]): r
           for r in (current(project_id, chapter_num + 1) if chapter_num else facts)}
    names = {r["name"]: r["kind"] for r in facts}
    out: dict[str, list] = {"added": [], "changed": [], "conflicts": []}

    def one(e: dict, src: str = "") -> str:
        """Сверить и записать один факт; вернуть, что вышло."""
        k = _fact_key(e["name"], e["attr"])
        old = now.get(k)
        where = f"из «{src}»" if src else ""
        if old is None:
            _add(project_id, e, chapter_num, "введено", where)
            out["added"].append(e)
            result = "added"
        elif _key(old["value"]) == _key(e["value"]):
            return "same"
        elif not e["changed"] and same_or_refined(old["value"], e["value"]):
            # Уточнение — подробнее прежнего; короче или то же — ничего не пишем
            if len(_key(e["value"])) > len(_key(old["value"])):
                _add(project_id, e, chapter_num, "уточнено", f"было «{old['value']}» (гл.{old['chapter_num']})")
                now[k] = {"name": e["name"], "attr": e["attr"], "value": e["value"], "chapter_num": chapter_num}
            return "same"
        elif not e["changed"] and complements(old["value"], e["value"]):
            # Два разных описания одной вещи, а не два значения одного признака:
            # «держится на одной петле» и «скоба недавно отогнута» (книга-прогон
            # 17.10, единственный конфликт библии за 12 глав — ложный)
            e = dict(e, value=f"{old['value']}; {e['value']}")
            _add(project_id, e, chapter_num, "дополнено", f"к гл.{old['chapter_num']}")
            result = "added"
        elif not e["changed"] and descriptive(e["attr"]) and marks_agree(old["value"], e["value"]):
            # Описание: спорят только метки — «синяя» и «голубая», «второй
            # этаж» и «третий»; «столик у окна» и «столик у стены» — дополнение
            e = dict(e, value=_join_description(old["value"], e["value"]))
            _add(project_id, e, chapter_num, "дополнено", f"к гл.{old['chapter_num']}")
            result = "added"
        elif not e["changed"] and e["kind"] == "событие" and same_night(old["value"], e["value"], src):
            _add(project_id, e, chapter_num, "уточнено",
                 f"та же ночь: было «{old['value']}» (гл.{old['chapter_num']})")
            result = "same"
        elif e["changed"]:
            _add(project_id, e, chapter_num, "изменено", e["changed"])
            out["changed"].append(dict(e, was=old["value"], was_chapter=old["chapter_num"]))
            result = "changed"
        elif _from_plan(old) and chapter_num >= (old.get("chapter_num") or 0):
            # План — намерение, текст главы — канон: расходится — верен текст.
            # Раньше текст писался «противоречием», а текущим оставался план:
            # «Фон», блок библии для гл.25 — 26 строк из 40 — копии плана
            # (гл.23 «пятница, ночь (план)», в тексте «суббота, 2:10»)
            _add(project_id, e, chapter_num, "изменено", f"по тексту главы; в плане «{old['value']}»")
            out["changed"].append(dict(e, was=old["value"], was_chapter=old["chapter_num"]))
            result = "changed"
        else:
            # Не перезаписываем: прежнее значение остаётся текущим
            _add(project_id, e, chapter_num, "противоречие",
                 f"было «{old['value']}» (гл.{old['chapter_num']})" + (f", {where}" if where else ""))
            out["conflicts"].append(dict(e, was=old["value"], was_chapter=old["chapter_num"], src=src))
            return "conflict"
        now[k] = {"name": e["name"], "attr": e["attr"], "value": e["value"], "chapter_num": chapter_num,
                  "status": "", "reason": ""}
        return result

    for e in entries or []:
        if not isinstance(e, dict):
            continue
        e = {k: str(e.get(k) or "").strip() for k in ("kind", "name", "attr", "value", "changed")}
        if not (e["name"] and e["attr"] and e["value"]):
            continue
        if e["kind"] not in KINDS:
            e["kind"] = "место"
        e["name"] = resolve_name(list(names), names, e["kind"], e["name"])
        names.setdefault(e["name"], e["kind"])
        main = one(e)
        for attr, value in facets(e["kind"], e["attr"], e["value"]).items():
            d = dict(e, attr=attr, value=value)
            # Тот же факт уже назван противоречием целиком — второй раз не сигналим
            if main == "conflict" and _fact_key(d["name"], attr) in now and not same_or_refined(
                    now[_fact_key(d["name"], attr)]["value"], value):
                continue
            one(d, f"{e['attr']}: {e['value']}")
    return out


PLAN_REASON = "план главы {}"


def _from_plan(row: dict) -> bool:
    """Запись — из плана главы (планировщик), а не правка автора вручную."""
    return row.get("status") == "автор" and str(row.get("reason") or "").startswith("план главы")


def drop_plan_facts(project_id: int, chapter_num: int) -> int:
    """
    Убрать записи прежнего плана главы — перед новым экспортом её плана. Иначе
    оставались текущими сцены, которых в плане уже нет: «Фон», гл.20 — «Анонс»
    (старый план) рядом с «Сделкой» (новый). Правки автора вручную остаются.
    """
    _ensure()
    with get_conn() as conn:
        return conn.execute("DELETE FROM series_bible WHERE project_id=? AND status='автор' AND reason=?",
                            (project_id, PLAN_REASON.format(chapter_num))).rowcount


def author_set(project_id: int, kind: str, name: str, attr: str, value: str,
               chapter_num: int = 0, reason: str = "") -> None:
    """
    Запись автора (планировщик, правка вручную) — тоже новая запись, не правка
    старой. Имя сводится к известной сущности, этаж и время из значения — тоже
    записи автора.
    """
    _ensure()
    kind = kind if kind in KINDS else "место"
    known = {r["name"]: r["kind"] for r in current(project_id)}
    e = {"kind": kind, "name": resolve_name(list(known), known, kind, name), "attr": attr, "value": value}
    _add(project_id, e, chapter_num, "автор", reason)
    for a, v in facets(kind, attr, value).items():
        _add(project_id, dict(e, attr=a, value=v), chapter_num, "автор", reason)


def known_for_analysis(project_id: int, chapter_num: int | None = None) -> str:
    """Известные сущности для анализа главы: называть так же, сверять значения.
    chapter_num — факты на момент главы: при пересчёте ранней главы анализ видел
    факты конца книги (разбор 21.10)."""
    facts = current(project_id, chapter_num)
    if not facts:
        return ""
    by_name: dict[str, list[str]] = {}
    for r in facts:
        by_name.setdefault(f"{r['kind']}: {r['name']}", []).append(f"{r['attr']} — {r['value']}")
    lines = [f"- {n}: " + "; ".join(v) for n, v in list(by_name.items())[-KNOWN_MAX:]]
    return "\n".join(lines)


def bible_block(project_id: int, focus_text: str = "", before_chapter: int | None = None) -> str:
    """
    Блок генератору: текущие факты, сначала тех сущностей, что упомянуты в
    задаче или плане главы. Недавно изменённые — с пометкой, чтобы генератор
    не откатился к старому значению. before_chapter — только факты глав раньше
    этой и записанные без главы: факты будущих глав писатель выдавал за
    предвидение.
    """
    facts = current(project_id, before_chapter)
    if not facts:
        return ""
    focus = _key(focus_text)

    def hit(r: dict) -> bool:
        words = [w for w in re.findall(r"[а-яa-z]{4,}", _key(r["name"]))]
        return any(w[:-1] in focus for w in words) if focus else False

    facts.sort(key=lambda r: (not hit(r), -r["chapter_num"]))
    lines = []
    for r in facts[:BLOCK_MAX]:
        note = f" (с гл.{r['chapter_num']}: {r['reason']})" if r["status"] in ("изменено", "автор") and r["reason"] else ""
        lines.append(f"- {r['name']} — {r['attr']}: {r['value']}{note}")
    return ("БИБЛИЯ СЕРИИ (пиши ровно так; менять факт можно только событием сюжета, "
            "и тогда покажи это событие):\n" + "\n".join(lines))


def conflict_signals(found: list[dict], chapter_num: int) -> list[str]:
    return [f"Противоречие с библией серии: {c['name']} — {c['attr']}: было «{c['was']}» "
            f"(гл.{c['was_chapter']}), в главе {chapter_num} «{c['value']}»"
            + (f" (в тексте: «{c['src']}»)" if c.get("src") else "")
            + " без события, которое это объясняет." for c in found]
