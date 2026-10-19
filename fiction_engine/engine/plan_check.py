"""
Сверка главы с планом (шаг 4 docs/ENGINE_BOOST.md, «Проверка главы по плану»).

План главы — из планировщика («СЦЕНА N: …») или заметка к главе. Писатель
получает его вместе с задачей, но что из плана в главу не попало, раньше
никто не смотрел: автор узнавал, только перечитав главу с планом рядом.

Проверяющий отмечает каждый пункт: есть, частично, нет — с цитатой из
главы. Цитата сверяется с текстом: не нашлась — пункт помечается, что
подтверждения нет (проверяющий мог её выдумать). Проверяющий — из другого
семейства, чем писатель: свои пропуски модель видит хуже.
"""

from __future__ import annotations

import re
from typing import Callable

PLAN_MAX_ITEMS = 12
HOLD_MARK = "ПОКА НЕ РАСКРЫВАТЬ"      # блок запретов в плане из планировщика (planner api_bp.HOLD_HEADER)
PLAN_ITEM_MAX = 700
STATUSES = ("есть", "частично", "нет")

_SCENE = re.compile(r"^\s*СЦЕНА\s+\d+\s*:", re.M | re.I)
_LIST = re.compile(r"^\s*(?:\d+[.)]|[-—•*])\s+", re.M)


def plan_items(plan: str) -> list[str]:
    """
    Пункты плана: блоки «СЦЕНА N: …» планировщика, иначе нумерованные или
    маркированные строки, иначе вся заметка одним пунктом.
    """
    # «Пока не раскрывать» из планировщика — запрет, а не пункт плана
    text = (plan or "").split(HOLD_MARK)[0].strip()
    if not text:
        return []
    if _SCENE.search(text):
        starts = [m.start() for m in _SCENE.finditer(text)]
        items = [text[a:b].strip() for a, b in zip(starts, starts[1:] + [len(text)])]
    elif len(_LIST.findall(text)) >= 2:
        starts = [m.start() for m in _LIST.finditer(text)]
        items = [text[a:b].strip() for a, b in zip(starts, starts[1:] + [len(text)])]
    else:
        items = [text]
    return [i[:PLAN_ITEM_MAX] for i in items if i][:PLAN_MAX_ITEMS]


def plan_end_line(plan: str) -> str:
    """
    Где кончается глава — строка писателю после плана из планировщика.
    Писатель добирал объём и шёл дальше плана: книга 3 (18.10), глава 1 из
    трёх сцен закончилась заселением в гостиницу — первой сценой главы 2.
    Только для плана со сценами («СЦЕНА N: …»); у обычной заметки конца нет.
    """
    text = (plan or "").split(HOLD_MARK)[0]
    scenes = list(_SCENE.finditer(text))
    if not scenes:
        return ""
    last = text[scenes[-1].start():].strip().splitlines()[0].strip()
    return (f"ГЛАВА ЗАКАНЧИВАЕТСЯ последней сценой плана — {last}. После неё ничего не пиши: "
            "следующие события — в следующих главах. Объём набирай внутри сцен плана, а не новыми сценами.")


def quote_found(quote: str, text: str) -> bool:
    """
    Цитата подтверждает пункт, если хоть один её кусок от 4 слов (между «…»,
    точками, кавычками) стоит в главе дословно. Строже, как в проверке
    непрерывности (все куски), здесь не нужно: цитата лишь показывает место,
    а проверяющий часто приклеивает имя говорящего — «Вероника: …» (замер
    17.10 на главе 1 автора: верные пункты помечались неподтверждёнными).
    """
    from .continuity_checker import _norm_quote
    t = _norm_quote(text)
    parts = [_norm_quote(p) for p in re.split(r"\.\.\.|…|[.!?:;«»\"]", quote or "")]
    return any(len(p.split()) >= 4 and p in t for p in parts)


_PROMPT = """Ниже план главы {num} по пунктам и сама глава. Для КАЖДОГО пункта плана
определи, выполнен ли он в главе:
- «есть» — то, что в пункте, в главе показано (место, люди, событие);
- «частично» — упомянуто вскользь, сделано наполовину или иначе, чем в плане
  (не то место, не те люди, событие пересказано, а не показано);
- «нет» — в главе этого нет.
Стиль и качество прозы не оценивай — только выполнение плана.

quote — точная цитата из главы, 5–15 слов подряд, где пункт выполнен (для «нет» — "").
Копируй дословно: без имени говорящего, без своих слов и пересказа.
note — одно предложение: чего не хватает или что сделано не так (для «есть» — "").

=== ПЛАН ===
{items}

=== ГЛАВА {num} ===
{text}

Ответь JSON без пояснений вокруг, по пункту на каждый пункт плана, в том же порядке:
{{"items": [{{"n": 1, "status": "есть", "quote": "…", "note": ""}}]}}"""


