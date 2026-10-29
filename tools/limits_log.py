"""Журнал лимитов подписки ChatGPT (Codex): окно 5 ч и неделя — проценты и даты сброса.

Отдельно от Fiction Engine: код приложения не импортирует. Лимиты читает у
`codex app-server` (account/rateLimits/read), как раннеры книг перед главой:
модель не вызывается, лимит не тратится.

Повод (29.10): неделя ChatGPT за две недели досрочно обнулялась шесть раз, а
история процентов лежала по логам разных раннеров, часть строк без даты.

    python tools/limits_log.py               — один замер в журнал (так зовёт планировщик Windows)
    python tools/limits_log.py --report      — сводка: сбросы, расход по дням, расход против нормы
    python tools/limits_log.py --install 30  — задача планировщика «FE limits log» раз в 30 минут
    python tools/limits_log.py --uninstall   — убрать задачу
    python tools/limits_log.py --import-log ФАЙЛ…  — дописать историю из логов раннеров
                                               («28.10 06:23:11 гл.1: ChatGPT неделя 63.0%, окно 26.0%»)

Журнал — ~/fiction_engine/limits_log.jsonl, строка JSON на замер.
"""
import argparse
import datetime as dt
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

HOME = Path.home() / "fiction_engine"
LOG = HOME / "limits_log.jsonl"
CFG = HOME / "limits_log_cfg.json"         # пути к codex для планировщика (у задачи свой PATH)
TASK = "FE limits log"
DROP = 3.0                                  # падение недели больше чем на 3 п. — сброс
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def codex_cmd() -> list[str]:
    """codex.cmd через cmd.exe ломает аргументы — node и codex.js напрямую, как в приложении."""
    if CFG.exists():
        cmd = json.loads(CFG.read_text(encoding="utf-8")).get("codex")
        if cmd and all(Path(x).exists() for x in cmd):
            return cmd
    exe = shutil.which("codex") or "codex"
    js = Path(exe).parent / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    if exe.lower().endswith(".cmd") and js.exists():
        return [shutil.which("node") or "node", str(js)]
    return [exe]


def _stop_proc(p: subprocess.Popen) -> None:
    if p.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, check=False,
                       creationflags=NO_WINDOW)
    else:
        p.kill()


def read_limits() -> dict:
    p = subprocess.Popen(codex_cmd() + ["app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", creationflags=NO_WINDOW)
    watchdog = threading.Timer(60, _stop_proc, [p])     # не ответил — не ждать вечно
    watchdog.start()
    try:
        def rpc(i, method, params):
            p.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": params}) + "\n")
            p.stdin.flush()
            for line in p.stdout:
                if line.startswith("{") and (m := json.loads(line)).get("id") == i:
                    return m
            raise RuntimeError("codex app-server закрылся без ответа")
        rpc(1, "initialize", {"clientInfo": {"name": "fe-limits-log", "version": "1"}})
        p.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "initialized"}) + "\n")
        snap = (rpc(2, "account/rateLimits/read", {}).get("result") or {}).get("rateLimits") or {}
    finally:
        watchdog.cancel()
        _stop_proc(p)
    return snap


def _iso(ts) -> str | None:
    return dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="minutes") if ts else None


def _load_rows() -> list[dict]:
    if not LOG.exists():
        return []
    rows = [json.loads(x) for x in LOG.read_text(encoding="utf-8").splitlines() if x.strip()]
    return sorted(rows, key=lambda r: r["t"])


def _append_rows(rows: list[dict]) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def take_sample() -> dict:
    snap = read_limits()
    week, win = snap.get("secondary") or {}, snap.get("primary") or {}
    row = {"t": dt.datetime.now().astimezone().isoformat(timespec="minutes"),
           "week": week.get("usedPercent"), "window": win.get("usedPercent"),
           "week_resets": _iso(week.get("resetsAt")), "window_resets": _iso(win.get("resetsAt")),
           "plan": snap.get("planType"), "src": "замер"}
    prev = next((r for r in reversed(_load_rows()) if r.get("week") is not None), None)
    if prev and row["week"] is not None:
        reset = is_reset(prev, row)
        if reset:
            row["reset"] = reset
    _append_rows([row])
    return row


def is_reset(prev: dict, cur: dict) -> str | None:
    """«досрочный» / «по сроку», если неделя упала или дата сброса недели ушла вперёд."""
    dropped = cur["week"] < (prev["week"] or 0) - DROP
    moved = (prev.get("week_resets") and cur.get("week_resets")
             and cur["week_resets"] > prev["week_resets"])
    if not (dropped or moved):
        return None
    due = prev.get("week_resets")
    return "по сроку" if due and cur["t"] >= due else "досрочный"


# ---------------------------------------------------------------- история из логов раннеров

