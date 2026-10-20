"""Снимок заданий главы (tools/prompt_snapshot.py): проверки ловят подложенное, прогон не зовёт моделей."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import prompt_snapshot as ps  # noqa: E402

GEN = "claude_subscription::claude-sonnet-5-5"
SOL = "chatgpt_subscription::gpt-6.1-sol@medium"


def _chapter(n: int, size: int = 60) -> str:
    return "\n\n".join(f"Глава {n} эпизод {i}: Варя открыла окно и посмотрела на двор, где стоял синий фургон."
                       for i in range(1, size + 1))


def _call(caller, system="", user="", model=SOL):
    return {"n": 1, "caller": [caller], "model": model, "system": system, "user": user}


def _kinds(found):
    return sorted({f["kind"] for f in found})


def test_future_chapter_and_cut_text():
    ch = {1: _chapter(1), 2: _chapter(2), 3: _chapter(3)}
    fake = ps.fake_chapter(2)
    writer = _call("step_generate", user="ГОЛОС — ЭТАЛОН:\n" + ch[3][:700] + "\n" + ch[1][:700], model=GEN)
    drift = _call("check_voice_drift", user="ГЛАВА 2 (первые 1200 символов):\n" + fake[:1200])
    critic = _call("step_critique", user="Глава 2:\n\n" + fake, model=GEN)
    found = ps.check([writer, drift, critic], ch, 2, fake, "", GEN, {})
    assert [f["msg"][:5] for f in found if f["kind"] == "БУДУЩЕЕ"] == ["гл.3:"]
    cut = [f for f in found if f["kind"] == "ОБРЕЗ"]
    assert len(cut) == 1 and cut[0]["caller"] == "check_voice_drift"
    # Критик той же семьи, что писатель, — замечание, не ошибка
    assert [f["caller"] for f in found if f["kind"] == "СЕМЬЯ"] == ["step_critique"]


def test_notes_placeholders_threshold_history():
    notes = " ".join(f"заметка автора номер {i} про тайный финал книги" for i in range(30))
    judge = _call("step_judge",
                  system="ПРАВИЛО ВЕРДИКТА: ИТОГ ≥ 30.\nСТАНДАРТ: ≥ 28 — приемлемо.\n"
                         "ИСТОРИЯ ОЦЕНОК ПРОЕКТА: Лучший: 34/50 (гл.7). Последний: 33/50 (гл.2).",
                  user=notes[:400] + "\n[Вставь 3-5 предложений из предыдущей главы]\n{voice_block}")
    found = ps.check([judge], {}, 5, ps.fake_chapter(5), notes, GEN, {SOL: 30})
    assert _kinds(found) == ["ЗАГЛУШКИ", "ЗАМЕТКИ", "ИСТОРИЯ", "ПОРОГ"]
    assert [f["msg"][:6] for f in found if f["kind"] == "ПОРОГ"] == ["«≥ 28»"]
    assert "[7]" in next(f["msg"] for f in found if f["kind"] == "ИСТОРИЯ")


def test_json_stub_takes_outer_sample():
    prompt = 'Ответь JSON:\n{"items": [{"n": 1, "status": "есть"}], "ahead": {"x": [1]}}'
    assert ps.json_like(prompt) == '{"items": [], "ahead": {"x": []}}'
    assert ps.json_like("Просто текст") is None


def _rewrite_ch3(project_id):
    """Гл.3 заново в проекте из пяти глав — путь автора в приложении целиком."""
    from engine.db_projects import save_chapter
    for n in range(1, 6):
        save_chapter(project_id, n, _chapter(n), f"Глава {n}")
    roles = {"model_gen": GEN, "model_critic": SOL, "model_editor": GEN, "model_judge": SOL}
    return ps.snapshot(project_id, 3, "Варя находит фургон.", roles)


def test_walk_without_live_calls(project_id):
    """Задания собраны со всех шагов, живых вызовов нет, подмена после прогона снята."""
    import engine.api as api
    real = api.call_model
    calls, _, steps = _rewrite_ch3(project_id)
    assert api.call_model is real
    assert {s["path"]: s["code"] for s in steps}["/pipeline/start"] == 200
    callers = {c["caller"][0] for c in calls}
    assert {"step_generate", "step_critique", "step_judge", "check_voice_drift"} <= callers
    assert not [c for c in calls if "запрещён" in c.get("answer", "")]


# Обход 20.10, ждут исправления. Исправят все — тест пройдёт, strict уронит его:
# снять xfail, и снимок станет проверкой в CI
@pytest.mark.xfail(strict=True, reason="эталон голоса из последних глав проекта (будущее при переписывании); "
                                       "дрейф голоса по первым 1200 символам; судье — история с этой главой")
def test_no_known_prompt_faults(project_id):
    _, found, _ = _rewrite_ch3(project_id)
    assert not [f for f in found if f["kind"] in ps.ERRORS + ("ИСТОРИЯ",)], found
