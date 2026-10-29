"""Журнал лимитов ChatGPT (tools/limits_log.py): сбросы, история из логов, сводка — без codex."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import limits_log as ll


def _rows(*pairs):
    return [{"t": t, "week": w, "week_resets": r, "src": "замер"} for t, w, r in pairs]


def test_reset_early_and_on_time():
    a, b = _rows(("2026-10-28T09:04+03:00", 69.0, "2026-11-02T11:41+03:00"),
                 ("2026-10-28T10:10+03:00", 1.0, "2026-11-04T09:38+03:00"))
    assert ll.is_reset(a, b) == "досрочный"
    a, b = _rows(("2026-11-02T11:00+03:00", 80.0, "2026-11-02T11:41+03:00"),
                 ("2026-11-02T12:00+03:00", 0.0, "2026-11-09T11:41+03:00"))
    assert ll.is_reset(a, b) == "по сроку"
    a, b = _rows(("2026-10-28T11:00+03:00", 2.0, "2026-11-04T09:38+03:00"),
                 ("2026-10-28T12:00+03:00", 5.0, "2026-11-04T09:38+03:00"))
    assert ll.is_reset(a, b) is None


def test_import_logs_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(ll, "HOME", tmp_path)
    monkeypatch.setattr(ll, "LOG", tmp_path / "limits_log.jsonl")
    log = tmp_path / "run.out"
    log.write_text("28.10 06:23:11 гл.1: ChatGPT неделя 63.0%, окно 26.0%\n"
                   "28.10 09:04:00 гл.5: ChatGPT неделя 69.0%, окно 40.0%\n"
                   "28.10 10:10:00 гл.5: ChatGPT неделя 1.0%, окно 4.0%\n"
                   "28.10 11:00:00 гл.6: ChatGPT неделя 2.0%, окно 9.0%\n", encoding="utf-8")
    assert ll.import_logs([str(log)]) == 4
    assert ll.import_logs([str(log)]) == 0                  # повторный импорт не дублирует
    rows = [json.loads(x) for x in ll.LOG.read_text(encoding="utf-8").splitlines()]
    assert [r["week"] for r in rows] == [63.0, 69.0, 1.0, 2.0]
    rep = ll.build_report()
    assert "Сбросы недели: 1" in rep and "69 % → 1 %" in rep
    assert "Израсходовано" in rep and "Сейчас: неделя 2 %" in rep