LINE = re.compile(r"^(?:(\d\d)\.(\d\d) )?(\d\d):(\d\d)(?::\d\d)?\s.*?ChatGPT неделя ([\d.]+)%, окно ([\d.]+)%")


def import_logs(files: list[str]) -> int:
    have = {r["t"][:16] for r in _load_rows()}
    rows = []
    for f in files:
        mt = dt.datetime.fromtimestamp(os.path.getmtime(f))
        for line in Path(f).read_text(encoding="utf-8", errors="ignore").splitlines():
            m = LINE.match(line)
            if not m:
                continue
            day, mon, h, mi, week, win = m.groups()
            if day:
                t = dt.datetime(mt.year, int(mon), int(day), int(h), int(mi))
                src = "лог"
            else:                       # строка без даты — день по времени файла
                t = mt.replace(hour=int(h), minute=int(mi), second=0, microsecond=0)
                if t > mt:
                    t -= dt.timedelta(days=1)
                src = "лог, дата по файлу"
            ts = t.astimezone().isoformat(timespec="minutes")
            if ts[:16] not in have:
                have.add(ts[:16])
                rows.append({"t": ts, "week": float(week), "window": float(win), "src": src})
    rows.sort(key=lambda r: r["t"])
    _append_rows(rows)
    return len(rows)


# ---------------------------------------------------------------- сводка

def build_report() -> str:
    rows = [r for r in _load_rows() if r.get("week") is not None]
    if not rows:
        return "Журнал пуст: сделайте замер (python tools/limits_log.py)."
    out = [f"Журнал лимитов ChatGPT: {len(rows)} замеров, {rows[0]['t'][:16]} — {rows[-1]['t'][:16]}", ""]
    resets, used, by_day = [], 0.0, {}
    for a, b in itertools.pairwise(rows):
        kind = b.get("reset") or (("досрочный?" if b.get("src") != "замер" else "досрочный")
                                  if b["week"] < a["week"] - DROP else None)
        if kind:
            resets.append((a, b, kind))
            gain = b["week"]                        # после сброса набралось уже столько
        else:
            gain = max(0.0, b["week"] - a["week"])
        used += gain
        by_day[b["t"][:10]] = by_day.get(b["t"][:10], 0.0) + gain
    out.append(f"Сбросы недели: {len(resets)}")
    for a, b, kind in resets:
        moved = f"; сброс был {a['week_resets'][:16]}, стал {b['week_resets'][:16]}" \
            if a.get("week_resets") and b.get("week_resets") else ""
        out.append(f"  {kind}: между {a['t'][:16]} и {b['t'][:16]} — {a['week']:.0f} % → {b['week']:.0f} %{moved}")
    days = (dt.datetime.fromisoformat(rows[-1]["t"]) - dt.datetime.fromisoformat(rows[0]["t"])).total_seconds() / 86400
    norm = days / 7 * 100
    out += ["", f"Израсходовано за {days:.1f} дн.: {used:.0f} % недели; по тарифу за это время — {norm:.0f} %"
            + (f" (в {used / norm:.1f} раза больше нормы)" if norm and used > norm else ""), "",
            "Расход по дням (п. недели):"]
    out += [f"  {d}: {v:.0f}" for d, v in sorted(by_day.items())]
    last = rows[-1]
    out += ["", f"Сейчас: неделя {last['week']:.0f} %, окно {last.get('window') or 0:.0f} %"
            + (f"; сброс недели {last['week_resets'][:16]}" if last.get("week_resets") else "")
            + (f", окна {last['window_resets'][11:16]}" if last.get("window_resets") else "")]
    return "\n".join(out)


# ---------------------------------------------------------------- планировщик Windows

def install_task(minutes: int) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    CFG.write_text(json.dumps({"codex": codex_cmd()}, ensure_ascii=False), encoding="utf-8")
    py = Path(sys.executable)
    pyw = py.with_name("pythonw.exe")               # без окна консоли раз в полчаса
    exe = pyw if pyw.exists() else py
    tr = f'"{exe}" "{Path(__file__).resolve()}"'
    r = subprocess.run(["schtasks", "/Create", "/F", "/SC", "MINUTE", "/MO", str(minutes), "/TN", TASK, "/TR", tr],
                       capture_output=True, text=True, check=False)
    print(r.stdout.strip() or r.stderr.strip())


def uninstall_task() -> None:
    r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK], capture_output=True, text=True, check=False)
    print(r.stdout.strip() or r.stderr.strip())


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--install", type=int, metavar="МИНУТ")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--import-log", nargs="+", metavar="ФАЙЛ")
    a = ap.parse_args()
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    if a.install:
        install_task(a.install)
    elif a.uninstall:
        uninstall_task()
    elif a.import_log:
        print(f"дописано строк: {import_logs(a.import_log)}")
    elif a.report:
        print(build_report())
    else:
        row = take_sample()
        if sys.stdout:
            print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
