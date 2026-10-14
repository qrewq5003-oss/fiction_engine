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

import re

from .db_core import get_conn

KINDS = ("место", "вещь", "событие", "персонаж", "показание")
BLOCK_MAX = 40          # строк в блоке генератору
KNOWN_MAX = 60          # сущностей в подсказке анализу

# Показания: кто что сказал, видел, знал. Замер плана 14.10 — почти половина
# противоречий серии здесь: «о сейфе знала только я» → «он видел, как я
# открывала». Сверка по числам и словам такие утверждения не сравнит, поэтому
# противоречие отмечает анализ главы (поле contradicts), а библия его хранит и
# отдаёт генератору: персонаж может солгать или узнать новое, но это должно
# быть видно в тексте.
TESTIMONY = "показание"
TESTIMONY_MAX = 20      # строк показаний в блоке генератору
TESTIMONY_IN_BLOCK = True   # ab_compare --without testimony


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
                status      TEXT NOT NULL DEFAULT 'введено',   -- введено | уточнено | изменено | противоречие | автор
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
    if any(_key(k) == _key(name) for k in known):
        return name
    if kind == TESTIMONY:
        # Показание — по персонажу: «Ирина» = «Ирина Воробьёва». Слова целиком, без
        # основ: «Лаптев» и «Лаптева» — разные люди
        words = set(_key(name).split())
        hits = [k for k in known if kind_known.get(k) == kind
                and (set(_key(k).split()) <= words or words <= set(_key(k).split()))]
        return hits[0] if len(hits) == 1 else name
    if kind != "место":
        return name
    head, prop = _head(name), _proper(name)
    if not prop:
        return name
    hits = [k for k in known if kind_known.get(k) == kind and _head(k) == head and _proper(k)
            and (_proper(k) <= prop or prop <= _proper(k))]
    return hits[0] if len(hits) == 1 else name


