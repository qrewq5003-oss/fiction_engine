"""Независимая сверка памяти книги: библия серии и State против текста глав.

Отдельно от Fiction Engine: код приложения не импортирует, маршруты не зовёт, базу
открывает только на чтение и ничего не меняет — печатает отчёт. Правки по отчёту
делает автор в приложении.

Повод (29.10, «Третий пар»): разбор гл.9 прочёл «Тиунов писарь. Захара Ильича» как
«писарь Захар Ильич» — по плану и тексту Захар Ильич тиун. Ошибку не поймали ни
противоречия библии (две версии лежали под разными ключами), ни разбор следующих
глав (он сверяется с той же памятью); заметил её критик гл.19, приняв за правду.

Проверки без моделей, секунды:
  1. роли   — должность рядом с именем, которой у этого имени нет ни у автора
              (подготовка, записи автора), ни в тексте глав; должности — общий словарь
              и слова-должности из «Персонажей» самой книги (новый мир — свои должности)
  2. имена  — имя в памяти, которого нет ни в одной главе
  3. цитаты — «цитата» в памяти, которой нет в тексте её главы (или ни в одной)
  4. числа  — число или месяц в записи главы N, которых нет в тексте главы N

Проверяются записи, которые память вывела из текста: в библии — всё, кроме записей
автора (план, правки) и противоречий; State — целиком.

    python tools/memory_audit.py                     — список проектов с номерами
    python tools/memory_audit.py 16                  — проект по номеру
    python tools/memory_audit.py 16 --out audit.md   — отчёт ещё и в файл
    python tools/memory_audit.py 16 --db путь.db     — другая база
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

DB = Path.home() / "fiction_engine" / "projects.db"


def norm(s: str) -> str:
    """Для поиска: строчные, ё→е, только буквы и цифры через один пробел."""
    return " ".join(re.findall(r"\w+", (s or "").lower().replace("ё", "е")))


# ---------------------------------------------------------------- данные

def load(db: Path, pid: int) -> dict:
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    project = c.execute("SELECT id, name FROM projects WHERE id=?", (pid,)).fetchone()
    if not project:
        sys.exit(f"проекта {pid} нет в {db}")
    chapters = {}
    for r in c.execute("SELECT number, content FROM chapters WHERE project_id=? ORDER BY id", (pid,)):
        chapters[r["number"]] = r["content"] or ""          # переписанная глава — последняя запись
    prep = {r["section"]: r["content"] or "" for r in
            c.execute("SELECT section, content FROM prep_data WHERE project_id=?", (pid,))}
    st = c.execute("SELECT global_state, plot_matrix, memory_graph FROM state_engine WHERE project_id=?",
                   (pid,)).fetchone()
    rows = [dict(r) for r in c.execute("SELECT * FROM series_bible WHERE project_id=? ORDER BY id", (pid,))]
    return {"name": project["name"], "chapters": chapters, "prep": prep,
            "state": dict(st) if st else {}, "bible": current(rows)}


def current(rows: list[dict]) -> list[dict]:
    """Текущие факты библии: по (сущность, признак) — последняя запись по главе и порядку, без противоречий.
    Запись без главы относится к последней главе на момент записи."""
    key = lambda s: re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е")).strip(" .«»\"")
    upto, keyed = 0, []
    for r in rows:
        upto = max(upto, r["chapter_num"] or 0)
        keyed.append(((r["chapter_num"] or upto), r["id"], r))
    cur = {}
    for *_, r in sorted(keyed, key=lambda x: x[:2]):
        if r["status"] != "противоречие":
            cur[(key(r["name"]), key(r["attr"]))] = r
    return list(cur.values())


def memory_items(d: dict) -> list[dict]:
    """Что проверять: {src, chapter, text} — записи библии от разбора и строки State."""
    items = []
    for r in d["bible"]:
        if r["status"] == "автор":
            continue
        items.append({"src": f"библия #{r['id']} «{r['name']} | {r['attr']}»", "chapter": r["chapter_num"] or None,
                      "text": r["value"], "name": r["name"]})
    for field, label in (("global_state", "State · мир"), ("plot_matrix", "State · сюжет"),
                         ("memory_graph", "State · память")):
        for line in (d["state"].get(field) or "").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = re.match(r"\s*[-*]?\s*гл\.?\s*(\d+)\s*:", line)
            items.append({"src": label, "chapter": int(m.group(1)) if m else None, "text": line.strip()})
    return items


def author_texts(d: dict) -> list[str]:
    return list(d["prep"].values()) + [r["value"] + " " + r["name"] for r in d["bible"] if r["status"] == "автор"]


def excerpt(text: str, start: int, end: int, pad: int = 70) -> str:
    s, e = max(0, start - pad), min(len(text), end + pad)
    return ("…" if s else "") + text[s:e].replace("\n", " ") + ("…" if e < len(text) else "")


# ---------------------------------------------------------------- 1. роли

ROLE_STEMS = ("тиун", "писар", "мытник", "мытар", "надзират", "паромщ", "перевозч", "прачк", "травниц", "купец",
              "купц", "кожевн", "лекар", "старец", "старц", "старост", "священ", "поп", "истопн", "десятн",
              "мерщик", "приказч", "плотн", "банщ", "свекр", "голов", "дьяк", "подьяч", "сотск",
              "кузнец", "мельник", "хозяйк", "работн", "конторщ", "сирот", "знахар", "повитух", "солдат",
              "воевод", "посадн", "стражн", "сторож", "гонец", "гонц", "боярин", "бояр", "дьякон", "пономар",
              "староверк", "игумен", "монах", "чернец", "лодочник", "рыбак", "пастух", "конюх", "ключник", "тысяцк",
              "урядник", "пристав", "судь", "лавочник",
              # наше время
              "капитан", "механик", "матрос", "боцман", "штурман", "рулев", "кок", "следовател", "полицейск",
              "оперативн", "участков", "сыщик", "детектив", "гид", "экскурсовод", "повар", "официант", "бармен",
              "врач", "доктор", "медсестр", "фельдшер", "директор", "администратор", "горничн", "проводни",
              "кассир", "охранник", "журналист", "адвокат", "нотариус", "бухгалтер", "менеджер", "водител",
              "инженер", "учител", "профессор", "секретар", "хозяин", "владел", "арендатор", "продавщиц",
              "продавец", "продавц")
# Короткие основы — только с падежным окончанием: «Попрекнул», «судьба», «кокетливо» — не должности
EXACT = {"поп": r"поп(а|у|ом|е|ы|ов)?", "судь": r"судь(я|и|е|ю|ей|ям|ями)", "сирот": r"сирот(а|ы|е|у|ой|ам|ами)?",
         "бояр": r"бояр(е|ы|ам|ами|ах)?", "кок": r"кок(а|у|ом|е|и)?", "гид": r"гид(а|у|ом|е|ы|ов)?",
         "врач": r"врач(а|у|ом|е|и|ей)?"}
NOT_NAMES = {"Отец", "Хозяин", "Другие", "Роль", "Возраст", "Речь", "Характер", "Внешность", "Прошлое"}


def role_of(word: str, skip: frozenset = frozenset(), stems: tuple = ROLE_STEMS) -> str | None:
    """Основа должности у слова. skip — основы, которые в этой книге фамилии («Мельник»)."""
    w = word.lower().replace("ё", "е")
    return next((s for s in stems if s not in skip and w.startswith(s)
                 and (s not in EXACT or re.fullmatch(EXACT[s], w))), None)


# Должность по виду слова: «навигатор», «архонт», «смотритель», «ключница» — для мира новой книги
AGENT = re.compile(r"[а-яё]{3,}(ник|щик|чик|тель|арь|ист|ер|ор|ан|ец|ун|ар|нт|иц[аы]|ниц|иня|ша|ачк|ичк)$")
ADJ = re.compile(r"(ий|ый|ой|ая|яя|ое|ее|ые|ие|ого|его|ому|ему|ых|их|ым|им|ую|юю)$")


def book_roles(prep: dict) -> tuple:
    """Должности из «Персонажей» подготовки, которых нет в общем словаре: «Роль: …» и «- Имя — …»."""
    chars = prep.get("characters", "")
    texts = re.findall(r"Роль:\s*(.+)", chars) + re.findall(r"^\s*[-*]\s*[^—\n]+?\s*—\s*(.+)$", chars, re.MULTILINE)
    out = []
    for t in texts:
        for w in re.findall(r"[А-ЯЁа-яё]+", t.replace("ё", "е")):
            # с заглавной — имя или место («посад Сосновец»); короткие («лука») — не должность
            if w[0].isupper() or len(w) < 5 or not AGENT.search(w) or ADJ.search(w) or role_of(w):
                continue
            out.append(w[:-1] if len(w) >= 6 else w)
    return tuple(dict.fromkeys(out))


def name_skip(names: dict) -> frozenset:
    return frozenset(s for s in ROLE_STEMS if any(n.lower().replace("ё", "е").startswith(s) for n in names))


def character_names(prep: dict) -> dict[str, re.Pattern]:
    """Имена из «Персонажей» подготовки → шаблон с падежными окончаниями. Общие для двоих (фамилия) — не берутся."""
    text = prep.get("characters", "")
    heads = re.findall(r"^##\s*(.+)$", text, re.MULTILINE) + re.findall(r"^\s*[-*]\s*([^—\n]+?)\s*—", text, re.MULTILINE)
    seen: dict[str, int] = {}
    for h in heads:
        for w in set(re.findall(r"[А-ЯЁ][а-яё]+", h)):
            seen[w] = seen.get(w, 0) + 1
    out = {}
    for w, n in seen.items():
        if n > 1 or w in NOT_NAMES or len(w) < 3:
            continue
        stem = w[:-1] if w[-1] in "аяйь" and len(w) > 3 else w
        out[w] = re.compile(rf"(?<![А-ЯЁа-яё]){stem}(?!ин)[а-яё]{{0,3}}(?![а-яё])")
    return out


def _cases(word: str) -> set:
    """Грубо: какие падежи допускает окончание. «капитана Пескарёв», «сейфа капитана Галине» — падежи
    не сходятся, это не приложение, а соседство; «писаря Захара», «прачка Настасья» — сходятся."""
    w = word.lower()
    for ends, cases in ((("ом", "ем"), {"твор"}), (("ой", "ей", "ою", "ею"), {"твор", "род_ж", "дат_ж"}),
                        (("а", "я"), {"род_м", "им_ж"}), (("ы", "и"), {"род_ж", "им_мн", "дат_ж"}),
                        (("у", "ю"), {"дат_м", "вин_ж"}), (("е",), {"дат_ж", "пред"})):
        if w.endswith(ends):
            return cases
    return {"им_м", "вин_м", "им_ж"}


def role_pairs(text: str, names: dict[str, re.Pattern], skip: frozenset = frozenset(), strict: bool = True,
               stems: tuple = ROLE_STEMS):
    """(имя, основа должности, начало, конец): «писаря Захара», «Ефим — княжий мытник».
    Через запятую («Сомов, рулевой», «Шустов, экскурсовод») — не берётся: в перечнях «кто» это два человека."""
    for name, rx in names.items():
        for m in rx.finditer(text):
            before = re.search(r"(\w+)\s+$", text[max(0, m.start() - 40):m.start()])
            if before and before.group(1)[0].islower() and (r := role_of(before.group(1), skip, stems)) \
                    and (not strict or _cases(before.group(1)) & _cases(m.group(0))):
                yield name, r, m.start() - len(before.group(0)), m.end()
            after = re.match(r"(?:\s+[А-ЯЁ][а-яё]+)?\s*[—–]\s*(?:[а-яё]+(?:ий|ый|ой|ая|ей)\s+)?(\w+)",
                             text[m.end():m.end() + 80])
            if after and (r := role_of(after.group(1), skip, stems)):
                yield name, r, m.start(), m.end() + after.end()


def check_roles(d, items):
    names = character_names(d["prep"])
    skip = name_skip(names)
    stems = ROLE_STEMS + book_roles(d["prep"])
    allowed: dict[str, set] = {n: set() for n in names}
    for t in author_texts(d) + list(d["chapters"].values()):
        for name, r, *_ in role_pairs(t, names, skip, strict=False, stems=stems):
            allowed[name].add(r)
    # своя роль из подготовки целиком: «## Имя … Роль: голова купеческой гильдии…» и «- Имя, 45 — прачка и травница»
    chars = d["prep"].get("characters", "")
    roles = [(b.splitlines()[0], m.group(1)) for b in re.split(r"\n(?=##\s)", chars)
             if b and (m := re.search(r"Роль:\s*(.+)", b))]
    roles += re.findall(r"^\s*[-*]\s*([^—\n]+?)\s*—\s*(.+)$", chars, re.MULTILINE)
    for head, role in roles:
        for name in names:
            if names[name].search(head):
                allowed[name] |= {r for w in re.findall(r"\w+", role) if (r := role_of(w, skip, stems))}
    out = []
    for it in items:
        for name, r, s, e in role_pairs(it["text"], names, skip, stems=stems):
            if r not in allowed[name]:
                out.append((it, f"{name}: «{r}…» — у автора и в тексте: {', '.join(sorted(allowed[name])) or 'нет'}",
                            excerpt(it["text"], s, e)))
    return out


# ---------------------------------------------------------------- 2. имена

def check_names(d, items):
    # имена из подготовки во всех формах, и притяжательных: «Силина бумага»
    known = [re.compile(rx.pattern.replace("(?!ин)", "").replace("{0,3}", "{0,4}")) for rx in
             character_names(d["prep"]).values()]

    def prefixes(texts):
        # начала слов с заглавной — «Лены» узнаётся по «Лена», «Лукьяновой» по «Лукьян»
        caps = set(re.findall(r"[А-ЯЁ][а-яё]+", " ".join(texts)))
        return {c[:k] for c in caps for k in range(2, 7)}
    in_text, in_author = prefixes(d["chapters"].values()), prefixes(author_texts(d))
    out, seen = [], set()
    for it in items:
        texts = [it["text"]] + ([it["name"]] if it.get("name") else [])
        for t in texts:
            for m in re.finditer(r"[А-ЯЁ][а-яё]{2,}", t):
                prev = t[:m.start()].rstrip()
                if not prev or prev[-1] in ".!?…«\"„:—–-(;" or prev.endswith("гл."):
                    continue                          # начало предложения, цитаты или строки
                w = m.group(0)
                if w in seen or any(rx.fullmatch(w) for rx in known):
                    continue
                stem = w[:max(2, min(len(w) - 2, 6))]
                if stem in in_text:
                    continue
                seen.add(w)
                hint = " (есть у автора — в главах ещё не было)" if stem in in_author else ""
                out.append((it, f"«{w}» нет ни в одной главе{hint}", excerpt(t, m.start(), m.end())))
    return out


# ---------------------------------------------------------------- 3. цитаты

def loose(part: str) -> str:
    """«вдовьего надзирателя» ~ «вдовий надзиратель»: слова по основе, окончания любые."""
    return r"\b" + r"\s+".join(re.escape(w[:max(4, len(w) - 4)]) + r"\w*" for w in part.split())


def check_quotes(d, items):
    chapters = {n: " " + norm(t) + " " for n, t in d["chapters"].items()}
    out = []
    for it in items:
        for m in re.finditer(r"«([^«»]{12,400})»", it["text"]):
            parts = [norm(p) for p in re.split(r"\.\.\.|…|[.!?;]", m.group(1))]
            parts = [p for p in parts if len(p) >= 8]
            if not parts:
                continue
            upto = " ".join(t for n, t in chapters.items() if not it["chapter"] or n <= it["chapter"])
            if all(p in upto for p in parts) or all(re.search(loose(p), upto) for p in parts):
                continue
            later = [n for n, t in chapters.items() if all(p in t for p in parts)]
            what = (f"цитата из поздней гл.{', '.join(map(str, later))}" if later else "цитаты нет в тексте глав")
            out.append((it, what, excerpt(it["text"], m.start(), m.end(), 20)))
    return out


# ---------------------------------------------------------------- 4. числа и месяцы

_END = r"(ый|ой|ий|ого|ому|ым|ом|ая|ую|ое|ые|ых|ыми|ей)"
NUMS = [(r"дв(а|е|ух|ум|умя)", 2), (r"тр(и|ех|ем|емя)", 3), (r"четыр(е|ех|ем|ьмя)", 4), (r"пят(ь|и|ью)", 5),
        (r"шест(ь|и|ью)", 6), (r"сем(ь|и|ью)", 7), (r"восем(ь|ью)|восьм(и|ью)", 8), (r"девят(ь|и|ью)", 9),
        (r"десят(ь|и|ью)", 10), (r"одиннадцат(ь|и|ью)", 11), (r"двенадцат(ь|и|ью)", 12),
        (r"тринадцат(ь|и|ью)", 13), (r"четырнадцат(ь|и|ью)", 14), (r"пятнадцат(ь|и|ью)", 15),
        (r"шестнадцат(ь|и|ью)", 16), (r"семнадцат(ь|и|ью)", 17), (r"восемнадцат(ь|и|ью)", 18),
        (r"девятнадцат(ь|и|ью)", 19), (r"двадцат(ь|и|ью)", 20), (r"тридцат(ь|и|ью)", 30), (r"сорок(а)?", 40),
        (r"пятьдесят|пятидесят(и|ью)", 50), (r"шестьдесят|шестидесят(и|ью)", 60),
        (r"семьдесят|семидесят(и|ью)", 70), (r"восемьдесят|восьмидесят(и|ью)", 80), (r"девяност(о|а)", 90),
        (r"сто|ста", 100), (r"двести|двухсот", 200), (r"триста|трехсот", 300), (r"четыреста|четырехсот", 400),
        (r"пятьсот|пятисот", 500), (r"шестьсот|шестисот", 600), (r"семьсот|семисот", 700),
        (r"восемьсот|восьмисот", 800), (r"девятьсот|девятисот", 900), (r"тысяч(а|и|у|ей|ью|ам|ами|ах)?", 1000),
        (r"втор" + _END, 2), (r"трет(ий|ье|ья|ью|ьего|ьему|ьим|ьем|ьи|ьих)", 3), (r"четверт" + _END, 4),
        (r"пят" + _END, 5), (r"шест" + _END, 6), (r"седьм" + _END, 7), (r"восьм" + _END, 8),
        (r"девят" + _END, 9), (r"десят" + _END, 10), (r"одиннадцат" + _END, 11), (r"двенадцат" + _END, 12),
        (r"тринадцат" + _END, 13), (r"четырнадцат" + _END, 14), (r"пятнадцат" + _END, 15),
        (r"шестнадцат" + _END, 16), (r"семнадцат" + _END, 17), (r"восемнадцат" + _END, 18),
        (r"девятнадцат" + _END, 19), (r"двадцат" + _END, 20), (r"тридцат" + _END, 30), (r"сороков" + _END, 40)]
NUM_RX = [(re.compile(rf"(?:{p})"), v) for p, v in NUMS]
MONTHS = re.compile(r"(январ|феврал|март|апрел|ма[йяюе]$|июн|июл|август|сентябр|октябр|ноябр|декабр|покров|купал)")


ONE = re.compile(r"од(ин|на|но|ного|ной|ну|ним|ному|ном)|перв(ый|ого|ому|ым|ом|ая|ую|ое|ой)")


def word_num(w: str) -> int | None:
    if w.isdigit():
        return int(w)
    return next((v for rx, v in NUM_RX if rx.fullmatch(w)), None)


def tokens(text: str, generous: bool) -> set:
    """Числа (составные: «сто двадцать» → 120) и месяцы. generous — ещё и части составных (для текста главы)."""
    out, run = set(), []

    def flush():
        if run:
            out.add(sum(run))
            if generous:
                out.update(run)
            run.clear()
    # Знаки препинания разрывают число: «чистыми двести. Десять серебряников» — не 210
    for w in re.findall(r"\w+|[.,;:!?—–()]", (text or "").lower().replace("ё", "е")):
        if not w[0].isalnum():
            flush()
            continue
        v = word_num(w)
        if v is None and run and run[-1] >= 20 and run[-1] % 10 == 0 and ONE.fullmatch(w):
            v = 1                    # «тридцать одна», «двести двадцать первая»; одно «один» числом не считается
        if v is None:
            flush()
            if (m := MONTHS.match(w)):
                out.add("мес:" + m.group(1).rstrip("$"))
            continue
        if v == 1000 and run and not w.isdigit():
            run[:] = [sum(run) * 1000]            # «две тысячи триста» — 2300
            continue
        if run and (v >= run[-1] or w.isdigit()):
            flush()
        run.append(v)
    flush()
    return out


def check_numbers(d, items):
    chapters = {n: tokens(t, True) for n, t in d["chapters"].items()}
    anyc = set().union(*chapters.values()) if chapters else set()
    plan = {}
    for r in d["bible"]:
        if r["status"] == "автор":
            plan.setdefault(r["chapter_num"], set()).update(tokens(r["value"], True))
    notes = tokens(" ".join(d["prep"].values()), True)
    out = []
    for it in items:
        n = it["chapter"]
        src = set().union(*(t for k, t in chapters.items() if k <= n)) if n else anyc
        src = src | plan.get(n, set()) | notes        # подготовка автора — тоже правда, не выдумка разбора
        # «гл.N» — не число факта; время «21:00» в прозе пишут словами («в девять вечера») — не сверяется
        fact = re.sub(r"гл\.?\s*\d+|\b\d{1,2}:\d{2}\b", " ", it["text"])
        missing = tokens(fact, False) - src
        missing = {x for x in missing if x not in (0, 1)}
        if not missing:
            continue
        show = ", ".join(str(x).replace("мес:", "") for x in sorted(missing, key=str))
        hint = []
        if n and missing & anyc:
            hint.append("есть в поздних главах")
        where = f"в главах 1–{n}, плане гл.{n} и подготовке" if n else "ни в одной главе и подготовке"
        at = next((it["text"].find(str(x)) for x in missing if isinstance(x, int) and str(x) in it["text"]), 0)
        out.append((it, f"нет {where}: {show}" + (f" ({'; '.join(hint)})" if hint else ""),
                    excerpt(it["text"], at, at + 4, 110)))
    return out


# ---------------------------------------------------------------- отчёт

CHECKS = (("Роли", check_roles), ("Имена", check_names), ("Цитаты", check_quotes), ("Числа и месяцы", check_numbers))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", type=int, nargs="?")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if a.project is None:
        c = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
        print("Проекты (номер — название — глав):")
        for pid, name in c.execute("SELECT id, name FROM projects ORDER BY id"):
            n = c.execute("SELECT COUNT(DISTINCT number) FROM chapters WHERE project_id=?", (pid,)).fetchone()[0]
            print(f"  {pid} — {name} — {n}")
        print("Запуск: python memory_audit.py НОМЕР --out отчёт.md")
        return
    d = load(a.db, a.project)
    items = memory_items(d)
    n_bible = sum(1 for i in items if i["src"].startswith("библия"))
    lines = [f"# Сверка памяти: проект {a.project} «{d['name']}»", "",
             (f"Глав {len(d['chapters'])}, проверено записей {len(items)} (библия от разбора {n_bible}, "
              f"строки State {len(items) - n_bible}). Только чтение базы."), ""]
    for i, (title, fn) in enumerate(CHECKS, 1):
        found = fn(d, items)
        lines += [f"## {i}. {title}: {len(found)}", ""]
        for it, what, ex in found:
            ch = f" (гл.{it['chapter']})" if it["chapter"] else ""
            lines += [f"- {it['src']}{ch} — {what}", f"  > {ex}"]
        lines.append("")
    report = "\n".join(lines)
    print(report)
    if a.out:
        a.out.write_text(report, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
