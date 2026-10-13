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
                status      TEXT NOT NULL DEFAULT 'введено',   -- введено | изменено | противоречие | автор
                reason      TEXT NOT NULL DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now'))
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bible_project ON series_bible(project_id)")


def _key(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip(" .«»\"")


def _rows(project_id: int) -> list[dict]:
    _ensure()
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM series_bible WHERE project_id=? ORDER BY id", (project_id,))]


def current(project_id: int) -> list[dict]:
    """Текущие факты: по каждой (сущность, атрибут) — последняя запись, кроме противоречий."""
    cur: dict[tuple[str, str], dict] = {}
    for r in _rows(project_id):
        if r["status"] == "противоречие":
            continue
        cur[(_key(r["name"]), _key(r["attr"]))] = r
    return list(cur.values())


def history(project_id: int, name: str, attr: str) -> list[dict]:
    k = (_key(name), _key(attr))
    return [r for r in _rows(project_id) if (_key(r["name"]), _key(r["attr"])) == k]


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
    now = {(_key(r["name"]), _key(r["attr"])): r for r in current(project_id)}
    out: dict[str, list] = {"added": [], "changed": [], "conflicts": []}
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        e = {k: str(e.get(k) or "").strip() for k in ("kind", "name", "attr", "value", "changed")}
        if not (e["name"] and e["attr"] and e["value"]):
            continue
        if e["kind"] not in KINDS:
            e["kind"] = "место"
        k = (_key(e["name"]), _key(e["attr"]))
        old = now.get(k)
        if old is None:
            _add(project_id, e, chapter_num, "введено")
            out["added"].append(e)
        elif _key(old["value"]) == _key(e["value"]):
            continue
        elif e["changed"]:
            _add(project_id, e, chapter_num, "изменено", e["changed"])
            out["changed"].append(dict(e, was=old["value"], was_chapter=old["chapter_num"]))
        else:
            # Не перезаписываем: прежнее значение остаётся текущим
            _add(project_id, e, chapter_num, "противоречие",
                 f"было «{old['value']}» (гл.{old['chapter_num']})")
            out["conflicts"].append(dict(e, was=old["value"], was_chapter=old["chapter_num"]))
        if e["changed"] or old is None:
            now[k] = {"name": e["name"], "attr": e["attr"], "value": e["value"], "chapter_num": chapter_num}
    return out


def author_set(project_id: int, kind: str, name: str, attr: str, value: str,
               chapter_num: int = 0, reason: str = "") -> None:
    """Запись автора (планировщик, правка вручную) — тоже новая запись, не правка старой."""
    _ensure()
    _add(project_id, {"kind": kind if kind in KINDS else "место", "name": name, "attr": attr,
                      "value": value}, chapter_num, "автор", reason)


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
    lines = []
    for r in facts[:BLOCK_MAX]:
        note = f" (с гл.{r['chapter_num']}: {r['reason']})" if r["status"] in ("изменено", "автор") and r["reason"] else ""
        lines.append(f"- {r['name']} — {r['attr']}: {r['value']}{note}")
    return ("БИБЛИЯ СЕРИИ (пиши ровно так; менять факт можно только событием сюжета, "
            "и тогда покажи это событие):\n" + "\n".join(lines))


def conflict_signals(found: list[dict], chapter_num: int) -> list[str]:
    return [f"Противоречие с библией серии: {c['name']} — {c['attr']}: было «{c['was']}» "
            f"(гл.{c['was_chapter']}), в главе {chapter_num} «{c['value']}» без события, которое это "
            f"объясняет." for c in found]
