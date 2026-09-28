#!/usr/bin/env python3
"""
ab_compare.py — слепое попарное сравнение глав двух ревизий движка.

Зачем
─────
tools/bench.py меряет модели на базовом промпте (build_prompt) — без блока
движка из UNIFIED_ENGINE_MASTER. Правки базы знаний он не видит. Этот
инструмент генерирует главы ПОЛНЫМ путём приложения (run_generation →
_build_context, блок движка включён) на двух ревизиях и отдаёт пары судье
вслепую.

Почему попарно. Абсолютная оценка критика шумит на ~11 баллов из 50
(bench.py) — больше искомого эффекта. Выбор «какая из двух лучше» на одной
задаче устойчивее. Каждая пара судится дважды, в прямом и обратном
порядке: так гасится предпочтение первой позиции.

Обе главы пары пишет одна модель, поэтому пристрастие судьи к своему
слогу действует на обе стороны одинаково.

Запуск
──────
    # ревизия «до» — в отдельной рабочей копии
    git worktree add /tmp/ab_old ece0528
    python tools/ab_compare.py generate --app /tmp/ab_old/fiction_engine --out bench/ab-old.json
    python tools/ab_compare.py generate --app fiction_engine --out bench/ab-new.json
    python tools/ab_compare.py rate bench/ab-old.json bench/ab-new.json --out bench/ab-rate.json

Попарный режим (judge) оставлен, но на длинных главах он не работает: замер
2026-09-27 — судьи в 30 голосах из 31 выбрали первую позицию. Основной
режим — rate: каждая глава отдельно по шкале, с повторами для оценки шума.

Рабочая БД только читается (ключи API); главы пишутся во временную.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Генератор — лучший по замеру 2026-09-13 (bench/2026-09-13.json). Судьи —
# другие семейства моделей: модель узнаёт свой слог (tests/test_blind_judging.py).
DEFAULT_GEN = "nano_gpt::z-ai/glm-5.3"
DEFAULT_JUDGES = ["nano_gpt::moonshotai/kimi-k2.5",
                  "nano_gpt::deepseek/deepseek-v4-pro-0813"]

# GLM 5.3 примерно в половине вызовов отдаёт пустое содержимое (bench.py,
# EMPTY_RETRIES). Без повтора такая глава выпала бы из пары.
EMPTY_RETRIES = 3
MODE = "quality"
CHAPTER = 3

# Посев: жанр, предыдущая глава, состояние, задача. Меняя его, вы делаете
# старые замеры несравнимыми.
SEEDS = {
    "thriller_medical": {
        "genre": "медицинский триллер",
        "prev": ("В областную больницу за двое суток поступили четверо детей из одного "
                 "посёлка: температура, сыпь на ладонях, спутанное сознание. Двое в "
                 "реанимации. Инфекционист Лев Аронов не нашёл ни одного известного "
                 "возбудителя. Главврач Сомова запретила сообщать в Роспотребнадзор до "
                 "результатов анализов: больница в шаге от закрытия после прошлой проверки."),
        "state": ("## ПЕРСОНАЖИ\n\n### Лев Аронов\nРоль: инфекционист, протагонист\n"
                  "Состояние: не спал сутки, подозревает отравление, а не инфекцию\n"
                  "Знает: все четверо дети пили воду из одной колонки у старого завода\n\n"
                  "### Нина Сомова\nРоль: главврач\nСостояние: боится огласки, давит на Аронова\n\n"
                  "### Катя Вешнякова\nРоль: мать одного из детей\nСостояние: требует правды\n\n"
                  "## ЛОКАЦИИ\nОбластная больница, реанимация, посёлок у закрытого химзавода\n"),
        "task": "У пятого ребёнка начинаются судороги; Аронов должен выбрать между протоколом "
                "Сомовой и рискованной проверкой своей версии.",
    },
    "thriller_adventure": {
        "genre": "приключения",
        "prev": ("Экспедиция геолога Ильи Ветрова ищет пропавшую в 1936 году партию "
                 "Кравцова на плато Путорана. У них карта из дневника Кравцова, "
                 "проводник-эвенк Семён и неделя до первых снегов. Вчера вертолёт "
                 "высадил их не у той реки: пилот спутал притоки, связи нет."),
        "state": ("## ПЕРСОНАЖИ\n\n### Илья Ветров\nРоль: геолог, руководитель экспедиции\n"
                  "Состояние: упрям, уверен в карте больше, чем в людях\n"
                  "Знает: в дневнике Кравцова последняя запись — про «ворота» в каньоне\n\n"
                  "### Семён\nРоль: проводник\nСостояние: немногословен, не верит карте\n\n"
                  "### Даша Ветрова\nРоль: сестра Ильи, фотограф\nСостояние: пошла, чтобы присматривать за братом\n\n"
                  "## ЛОКАЦИИ\nПлато Путорана, безымянный приток, каньон с водопадами\n"),
        "task": "Чтобы вернуться к нужной реке, экспедиция идёт через каньон, и на переправе "
                "они находят след партии Кравцова.",
    },
    "realism_magical": {
        "genre": "магический реализм",
        "prev": ("В доме Лапиных на Садовой с тех пор, как умер дед, часы в прихожей "
                 "идут назад — на час в сутки. Бабушка Вера заводит их каждое утро и "
                 "говорит, что так дед досчитывает то, что не успел. Внучка Соня "
                 "приехала на лето и узнала, что дом продают."),
        "state": ("## ПЕРСОНАЖИ\n\n### Соня\nРоль: внучка, 17 лет, протагонист\n"
                  "Состояние: злится на мать за продажу дома\n"
                  "Знает: часы остановятся, когда дойдут до дня смерти деда\n\n"
                  "### Вера Андреевна\nРоль: бабушка\nСостояние: спокойна, ничего не объясняет\n\n"
                  "### Ольга\nРоль: мать Сони\nСостояние: торопится с продажей, устала\n\n"
                  "## ЛОКАЦИИ\nДом на Садовой, сад с яблонями, рынок в райцентре\n"),
        "task": "Приезжают покупатели смотреть дом; часы в этот день начинают идти вперёд.",
    },
    "scifi_alt_history": {
        "genre": "альтернативная история",
        "prev": ("1987 год. После того как в 1962-м Карибский кризис закончился обменом "
                 "ядерными ударами по Кубе и Турции, мир живёт в режиме Договора о "
                 "ядерном разоружении под надзором Совета наблюдателей. Инспектор Совета "
                 "Андрей Рощин прибывает в закрытый Арзамас-16 с плановой проверкой."),
        "state": ("## ПЕРСОНАЖИ\n\n### Андрей Рощин\nРоль: инспектор Совета наблюдателей, протагонист\n"
                  "Состояние: исполнителен, верит в Договор\n"
                  "Знает: в отчётах города расход энергии на треть выше заявленного\n\n"
                  "### Полковник Дьяков\nРоль: комендант города\nСостояние: гостеприимен, осторожен\n\n"
                  "### Лиза Корнева\nРоль: инженер-энергетик\nСостояние: хочет что-то сказать и боится\n\n"
                  "## ЛОКАЦИИ\nЗакрытый город, энергоблок, гостиница Совета\n"),
        "task": "Рощин проверяет энергоблок и замечает, что показания счётчиков подделаны; "
                "Лиза ищет способ поговорить с ним без свидетелей.",
    },
    "thriller_legal": {
        "genre": "юридический триллер",
        "prev": ("Адвокат Марина Кострова взяла дело Дениса Шевцова, обвиняемого в поджоге "
                 "склада, где погиб сторож. Главная улика обвинения — запись с камеры "
                 "соседнего магазина: человек в куртке Шевцова у ворот склада в 23:40. "
                 "Прокурор Громов предложил сделку: признание и восемь лет. Шевцов "
                 "отказался и сказал Марине, что в тот вечер куртку у него украли."),
        "state": ("## ПЕРСОНАЖИ\n\n### Марина Кострова\nРоль: адвокат, протагонист\n"
                  "Состояние: не уверена в невиновности клиента, но уверена, что улика слабее, чем кажется\n"
                  "Знает: запись с камеры магазина изъята без протокола осмотра\n\n"
                  "### Денис Шевцов\nРоль: обвиняемый\nСостояние: зол, упрям, что-то недоговаривает\n\n"
                  "### Павел Громов\nРоль: прокурор\nСостояние: опытен, спокоен, торопит дело\n\n"
                  "## ЛОКАЦИИ\nРайонный суд, следственный изолятор, магазин напротив склада\n"),
        "task": "Предварительное слушание: Марина пытается исключить запись с камеры из доказательств, "
                "а Громов отвечает ходом, которого она не ждала.",
    },
    "detective_classic": {
        "genre": "классический детектив",
        "prev": ("Инспектор Вера Смолина осмотрела кабинет покойного нотариуса Гордеева. "
                 "Сейф был открыт, но деньги на месте. Пропала только папка с завещанием "
                 "вдовы Ларионовой. Секретарь Гордеева, Ирина, клялась, что вечером "
                 "кабинет был заперт. Ключ был у троих: у самого нотариуса, у Ирины и "
                 "у его компаньона Лаптева, который в ту ночь, по его словам, был в театре."),
        "state": ("## ПЕРСОНАЖИ\n\n### Вера Смолина\nРоль: инспектор, протагонист\n"
                  "Состояние: упрямо ищет мотив, не верит простым версиям\n"
                  "Знает: пропало только завещание Ларионовой\n\n"
                  "### Ирина Воробьёва\nРоль: секретарь убитого\nСостояние: напугана, что-то скрывает\n\n"
                  "### Аркадий Лаптев\nРоль: компаньон убитого\nСостояние: подчёркнуто спокоен\n\n"
                  "## ЛОКАЦИИ\nНотариальная контора на Литейном, театр, квартира вдовы Ларионовой\n"),
        "task": "Вера проверяет алиби Лаптева в театре и находит деталь, которая ему противоречит.",
    },
    "fantasy_dark": {
        "genre": "тёмное фэнтези",
        "prev": ("Отряд Кайры вернулся из Серых топей вдвоём из семи. Вторым был Брам, "
                 "мальчишка-проводник, которому в топях отрубили два пальца. Капитан "
                 "гарнизона Ольст выслушал доклад и приказал запереть обоих: в крепости "
                 "решили, что топь не отпускает людей просто так."),
        "state": ("## ПЕРСОНАЖИ\n\n### Кайра\nРоль: наёмница, протагонист\n"
                  "Состояние: изранена, злится, не доверяет гарнизону\n"
                  "Знает: в топях отряд встретил что-то, что говорило голосом погибших\n\n"
                  "### Брам\nРоль: проводник, 15 лет\nСостояние: молчит с самого возвращения\n\n"
                  "### Капитан Ольст\nРоль: комендант крепости\nСостояние: боится заразы, решает жёстко\n\n"
                  "## ЛОКАЦИИ\nКрепость Хальм у края Серых топей, подземные камеры, двор для казней\n"),
        "task": "Ночью в камере Брам впервые заговаривает — чужим голосом. Кайра должна решить, что с ним делать.",
    },
    "thriller_psychological": {
        "genre": "психологический триллер",
        "prev": ("Анна третью неделю находит в своей квартире вещи не на своих местах. "
                 "Муж, Олег, мягко говорит, что она устала и всё забывает. Психотерапевт "
                 "советует вести дневник. Вчера Анна нашла в дневнике запись, сделанную её "
                 "почерком, которой она не помнит: «Не верь ему. Проверь гараж»."),
        "state": ("## ПЕРСОНАЖИ\n\n### Анна\nРоль: протагонист\n"
                  "Состояние: сомневается в собственной памяти\n"
                  "Знает: в дневнике запись, которую она не помнит\n\n"
                  "### Олег\nРоль: муж\nСостояние: заботлив, терпелив, всегда рядом\n\n"
                  "### Доктор Мельник\nРоль: психотерапевт Анны\n\n"
                  "## ЛОКАЦИИ\nКвартира, гараж во дворе, кабинет терапевта\n"),
        "task": "Анна идёт в гараж, пока Олег на работе, и находит то, что меняет её версию происходящего.",
    },
    "realism_psychological": {
        "genre": "психологическая проза",
        "prev": ("Михаилу пятьдесят два, и его сократили с завода, где он проработал "
                 "тридцать лет. Жене он пока не сказал: каждое утро уходит «на смену» и "
                 "сидит до вечера в библиотеке. Сын-студент вчера попросил денег на "
                 "поездку с друзьями, и Михаил, не раздумывая, пообещал."),
        "state": ("## ПЕРСОНАЖИ\n\n### Михаил\nРоль: протагонист\n"
                  "Состояние: скрывает увольнение, стыдится, держится за привычный распорядок\n\n"
                  "### Людмила\nРоль: жена\nСостояние: чувствует, что что-то не так, молчит\n\n"
                  "### Денис\nРоль: сын, 20 лет\n\n"
                  "## ЛОКАЦИИ\nКвартира в панельном доме, районная библиотека, проходная завода\n"),
        "task": "Людмила случайно встречает Михаила днём у библиотеки. Разговор дома вечером.",
    },
}


# ─── Генерация ───────────────────────────────────────────────────────────────

def _read_real_keys(app: Path) -> list[tuple[str, str]]:
    import sqlite3
    sys.path.insert(0, str(app))
    import engine.db_core as dbc
    real = Path(dbc.DB_PATH)
    if not real.exists():
        return []
    conn = sqlite3.connect(f"file:{real}?mode=ro", uri=True)
    try:
        return [(r[0], r[1]) for r in conn.execute("SELECT provider, api_key FROM api_keys")
                if (r[1] or "").strip()]
    finally:
        conn.close()


def _git_rev(path: Path) -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=path,
                          capture_output=True, text=True).stdout.strip()


def generate(app: Path, out: Path, model: str, runs: int, genres: list[str],
             as_genre: str | None = None, secondary: str | None = None) -> int:
    app = app.resolve()
    keys = _read_real_keys(app)
    import engine.db_core as dbc
    dbc.DB_PATH = Path(tempfile.mkdtemp(prefix="ab_")) / "ab.db"
    dbc.init_db()
    with dbc.get_conn() as conn:
        for provider, key in keys:
            conn.execute("INSERT OR REPLACE INTO api_keys (provider, api_key) VALUES (?,?)",
                         (provider, key))
    import engine.db as db
    import engine.pipeline as pipeline
    from engine.pipeline_config import PROSE_MAX_TOKENS

    # Перехват: запоминаем, что ушло генератору, — размер контекста
    sent: dict = {}
    real_call = pipeline._call

    def recording_call(model_value, system, user, max_tokens=6000, **kw):
        if max_tokens == PROSE_MAX_TOKENS:
            sent["system"], sent["user"] = system, user
        return real_call(model_value, system, user, max_tokens=max_tokens, **kw)

    pipeline._call = recording_call

    result = {"date": date.today().isoformat(), "git": _git_rev(app), "app": str(app),
              "model": model, "mode": MODE, "as_genre": as_genre, "secondary": secondary,
              "chapters": []}
    for genre_key in genres:
        seed = SEEDS[genre_key]
        for run in range(runs):
            # as_genre: тот же сюжет под другим ключом — например, как проект
            # определялся бы до появления своего ключа у жанра; «none» — без
            # жанра вовсе (универсальный промпт), тогда и текст жанра пустой
            no_genre = as_genre == "none"
            pid = db.create_project(f"{genre_key}-{run}", "" if no_genre else seed["genre"])
            if hasattr(db, "set_project_genre_key") and not no_genre:
                db.set_project_genre_key(pid, as_genre or genre_key)
            if secondary:
                db.set_project_genre_secondary(pid, secondary)
            db.set_active_project(pid)
            db.save_chapter(pid, CHAPTER - 1, seed["prev"], "Предыдущая глава")
            db.update_state(pid, seed["state"], "", "")
            t0 = time.time()
            text, error, empty_retries = "", None, 0
            for attempt in range(EMPTY_RETRIES):
                try:
                    res = pipeline.run_generation(db.get_project(pid), CHAPTER, MODE, model, seed["task"])
                    text, error = res["text"], None
                    break
                except Exception as e:
                    error = str(e)[:300]
                    if "пустой ответ" not in error:
                        break
                    empty_retries += 1
            item = {"genre": genre_key, "run": run, "text": text, "error": error,
                    "words": len(text.split()), "seconds": round(time.time() - t0),
                    "context_chars": len(sent.get("user", "")),
                    "empty_retries": empty_retries,
                    "system_chars": len(sent.get("system", ""))}
            result["chapters"].append(item)
            print(f"  {genre_key:24} #{run}  {item['words']:5} слов  "
                  f"контекст {item['context_chars']:6}  {item['seconds']:4} с"
                  + (f"  ОШИБКА {error[:60]}" if error else ""), flush=True)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


# ─── Судья ───────────────────────────────────────────────────────────────────

JUDGE_SYSTEM = ("Ты опытный литературный редактор. Сравниваешь две главы на одну и ту же "
                "задачу. Отвечаешь только JSON.")

JUDGE_PROMPT = """Жанр: {genre}
Задача главы: {task}