def check_plan(chapter_num: int, plan: str, chapter_text: str,
               api_call_fn: Callable[[str], str]) -> list[dict]:
    """
    → [{n, item, status, quote, quote_ok, note}] по пунктам плана.
    quote_ok — цитата нашлась в главе; без неё «есть» и «частично» не
    подтверждены. Пункт, который проверяющий пропустил, — status «?».
    """
    items = plan_items(plan)
    if not items or not (chapter_text or "").strip():
        return []
    from .pipeline_config import CRITIC_TEXT_LIMIT
    from .pipeline_llm import parse_json
    raw = api_call_fn(_PROMPT.format(
        num=chapter_num, text=chapter_text[:CRITIC_TEXT_LIMIT],
        items="\n\n".join(f"[{i}] {t}" for i, t in enumerate(items, 1))))
    data = parse_json(raw)
    got = data if isinstance(data, list) else \
        data.get("items") if isinstance(data, dict) else None
    if not isinstance(got, list):
        raise ValueError("сверка с планом: ответ модели не разобран")
    by_n: dict[int, dict] = {}
    for k, x in enumerate(got, 1):
        if not isinstance(x, dict):
            continue
        try:
            n = int(x.get("n") or k)
        except (TypeError, ValueError):
            n = k
        by_n.setdefault(n, x)
    out = []
    for n, item in enumerate(items, 1):
        x = by_n.get(n, {})
        status = str(x.get("status") or "").strip().lower()
        status = status if status in STATUSES else "?"
        quote = str(x.get("quote") or "").strip()
        out.append({"n": n, "item": item, "status": status, "quote": quote,
                    "quote_ok": quote_found(quote, chapter_text),
                    "note": str(x.get("note") or "").strip()})
    return out


# ─── Сверки кругов «Мастерской» ─────────────────────────────────────────────
# Хранятся по запуску и тексту круга: выбор круга при «Принять» учитывает,
# какой текст закрывает план полнее (pipeline.best_round).

def _ensure_round_checks() -> None:
    from .db_core import get_conn
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_plan_checks (
                run_id     INTEGER NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
                text_hash  TEXT NOT NULL,
                missing    INTEGER NOT NULL,
                partial    INTEGER NOT NULL,
                checked_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (run_id, text_hash)
            )""")


def _text_hash(text: str) -> str:
    import hashlib
    return hashlib.sha1((text or "").strip().encode("utf-8")).hexdigest()


def save_round_check(run_id: int, text: str, items: list[dict]) -> None:
    """Итог сверки текста круга: пунктов «нет» и «частично». Повторная сверка того же текста — вместо прежней."""
    if not (run_id and items and (text or "").strip()):
        return
    _ensure_round_checks()
    from .db_core import get_conn
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO pipeline_plan_checks (run_id, text_hash, missing, partial) "
                     "VALUES (?,?,?,?)",
                     (run_id, _text_hash(text), sum(x["status"] == "нет" for x in items),
                      sum(x["status"] == "частично" for x in items)))


def attach_round_checks(run_id: int, rounds: list[dict]) -> list[dict]:
    """Кругам со сверенным текстом — plan: {missing, partial}; не сверен — None."""
    _ensure_round_checks()
    from .db_core import get_conn
    with get_conn() as conn:
        got = {h: {"missing": m, "partial": p} for h, m, p in conn.execute(
            "SELECT text_hash, missing, partial FROM pipeline_plan_checks WHERE run_id=?", (run_id,))}
    for r in rounds:
        r["plan"] = got.get(_text_hash(r["text"]))
    return rounds


def plan_checker_model(model_gen: str) -> tuple[str, str]:
    """
    Проверяющий для главы писателя model_gen → (модель, причина отказа).
    Сначала проверяющий непрерывности из настроек (наборы ролей ставят его
    из другого семейства: Sol для Sonnet, Sonnet для Sol), затем судья по
    умолчанию; из того же семейства, что писатель, — не берётся.
    """
    from .continuity_checker import continuity_model
    from .pipeline_config import default_role_models, model_family
    fam = model_family(model_gen) if model_gen else ""
    for m in (continuity_model(), default_role_models().get("judge", "")):
        if m and (not fam or model_family(m) != fam):
            return m, ""
    return "", ("Нет проверяющего другого семейства, чем писатель: выбери его в "
                "«Настройки → Проверка непрерывности» или набор ролей в «Мастерской».")