def _words(v: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[а-яa-z]{4,}", _key(v))}


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
        return bool(mo or mn) and (mo <= mn or mn <= mo)
    return len(wo & wn) * 2 >= min(len(wo), len(wn))


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


def current(project_id: int) -> list[dict]:
    """Текущие факты: по каждой (сущность, признак) — последняя запись, кроме противоречий."""
    cur: dict[tuple[str, str], dict] = {}
    for r in _rows(project_id):
        if r["status"] == "противоречие":
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
    now = {_fact_key(r["name"], r["attr"]): r for r in facts}
    names = {r["name"]: r["kind"] for r in facts}
    out: dict[str, list] = {"added": [], "changed": [], "conflicts": []}
    # Кто давал показания в прошлых главах. Противоречие показаний — только с
    # собой прежним: расхождение разных людей (Лаптев «вернулся ко второму акту»,
    # капельдинер «не возвращался») — улика, а не ошибка автора
    earlier = {_key(r["name"]) for r in facts if r["kind"] == TESTIMONY and r["chapter_num"] < chapter_num}

    def said_before(name: str) -> bool:
        return _key(name) in earlier

    def one(e: dict, src: str = "") -> str:
        """Сверить и записать один факт; вернуть, что вышло."""
        k = _fact_key(e["name"], e["attr"])
        old = now.get(k)
        where = f"из «{src}»" if src else ""
        if e.get("contradicts") and not e["changed"] and said_before(e["name"]):
            # Анализ главы видит противоречие с известным показанием — даже если
            # тема названа иначе; прежнее остаётся текущим
            was = old["value"] if old else e["contradicts"]
            was_ch = old["chapter_num"] if old else 0
            _add(project_id, e, chapter_num, "противоречие",
                 f"было «{was}»" + (f" (гл.{was_ch})" if was_ch else ""))
            out["conflicts"].append(dict(e, was=was, was_chapter=was_ch, src=src))
            return "conflict"
        if old is None:
            _add(project_id, e, chapter_num, "введено", where)
            out["added"].append(e)
            result = "added"
        elif _key(old["value"]) == _key(e["value"]):
            return "same"
        elif e["kind"] == TESTIMONY and not e["changed"] and not e["contradicts"]:
            # Новое утверждение о том же, а анализ противоречия не увидел — дополнение
            _add(project_id, e, chapter_num, "уточнено", f"было «{old['value']}» (гл.{old['chapter_num']})")
            result = "same"
        elif not e["changed"] and e["kind"] != TESTIMONY and same_or_refined(old["value"], e["value"]):
            # Уточнение — подробнее прежнего; короче или то же — ничего не пишем
            if len(_key(e["value"])) > len(_key(old["value"])):
                _add(project_id, e, chapter_num, "уточнено", f"было «{old['value']}» (гл.{old['chapter_num']})")
                now[k] = {"name": e["name"], "attr": e["attr"], "value": e["value"], "chapter_num": chapter_num}
            return "same"
        elif e["changed"]:
            _add(project_id, e, chapter_num, "изменено", e["changed"])
            out["changed"].append(dict(e, was=old["value"], was_chapter=old["chapter_num"]))
            result = "changed"
        else:
            # Не перезаписываем: прежнее значение остаётся текущим
            _add(project_id, e, chapter_num, "противоречие",
                 f"было «{old['value']}» (гл.{old['chapter_num']})" + (f", {where}" if where else ""))
            out["conflicts"].append(dict(e, was=old["value"], was_chapter=old["chapter_num"], src=src))
            return "conflict"
        now[k] = {"name": e["name"], "attr": e["attr"], "value": e["value"], "chapter_num": chapter_num}
        return result

    for e in entries or []:
        if not isinstance(e, dict):
            continue
        e = {k: str(e.get(k) or "").strip()
             for k in ("kind", "name", "attr", "value", "changed", "contradicts")}
        if e["kind"] != TESTIMONY:
            e["contradicts"] = ""       # у мест и вещей противоречие решает сверка значений
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


def known_for_analysis(project_id: int) -> str:
    """Известные сущности для анализа главы: называть так же, сверять значения."""
    facts = current(project_id)
    if not facts:
        return ""
    by_name: dict[str, list[str]] = {}
    for r in facts:
        by_name.setdefault(f"{r['kind']}: {r['name']}", []).append(f"{r['attr']} — {r['value']}")
    lines = [f"- {n}: " + "; ".join(v) for n, v in list(by_name.items())[-KNOWN_MAX:]]
    return "\n".join(lines)


def bible_block(project_id: int, focus_text: str = "") -> str:
    """
    Блок генератору: текущие факты, сначала тех сущностей, что упомянуты в
    задаче или плане главы. Недавно изменённые — с пометкой, чтобы генератор
    не откатился к старому значению.
    """
    facts = current(project_id)
    if not facts:
        return ""
    focus = _key(focus_text)

    def hit(r: dict) -> bool:
        words = [w for w in re.findall(r"[а-яa-z]{4,}", _key(r["name"]))]
        return any(w[:-1] in focus for w in words) if focus else False

    facts.sort(key=lambda r: (not hit(r), -r["chapter_num"]))
    said = [r for r in facts if r["kind"] == TESTIMONY][:TESTIMONY_MAX] if TESTIMONY_IN_BLOCK else []
    facts = [r for r in facts if r["kind"] != TESTIMONY]

    def line(r: dict) -> str:
        note = f" (с гл.{r['chapter_num']}: {r['reason']})" if r["status"] in ("изменено", "автор") and r["reason"] else ""
        return f"- {r['name']} — {r['attr']}: {r['value']}{note}"

    out = []
    if facts:
        out.append("БИБЛИЯ СЕРИИ (пиши ровно так; менять факт можно только событием сюжета, "
                   "и тогда покажи это событие):\n" + "\n".join(line(r) for r in facts[:BLOCK_MAX]))
    if said:
        out.append("ПОКАЗАНИЯ — что персонажи уже сказали, видели и знают (персонаж может солгать, "
                   "передумать или узнать новое, но тогда это видно в тексте — пойман на лжи, "
                   "узнал от кого-то; молча другое не говорит):\n"
                   + "\n".join(f"- {r['name']} (гл.{r['chapter_num']}) — {r['attr']}: {r['value']}"
                               + (f" ({r['reason']})" if r["status"] == "изменено" and r["reason"] else "")
                               for r in said))
    return "\n\n".join(out)


def conflict_signals(found: list[dict], chapter_num: int) -> list[str]:
    return [f"Противоречие с библией серии: {c['name']} — {c['attr']}: было «{c['was']}»"
            + (f" (гл.{c['was_chapter']})" if c.get("was_chapter") else "")
            + f", в главе {chapter_num} «{c['value']}»"
            + (f" (в тексте: «{c['src']}»)" if c.get("src") else "")
            + " без события, которое это объясняет." for c in found]
