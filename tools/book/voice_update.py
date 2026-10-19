"""Обновление голоса книги по принятым главам (автор: «раз в 8 глав»).

    cd ПАПКА_КНИГИ && python tools/book/voice_update.py CHECK_FROM CHECK_TO [--apply]

Опыт книги «Фон»: правила в профиль не писать — модель их цитирует; оставлять манеру и эталоны.

1. «Голос → Проверить» (Sol) по главам CHECK_FROM..CHECK_TO — оценка и «не совпадает».
2. Манера принятых глав без модели (tools/style_markers.markers): диалог, длина фразы, «я», сравнения.
3. Sol выбирает 3 эталонных отрывка из глав (не Claude: текст писал Sonnet); цитаты сверяются дословно.
--apply — сохранить новый профиль, включить, старый удалить.
Всё через маршруты приложения; результат — voice_update.json.
"""
import json, re, sys
from pathlib import Path
from statistics import mean
import requests

B = Path.cwd()                       # папка книги
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from style_markers import markers                      # noqa: E402

FE = "http://127.0.0.1:5000"
H = {"X-FE-Token": (Path.home() / "fiction_engine" / "api_token").read_text().strip()}
BOOK = json.load(open(B / "book.json", encoding="utf-8"))
# Оценивает и выбирает эталоны судья набора — другая семья, чем писатель (Claude не судит текст Claude)
SOL = (BOOK.get("roles") or {}).get("model_judge") or "chatgpt_subscription::gpt-6.1-sol@medium"
SETUP = json.load(open(B / "setup.json", encoding="utf-8"))
OUT = B / "voice_update.json"
a, b = int(sys.argv[1]), int(sys.argv[2])
apply = "--apply" in sys.argv
s = requests.Session(); s.headers.update(H)
res = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
run = res.setdefault(f"{a}-{b}", {})

active = {p["id"] for p in s.get(FE + "/api/projects/list").json()["projects"]}
assert SETUP["fe_pid"] in active


def chapter(n):
    return (B / "chapters" / f"ch{n:02}.txt").read_text(encoding="utf-8")


# 1. Проверка голоса
checks = run.setdefault("check", {})
for n in range(a, b + 1):
    if str(n) in checks:
        continue
    r = s.post(FE + "/voice/check", json={"text": chapter(n), "model": SOL}, timeout=900).json()
    checks[str(n)] = {"score": r.get("score"), "analysis": r.get("analysis") or r.get("error")}
    print(f"гл.{n}: голос {r.get('score')}/10", flush=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

# 2. Манера без модели
ms = [markers(chapter(n)) for n in range(1, b + 1)]
manner = {k: round(mean(m[k] for m in ms), 1) for k in ms[0]}
run["manner"] = manner
print("манера:", manner)

# 3. Эталон — выбирает Sol
if "excerpts" not in run:
    texts = "\n\n".join(f"=== ГЛАВА {n} ===\n{chapter(n)}" for n in range(max(1, b - 5), b + 1))
    prompt = ("Ниже главы книги, рассказ от первого лица. Выбери 3 отрывка по 3–6 предложений подряд, которые лучше всего "
              "передают голос рассказчицы: как она видит, думает, шутит, разбирает кадр. Разные по типу: разбор улики, "
              "диалог, момент чувства. Отрывки — дословно, без пропусков внутри.\n\n" + texts +
              '\n\nОтветь JSON: {"excerpts": [{"chapter": 3, "kind": "разбор", "text": "…"}]}')
    r = s.post(FE + "/api/inline_call", json={"model": SOL, "system": "Ты литературный редактор. Только JSON.",
                                               "prompt": prompt, "max_tokens": 3000}, timeout=900).json()
    raw = r.get("result") or ""
    m = re.search(r"\{.*\}", raw, re.S)
    ex = json.loads(m.group(0)).get("excerpts", []) if m else []
    full = " ".join(" ".join(chapter(n).split()) for n in range(1, b + 1))
    for x in ex:
        x["found"] = " ".join(x.get("text", "").split()) in full
    run["excerpts"] = ex
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
for x in run["excerpts"]:
    print(f"эталон гл.{x.get('chapter')} ({x.get('kind')}, найден дословно: {x['found']}): {x.get('text','')[:120]}")

if apply:
    prof = BOOK["voice"]["profile"]
    head = prof.split("ЭТАЛОН")[0].rstrip()
    numbers = (f"\n\nЗАМЕРЕНО ПО ГЛАВАМ 1–{b}: в среднем {manner['слов во фразе']} слов во фразе, "
               f"диалог {manner['диалог, %']:.0f}% текста. Держать эту манеру.")
    ex = [x for x in run["excerpts"] if x["found"]][:3]
    etalon = "\n\nЭТАЛОН (из книги)\n" + "\n\n".join(x["text"].strip() for x in ex)
    new = (head + numbers + etalon)
    if len(new) > 1800:                     # профиль режется на 1800 — эталоны укорачиваем, а не правила
        keep = 1800 - len(head + numbers) - len("\n\nЭТАЛОН (из книги)\n")
        etalon = "\n\nЭТАЛОН (из книги)\n" + "\n\n".join(x["text"].strip() for x in ex)[:keep].rsplit(".", 1)[0] + "."
        new = head + numbers + etalon
    name = f"Варя — «Разбор» (гл.{b})"
    v = s.post(FE + "/voice/save", json={"name": name, "profile": new, "source": "custom"}).json()
    print("новый голос:", v, s.post(FE + "/voice/activate", json={"id": v["id"]}).json())
    print("старый удалён:", s.post(FE + "/voice/delete", json={"id": SETUP["voice_id"]}).status_code)
    SETUP["voice_id"] = v["id"]
    json.dump(SETUP, open(B / "setup.json", "w", encoding="utf-8"), ensure_ascii=False)
    BOOK["voice"] = {"name": name, "profile": new}
    json.dump(BOOK, open(B / "book.json", "w", encoding="utf-8", newline=""), ensure_ascii=False, indent=1)
    run["applied"] = {"name": name, "chars": len(new)}
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(new)
