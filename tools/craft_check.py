"""
Модули UNIFIED как проверка, а не совет (пилот, 14.10).

Блок движка — советы перед письмом — прозе сильных моделей не помогает и не
вредит (bench/ab-sonnet-noengine-2026-10-14.json, ab-panel-noengine-2026-10-06.json).
Сработало другое: конкретные вопросы о ремесле, на которые судья отвечает по
тексту (вторая линия, bench/ab-secondary-families-2026-10-13.json). Здесь —
вопросы из трёх модулей (хуки и концовки, кривая напряжения, подтекст), взятые
из их PROMPT:QUICK, «Нельзя», «Ошибок» и чеклистов. Сначала проверяем прибор:
различают ли вопросы главу, где модуль выполнен, и главу, где он провален.

    python tools/craft_check.py rewrite   hooks   [каталог]
    python tools/craft_check.py questions hooks   [каталог]
    python tools/craft_check.py summary   [каталог …]

rewrite — 4 главы набора GLM (по одной на жанр) писатель переписывает дважды:
A — модуль выполнен, B — провален; сюжет, сцены и объём те же. Писатель —
FE_CRAFT_REWRITER (по умолчанию Claude Sonnet через подписку: провал он пишет
чисто, DeepSeek — точечно). questions — судьи FE_CRAFT_JUDGES (по умолчанию
Kimi и DeepSeek) отвечают на 5 вопросов 0–2. summary — по ответу одного судьи:
сколько проваленных глав ниже порога и нет ли там живых.
Каталог по умолчанию — .ab_work/craft/<модуль>.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
REWRITER = "claude_subscription::claude-sonnet-5-5"
JUDGES = ["nano_gpt::moonshotai/kimi-k2.5", "nano_gpt::deepseek/deepseek-v4-pro-0813"]
GENRES = ["detective_classic", "realism_psychological", "thriller_psychological", "fantasy_dark"]
FAIL_SUM = 5.5

MODULES: dict[str, dict] = {
    "hooks": {
        "source": "03_ADVANCED_ENGINES/19_hooks_closings.md",
        "what": "начало и концовку главы",
        "A": "первое предложение сразу создаёт вопрос или натяжение (действие в разгаре, деталь не на "
             "месте, парадокс или голос персонажа); в первых 150 словах нет предыстории и справки — "
             "она вплетена позже; из первого абзаца ясно, кто, какой тон и что происходит; последний "
             "абзац несёт вес — переворачивающий факт, тихий удар деталью или открытый вопрос, — и ничего "
             "не объясняет",
        "B": "глава открывается пробуждением героя или погодой без функции, затем идёт абзац-другой "
             "предыстории и справки до того, как что-то происходит; концовка — абзац-резюме, где "
             "рассказчик объясняет, что сегодня изменилось и что герой понял, и глава просто "
             "останавливается",
        "Q": ["Первое предложение создаёт вопрос или натяжение — действие в разгаре, деталь не на месте, "
              "парадокс, голос персонажа, — а не пробуждение, погода или справка",
              "В первых 150 словах нет предыстории и экспозиции перед действием",
              "Из первого абзаца ясно, кто в сцене, какой тон и что происходит",
              "Последний абзац несёт вес — переворачивающий факт, тихий удар деталью, открытый вопрос, "
              "— а не просто останавливается",
              "Концовка не объясняет то, что читатель уже понял: нет абзаца-резюме и вывода"],
    },
    "tension": {
        "source": "03_ADVANCED_ENGINES/01_tension_curve.md",
        "what": "кривую напряжения главы",
        "A": "сцены на разной высоте напряжения — волна, а не плато; пик стоит ближе к концу; после "
             "спокойного места напряжение поднимается выше прежнего; последняя сцена кончается на "
             "подъёме — вопросом, угрозой, неполным откровением или предстоящим выбором; напряжение "
             "создают события и ставки, а не слова рассказчика",
        "B": "все сцены идут на одной ровной высоте; если есть острый момент — он в начале, дальше "
             "напряжение спадает; последняя сцена спокойная, всё улажено, вопросов не осталось; "
             "рассказчик сам говорит, что было напряжённо и тревожно",
        "Q": ["Сцены главы на разной высоте напряжения — волна, а не одна ровная высота",
              "Пик напряжения стоит ближе к концу главы, а не в начале",
              "После спокойного места напряжение снова поднимается выше прежнего",
              "Последняя сцена кончается на подъёме — вопрос, угроза, неполное откровение, предстоящий "
              "выбор, — а не на успокоении",
              "Напряжение создают события и ставки, а не слова рассказчика о напряжении"],
    },
    "subtext": {
        "source": "03_ADVANCED_ENGINES/10_subtext_engine.md",
        "what": "подтекст в диалогах и сценах",
        "A": "в ключевых диалогах говорят об одном, а имеют в виду другое; на прямой вопрос о главном "
             "персонаж отвечает бытовым, действием руками или молчанием, и читатель слышит настоящий "
             "ответ; слова расходятся с телом и действием; у каждого в разговоре есть то, чего он не "
             "говорит; рассказчик подтекст не называет",
        "B": "персонажи говорят ровно то, что думают и чувствуют, прямо называют свои чувства и цели; "
             "на прямой вопрос — прямой ответ; слова и поступки совпадают; рассказчик после реплик "
             "объясняет, что персонаж имел в виду и что почувствовал",
        "Q": ["В ключевом диалоге говорят об одном, а имеют в виду другое",
              "На прямой вопрос о главном персонаж отвечает бытовым, действием или молчанием — и "
              "читатель слышит настоящий ответ",
              "Хотя бы раз слова персонажа расходятся с его действием или телом",
              "У персонажей в разговоре есть скрытые цели: спрашивают об одном, чтобы узнать другое",
              "Текст не называет подтекст прямо («она поняла, что он имел в виду», «за его словами "
              "стояло…»)"],
    },
}

SYS_REWRITE = ("Ты опытный редактор художественной прозы. Переписываешь главу по заданию. "
               "Отвечаешь только текстом главы, без пояснений.")
COMMON = ("Сохрани сюжет, сцены, персонажей, события и их порядок. Сохрани объём (около {w} слов) и "
          "манеру. Переработай только {what}.")
TASK = {"A": "Сделай это хорошо: {A}.",
        "B": "Сделай это проваленным: {B}. Пиши ровно и без иронии, как будто так и задумано."}
ASK = """Ниже глава. Ответь на вопросы о ней. Оценка: 0 — нет, 1 — частично, 2 — да, явно.
Сначала короткая цитата-доказательство, потом оценка.