Две версии главы написаны на одну задачу. Сравни их как редактор, который выбирает, какую
отдать в печать. Оцени: живость и точность прозы, голос, отсутствие штампов и
ИИ-клише, соответствие жанру и его ожиданиям, работу сцены (напряжение, подтекст,
движение), диалоги, концовку. НЕ предпочитай текст за длину.

=== ВЕРСИЯ A ===
{a}

=== ВЕРСИЯ B ===
{b}

Ответь JSON без пояснений вокруг:
{{"winner": "A" | "B" | "tie", "margin": "слабо" | "заметно" | "сильно",
  "reason": "2–3 предложения: чем победитель лучше"}}"""


def _parse_verdict(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {"winner": "?", "margin": "", "reason": raw[:200]}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        w = re.search(r'"winner"\s*:\s*"(A|B|tie)"', raw)
        return {"winner": w.group(1) if w else "?", "margin": "", "reason": raw[:200]}


def judge(old_path: Path, new_path: Path, out: Path, judges: list[str]) -> int:
    sys.path.insert(0, str(ROOT / "fiction_engine"))
    from engine.pipeline import _call
    old = json.loads(old_path.read_text(encoding="utf-8"))
    new = json.loads(new_path.read_text(encoding="utf-8"))
    pairs = [(o, n) for o in old["chapters"] for n in new["chapters"]
             if o["genre"] == n["genre"] and o["run"] == n["run"]
             and o["text"] and n["text"]]
    rng = random.Random(20260927)
    report = {"date": date.today().isoformat(), "old": old["git"], "new": new["git"],
              "model": new["model"], "judges": judges, "pairs": []}
    score = {"new": 0, "old": 0, "tie": 0, "?": 0}
    for o, n in pairs:
        seed = SEEDS[o["genre"]]
        entry = {"genre": o["genre"], "run": o["run"],
                 "words_old": o["words"], "words_new": n["words"], "votes": []}
        for jm in judges:
            # Два порядка: новая версия то A, то B
            orders = [("new", "old"), ("old", "new")]
            rng.shuffle(orders)
            for first, second in orders:
                texts = {"new": n["text"], "old": o["text"]}
                prompt = JUDGE_PROMPT.format(genre=seed["genre"], task=seed["task"],
                                             a=texts[first], b=texts[second])
                try:
                    v = _parse_verdict(_call(jm, JUDGE_SYSTEM, prompt, max_tokens=600))
                except Exception as e:
                    v = {"winner": "?", "margin": "", "reason": f"ошибка: {str(e)[:120]}"}
                who = {"A": first, "B": second, "tie": "tie"}.get(v.get("winner"), "?")
                score[who] += 1
                entry["votes"].append({"judge": jm.split("::")[-1], "order": f"{first}/{second}",
                                       "winner": who, "margin": v.get("margin", ""),
                                       "reason": v.get("reason", "")})
                print(f"  {o['genre']:24} #{o['run']}  {jm.split('::')[-1]:28} "
                      f"порядок {first}/{second:4} → {who}", flush=True)
        report["pairs"].append(entry)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    # Устойчивость к порядку: судья в паре выбрал одну и ту же главу при
    # обоих порядках. Замер 2026-09-27 на GLM-главах: 0 из 16 — судьи
    # выбирали позицию A, а не текст. Без этой строки счёт 15:16 выглядел
    # бы как «разницы нет», хотя замер просто ничего не измерил.
    stable = total_jp = 0
    for entry in report["pairs"]:
        per_judge: dict[str, list[str]] = {}
        for v in entry["votes"]:
            per_judge.setdefault(v["judge"], []).append(v["winner"])
        for winners in per_judge.values():
            total_jp += 1
            stable += len(set(winners)) == 1 and winners[0] in ("new", "old")
    first_pos = sum(1 for e in report["pairs"] for v in e["votes"]
                    if v["winner"] == v["order"].split("/")[0])
    report["score"] = score
    report["order_stable"] = f"{stable}/{total_jp}"
    report["first_position_wins"] = first_pos
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(score.values())
    print(f"\n  новая {score['new']}  старая {score['old']}  ничья {score['tie']}  "
          f"не разобрано {score['?']}  из {total} голосов")
    print(f"  устойчивость к порядку: {stable}/{total_jp}; "
          f"выиграла первая позиция: {first_pos} из {total}")
    if total_jp and stable / total_jp < 0.5:
        print("  ВНИМАНИЕ: судьи выбирают позицию, а не текст — счёт ничего не значит")
    return 0


# ─── Оценка по шкале ─────────────────────────────────────────────────────────
#
# Попарное судейство 2026-09-27 провалилось: две главы по ~2500 слов в одном
# запросе, и оба судьи в 30 голосах из 31 выбрали первую позицию. Здесь судья
# видит одну главу, не знает ревизию, сначала выписывает находки, потом
# ставит баллы. Каждая глава оценивается REPEATS раз каждым судьёй: разброс
# повторов — шум, и разница версий имеет смысл, только если она больше него.

RUBRIC = {
    "prose": "живость и точность прозы: конкретные детали, сильные глаголы, нет воды",
    "voice": "голос: узнаваемая манера рассказчика и персонажей, различимые реплики",
    "rhythm": "ритм: чередование коротких и длинных фраз, темп под сцену",
    "scene": "работа сцены: напряжение, подтекст, движение, концовка тянет дальше",
    "genre": "жанр: выполнены ожидания жанра и задача главы",
    "clean": "чистота: нет штампов, ИИ-клише, пересказа эмоций словами «почувствовал»",
}
REPEATS = 2

RATE_SYSTEM = ("Ты строгий литературный редактор. Оцениваешь одну главу по шкале. "
               "Отвечаешь только JSON.")

RATE_PROMPT = """Жанр: {genre}
Задача главы: {task}

