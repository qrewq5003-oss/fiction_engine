"""
Проверка второй линии книги по семействам жанров (ROADMAP_TEXT, «Отложено:
проверка второй линии»).

Для романтики замер 06.10 показал: судья с оценкой 0–10 и с контрактом живую
и проваленную линию не различает, а пять конкретных вопросов о ремесле линии
(0–2 каждый) — различают: живая 10 из 10, проваленная 7.0. Здесь то же для
остальных семейств.

    python tools/secondary_line/families.py rewrite  horror [каталог]
    python tools/secondary_line/families.py questions horror [каталог]
    python tools/secondary_line/families.py report   horror [каталог]

rewrite — 4 главы основного жанра из набора GLM (bench/base-pool-2026-10-05.json)
DeepSeek переписывает дважды: A — с живой второй линией семейства, B — с той же
линией, проваленной. questions — судьи отвечают на вопросы семейства. report —
различает ли набор A и B и ловит ли правило проваленные без ложных отказов.
Каталог по умолчанию — .ab_work/secondary_line/<семейство>.
"""
from __future__ import annotations

import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]

REWRITER = "nano_gpt::deepseek/deepseek-v4-pro-0813"
CHAPTERS = 4

# Правило провала по ответу одного судьи (report): сумма из 10 не больше
# FAIL_SUM — или ключевой вопрос (key, 1-based) получил 0. Оно оказалось
# слишком строгим: один придирчивый ответ бракует живую главу.
FAIL_SUM = 7
# Правило по главе (summary): среднее судей по главе не больше CHAPTER_FAIL.
# 5.5 — самый строгий из проверенных порогов (5.0–6.5), при котором на парах,
# написанных Sonnet, нет ни одного ложного отказа живой линии.
CHAPTER_FAIL = 5.5