{qs}

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг: {{"answers": [{{"q": 1, "quote": "…", "score": 0}}, …]}}"""


def _setup():
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(ROOT / "fiction_engine"))
    import ab_compare as ab
    ab._temp_db(ROOT / "fiction_engine")
    from engine.pipeline import _call
    return _call


def _mt(model: str, n: int) -> int:
    # Claude через подписку тратит лимит и на скрытое размышление
    return 32000 if model.startswith("claude_subscription::") else n


def _retry_wait(e: Exception) -> None:
    if "429" in str(e):
        time.sleep(random.uniform(20, 40))


def rewrite(mod: str, d: Path) -> None:
    _call = _setup()
    m = MODULES[mod]
    writer = os.environ.get("FE_CRAFT_REWRITER") or REWRITER
    pool = json.load(open(ROOT / "bench/base-pool-2026-10-05.json"))["chapters"]
    base = [next(c for c in pool if c["genre"] == g and c.get("text")) for g in GENRES]

    def run(job):
        c, v = job
        prompt = (COMMON.format(w=c["words"], what=m["what"]) + "\n\n" + TASK[v].format(**m)
                  + "\n\n=== ГЛАВА ===\n" + c["text"])
        for _ in range(3):
            try:
                t = _call(writer, SYS_REWRITE, prompt, max_tokens=_mt(writer, 12000))
                if t and len(t.split()) > 0.6 * int(c["words"]):
                    return {"genre": c["genre"], "variant": v, "text": t.strip(), "words": len(t.split())}
            except Exception as e:
                print("ошибка", c["genre"], v, str(e)[:120], flush=True)
                _retry_wait(e)
        return {"genre": c["genre"], "variant": v, "text": "", "words": 0}

    workers = 1 if writer.startswith("claude_subscription::") else 3
    rows = list(ThreadPoolExecutor(workers).map(run, [(c, v) for c in base for v in "AB"]))
    json.dump({"module": mod, "rewriter": writer, "chapters": rows},
              open(d / "rewritten.json", "w"), ensure_ascii=False, indent=1)
    for r in rows:
        print(f"  {mod} {r['genre']} {r['variant']} {r['words']} слов", flush=True)


def questions(mod: str, d: Path) -> None:
    _call = _setup()
    from engine.pipeline_llm import parse_json
    m = MODULES[mod]
    chs = [r for r in json.load(open(d / "rewritten.json"))["chapters"] if r["text"]]
    qs = "\n".join(f"{i}. {q}" for i, q in enumerate(m["Q"], 1))
    judges = [j for j in os.environ.get("FE_CRAFT_JUDGES", "").split(",") if j] or JUDGES

    def run(job):
        c, jm = job
        for _ in range(2):
            try:
                got = parse_json(_call(jm, "Ты строгий редактор. Отвечаешь только JSON.",
                                       ASK.format(qs=qs, text=c["text"]), max_tokens=_mt(jm, 3000))) or {}
                a = {int(x["q"]): float(x["score"]) for x in got.get("answers", [])}
                if len(a) == len(m["Q"]):
                    return {"genre": c["genre"], "variant": c["variant"], "judge": jm.split("::")[-1], "scores": a}
            except Exception as e:
                print("  не разобрано:", str(e)[:100], flush=True)
                _retry_wait(e)
        return {"genre": c["genre"], "variant": c["variant"], "judge": jm.split("::")[-1], "scores": None}

    workers = 1 if any(j.startswith("claude_subscription::") for j in judges) else 3
    jobs = [(c, jm) for c in chs for jm in judges]
    random.Random(5).shuffle(jobs)
    rows = list(ThreadPoolExecutor(workers).map(run, jobs))
    json.dump(rows, open(d / os.environ.get("FE_CRAFT_OUT", "questions.json"), "w"),
              ensure_ascii=False, indent=1)
    summary([d])


def summary(dirs: list[Path], thr: float = FAIL_SUM) -> list[dict]:
    """По ответу одного судьи: поймано проваленных B и ложно забраковано живых A."""
    out = []
    for d in dirs:
        for fn in sorted(d.glob("questions*.json")):
            rows = [r for r in json.load(open(fn)) if r.get("scores")]
            mod = d.name
            for j in sorted({r["judge"] for r in rows}):
                a = [sum(r["scores"].values()) for r in rows if r["judge"] == j and r["variant"] == "A"]
                b = [sum(r["scores"].values()) for r in rows if r["judge"] == j and r["variant"] == "B"]
                if not a or not b:
                    continue
                row = {"module": mod, "judge": j, "A": round(mean(a), 2), "B": round(mean(b), 2),
                       "caught": f"{sum(x <= thr for x in b)}/{len(b)}",
                       "false_A": f"{sum(x <= thr for x in a)}/{len(a)}",
                       "ready": sum(x <= thr for x in a) == 0 and 2 * sum(x <= thr for x in b) >= len(b)}
                out.append(row)
                print(f"  {mod:8} судит {j[:28]:28} A {row['A']:5} B {row['B']:5} "
                      f"поймано {row['caught']} ложных {row['false_A']} {'годен' if row['ready'] else '—'}")
    return out


# ─── Слабости обычных глав (что на самом деле не так) ────────────────────────
#
# Модули описывают ремесло, которым модели уже владеют: хуки и напряжение
# обычные главы проходят на 9–10 из 10. Чтобы выбрать, какие модули делать
# проверкой, нужно знать реальные слабости. Судья выписывает до 6 слабостей
# уровня сцены и главы с цитатой; тип — модуль базы, который об этом.

WEAK_TYPES = {
    "сцена_пустая": ("06_scene_structure", "сцена ничего не меняет: ни знания, ни отношений, ни цели"),
    "мотивация": ("09_deep_character_psychology", "поступок или реакция без причины, удобные сюжету"),
    "персонаж_функция": ("02_character_resonance", "персонаж — функция: без своих целей и реакций"),
    "ставки": ("20_stakes_escalation", "неясно, что герой потеряет; ставка не растёт"),
    "темп": ("12_pacing_engine", "провисание, пересказ, затянутая или скомканная сцена"),
    "диалог": ("01_dialogues", "реплики-экспозиция, все говорят одинаково, разговор ради справки"),
    "подтекст": ("10_subtext_engine", "сказано прямо то, что сильнее было бы недосказать"),
    "фокал": ("05_pov", "сбой точки зрения: знание или ощущение вне фокального персонажа"),
    "описание": ("22_sensory_immersion", "общее описание без конкретной детали, декорация"),
    "голос": ("07_voice_consistency", "голос рассказчика скачет, чужой регистр"),
    "тема": ("03_thematic_dna", "событие без смысла для темы и героя"),
    "начало_конец": ("19_hooks_closings", "слабое начало или концовка главы"),
    "логика": ("08_world_state_kernel", "нестыковка, ошибка факта, физики, времени"),
    "другое": ("", ""),
}

WEAK_PROMPT = """Ты редактор. Найди в главе до 6 самых серьёзных слабостей УРОВНЯ СЦЕНЫ И ГЛАВЫ —
то, что редактор вернул бы автору на переработку. Не стиль отдельных фраз (штампы, повторы
слов) — а устройство: сцены, персонажи, ставки, темп, диалог, точка зрения. Если глава
сильная — найди меньше, не выдумывай. Хвалить не нужно.

