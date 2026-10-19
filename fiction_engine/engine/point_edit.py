"""
Точечная редактура по критике — круг «Ещё круг редактуры» без переписывания.

Прежний редактор получал «перепиши текст, исправив все проблемы» и
возвращал главу заново. На главах автора 17.10 круг менял 14–59 % слов,
глава 2 за два круга потеряла 40 % объёма, а «Кратохвил», «одиннадцать в
подвале» и «под обезболом» появились именно на кругах редактуры — в местах,
о которых критика молчала.

Здесь редактор возвращает список правок: «фрагмент дословно → чем
заменить» и «вставить после фрагмента». Подставляет их код (тем же поиском,
что у правщика непрерывности, `continuity_fix`); всё остальное остаётся
слово в слово.
"""
from __future__ import annotations

import re
from typing import Callable

EDIT_MODE_KEY = "edit_mode"
# self — точечно, места выбирает сам редактор (по умолчанию); points — точечно
# по разбору критика; rewrite — целиком, по выбору автора.
#
# Почему не по критику (замер 18.10, bench/edit-source-2026-10-18.json): правки
# сравнивались с исходником вслепую по каждому фрагменту, судья — другой семьи.
# Набор GPT (правит Sol, судит Sonnet): по разбору критика лучше исходника
# 48–50 % правок, при любом из трёх критиков; сам — 77 % (65 из 84). Набор
# Sonnet (правит Sonnet, судит Sol): 64 % → 87 % (97 из 111). Новый промт
# критика («только конкретные места с цитатой») не помог — 49 %. Советы
# критика («покажи эмоцию», «добавь напряжения») редактор исполнял штампами:
# дописанные выводы героя, «задержала дыхание», вставные реплики.
EDIT_MODES = ("self", "points", "rewrite")
POINT_EDITS_MAX = 6          # было 15: Opus-критик упирался в потолок, правок втрое больше при той же доле удачных
INSERT_WORDS_MAX = 600

# Вместо разбора критика — в режиме self
SELF_REVIEW = ("Отдельного разбора нет. Прочитай главу как строгий редактор и сам найди до 6 мест, "
               "где проза станет точнее и сильнее: неясность, лишнее, повтор, сбой логики или ритма. "
               "Если хороших правок меньше — дай меньше.")

SYS_POINT_EDITOR = ("Ты — редактор и автор этой книги. Правишь главу точечно по критике: "
                    "только названные места. Отвечаешь только JSON.")

_PROMPT = """Ниже задача главы, критика и сама глава. Исправь проблемы, которые
называет критика, ТОЧЕЧНО — главу не переписывай.

Правки двух видов:
- замена: "old" — фрагмент главы дословно (одно–три предложения, чтобы найти
  его однозначно), "new" — тот же фрагмент, исправленный;
- вставка: "after" — фрагмент главы дословно, после абзаца с которым вставить,
  "new" — новый текст (абзац или сцена, до {insert_max} слов). Вставка — для
  того, чего в главе нет, а задача или критика требует.

Правила:
- Не трогай места, о которых критика молчит.
- Имена, факты, время, места и кто что знает — как в главе и в задаче; новых
  фактов о прошлом не вводи.
- Сохраняй голос, ритм и длину абзацев главы.
- Совет критика, с которым текст лучше не станет, можно пропустить.
- Не дописывай за героя выводы и итоги («всё укладывалось в…», «предстояло
  проверить», «он понял, что…»): вывод делает читатель.
- Не добавляй жесты-реакции ради эмоции (задержала дыхание, сжала пальцы,
  холодок по спине). Если совет просит «показать чувство», а в тексте уже есть
  деталь или действие, которые его передают, — совет пропусти.
- Не вставляй новые реплики и действия в чужой разговор, чтобы его «оживить».
- Сокращая, не выбрасывай конкретные детали (числа, предметы, порядок действий):
  в детективе они бывают уликой.
- Не больше {max_edits} правок; важные — первыми.

=== ЗАДАЧА ГЛАВЫ ===
{task}

=== КРИТИКА ===
{critique}

=== ГЛАВА ===
{text}

Ответь JSON без пояснений вокруг:
{{"edits": [{{"old": "…", "new": "…", "why": "…"}}, {{"after": "…", "new": "…", "why": "…"}}]}}"""


# Пункты плана, которых в главе нет или они сделаны частично (engine/plan_check),
# идут редактору первыми. Почти всегда это время и даты сцен из планировщика
# (книга на Sonnet 18.10: «сцена днём, а не вечером», «не названа дата»). Такие
# правки редактор помечает PLAN_MARK: фильтр судьи их не откатывает —
# сравнение «как проза» вставку факта проигрывает почти всегда (19 пунктов →
# после правки 1 → после фильтра 8), а проверяет их повторная сверка с планом.
PLAN_MARK = "ПЛАН:"


