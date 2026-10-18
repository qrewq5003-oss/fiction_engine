"""
engine/chapter_import.py — глава книги на доске: разбивка текста на сцены.

Модель (вызов делает Fiction Engine) читает главу и возвращает сцены с
полями карточки и связи между ними — и с уже стоящими на доске сценами
прошлых глав, чтобы граф показывал, что из чего вытекает. Здесь — промт и
разбор ответа: всё, что модель вернула не так, отбрасывается, а не
угадывается.
"""
import json
import re

TIMES = ("Утро", "День", "Вечер", "Ночь")
LINK_TYPES = ("cause", "parallel", "mirror", "contrast")
FIELDS = ("title", "location", "day", "time_of_day", "characters", "what_happens", "emotion")
TEXT_MAX = 60000        # символов главы в запросе: ~10 тыс. слов
BOARD_MAX = 80          # сцен с доски в запросе — для связей с прошлым

SYSTEM = "Ты редактор-сценарист. Размечаешь готовую главу на сцены. Отвечаешь только JSON."

PROMPT = """Ниже глава {chapter} книги. Раздели её на сцены — так, как их разметил бы
сценарист: новая сцена там, где меняется место, время или непрерывное действие.
Обычно в главе 2–8 сцен. Ничего не придумывай сверх текста.

Для каждой сцены:
- title — короткое название (2–6 слов);
- location — где происходит;
- day — какой день, если он назван или ясен из текста («пятница», «на следующий день»), иначе "";
- time_of_day — одно из: Утро, День, Вечер, Ночь, или "";
- characters — кто участвует, через запятую;
- what_happens — что происходит, 1–3 предложения: события и что меняется;
- emotion — эмоция сцены одним-двумя словами.

Связи (links) — только явные по тексту:
- cause — одна сцена ведёт к другой (улика → допрос, решение → поступок);
- parallel — идут одновременно; mirror — одна отражает другую; contrast — противоречит.
Сцены этой главы обозначай номерами 1, 2, 3…; сцены с доски — их метками S<id>.
Соседние сцены одной главы не связывай только за то, что они идут подряд.
Если на доске есть сцены прошлых глав, найди, что из них продолжается здесь:
последствие, ответ, возврат к улике или месту, — и свяжи (S<id> → номер сцены).
{board}
=== ГЛАВА {chapter} ===
{text}

Ответь JSON без пояснений вокруг:
{{"scenes": [{{"title": "", "location": "", "day": "", "time_of_day": "", "characters": "",
"what_happens": "", "emotion": ""}}],
"links": [{{"from": 1, "to": 2, "type": "cause", "label": "коротко почему"}}]}}"""


def board_block(scenes: list[dict], chapter: int) -> str:
    """Сцены прошлых глав с доски — метки S<id> для связей. Свои сцены главы не нужны."""
    prev = [s for s in scenes if s.get("chapter_num") and s["chapter_num"] < chapter]
    prev = prev[-BOARD_MAX:]
    if not prev:
        return ""
    lines = [f"S{s['id']} (гл.{s['chapter_num']}): {s.get('title') or 'без названия'}"
             + (f" — {(s.get('what_happens') or '')[:160]}" if s.get("what_happens") else "")
             for s in prev]
    return "\n=== СЦЕНЫ ПРОШЛЫХ ГЛАВ НА ДОСКЕ ===\n" + "\n".join(lines) + "\n"


def build_prompt(text: str, chapter: int, board: list[dict]) -> str:
    return PROMPT.format(chapter=chapter, board=board_block(board, chapter), text=text[:TEXT_MAX])


def _json(raw: str):
    raw = (raw or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if m:
        raw = m.group(1)
    start = raw.find("{")
    if start < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(raw[start:])[0]
    except ValueError:
        return None


def _time(v: str) -> str:
    v = (v or "").strip().capitalize()
    return v if v in TIMES else ""


def _ref(v, n_new: int, board_ids: set[int]):
    """Номер сцены главы (1…n) → ("new", i); S<id> с доски → ("board", id); иначе None."""
    s = str(v).strip().upper()
    if s.startswith("S") and s[1:].isdigit():
        return ("board", int(s[1:])) if int(s[1:]) in board_ids else None
    if s.isdigit() and 1 <= int(s) <= n_new:
        return ("new", int(s) - 1)
    return None


def parse(raw: str, board_ids: set[int]) -> dict:
    """
    Ответ модели → {"scenes": [...], "links": [...]}. Сцена без названия и
    без «что происходит» отбрасывается; связь — если хоть один конец не
    распознан, если она на саму себя или обе стороны на доске (их автор
    связал или нет сам).
    """
    d = _json(raw)
    if not isinstance(d, dict):
        raise ValueError("модель ответила не JSON")
    scenes = []
    for s in d.get("scenes") or []:
        if not isinstance(s, dict):
            continue
        sc = {f: str(s.get(f) or "").strip() for f in FIELDS}
        sc["time_of_day"] = _time(sc["time_of_day"])
        if sc["title"] or sc["what_happens"]:
            scenes.append(sc)
    if not scenes:
        raise ValueError("модель не нашла сцен")
    links, seen = [], set()
    for ln in d.get("links") or []:
        if not isinstance(ln, dict):
            continue
        a, b = _ref(ln.get("from"), len(scenes), board_ids), _ref(ln.get("to"), len(scenes), board_ids)
        kind = str(ln.get("type") or "cause").strip().lower()
        if not a or not b or a == b or (a[0] == b[0] == "board") or kind not in LINK_TYPES:
            continue
        if (a, b) in seen:
            continue
        seen.add((a, b))
        links.append({"from": list(a), "to": list(b), "type": kind,
                      "label": str(ln.get("label") or "").strip()[:80]})
    return {"scenes": scenes, "links": links}


def insert_position(act_scenes: list[dict], chapter: int) -> int:
    """
    Индекс в акте, куда встают сцены главы: после последней сцены более
    ранней главы, перед первой более поздней; глав на доске нет — в конец.
    act_scenes — сцены акта в порядке доски.
    """
    after = [i for i, s in enumerate(act_scenes) if s.get("chapter_num") and s["chapter_num"] <= chapter]
    if after:
        return after[-1] + 1
    later = [i for i, s in enumerate(act_scenes) if s.get("chapter_num") and s["chapter_num"] > chapter]
    return later[0] if later else len(act_scenes)