Для каждой:
- quote: точная цитата из текста, до 20 слов, без изменений — где слабость видна;
- type: одно из: {types};
- why: в чём проблема, до 15 слов.

Типы: {legend}

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг: {{"weak": [{{"quote": "…", "type": "…", "why": "…"}}]}}"""


def weak(sources: dict[str, Path], judges_for: dict[str, list[str]], out: Path) -> None:
    """Слабости уровня сцены: {писатель: файл глав}, {писатель: судьи}."""
    from collections import Counter
    _call = _setup()
    from engine.continuity_checker import quote_in
    from engine.pipeline_llm import parse_json
    legend = "; ".join(f"{k} — {v[1]}" for k, v in WEAK_TYPES.items() if v[1])
    jobs = [(w, c, jm) for w, p in sources.items() for c in json.load(open(p))["chapters"]
            if c.get("text") for jm in judges_for[w]]

    def run(job):
        w, c, jm = job
        prompt = WEAK_PROMPT.format(types=", ".join(WEAK_TYPES), legend=legend, text=c["text"])
        items = None
        for _ in range(2):
            try:
                got = parse_json(_call(jm, "Ты строгий редактор. Отвечаешь только JSON.", prompt,
                                       max_tokens=_mt(jm, 4000)))
                items = got.get("weak") if isinstance(got, dict) else got if isinstance(got, list) else None
                if isinstance(items, list):
                    break
            except Exception as e:
                print("  не разобрано:", str(e)[:100], flush=True)
                _retry_wait(e)
        found = [{"type": x.get("type", "другое"), "quote": x.get("quote", ""), "why": x.get("why", ""),
                  "verified": quote_in(x.get("quote", ""), c["text"])}
                 for x in items or [] if isinstance(x, dict)]
        print(f"  {w:9} {c['genre']:24} #{c['run']} {jm.split('::')[-1]:28} "
              + ("нет ответа" if items is None else f"{sum(f['verified'] for f in found)} подтв. из {len(found)}"),
              flush=True)
        return {"writer": w, "genre": c["genre"], "run": c["run"], "judge": jm.split("::")[-1],
                "failed": items is None, "weak": found}

    sub = any(j.startswith("claude_subscription::") for js in judges_for.values() for j in js)
    # Claude через подписку — строго по одному; остальные параллельно
    nano = [j for j in jobs if not j[2].startswith("claude_subscription::")]
    claude = [j for j in jobs if j[2].startswith("claude_subscription::")]
    with ThreadPoolExecutor(3) as pool:
        fut = pool.map(run, nano)
        rows = [run(j) for j in claude] if sub else []
        rows += list(fut)
    real = [dict(f, writer=r["writer"]) for r in rows for f in r["weak"] if f["verified"]]
    print()
    for w in sources:
        n_ch = len({(r["genre"], r["run"]) for r in rows if r["writer"] == w})
        c = Counter(f["type"] for f in real if f["writer"] == w)
        print(f"  {w:9} глав {n_ch}: " + ", ".join(f"{t} {k}" for t, k in c.most_common()))
    allc = Counter(f["type"] for f in real)
    print("  всего:   " + ", ".join(f"{t} {k} ({WEAK_TYPES.get(t, ('',))[0]})" for t, k in allc.most_common()))
    out.write_text(json.dumps({"judges_for": judges_for, "types": WEAK_TYPES, "rows": rows,
                               "by_type": dict(allc.most_common())}, ensure_ascii=False, indent=1),
                   encoding="utf-8")


# ─── Правка по находкам ──────────────────────────────────────────────────────
#
# Судья лучше находит слабость с цитатой, чем ставит балл: Kimi ставил
# проваленному подтексту 10 из 10, но, выписывая слабости, сам находит его.
# Поэтому UNIFIED работает здесь не советом перед письмом, а содержанием
# правки: судья другого семейства выписывает места (строка и сцена), редактор
# правит только их по указаниям модулей, свежие судьи считают, сколько
# слабостей осталось.

# Тип находки → модуль, чей PROMPT:QUICK идёт редактору как указание
FIX_GUIDE = {
    "подтекст": "03_ADVANCED_ENGINES/10_subtext_engine.md",
    "эмоция_названа": "03_ADVANCED_ENGINES/10_subtext_engine.md",
    "мотивация": "03_ADVANCED_ENGINES/09_deep_character_psychology.md",
    "персонаж_функция": "03_ADVANCED_ENGINES/09_deep_character_psychology.md",
    "темп": "03_ADVANCED_ENGINES/12_pacing_engine.md",
    "вода": "03_ADVANCED_ENGINES/12_pacing_engine.md",
    "диалог": "03_ADVANCED_ENGINES/15_dialogue_style.md",
    "начало_конец": "03_ADVANCED_ENGINES/19_hooks_closings.md",
    "ставки": "03_ADVANCED_ENGINES/20_stakes_escalation.md",
}
FIX_RULES = {
    "логика": "Нестыковку исправь минимально: число, время, факт — так, чтобы сцена стала "
              "согласованной, сюжет не меняй.",
    "фокал": "Убери знание или ощущение, недоступное фокальному персонажу.",
    "повтор": "Повтор замени или убери.",
}

FIX_SYS = ("Ты литературный редактор. Правишь главу точечно: меняешь только указанные места. "
           "Отвечаешь только полным текстом главы, без пояснений.")
FIX_PROMPT = """Ниже глава и список слабых мест, которые нашёл редактор. Исправь ТОЛЬКО их: само место
и, если нужно, соседнее предложение. Остальной текст оставь дословно, слово в слово. Не добавляй
сцен и событий, не меняй сюжет, имена и порядок. Объём — как был (±5 %).

