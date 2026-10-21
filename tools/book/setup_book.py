"""Проект книги в приложении автора (FE :5000, планировщик :5001) через его же маршруты.

    cd ПАПКА_КНИГИ && python tools/book/setup_book.py

Берёт book.json из текущей папки, пишет setup.json (fe_pid, pl_pid, voice_id).
"""
import json, os, re
from pathlib import Path
import requests

B = Path.cwd()                       # папка книги
BOOK = json.load(open(B / "book.json", encoding="utf-8"))
# Копия приложения (дымовая книга) — свои адреса
FE = os.environ.get("BOOK_FE", "http://127.0.0.1:5000")
PL = os.environ.get("BOOK_PL", "http://127.0.0.1:5001")
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fe_auth                                          # noqa: E402
H = fe_auth.headers()
OUT = B / "setup.json"
done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}

fe = fe_auth.Session()
fe.headers.update(H)
names = {p["name"]: p["id"] for p in fe.get(FE + "/api/projects/list", timeout=30).json().get("projects", [])}
if BOOK["name"] in names:
    raise SystemExit(f"проект «{BOOK['name']}» уже есть (id {names[BOOK['name']]}) — не создаю второй")

r = fe.post(FE + "/project/new", data={"name": BOOK["name"], "genre": BOOK["genre"], "genre_key": BOOK["genre_key"]},
            allow_redirects=False, timeout=30)
print("FE проект:", r.status_code)
pid = {p["name"]: p["id"] for p in fe.get(FE + "/api/projects/list", timeout=30).json()["projects"]}[BOOK["name"]]
done["fe_pid"] = pid
print("  id", pid)
print("стиль:", fe.post(FE + "/project/style-key", data={"style_key": BOOK["style_key"]}, allow_redirects=False).status_code)
for sec, text in BOOK["prep"].items():
    if text:
        print("подготовка", sec, fe.post(FE + "/prep/save", json={"section": sec, "content": text}).json())
v = fe.post(FE + "/voice/save", json={"name": BOOK["voice"]["name"], "profile": BOOK["voice"]["profile"],
                                       "source": "custom"}).json()
print("голос:", v)
print("голос активен:", fe.post(FE + "/voice/activate", json={"id": v["id"]}).json())
done["voice_id"] = v["id"]

pl = fe_auth.Session()
csrf = re.search(r'name="csrf-token" content="([^"]+)"', pl.get(PL + "/projects", timeout=30).text).group(1)
r = pl.post(PL + "/projects/new", json={"name": BOOK["name"], "genre": BOOK["genre"],
                                         "description": BOOK.get("description", "")},
            headers={"X-CSRF-Token": csrf}, timeout=30).json()
done["pl_pid"] = r["id"]
print("планировщик:", r)
pl.get(PL + f"/switch/{r['id']}", timeout=30)
csrf = re.search(r'name="csrf-token" content="([^"]+)"', pl.get(PL + "/projects", timeout=30).text).group(1)
print("связь с FE:", pl.post(PL + f"/api/fe/import/{pid}", json={}, headers={"X-CSRF-Token": csrf}, timeout=120).json())

# План всей книги — на доску сразу: планировщик шлёт сцены после главы сторожу
# забеганий приложения (engine/run_ahead). run_book берёт сцены главы с доски
if BOOK.get("plan_ahead"):
    acts = sorted(pl.get(PL + "/api/acts", timeout=30).json()["acts"], key=lambda a: a["number"])
    for n, ch in enumerate(BOOK["chapters"], 1):
        act = acts[min(len(acts) - 1, (n - 1) * len(acts) // len(BOOK["chapters"]))]["id"]
        for sc in ch["scenes"]:
            pl.post(PL + "/api/scenes/new", json={"act_id": act, "title": sc["title"], "location": sc["location"],
                                                  "day": sc.get("day", ""), "time_of_day": sc["time"],
                                                  "characters": sc["chars"], "what_happens": sc["what"],
                                                  "emotion": sc["emo"], "hold": sc.get("hold", "")},
                    headers={"X-CSRF-Token": csrf}, timeout=30)
    print("план на доске:", sum(len(ch["scenes"]) for ch in BOOK["chapters"]), "сцен")
OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
