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


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "summary":
        summary([Path(p) for p in sys.argv[2:]] or sorted(p for p in (ROOT / ".ab_work/craft").glob("*")
                                                         if p.is_dir()))
        sys.exit(0)
    mod = sys.argv[2]
    d = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / ".ab_work/craft" / mod
    d.mkdir(parents=True, exist_ok=True)
    {"rewrite": rewrite, "questions": questions}[cmd](mod, d)