FAMILIES: dict[str, dict] = {
    "romance": {
        "base": "detective_classic", "label": "романтическая",
        "line": "романтическую линию между главной героиней и одним из мужских персонажей главы "
                "(с кем у неё больше всего сцен)",
        "A": "химия показана через детали — что она замечает в нём, паузы, недосказанность, телесная "
             "реакция без названия чувства; есть напряжение и препятствие; линия идёт через несколько "
             "сцен и сдвигает их отношения",
        "B": "чувства названы прямо и без опоры («она поняла, что влюблена»), химии и напряжения нет, "
             "он плоский и функциональный, их разговоры только по делу, влечение возникает внезапно",
        "Q": ["Чувство показано через детали — что она замечает в нём, паузы, тело, — а не названо "
              "словами («влюблена», «любит»)",
              "Между ними есть напряжение или препятствие, которое мешает прямо сейчас",
              "Признание или влечение подготовлено предыдущими сценами, а не возникает внезапно",
              "Он — живой человек со своими целями и реакциями, а не функция сюжета",
              "Их разговоры несут подтекст: говорят об одном, слышат другое"],
        "key": 1,
    },
    "detective": {
        "base": "realism_psychological", "label": "детективная",
        "line": "детективную линию: загадку (пропажа, подозрительная смерть, ложь кого-то из близких), "
                "которую главный герой пытается разгадать",
        "A": "загадка конкретна; герой добывает сведения сам — расспрашивает, замечает, проверяет; "
             "детали-улики показаны читателю до вывода; вывод следует из показанного; к концу главы "
             "вопрос острее или известно больше",
        "B": "загадка объявлена общими словами («он решил докопаться до правды»), ответы приходят "
             "готовыми — кто-то рассказывает или находится записка, улик до вывода нет, вывод — "
             "озарение или совпадение, к концу главы ничего не сдвинулось",
        "Q": ["Есть конкретная загадка — что случилось, кто, почему, — а не общее «что-то не так»",
              "Герой добывает сведения действием — расспрашивает, замечает, проверяет, — а не получает "
              "ответ готовым",
              "Улики и детали показаны читателю до вывода, а не появляются задним числом",
              "Вывод героя следует из показанного, а не из озарения или совпадения",
              "К концу главы известно больше или вопрос стал острее, чем в начале"],
        "key": 2,
    },
    "thriller": {
        "base": "realism_psychological", "label": "триллерная",
        "line": "триллерную линию: внешнюю угрозу главному герою (преследователь, шантаж, опасность, "
                "у которой есть срок)",
        "A": "угроза конкретна — кто или что и чем грозит; есть срок или сжимающееся пространство; "
             "опасность видна по действиям и последствиям; герой принимает решения под давлением, и "
             "они чего-то стоят; к концу главы ставка выше",
        "B": "угроза названа общими словами («ему грозила опасность», «он чувствовал, что за ним "
             "следят»), срока и ограничений нет, ничего не происходит, герой ничего не решает и ничем "
             "не платит, к концу главы ставка та же",
        "Q": ["Угроза конкретна: известно, кто или что угрожает и чем",
              "Есть ограничение времени или пространства, и оно сжимается",
              "Опасность показана через действия и последствия, а не названа словами",
              "Герой принимает решения под давлением, и эти решения чего-то стоят",
              "Ставка растёт к концу главы или появляется новая угроза"],
        "key": 3,
    },
    "horror": {
        "base": "detective_classic", "label": "хоррор-",
        "line": "хоррор-линию: что-то необъяснимое и пугающее рядом с главной героиней (в доме, в "
                "месте преступления, в ком-то из людей)",
        "A": "страх создаётся деталями восприятия — звук, запах, неправильность, — не называется; "
             "тревога нарастает постепенно; источник недосказан; реакции телесны и без комментария "
             "героини о собственном страхе; нормальный мир надломлен конкретным образом",
        "B": "страх назван прямо («ей стало страшно», «жуткое чувство охватило её»), сразу на "
             "максимуме, без нарастания; источник объяснён целиком или размыт до «чего-то зловещего»; "
             "героиня рассуждает о своём страхе; образов нет — общие слова «мрачно», «зловеще»",
        "Q": ["Страх создаётся деталями восприятия — звук, запах, неправильность, — а не назван "
              "(«ей стало страшно»)",
              "Тревога нарастает постепенно, а не появляется сразу на максимуме",
              "Источник угрозы недосказан: показано достаточно, чтобы тревожить, но не всё объяснено",
              "Реакции героини телесны, она не комментирует собственный страх",
              "Нормальный мир надломлен конкретным, запоминающимся образом, а не общими словами "
              "«мрачно», «зловеще»"],
        "key": 1,
    },
    "fantasy": {
        "base": "detective_classic", "label": "фэнтезийная",
        "line": "фэнтезийную линию: в мире есть магия или чудесное, и оно касается расследования",
        "A": "у чудесного есть правила и цена; мир показан деталями и последствиями, без лекции; "
             "магия влияет на выбор и действия героев в этой главе; люди реагируют на неё в логике "
             "своего мира; есть ощущение, что мир больше объяснённого",
        "B": "магия решает задачу по желанию, без цены и правил; мир объяснён лекцией рассказчика; "
             "чудесное — декорация, на решения не влияет; реакции людей случайны; всё объяснено",
        "Q": ["Чудесное подчиняется правилам или цене, а не решает проблему по желанию",
              "Мир показан через конкретные детали и последствия, а не объяснён лекцией",
              "Магия или чудесное влияет на выбор и действия героев в этой главе",
              "Персонажи реагируют на чудесное последовательно, в логике своего мира",
              "Есть ощущение тайны: мир больше, чем объяснено"],
        "key": 1,
    },
    "scifi": {
        "base": "thriller_psychological", "label": "научно-фантастическая",
        "line": "научно-фантастическую линию: технология или научная идея (имплант, наблюдение, "
                "редактирование памяти, ИИ), которая есть в мире главы",
        "A": "идея конкретна и работает по понятным правилам; меняет поведение людей и ситуацию; "
             "объяснения встроены в действие; у неё есть следствие, которого герои не ждали; детали "
             "согласованы",
        "B": "технология — название и декорация («благодаря новейшей технологии»), правил нет, на "
             "людей не влияет; объяснена лекцией; следствий нет; детали противоречат друг другу",
        "Q": ["Научная или техническая идея конкретна и работает по понятным правилам",
              "Технология меняет поведение людей или ситуацию, а не просто декорация",
              "Объяснения встроены в действие, без лекции",
              "У идеи есть следствие, которого персонажи не ожидали",
              "Детали технологии и мира согласованы между собой"],
        "key": 2,
    },
    "realism": {
        "base": "fantasy_dark", "label": "психологическая",
        "line": "психологическую линию: внутренний конфликт главного героя и его отношения с одним "
                "близким человеком",
        "A": "внутреннее состояние видно по поступкам, деталям и умолчаниям, рассказчик его не "
             "объясняет; в герое есть противоречие — хочет одного, делает другое; бытовые детали "
             "конкретны и работают на характер; отношения в главе сдвигаются; морали нет",
        "B": "чувства и мотивы объяснены рассказчиком прямо («он чувствовал вину, потому что…»), "
             "противоречия нет, детали общие, отношения не меняются, в конце готовый вывод или мораль",
        "Q": ["Внутреннее состояние показано через поступки, детали и умолчания, а не объяснено "
              "рассказчиком",
              "В герое есть противоречие: хочет одного, делает другое",
              "Бытовые детали конкретны и работают на характер",
              "Отношения между людьми в главе сдвигаются хотя бы на шаг",
              "Нет готовых выводов и морали: читатель делает их сам"],
        "key": 1,
    },
}