Оцени главу по шкале 1–10 по каждому критерию:
{rubric}

Шкала: 5 — средний публикуемый текст, 7 — хорошо, 9 — сильная книжная проза.
Длина главы на оценку не влияет.

Сначала выпиши находки — 3 сильных места и 3 слабых, короткими цитатами
из текста. Потом ставь баллы, опираясь на них.

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг:
{{"strong": ["…", "…", "…"], "weak": ["…", "…", "…"],
  "scores": {{{keys}}}}}"""


def _parse_scores(raw: str) -> dict[str, float] | None:
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            got = json.loads(m.group()).get("scores", {})
            vals = {k: float(got[k]) for k in RUBRIC if k in got}
            if len(vals) == len(RUBRIC):
                return vals
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError):
            pass
    vals = {}
    for k in RUBRIC:
        f = re.search(rf'"{k}"\s*:\s*(\d+(?:\.\d+)?)', raw)
        if f:
            vals[k] = float(f.group(1))
    return vals if len(vals) == len(RUBRIC) else None


def rate(old_path: Path, new_path: Path, out: Path, judges: list[str], workers: int) -> int:
    from concurrent.futures import ThreadPoolExecutor
    from statistics import mean
    sys.path.insert(0, str(ROOT / "fiction_engine"))
    from engine.pipeline import _call
    sides = {"old": json.loads(old_path.read_text(encoding="utf-8")),
             "new": json.loads(new_path.read_text(encoding="utf-8"))}
    rubric = "\n".join(f"- {k}: {v}" for k, v in RUBRIC.items())
    keys = ", ".join(f'"{k}": N' for k in RUBRIC)
    jobs = [(side, ch, jm, rep) for side, data in sides.items() for ch in data["chapters"]
            if ch["text"] for jm in judges for rep in range(REPEATS)]
    random.Random(20260927).shuffle(jobs)   # вперемешку: ревизии не идут блоками

    def run(job):
        side, ch, jm, rep = job
        seed = SEEDS[ch["genre"]]
        prompt = RATE_PROMPT.format(genre=seed["genre"], task=seed["task"], rubric=rubric,
                                    keys=keys, text=ch["text"])
        scores, raw = None, ""
        for _ in range(2):
            try:
                raw = _call(jm, RATE_SYSTEM, prompt, max_tokens=1500)
            except Exception as e:
                raw = f"ошибка: {str(e)[:120]}"
            scores = _parse_scores(raw)
            if scores:
                break
        total = round(mean(scores.values()), 2) if scores else None
        print(f"  {side:3} {ch['genre']:24} #{ch['run']}  {jm.split('::')[-1]:28} "
              f"повтор {rep} → {total}", flush=True)
        return {"side": side, "genre": ch["genre"], "run": ch["run"],
                "judge": jm.split("::")[-1], "repeat": rep, "scores": scores,
                "total": total, "raw": None if scores else raw[:300]}

    with ThreadPoolExecutor(workers) as pool:
        ratings = list(pool.map(run, jobs))
    ok = [r for r in ratings if r["scores"]]

    def avg(rows, key="total"):
        vals = [r["scores"][key] if key in RUBRIC else r[key] for r in rows]
        return round(mean(vals), 2) if vals else None

    summary = {side: {"total": avg([r for r in ok if r["side"] == side]),
                      **{k: avg([r for r in ok if r["side"] == side], k) for k in RUBRIC}}
               for side in sides}
    # Шум: насколько расходятся повторы одного судьи на одной главе
    groups: dict[tuple, list[float]] = {}
    for r in ok:
        groups.setdefault((r["side"], r["genre"], r["run"], r["judge"]), []).append(r["total"])
    spreads = [max(v) - min(v) for v in groups.values() if len(v) > 1]
    noise = round(mean(spreads), 2) if spreads else None
    # Разница по парам (жанр, прогон), усреднённая по судьям и повторам
    diffs = []
    for g in SEEDS:
        for run_ in {r["run"] for r in ok if r["genre"] == g}:
            o = [r["total"] for r in ok if r["genre"] == g and r["run"] == run_ and r["side"] == "old"]
            n = [r["total"] for r in ok if r["genre"] == g and r["run"] == run_ and r["side"] == "new"]
            if o and n:
                diffs.append({"genre": g, "run": run_, "diff": round(mean(n) - mean(o), 2)})
    by_judge = {j.split("::")[-1]: {side: avg([r for r in ok if r["side"] == side
                                               and r["judge"] == j.split("::")[-1]])
                                    for side in sides} for j in judges}
    report = {"date": date.today().isoformat(), "old": sides["old"]["git"],
              "new": sides["new"]["git"], "model": sides["new"]["model"],
              "judges": judges, "repeats": REPEATS, "summary": summary,
              "by_judge": by_judge, "pair_diffs": diffs, "repeat_noise": noise,
              "failed": len(ratings) - len(ok), "ratings": ratings}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n  {'':8}{'итог':>6}" + "".join(f"{k:>8}" for k in RUBRIC))
    for side in ("old", "new"):
        s = summary[side]
        print(f"  {side:8}{s['total']:>6}" + "".join(f"{s[k]:>8}" for k in RUBRIC))
    for j, v in by_judge.items():
        print(f"  {j:30} старая {v['old']}  новая {v['new']}")
    wins = sum(d["diff"] > 0 for d in diffs)
    print(f"  пары: новая выше в {wins} из {len(diffs)}; "
          f"средняя разница {round(mean(d['diff'] for d in diffs), 2) if diffs else '—'}")
    print(f"  шум повторов (размах одного судьи на одной главе): {noise}; "
          f"не разобрано {report['failed']} из {len(ratings)}")
    return 0


# ─── Слабые места ────────────────────────────────────────────────────────────
#
# Оценка по шкале говорит «чистота 6.8», но не говорит, ЧТО грязно. Здесь
# судья выписывает слабые места цитатами, с типом из закрытого списка и
# обобщённой формой приёма — чтобы их можно было сложить по многим главам
# и увидеть, какие обороты модель повторяет из главы в главу. Цитата
# проверяется по тексту: выдуманная судьёй в сводку не идёт.

FLAW_TYPES = {
    "штамп": "затёртый оборот, клише",
    "ии_оборот": "типичная ИИ-конструкция: «не X, а Y», тройки, мудрость в конце абзаца",
    "эмоция_названа": "чувство названо словами вместо показа",
    "повтор": "повтор слова, образа или конструкции",
    "вода": "лишнее, пересказ, затянутость",
    "логика": "нестыковка, ошибка факта или физики",
    "язык": "грамматика, калька, чужой язык, неверное слово",
    "диалог": "неживая речь, экспозиция в репликах",
    "ритм": "монотонность, однотипные фразы подряд",
    "другое": "",
}

FLAW_PROMPT = """Жанр: {genre}

