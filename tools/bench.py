#!/usr/bin/env python3
"""
bench.py — повторяемый замер качества текста.

Зачем
─────
13 сентября 2026 замер 19 моделей показал, что ни одна глава не проходит
порог принятия движка (средний итог 24.3 из 50 при пороге 40), а двенадцать
претензий критика из четырнадцати — про одно и то же. Выводы получены
одноразовыми скриптами по одному прогону на модель: отличить настоящую
починку от везения по ним нельзя.

Этот инструмент делает замер повторяемым. Он — нулевой этап
ROADMAP_TEXT.md: без него все остальные проверяются словами «стало лучше».

Что именно меряется
───────────────────
ДВИЖОК, а не ваш роман. Промпт собирается из фиксированного посева во
временную базу, поэтому он зависит только от кода движка. Если бы посев
брался из рабочего проекта, промпт менялся бы вместе с текстом романа и
два замера перестали бы быть сравнимыми.

Рабочая база при этом не открывается вовсе.

Честность сравнения
───────────────────
В файл замера кладутся хэш промпта и ревизия git. При сравнении двух
файлов инструмент СНАЧАЛА говорит, совпадают ли промпты: если нет, разница
в баллах может быть следствием правки промпта, а не улучшения, и об этом
надо знать до того, как радоваться.

Запуск
──────
    python tools/bench.py --out bench/2026-09-14.json
    python tools/bench.py --models z-ai/glm-5.3,moonshotai/kimi-k2.5 --runs 3
    python tools/bench.py --compare bench/2026-09-13.json bench/2026-09-14.json
    python tools/bench.py --list          # что замеряется по умолчанию

Нужен ключ провайдера в рабочей БД — он читается, но ничего не пишется.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "fiction_engine"

# Пять лучших по замеру 2026-09-13. Меняется флагом --models.
DEFAULT_MODELS = [
    "nano_gpt::z-ai/glm-5.3",
    "nano_gpt::moonshotai/kimi-k2.5",
    "nano_gpt::deepseek/deepseek-v4-pro-0813",
    "nano_gpt::moonshotai/kimi-k2-thinking",
    "anthropic_direct::claude-haiku-4-5-20251001",
]

# Судья один на все модели — иначе шкалы разные и сравнивать нечего.
DEFAULT_JUDGE = "anthropic_direct::claude-haiku-4-5-20251001"

CRITERIA = ("voice", "structure", "characters", "scenes", "dialog")

# ─── Фиксированный посев ─────────────────────────────────────────────────────
#
# Меняя его, вы меняете замер: старые файлы станут несравнимы. Хэш промпта
# в выводе это покажет, но лучше просто не трогать без причины.

SEED = {
    "name": "Эталон замера",
    "genre": "городское фэнтези",
    "chapter_num": 3,
    "prev_chapter": (
        "Лукаш вышел из подвала под утро. Руки были в земле. "
        "Он не помнил, как поднялся по лестнице. " * 12
    ),
    "state": (
        "## ПЕРСОНАЖИ\n\n"
        "### Лукаш Новак\n"
        "Роль: протагонист, инженер сенсорных систем\n"
        "Состояние: механически функционирует, психически раскалывается\n"
        "Цель: понять природу видения\n"
        "Знает: под зданием был алхимический узел\n\n"
        "### Павел\n"
        "Роль: единственный, кто остался рядом\n"
        "Состояние: не верит официальной версии\n\n"
        "## ЛОКАЦИИ\nПрага: промышленная зона, музей алхимии, кафе на Виноградах\n"
    ),
    "task": "Лукаш приходит в музей алхимии на встречу с незнакомцем, "
            "который знает о его видении.",
}


def _read_real_keys() -> list[tuple[str, str]]:
    """Ключи из рабочей БД. Только чтение — замер в неё ничего не пишет."""
    import sqlite3
    sys.path.insert(0, str(APP))
    import engine.db_core as dbc
    real = Path(dbc.DB_PATH)
    if not real.exists():
        return []
    conn = sqlite3.connect(f"file:{real}?mode=ro", uri=True)
    try:
        return [(r[0], r[1]) for r in conn.execute("SELECT provider, api_key FROM api_keys")
                if (r[1] or "").strip()]
    except Exception:
        return []
    finally:
        conn.close()


def _bootstrap(mode: str):
    """Временная БД с фиксированным посевом. Возвращает (промпт, жанр)."""
    keys = _read_real_keys()          # прочитать ДО подмены пути
    sys.path.insert(0, str(APP))
    import engine.db_core as dbc
    dbc.DB_PATH = Path(tempfile.mkdtemp(prefix="bench_")) / "bench.db"
    dbc.init_db()
    with dbc.get_conn() as conn:
        for provider, key in keys:
            conn.execute("INSERT OR REPLACE INTO api_keys (provider, api_key) VALUES (?,?)",
                         (provider, key))
    from engine.db import (create_project, set_active_project, save_chapter,
                           update_state, get_project)
    from engine.state_prompts import build_prompt

    pid = create_project(SEED["name"], SEED["genre"])
    set_active_project(pid)
    save_chapter(pid, SEED["chapter_num"] - 1, SEED["prev_chapter"], "Предыдущая глава")
    update_state(pid, SEED["state"], "", "")
    prompt = build_prompt(pid, SEED["chapter_num"], mode, get_project(pid))
    return prompt, SEED["genre"]


def _git_rev() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return "?"


# Сколько раз повторять вызов, если модель вернула пустой ответ.
#
# Замер 2026-09-13: z-ai/glm-5.3 отдаёт пустое содержимое примерно в
# половине вызовов (поведение провайдера — проверено и сырым HTTP, и через
# SDK). Без повтора замер такой модели показал бы 0 из 50, что неотличимо
# от «написала плохо». Повтор именно здесь, а не в движке: движок обязан
# сообщить автору об отказе, а замер — измерить модель, когда она отвечает.
EMPTY_RETRIES = 3


def _measure(model: str, prompt: str, genre: str, judge: str) -> dict:
    from engine.pipeline import _call, score_text
    from engine.pipeline_config import PROSE_MAX_TOKENS
    sys_gen = "Ты профессиональный писатель. Пишешь главу романа."
    t0 = time.time()
    text, empty_tries = None, 0
    for attempt in range(EMPTY_RETRIES):
        try:
            text = _call(model, sys_gen, prompt, max_tokens=PROSE_MAX_TOKENS)
            break
        except ValueError as e:
            if "пустой ответ" not in str(e) or attempt == EMPTY_RETRIES - 1:
                raise
            empty_tries += 1
    gen_s = round(time.time() - t0)
    sc = score_text(text, genre, judge)
    return {
        "words": len(text.split()),
        "seconds": gen_s,
        "total": sc["total"],
        **{c: sc[c] for c in CRITERIA},
        "verdict": sc["verdict"],
        "main_issue": (sc.get("main_issue") or "")[:160],
        "pct_short": (sc.get("rhythm") or {}).get("short"),   # ключ именно short
        "empty_retries": empty_tries,
    }


# ─── Замер редакторов ────────────────────────────────────────────────────────
#
# Отдельный режим, потому что мерит другое: не «как пишет», а «станет ли
# переписывать». Опыт 2026-09-13 показал, что это разные способности —
# DeepSeek V4 Pro дважды вернул исходник дословно (схожесть 96.9% между
# двумя своими же «редактурами»), а Kimi K2.5 переписала по-настоящему и
# сдвинула долю коротких предложений с 59% до 14%.
#
# Вход фиксированный: bench/editor_input.txt. Так модели сравнимы между
# собой, и хватает одного вызова на каждую вместо двух.
#
# Мерится арифметикой, а не судьёй: схожесть текстов, доля коротких, объём.
# Шума в этих числах нет — в отличие от баллов, где он равен 11.

EDITOR_INPUT = ROOT / "bench" / "editor_input.txt"

EDIT_ASK = (
    "Перепиши текст ниже, исправив ТОЛЬКО ритм предложений. Сюжет, события, "
    "реплики и порядок сцен не менять. Объединяй рубленые фразы в средние и "
    "длинные там, где это не ломает смысл."
)


def run_editors(models: list[str], out: Path | None) -> int:
    import difflib
    from engine.pipeline import _call
    from engine.pipeline_steps import analyze_sentence_rhythm
    from engine.pipeline_config import PROSE_MAX_TOKENS, RHYTHM_RANGE

    _bootstrap("master")                       # ключи + временная БД
    src = EDITOR_INPUT.read_text(encoding="utf-8")
    before = analyze_sentence_rhythm(src)
    lo, hi = RHYTHM_RANGE["short"]
    print(f"  вход: {len(src.split())} слов, коротких {before['short']}% "
          f"(допуск {lo}-{hi}%)\n")
    print(f"  {'редактор':40} {'коротких':>9} {'схожесть':>9} {'объём':>8}  вывод")
    print("  " + "─" * 82)

    results = {}
    for model in models:
        name = model.split("::", 1)[1]
        try:
            edited = _call(model, "Ты редактор. Возвращаешь только переработанный текст.",
                           f"{before['hint']}\n\n{EDIT_ASK}\n\nТЕКСТ:\n{src}",
                           max_tokens=PROSE_MAX_TOKENS)
        except Exception as e:
            results[name] = {"error": str(e)[:70]}
            print(f"  {name:40} {'—':>9} {'—':>9} {'—':>8}  {str(e)[:28]}", flush=True)
            continue
        after = analyze_sentence_rhythm(edited)
        same  = difflib.SequenceMatcher(None, src, edited).ratio()
        grow  = len(edited.split()) / max(len(src.split()), 1)
        rewrote  = same < 0.95
        in_range = lo <= after["short"] <= hi
        kept     = grow <= 1.15
        verdict = ("годится" if (rewrote and in_range and kept) else
                   "вернул исходник" if not rewrote else
                   "раздул текст" if not kept else
                   "перелёт" if after["short"] < lo else "не дотянул")
        results[name] = {"short_before": before["short"], "short_after": after["short"],
                         "similarity": round(same, 3), "growth": round(grow, 2),
                         "rewrote": rewrote, "in_range": in_range, "kept_length": kept,
                         "verdict": verdict}
        print(f"  {name:40} {before['short']:3}→{after['short']:3}% "
              f"{same:8.0%} {grow:7.0%}  {verdict}", flush=True)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "date": date.today().isoformat(), "git": _git_rev(),
            "kind": "editors",
            "input_hash": hashlib.sha256(src.encode()).hexdigest()[:12],
            "input_words": len(src.split()),
            "criteria": "переписал (схожесть <95%) И попал в допуск 20-40% И не раздул (<115%)",
            "models": results,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n  записано: {out}")
    good = [n for n, v in results.items() if v.get("verdict") == "годится"]
    print(f"\n  годятся в редакторы: {', '.join(good) if good else 'ни одна'}")
    return 0


def run_edit_gain(gen_model: str, editor: str, judge: str, runs: int,
                  mode: str, out: Path | None) -> int:
    """
    Окупается ли лишний вызов редактора — ПАРНЫМ сравнением.

    Один и тот же текст оценивается до и после редактуры. Это важно:
    разброс между независимыми прогонами равен 4 баллам (этап 0), и на
    нём эффект в 2-3 балла утонет. В паре разброс генерации общий для
    обеих оценок и сокращается, поэтому различимо куда меньшее.

    Судья один и тот же на обе оценки — иначе сравниваются шкалы.
    """
    import difflib, statistics
    from engine.pipeline import _call, score_text
    from engine.pipeline_steps import analyze_sentence_rhythm
    from engine.pipeline_config import PROSE_MAX_TOKENS

    prompt, genre = _bootstrap(mode)
    print(f"  генератор {gen_model.split('::')[1]}")
    print(f"  редактор  {editor.split('::')[1]}")
    print(f"  судья     {judge.split('::')[1]}, режим {mode}, пар {runs}\n")
    print(f"  {'#':>2} {'до':>5} {'после':>6} {'Δ':>6}  {'коротких':>12}  {'слов':>13}  схожесть")
    print("  " + "─" * 72)

    pairs = []
    for i in range(runs):
        try:
            draft = _call(gen_model, "Ты профессиональный писатель. Пишешь главу романа.",
                          prompt, max_tokens=PROSE_MAX_TOKENS)
            s_before = score_text(draft, genre, judge)
            rh = analyze_sentence_rhythm(draft)
            crit = s_before.get("raw", "")
            edited = _call(editor, "Ты редактор. Возвращаешь только переработанный текст.",
                           f"ОРИГИНАЛЬНЫЙ ТЕКСТ:\n{draft}\n\nКРИТИКА РЕДАКТОРА:\n{crit}\n\n"
                           f"ЗАМЕРЕНО: {rh['hint']}\n\n"
                           "Перепиши текст, исправив все указанные проблемы. "
                           "Сохрани сюжет и персонажей.",
                           max_tokens=PROSE_MAX_TOKENS)
            s_after = score_text(edited, genre, judge)
            rh2 = analyze_sentence_rhythm(edited)
        except Exception as e:
            print(f"  {i+1:>2} ОШИБКА: {str(e)[:60]}", flush=True)
            continue
        d = s_after["total"] - s_before["total"]
        same = difflib.SequenceMatcher(None, draft, edited).ratio()
        pairs.append({"before": s_before["total"], "after": s_after["total"], "delta": d,
                      "short_before": rh["short"], "short_after": rh2["short"],
                      "words_before": len(draft.split()), "words_after": len(edited.split()),
                      "similarity": round(same, 3)})
        print(f"  {i+1:>2} {s_before['total']:5.0f} {s_after['total']:6.0f} {d:+6.0f}"
              f"  {rh['short']:5}% →{rh2['short']:4}%  {len(draft.split()):6}→{len(edited.split()):6}"
              f"  {same:8.0%}", flush=True)

    if not pairs:
        print("\n  ни одной пары не собрано"); return 1
    deltas = [p["delta"] for p in pairs]
    mean_d = statistics.mean(deltas)
    print(f"\n  средний прирост от редактуры: {mean_d:+.1f} балла")
    print(f"  пар с приростом: {sum(1 for d in deltas if d > 0)} из {len(deltas)}")
    if len(deltas) > 1:
        sd = statistics.stdev(deltas)
        print(f"  разброс прироста: {sd:.1f}; различимо примерно от "
              f"{2*sd/len(deltas)**0.5:.1f} балла при {len(deltas)} парах")
    print(f"  доля коротких: {statistics.mean(p['short_before'] for p in pairs):.0f}% → "
          f"{statistics.mean(p['short_after'] for p in pairs):.0f}%")
    print(f"  объём: {statistics.mean(p['words_after']/p['words_before'] for p in pairs):.0%} от исходного")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "date": date.today().isoformat(), "git": _git_rev(), "kind": "edit_gain",
            "generator": gen_model, "editor": editor, "judge": judge, "mode": mode,
            "note": "парное сравнение: один и тот же текст до и после редактуры",
            "pairs": pairs, "mean_delta": round(mean_d, 2),
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n  записано: {out}")
    return 0


def run(models: list[str], mode: str, judge: str, runs: int, out: Path | None) -> int:
    prompt, genre = _bootstrap(mode)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]
    print(f"  режим {mode}, промпт {len(prompt)} символов, хэш {prompt_hash}")
    print(f"  судья {judge}")
    print(f"  моделей {len(models)}, прогонов на модель {runs}\n")

    results: dict[str, dict] = {}
    for model in models:
        name = model.split("::", 1)[1]
        got = []
        for i in range(runs):
            try:
                got.append(_measure(model, prompt, genre, judge))
                print(f"  {name:42} #{i+1} итог {got[-1]['total']:.0f}  "
                      f"{got[-1]['words']} слов  {got[-1]['seconds']} c", flush=True)
            except Exception as e:
                print(f"  {name:42} #{i+1} ОШИБКА: {str(e)[:60]}", flush=True)
        if not got:
            results[name] = {"error": "все прогоны не удались"}
            continue
        totals = [g["total"] for g in got]
        results[name] = {
            "runs": got,
            "total_mean": round(statistics.mean(totals), 1),
            "total_spread": round(max(totals) - min(totals), 1),
        }

    payload = {
        "date": date.today().isoformat(),
        "git": _git_rev(),
        "mode": mode,
        "judge": judge,
        "runs_per_model": runs,
        "prompt_hash": prompt_hash,
        "prompt_chars": len(prompt),
        "threshold": "total >= 40 и каждый критерий >= 7",
        "models": results,
    }
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n  записано: {out}")

    measured = [v for v in results.values() if "total_mean" in v]
    if measured:
        means = [v["total_mean"] for v in measured]
        spreads = [v["total_spread"] for v in measured]
        print(f"\n  средний итог: {statistics.mean(means):.1f} из 50 (порог 40)")
        print(f"  взяли порог:  {sum(1 for m in means if m >= 40)} из {len(means)}")
        if runs > 1:
            worst = max(spreads)
            print(f"  разброс между прогонами одной модели: до {worst:.0f} баллов")
            print(f"  {_resolution_note(worst, runs)}")
        else:
            print("  ⚠ один прогон на модель — разброс неизвестен. Замер 2026-09-13")
            print("    показал до 6 баллов между прогонами ОДНОЙ модели на одном")
            print("    промпте. Разницу меньше этого читать как результат нельзя.")
    return 0


def _resolution_note(spread: float, runs: int) -> str:
    """
    Что различимо при таком разбросе и таком числе прогонов.

    Оценка грубая и намеренно осторожная: половина наблюдённого размаха
    принимается за стандартное отклонение, различимым считается сдвиг
    примерно в два стандартных отклонения среднего. Точности тут нет —
    задача одна: не дать прочитать шум как улучшение.
    """
    import math
    sd = max(spread, 1.0) / 2
    detectable = 2 * sd / math.sqrt(max(runs, 1))
    return (f"различим сдвиг примерно от {detectable:.0f} баллов; "
            f"меньше — не отличить от разброса")


def compare(a: Path, b: Path) -> int:
    da, db = (json.loads(p.read_text(encoding="utf-8")) for p in (a, b))

    print(f"  A: {a.name}  {da.get('date')}  git {da.get('git')}  промпт {da.get('prompt_hash')}")
    print(f"  B: {b.name}  {db.get('date')}  git {db.get('git')}  промпт {db.get('prompt_hash')}\n")

    if not da.get("prompt_hash") or not db.get("prompt_hash"):
        print("  ⚠ У ОДНОГО ИЗ ФАЙЛОВ НЕТ ХЭША ПРОМПТА — он сделан не bench.py,")
        print("    и на каком промпте мерился, неизвестно. Сравнение справочное.")
        for f, d in ((a, da), (b, db)):
            if d.get("note"):
                print(f"    {f.name}: {d['note'][:150]}")
        print()
    elif da["prompt_hash"] != db["prompt_hash"]:
        print("  ⚠ ПРОМПТЫ РАЗНЫЕ. Разница в баллах может быть следствием правки")
        print("    промпта, а не улучшения текста. Это не ошибка — но читать")
        print("    таблицу ниже как «стало лучше» уже нельзя.\n")
    if da.get("judge") != db.get("judge"):
        print("  ⚠ СУДЬИ РАЗНЫЕ — шкалы несравнимы, таблица ниже бессмысленна.\n")
    if da.get("mode") != db.get("mode"):
        print(f"  ⚠ РЕЖИМЫ РАЗНЫЕ: {da.get('mode')} против {db.get('mode')}.\n")

    ma, mb = da.get("models", {}), db.get("models", {})
    common = sorted(set(ma) & set(mb))
    if not common:
        print("  общих моделей нет — сравнивать нечего")
        return 1

    def mean_of(entry):
        if "total_mean" in entry:
            return entry["total_mean"]
        return entry.get("итог") or entry.get("total")     # формат первого замера

    print(f"  {'модель':42} {'A':>6} {'B':>6} {'Δ':>6}")
    print("  " + "─" * 62)
    deltas = []
    for name in common:
        va, vb = mean_of(ma[name]), mean_of(mb[name])
        if va is None or vb is None:
            print(f"  {name:42} {'—':>6} {'—':>6}")
            continue
        d = vb - va
        deltas.append(d)
        print(f"  {name:42} {va:6.1f} {vb:6.1f} {d:+6.1f}")
    if deltas:
        print(f"\n  средний сдвиг: {statistics.mean(deltas):+.1f} балла")
        print(f"  моделей лучше: {sum(1 for d in deltas if d > 0)} из {len(deltas)}")
        runs_a = da.get("runs_per_model", 1)
        runs_b = db.get("runs_per_model", 1)
        spreads = [v["total_spread"] for d in (da, db)
                   for v in d.get("models", {}).values() if "total_spread" in v]
        worst = max(spreads) if spreads else 6.0     # 6 — наблюдение 2026-09-13
        print("  " + _resolution_note(worst, min(runs_a, runs_b)))
        import math
        limit = 2 * (max(worst, 1.0) / 2) / math.sqrt(max(min(runs_a, runs_b), 1))
        if max(abs(d) for d in deltas) <= limit:
            print(f"  весь сдвиг в пределах разброса — это шум, а не эффект")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Повторяемый замер качества текста")
    ap.add_argument("--models", help="список через запятую (без префикса провайдера — "
                                     "подставится nano_gpt::)")
    ap.add_argument("--mode", default="master", choices=("quick", "quality", "master"))
    ap.add_argument("--judge", default=DEFAULT_JUDGE)
    ap.add_argument("--runs", type=int, default=1, help="прогонов на модель")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("A", "B"))
    ap.add_argument("--list", action="store_true", help="показать состав по умолчанию")
    ap.add_argument("--editors", action="store_true",
                    help="мерить готовность переписывать, а не писать")
    ap.add_argument("--edit-gain", metavar="РЕДАКТОР",
                    help="парно мерить, что даёт редактура: текст до и после")
    ap.add_argument("--generator", default="nano_gpt::z-ai/glm-5.3",
                    help="генератор для --edit-gain")
    args = ap.parse_args()

    if args.compare:
        return compare(*args.compare)
    if args.list:
        print("  модели по умолчанию:")
        for m in DEFAULT_MODELS:
            print("   ", m)
        print(f"\n  судья: {DEFAULT_JUDGE}")
        print(f"  посев: «{SEED['name']}», {SEED['genre']}, глава {SEED['chapter_num']}")
        return 0

    models = DEFAULT_MODELS
    if args.models:
        models = [m if "::" in m else "nano_gpt::" + m
                  for m in (x.strip() for x in args.models.split(",")) if m]
    if args.edit_gain:
        ed = args.edit_gain if "::" in args.edit_gain else "nano_gpt::" + args.edit_gain
        return run_edit_gain(args.generator, ed, args.judge, args.runs, args.mode, args.out)
    if args.editors:
        return run_editors(models, args.out)
    return run(models, args.mode, args.judge, args.runs, args.out)


if __name__ == "__main__":
    sys.exit(main())