=== СЛАБЫЕ МЕСТА ===
{items}

=== КАК ПРАВИТЬ (из базы ремесла) ===
{guide}

=== ГЛАВА ===
{text}"""


def _guide(types: set[str]) -> str:
    from engine.engine_extractors import extract_prompt_sections
    from engine.engine_loaders_core import load_anticliche_replacements
    kb = ROOT / "UNIFIED_ENGINE_MASTER"
    parts, seen = [], set()
    if types & {"штамп", "ии_оборот", "эмоция_названа"}:
        parts.append(load_anticliche_replacements(kb))
    for t in sorted(types):
        f = FIX_GUIDE.get(t)
        if f and f not in seen:
            seen.add(f)
            q = extract_prompt_sections((kb / f).read_text(encoding="utf-8"), full=False)
            if q:
                parts.append(q)
        if t in FIX_RULES:
            parts.append(FIX_RULES[t])
    return "\n\n".join(parts)


def _find(_call, jm: str, text: str, genre: str) -> list[dict]:
    """Слабости строки (FLAW_PROMPT из ab_compare) и сцены (WEAK_PROMPT) с проверенной цитатой."""
    import ab_compare as ab
    from engine.continuity_checker import quote_in
    from engine.pipeline_llm import parse_json
    prompts = [
        ("flaws", ab.FLAW_PROMPT.format(genre=ab.SEEDS[genre]["genre"], types=", ".join(ab.FLAW_TYPES),
                                        legend="; ".join(f"{k} — {v}" for k, v in ab.FLAW_TYPES.items() if v),
                                        text=text)),
        ("weak", WEAK_PROMPT.format(types=", ".join(WEAK_TYPES), text=text,
                                    legend="; ".join(f"{k} — {v[1]}" for k, v in WEAK_TYPES.items() if v[1]))),
    ]
    out: list[dict] = []
    for key, pr in prompts:
        for _ in range(2):
            try:
                got = parse_json(_call(jm, "Ты строгий редактор. Отвечаешь только JSON.", pr,
                                       max_tokens=_mt(jm, 4000)))
                items = got.get(key) if isinstance(got, dict) else got
                if isinstance(items, list):
                    out += [{"level": key, "type": x.get("type", "другое"), "quote": x.get("quote", ""),
                             "why": x.get("why", "")} for x in items
                            if isinstance(x, dict) and quote_in(x.get("quote", ""), text)]
                    break
            except Exception as e:
                print("  не разобрано:", str(e)[:100], flush=True)
                _retry_wait(e)
    return out


def fix(src: Path, finder: str, editors: list[str], d: Path) -> None:
    _call = _setup()
    import difflib
    chs = [c for c in json.load(open(src))["chapters"] if c.get("text")]
    with ThreadPoolExecutor(3) as pool:
        found = list(pool.map(lambda c: _find(_call, finder, c["text"], c["genre"]), chs))
    for c, f in zip(chs, found):
        c["found"] = f
        print(f"  {c['genre']:24} #{c['run']} находок {len(f)}", flush=True)
    json.dump({"source": str(src), "finder": finder, "chapters": chs},
              open(d / "found.json", "w"), ensure_ascii=False, indent=1)

    def edit(job):
        c, ed = job
        items = "\n".join(f"{i}. [{x['type']}] «{x['quote']}» — {x['why']}" for i, x in enumerate(c["found"], 1))
        prompt = FIX_PROMPT.format(items=items, guide=_guide({x["type"] for x in c["found"]}), text=c["text"])
        for _ in range(3):
            try:
                t = _call(ed, FIX_SYS, prompt, max_tokens=_mt(ed, 12000)).strip()
                if t and len(t.split()) > 0.8 * len(c["text"].split()):
                    a, b = c["text"].split(), t.split()
                    same = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
                    return {"genre": c["genre"], "run": c["run"], "text": t, "words": len(b),
                            "same_ratio": round(same, 3),
                            "quotes_gone": sum(1 for x in c["found"] if _norm(x["quote"]) not in _norm(t))}
            except Exception as e:
                print("  ошибка правки:", str(e)[:100], flush=True)
                _retry_wait(e)
        return {"genre": c["genre"], "run": c["run"], "text": "", "words": 0}

    for ed in editors:
        sub = ed.startswith("claude_subscription::")
        rows = list(ThreadPoolExecutor(1 if sub else 3).map(edit, [(c, ed) for c in chs]))
        tag = ed.split("::")[-1].split("/")[-1]
        json.dump({"model": ed, "chapters": rows}, open(d / f"edited-{tag}.json", "w"),
                  ensure_ascii=False, indent=1)
        for r, c in zip(rows, chs):
            print(f"  {tag[:18]:18} {r['genre']:24} #{r['run']} слов {r['words']} "
                  f"совпадает {r.get('same_ratio')} ушло цитат {r.get('quotes_gone')}/{len(c['found'])}",
                  flush=True)


def _norm(s: str) -> str:
    from engine.continuity_checker import _norm_quote
    return _norm_quote(s)


def measure(versions: dict[str, Path], judges: list[str], out: Path) -> None:
    """Свежие судьи ищут слабости в каждой версии; считаем подтверждённые."""
    _call = _setup()
    jobs = [(v, c, jm) for v, p in versions.items() for c in json.load(open(p))["chapters"]
            if c.get("text") for jm in judges]

    def run(job):
        v, c, jm = job
        f = _find(_call, jm, c["text"], c["genre"])
        print(f"  {v:18} {c['genre']:24} #{c['run']} {jm.split('::')[-1][:24]:24} {len(f)}", flush=True)
        return {"version": v, "genre": c["genre"], "run": c["run"], "judge": jm.split("::")[-1], "found": f}

    rows = list(ThreadPoolExecutor(3).map(run, jobs))
    print()
    for j in judges:
        jj = j.split("::")[-1]
        for v in versions:
            r = [x for x in rows if x["version"] == v and x["judge"] == jj]
            fl = sum(1 for x in r for f in x["found"] if f["level"] == "flaws")
            wk = sum(1 for x in r for f in x["found"] if f["level"] == "weak")
            print(f"  {jj[:24]:24} {v:18} строка {fl:3}  сцена {wk:3}  всего {fl + wk:3}  (глав {len(r)})")
    out.write_text(json.dumps({"judges": judges, "versions": {k: str(p) for k, p in versions.items()},
                               "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


# ─── Калибровка шкалы классикой ──────────────────────────────────────────────
#
# «7.7 из 10» у наших глав — мнение судей по рубрике ab_compare.RUBRIC, ни с
# чем не сверенное. Те же судьи и та же рубрика — на главах классики
# (общественное достояние) того же жанра и объёма. Задача главы нейтральная
# у всех: классика писалась не под нашу задачу. Судья называет автора, если
# узнал текст, — узнанная классика может получить надбавку за имя.

CALIB_GENRE = {"detective_classic": "детектив", "fantasy_dark": "тёмная фантастика, мистика",
               "thriller_psychological": "психологический триллер",
               "realism_psychological": "психологическая проза"}
CALIB_TAIL = """