def plan_task(misses: list[dict]) -> str:
    """Задание редактору по пунктам плана «нет»/«частично» → текст перед разбором."""
    lines = [f"- [{x['n']}] {str(x.get('item', ''))[:400]}" + (f" — {x['note']}" if x.get("note") else "")
             for x in misses]
    return ("СНАЧАЛА — ПЛАН ГЛАВЫ. Сверка нашла пункты плана, которых в главе нет или они выполнены "
            "частично:\n" + "\n".join(lines) + "\nЗакрой их правкой или вставкой в подходящем месте — это "
            f"важнее остального. У таких правок \"why\" начинай с «{PLAN_MARK}».")


def ahead_task(reveals: list[dict]) -> str:
    """Задание редактору по раскрытиям раньше плана (engine/run_ahead) → текст перед разбором."""
    lines = [f"- «{x['quote'][:200]}» — {x.get('why', '')[:300]} ({x.get('plan', '')})" for x in reveals]
    return ("СНАЧАЛА — ЗАБЕГАНИЕ ВПЕРЁД. Глава раскрывает то, что по плану читатель узнаёт позже:\n"
            + "\n".join(lines) + "\nУбери раскрытие правкой этого места: оставь сцену и улику, но так, "
            "чтобы читатель ещё не знал ответа (догадка, намёк, недосказанность). Это важнее остального. "
            f"У таких правок \"why\" начинай с «{PLAN_MARK}».")


def plan_edit_texts(applied: list[dict]) -> list[str]:
    """Новый текст правок по плану — их фильтр судьи не трогает."""
    return [str(e.get("new") or "") for e in applied
            if str(e.get("why") or "").strip().upper().startswith(PLAN_MARK) and str(e.get("new") or "").strip()]


def edit_mode() -> str:
    """Режим «Ещё круга редактуры» из настроек: self, points или rewrite (EDIT_MODES)."""
    try:
        from .db_settings import get_setting
        m = (get_setting(EDIT_MODE_KEY) or "").strip()
    except Exception:          # нет базы — по умолчанию
        m = ""
    return m if m in EDIT_MODES else "self"


def _locate(text: str, fragment: str) -> tuple[int, int] | None:
    """Где в тексте фрагмент: дословно → по словам → по первому и последнему предложению."""
    from .continuity_fix import _anchored_span, _flex_pattern
    if fragment and fragment in text:
        i = text.index(fragment)
        return i, i + len(fragment)
    pat = _flex_pattern(fragment)
    m = pat.search(text) if pat else None
    if m:
        return m.start(), m.end()
    return _anchored_span(text, fragment)


def _insert_after(text: str, after: str, new: str) -> str | None:
    """Вставить new отдельным абзацем после абзаца, где стоит after; не нашёлся — None."""
    span = _locate(text, after)
    if not span:
        return None
    end = text.find("\n\n", span[1])
    end = len(text) if end < 0 else end
    return text[:end].rstrip() + "\n\n" + new.strip() + "\n\n" + text[end:].lstrip("\n")


def _parse_edits(raw: str) -> list | None:
    """Список правок из ответа редактора; не разобран — None."""
    from .pipeline_llm import parse_json
    try:
        data = parse_json(raw)
    except Exception:
        return None
    edits = data if isinstance(data, list) else data.get("edits") if isinstance(data, dict) else None
    return edits if isinstance(edits, list) else None


def point_edit(text: str, critique: str, task: str, api_call_fn: Callable[[str], str]) -> dict:
    """
    → {text, applied, failed, changed}. Модель не дала правок или ответ не
    разобран — текст как был (failed объясняет почему).
    """
    from .continuity_fix import apply_edits, changed_share
    prompt = _PROMPT.format(task=(task or "").strip() or "—", critique=critique.strip(),
                            text=text, max_edits=POINT_EDITS_MAX, insert_max=INSERT_WORDS_MAX)
    raw = api_call_fn(prompt)
    edits = _parse_edits(raw)
    if edits is None:
        # Один повтор: на книге 18.10 (гл.3, Sonnet) неразобранный ответ
        # оставил круг без правок, а судья снизил главу за «нет редактуры»
        raw = api_call_fn(prompt)
        edits = _parse_edits(raw)
    if edits is None:
        head = " ".join(str(raw or "").split())[:160]
        return {"text": text, "applied": [], "changed": 0.0,
                "failed": [{"why": f"ответ редактора не разобран (дважды): «{head}»"}]}
    edits = [e for e in edits if isinstance(e, dict)][:POINT_EDITS_MAX]
    replaces = [e for e in edits if not e.get("after")]
    inserts = [e for e in edits if e.get("after")]
    out, applied, failed = apply_edits(text, replaces)
    for e in inserts:
        new = str(e.get("new") or "").strip()
        if not new:
            failed.append(dict(e, why="пустая вставка"))
            continue
        if len(new.split()) > INSERT_WORDS_MAX:
            new = " ".join(new.split()[:INSERT_WORDS_MAX])
            new = new[:new.rfind(".") + 1] or new
        got = _insert_after(out, str(e["after"]), new)
        if got is None:
            failed.append(dict(e, why="место вставки не найдено в главе"))
        else:
            out = got
            applied.append(dict(e, way="insert"))
    out = re.sub(r"\n{3,}", "\n\n", out)
    return {"text": out, "applied": applied, "failed": failed,
            "changed": round(changed_share(text, out), 3)}