SYS_REWRITE = ("Ты опытный редактор художественной прозы. Переписываешь главу по заданию. "
               "Отвечаешь только текстом главы, без пояснений.")
COMMON = ("Сохрани основную линию главы целиком: те же сцены, персонажи, события и их порядок. "
          "Сохрани объём (около {w} слов) и манеру. Добавь в главу {line} — она идёт через "
          "несколько сцен.")
TASK = {"A": "Сделай эту линию живой: {A}.",
        "B": "Линия должна присутствовать в тех же сценах и тем же объёмом, но быть проваленной: {B}. "
             "Пиши это ровно и без иронии, как будто так и задумано."}

ASK = """Ниже глава с {label} линией. Ответь на вопросы только об этой линии.
Оценка: 0 — нет, 1 — частично, 2 — да, явно. Сначала короткая цитата-доказательство, потом оценка.

{qs}

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг: {{"answers": [{{"q": 1, "quote": "…", "score": 0}}, …]}}"""


def _backoff(e: Exception) -> None:
    """Отказ 429 (слишком много запросов) — подождать, а не тратить попытку сразу."""
    if "429" in str(e):
        import time
        time.sleep(random.uniform(20, 40))


def _setup():
    sys.path.insert(0, str(ROOT / "tools"))
    sys.path.insert(0, str(ROOT / "fiction_engine"))
    import ab_compare as ab
    ab._temp_db(ROOT / "fiction_engine")
    return ab


def rewrite(fam: str, d: Path) -> None:
    ab = _setup()
    from engine.pipeline import _call
    f = FAMILIES[fam]
    # FE_LINE_REWRITER — другой писатель пар A/B (Claude через подписку — по одному вызову)
    writer = os.environ.get("FE_LINE_REWRITER") or REWRITER
    sub = writer.startswith("claude_subscription::")
    pool = json.load(open(ROOT / "bench/base-pool-2026-10-05.json"))["chapters"]
    base = [c for c in pool if c["genre"] == f["base"] and c.get("text")][:CHAPTERS]

    def run(job):
        c, v = job
        prompt = (COMMON.format(w=c["words"], line=f["line"]) + "\n\n" + TASK[v].format(**f)
                  + "\n\n=== ГЛАВА ===\n" + c["text"])
        for _ in range(3):
            try:
                t = _call(writer, SYS_REWRITE, prompt, max_tokens=32000 if sub else 12000)
                if t and len(t.split()) > 0.6 * c["words"]:
                    return {"run": c["run"], "variant": v, "text": t.strip(), "words": len(t.split())}
            except Exception as e:
                print("ошибка", c["run"], v, str(e)[:120], flush=True)
                _backoff(e)
        return {"run": c["run"], "variant": v, "text": "", "words": 0}

    rows = list(ThreadPoolExecutor(1 if sub else 3).map(run, [(c, v) for c in base for v in "AB"]))
    json.dump({"family": fam, "base": f["base"], "rewriter": writer, "chapters": rows},
              open(d / "rewritten.json", "w"), ensure_ascii=False, indent=1)
    for r in rows:
        print(f"  {fam} {r['run']} {r['variant']} {r['words']} слов", flush=True)


def questions(fam: str, d: Path) -> None:
    ab = _setup()
    from engine.pipeline import _call
    from engine.pipeline_llm import parse_json
    f = FAMILIES[fam]
    chs = [r for r in json.load(open(d / "rewritten.json"))["chapters"] if r["text"]]
    qs = "\n".join(f"{i}. {q}" for i, q in enumerate(f["Q"], 1))

    def run(job):
        c, jm = job
        for _ in range(2):
            try:
                got = parse_json(_call(jm, "Ты строгий редактор. Отвечаешь только JSON.",
                                       ASK.format(label=f["label"], qs=qs, text=c["text"]),
                                       max_tokens=32000 if jm.startswith("claude_subscription::")
                                       else 3000)) or {}
                a = {int(x["q"]): float(x["score"]) for x in got.get("answers", [])}
                if len(a) == len(f["Q"]):
                    return {"variant": c["variant"], "run": c["run"], "judge": jm.split("::")[-1], "scores": a}
            except Exception as e:
                print("  не разобрано:", str(e)[:100], flush=True)
                _backoff(e)
        return {"variant": c["variant"], "run": c["run"], "judge": jm.split("::")[-1], "scores": None}

    # FE_LINE_JUDGES — свои судьи (через запятую), FE_LINE_OUT — свой файл ответов.
    # Claude через подписку — строго по одному вызову.
    judges = [j for j in os.environ.get("FE_LINE_JUDGES", "").split(",") if j] or ab.DEFAULT_JUDGES
    workers = 1 if any(j.startswith("claude_subscription::") for j in judges) else 3
    jobs = [(c, jm) for c in chs for jm in judges]
    random.Random(3).shuffle(jobs)
    rows = list(ThreadPoolExecutor(workers).map(run, jobs))
    json.dump(rows, open(d / _out_name(), "w"), ensure_ascii=False, indent=1)
    report(fam, d)