Отдельно: если ты узнал этот текст — назови автора и произведение, иначе «не знаю».
Добавь в JSON поле "recognized": "…"."""


def calibrate(sets: dict[str, Path], judges: list[str], out: Path) -> None:
    _call = _setup()
    import ab_compare as ab
    from engine.pipeline_llm import parse_json
    rubric = "\n".join(f"- {k}: {v}" for k, v in ab.RUBRIC.items())
    keys = ", ".join(f'"{k}": N' for k in ab.RUBRIC)
    jobs = [(name, c, jm) for name, p in sets.items() for c in json.load(open(p))["chapters"]
            if c.get("text") for jm in judges]

    def run(job):
        name, c, jm = job
        prompt = ab.RATE_PROMPT.format(genre=CALIB_GENRE[c["genre"]], task="глава художественной прозы",
                                       rubric=rubric, keys=keys, text=c["text"]) + CALIB_TAIL
        got, sc = None, None
        for _ in range(2):
            try:
                got = parse_json(_call(jm, ab.RATE_SYSTEM, prompt, max_tokens=_mt(jm, 2000)))
                sc = {k: float(got["scores"][k]) for k in ab.RUBRIC} if isinstance(got, dict) else None
                if sc:
                    break
            except Exception as e:
                print("  не разобрано:", str(e)[:100], flush=True)
                _retry_wait(e)
        rec = str((got or {}).get("recognized", "")) if isinstance(got, dict) else ""
        mean_ = round(mean(sc.values()), 2) if sc else None
        print(f"  {name:9} {c.get('title', c['genre'])[:40]:40} {jm.split('::')[-1][:22]:22} "
              f"{mean_}  узнал: {rec[:40]}", flush=True)
        return {"set": name, "genre": c["genre"], "run": c["run"], "title": c.get("title", ""),
                "judge": jm.split("::")[-1], "scores": sc, "mean": mean_, "recognized": rec}

    rows = list(ThreadPoolExecutor(3).map(run, jobs))
    print()
    for name in sets:
        for j in judges:
            jj = j.split("::")[-1]
            v = [r["mean"] for r in rows if r["set"] == name and r["judge"] == jj and r["mean"] is not None]
            if v:
                print(f"  {name:9} {jj[:24]:24} среднее {mean(v):.2f}  ({len(v)} глав)")
    out.write_text(json.dumps({"judges": judges, "sets": {k: str(v) for k, v in sets.items()},
                               "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "calibrate":
        C = ROOT / ".ab_work/craft"
        W = ROOT / ".ab_work/writers"
        sub = {}
        for name, p in (("GLM", C / "glm.json"), ("DeepSeek", W / "deepseek.json"), ("Sonnet", W / "sonnet2.json")):
            chs = [c for c in json.load(open(p))["chapters"] if int(c["run"]) == 0]
            sub[name] = C / f"calib-{name}.json"
            json.dump({"chapters": chs}, open(sub[name], "w"), ensure_ascii=False)
        calibrate({"классика": C / "classics.json", **sub}, JUDGES, C / "calibrate.json")
        sys.exit(0)
    if cmd == "fix":
        d = ROOT / ".ab_work/craft/fix"
        d.mkdir(parents=True, exist_ok=True)
        fix(ROOT / ".ab_work/writers/deepseek.json", JUDGES[0], [JUDGES[1], REWRITER], d)
        sys.exit(0)
    if cmd == "measure":
        d = ROOT / ".ab_work/craft/fix"
        measure({"до": ROOT / ".ab_work/writers/deepseek.json",
                 "правил DeepSeek": d / "edited-deepseek-v4-pro-0813.json",
                 "правил Sonnet": d / "edited-claude-sonnet-5-5.json"}, JUDGES, d / "measure.json")
        sys.exit(0)
    if cmd == "weak":
        K, D, S = JUDGES[0], JUDGES[1], REWRITER
        W = ROOT / ".ab_work/writers"
        weak({"glm": ROOT / ".ab_work/craft/glm.json", "deepseek": W / "deepseek.json",
              "sonnet": W / "sonnet2.json"},
             # никто не судит своё семейство; Claude не судит Claude
             {"glm": [K, S], "deepseek": [K, S], "sonnet": [K, D]},
             ROOT / ".ab_work/craft/weak.json")
        sys.exit(0)
    if cmd == "summary":
        summary([Path(p) for p in sys.argv[2:]] or sorted(p for p in (ROOT / ".ab_work/craft").glob("*")
                                                         if p.is_dir()))
        sys.exit(0)
    mod = sys.argv[2]
    d = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / ".ab_work/craft" / mod
    d.mkdir(parents=True, exist_ok=True)
    {"rewrite": rewrite, "questions": questions}[cmd](mod, d)