Ты редактор. Найди в главе до 8 самых заметных слабых мест — те, что
редактор вычеркнул бы в первую очередь. Хвалить не нужно.

Для каждого:
- quote: точная цитата из текста, до 15 слов, без изменений;
- type: одно из {types};
- pattern: обобщённая форма приёма, если он повторяемый («не X, а Y»,
  «сердце пропустило удар», «X, и Y, и Z» и т. п.), иначе пусто;
- why: в чём проблема, до 12 слов.

Типы: {legend}

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг:
{{"flaws": [{{"quote": "…", "type": "…", "pattern": "…", "why": "…"}}]}}"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[«»\"„“”…]", "", s)).strip().lower()


def flaws(paths: list[Path], out: Path, judges: list[str], workers: int) -> int:
    from collections import Counter
    from concurrent.futures import ThreadPoolExecutor
    sys.path.insert(0, str(ROOT / "fiction_engine"))
    from engine.pipeline import _call
    from engine.pipeline_llm import parse_json
    chapters = [(p.name, ch) for p in paths
                for ch in json.loads(p.read_text(encoding="utf-8"))["chapters"] if ch["text"]]
    legend = "; ".join(f"{k} — {v}" for k, v in FLAW_TYPES.items() if v)
    jobs = [(src, ch, jm) for src, ch in chapters for jm in judges]

    def run(job):
        src, ch, jm = job
        prompt = FLAW_PROMPT.format(genre=SEEDS[ch["genre"]]["genre"], types=", ".join(FLAW_TYPES),
                                    legend=legend, text=ch["text"])
        found: list[dict] = []
        for _ in range(2):
            try:
                got = parse_json(_call(jm, RATE_SYSTEM, prompt, max_tokens=4000)) or {}
            except Exception as e:
                got = {"error": str(e)[:120]}
            found = got.get("flaws", []) if isinstance(got, dict) else []
            if found:
                break
        text_n = _norm(ch["text"])
        items = []
        for f in found:
            if not isinstance(f, dict) or not f.get("quote"):
                continue
            items.append({"quote": f["quote"], "type": f.get("type", "другое"),
                          "pattern": (f.get("pattern") or "").strip(), "why": f.get("why", ""),
                          # цитата, которой нет в тексте, — выдумка судьи
                          "verified": _norm(f["quote"]) in text_n})
        print(f"  {src[:22]:22} {ch['genre']:24} #{ch['run']}  {jm.split('::')[-1]:28} "
              f"→ {len(items)} ({sum(i['verified'] for i in items)} подтв.)", flush=True)
        return {"source": src, "genre": ch["genre"], "run": ch["run"],
                "judge": jm.split("::")[-1], "flaws": items}

    with ThreadPoolExecutor(workers) as pool:
        rows = list(pool.map(run, jobs))
    real = [dict(f, chapter=(r["source"], r["genre"], r["run"]), judge=r["judge"])
            for r in rows for f in r["flaws"] if f["verified"]]
    by_type = Counter(f["type"] for f in real)
    # Приём считается повторяемым, если встречается в разных главах
    pat_chapters: dict[str, set] = {}
    for f in real:
        if f["pattern"]:
            pat_chapters.setdefault(_norm(f["pattern"]), set()).add(f["chapter"])
    patterns = sorted(((p, len(c)) for p, c in pat_chapters.items()), key=lambda x: -x[1])
    total = sum(len(r["flaws"]) for r in rows)
    report = {"date": date.today().isoformat(), "sources": [p.name for p in paths],
              "judges": judges, "chapters": len(chapters),
              "flaws_total": total, "flaws_verified": len(real),
              "by_type": dict(by_type.most_common()),
              "patterns": [{"pattern": p, "chapters": n} for p, n in patterns],
              "rows": rows}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  глав {len(chapters)}, находок {total}, подтверждено цитатой {len(real)}")
    for t, n in by_type.most_common():
        print(f"  {t:16} {n}")
    print("\n  приёмы в 2+ главах:")
    for p, n in patterns:
        if n >= 2:
            print(f"  {n:3}  {p}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--app", type=Path, required=True)
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--model", default=DEFAULT_GEN)
    g.add_argument("--runs", type=int, default=2)
    # По умолчанию — четыре исходных жанра, чтобы замеры сравнивались между собой
    g.add_argument("--genres", default="detective_classic,fantasy_dark,thriller_psychological,realism_psychological")
    g.add_argument("--as-genre", default=None, help="ключ жанра проекта вместо ключа задачи")
    g.add_argument("--secondary", default=None, help="второй жанр или модификатор (comedy, young_adult)")
    j = sub.add_parser("judge")
    j.add_argument("old", type=Path)
    j.add_argument("new", type=Path)
    j.add_argument("--out", type=Path, required=True)
    j.add_argument("--judges", default=",".join(DEFAULT_JUDGES))
    r = sub.add_parser("rate", help="оценка каждой главы по шкале, без пар")
    r.add_argument("old", type=Path)
    r.add_argument("new", type=Path)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--judges", default=",".join(DEFAULT_JUDGES))
    r.add_argument("--workers", type=int, default=4)
    fl = sub.add_parser("flaws", help="слабые места глав цитатами, сводка по типам и приёмам")
    fl.add_argument("chapters", type=Path, nargs="+")
    fl.add_argument("--out", type=Path, required=True)
    fl.add_argument("--judges", default=",".join(DEFAULT_JUDGES))
    fl.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "generate":
        sys.path.insert(0, str(a.app.resolve()))
        return generate(a.app, a.out, a.model, a.runs, a.genres.split(","),
                        a.as_genre, a.secondary)
    if a.cmd == "flaws":
        return flaws(a.chapters, a.out, a.judges.split(","), a.workers)
    if a.cmd == "rate":
        return rate(a.old, a.new, a.out, a.judges.split(","), a.workers)
    return judge(a.old, a.new, a.out, a.judges.split(","))


if __name__ == "__main__":
    sys.exit(main())