def fails(scores: dict, key: int) -> bool:
    return sum(scores.values()) <= FAIL_SUM or scores[key] == 0


def _out_name() -> str:
    return os.environ.get("FE_LINE_OUT", "questions.json")


def report(fam: str, d: Path) -> dict:
    f = FAMILIES[fam]
    rows = json.load(open(d / _out_name()))
    ok = [r for r in rows if r["scores"]]
    for r in ok:
        r["scores"] = {int(k): v for k, v in r["scores"].items()}
    print(f"== {fam} (основа {f['base']})")
    if not {r["variant"] for r in ok} >= {"A", "B"}:
        print(f"  нет ответов судей по обеим версиям (разобрано {len(ok)} из {len(rows)})")
        return {"family": fam, "ready": False, "unparsed": len(rows) - len(ok)}
    for i, q in enumerate(f["Q"], 1):
        a = mean(r["scores"][i] for r in ok if r["variant"] == "A")
        b = mean(r["scores"][i] for r in ok if r["variant"] == "B")
        print(f"  A {a:.2f}  B {b:.2f}  {q[:70]}")
    out = {"family": fam}
    for v in "AB":
        s = [sum(r["scores"].values()) for r in ok if r["variant"] == v]
        n_fail = sum(fails(r["scores"], f["key"]) for r in ok if r["variant"] == v)
        out[v] = {"sum": round(mean(s), 2), "fail": n_fail, "n": len(s)}
        print(f"  {v} сумма {mean(s):.2f} из 10, правило бракует {n_fail} из {len(s)}")
    out["unparsed"] = len(rows) - len(ok)
    out["ready"] = out["A"]["fail"] == 0 and out["B"]["fail"] * 2 >= out["B"]["n"]
    print(f"  не разобрано {out['unparsed']}; набор {'годен' if out['ready'] else 'НЕ годен'}")
    return out


def summary(dirs: list[Path], thr: float = CHAPTER_FAIL) -> list[dict]:
    """
    Годен ли набор по правилу «среднее судей по главе ≤ thr»: поймана хотя бы
    половина проваленных глав и ни одной живой. Для каждого каталога пар
    (кто писал) и каждого файла ответов (кто судил).
    """
    out = []
    for base in dirs:
        for fam in FAMILIES:
            for fn in sorted((base / fam).glob("questions*.json")):
                rows = [r for r in json.load(open(fn)) if r.get("scores")]
                ch: dict = {}
                for r in rows:
                    ch.setdefault((r["variant"], r["run"]), []).append(sum(r["scores"].values()))
                a = [mean(v) for (k, _), v in ch.items() if k == "A"]
                b = [mean(v) for (k, _), v in ch.items() if k == "B"]
                if not a or not b:
                    continue
                writer = json.load(open(base / fam / "rewritten.json")).get("rewriter", "?")
                caught, false_a = sum(x <= thr for x in b), sum(x <= thr for x in a)
                row = {"family": fam, "writer": writer.split("::")[-1],
                       "judges": sorted({r["judge"] for r in rows}), "A": round(mean(a), 2),
                       "B": round(mean(b), 2), "caught": f"{caught}/{len(b)}",
                       "false_A": f"{false_a}/{len(a)}",
                       "ready": false_a == 0 and caught * 2 >= len(b)}
                out.append(row)
                print(f"  {fam:9} пишет {row['writer'][:18]:18} судят {','.join(row['judges'])[:40]:40} "
                      f"A {row['A']:5} B {row['B']:5} поймано {row['caught']} ложных {row['false_A']} "
                      f"{'годен' if row['ready'] else '—'}")
    return out


if __name__ == "__main__":
    if sys.argv[1] == "summary":
        summary([Path(p) for p in sys.argv[2:]] or [ROOT / ".ab_work/secondary_line",
                                                    ROOT / ".ab_work/secondary_line_sonnet"])
        sys.exit(0)
    cmd, fam = sys.argv[1], sys.argv[2]
    d = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / ".ab_work/secondary_line" / fam
    d.mkdir(parents=True, exist_ok=True)
    {"rewrite": rewrite, "questions": questions, "report": report}[cmd](fam, d)
