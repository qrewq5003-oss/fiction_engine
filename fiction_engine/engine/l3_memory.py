"""
L3 Memory — автоматические саммари глав для длинных серий.

Логика:
  1. После сохранения главы вызывается generate_l3_summary()
  2. Дешёвая модель сжимает главу в структурированный JSON
  3. При следующей генерации get_l3_context() подгружает последние 3 саммари
     вместо сырых глав — экономим токены, сохраняем связность

Формат саммари:
  events     — что произошло (1-3 предложения)
  characters — изменения в персонажах (кратко)
  conflicts  — активные конфликты (что открылось / что обострилось)
  promises   — сюжетные обещания читателю (setup без payoff)
  mood       — тональность главы (одно слово или короткая фраза)
"""

import json
import re
from .db import save_l3_summary, get_l3_summaries, get_l3_summary
from .logger import get_logger

log = get_logger(__name__)

# Сколько токенов нужно саммари, чтобы уместиться целиком.
#
# Раньше вызыватель давал всем вспомогательным задачам плоские 400. Замер
# на живом прогоне 2026-09-12 (глава 3, 5 попыток подряд через /api/l3/N/
# generate): при 400 ответ обрывался со stop_reason='max_tokens' посреди
# строки, `{.*}` захватывал огрызок, json.loads падал — 5 отказов из 5.
# При 1500 — stop_reason='end_turn' и целый JSON. Пять полей плюс массив
# promises по-русски в 400 токенов физически не помещаются.
SUMMARY_MAX_TOKENS = 1500


SUMMARY_PROMPT = """Ты помогаешь писателю отслеживать длинную серию.
Прочитай текст главы и создай структурированное саммари для памяти.

ТЕКСТ ГЛАВЫ {chapter_num}:
{chapter_text}

Ответь ТОЛЬКО валидным JSON (без markdown, без пояснений):
{{
  "events": "Что произошло. 1-3 предложения максимум.",
  "characters": "Изменения в персонажах: кто что узнал, как изменился, важные решения.",
  "conflicts": "Активные конфликты: что обострилось, что открылось, что осталось висеть.",
  "promises": [
    {{"id": "{chapter_num}_0", "text": "Первое сюжетное обещание: setup без payoff.", "resolved": false, "resolved_chapter": null}},
    {{"id": "{chapter_num}_1", "text": "Второе обещание если есть.", "resolved": false, "resolved_chapter": null}}
  ],
  "mood": "Тональность одним словом или короткой фразой: например 'тревожное', 'нежное с тенью угрозы'."
}}

Поле promises — список объектов. Если обещаний нет — пустой список [].
Каждый id уникален: номер_главы_порядковый_номер (например {chapter_num}_0, {chapter_num}_1)."""


def normalize_promises(raw, chapter_num: int) -> list[dict]:
    """
    Нормализует поле promises в единый формат списка объектов.

    Поддерживает два формата:
    - Новый: список [{id, text, resolved, resolved_chapter}]
    - Старый (legacy): строка — конвертируется в список с одним элементом

    Используется при чтении старых саммари и при генерации новых.
    """
    if isinstance(raw, list):
        result = []
        for i, item in enumerate(raw):
            if isinstance(item, dict) and item.get("text", "").strip():
                result.append({
                    "id":               item.get("id", f"{chapter_num}_{i}"),
                    "text":             item["text"].strip(),
                    "resolved":         bool(item.get("resolved", False)),
                    "resolved_chapter": item.get("resolved_chapter"),
                })
        return result
    if isinstance(raw, str) and raw.strip():
        return [{
            "id":               f"{chapter_num}_0",
            "text":             raw.strip(),
            "resolved":         False,
            "resolved_chapter": None,
        }]
    return []


def get_active_promises(promises: list[dict]) -> list[dict]:
    """Возвращает только незакрытые обещания."""
    return [p for p in promises if not p.get("resolved", False)]


def mark_promise_resolved(
    project_id: int,
    promise_id: str,
    resolved_chapter: int,
) -> bool:
    """
    Отметить обещание как выполненное.

    Находит саммари главы по promise_id (формат "chapter_num_index"),
    обновляет поле resolved и resolved_chapter, сохраняет обратно.

    Возвращает True если обещание найдено и обновлено.
    """
    try:
        chapter_num = int(promise_id.split("_")[0])
    except (ValueError, IndexError):
        return False

    summary = get_l3_summary(project_id, chapter_num)
    if not summary:
        return False

    promises = normalize_promises(summary.get("promises", []), chapter_num)
    updated = False
    for p in promises:
        if p["id"] == promise_id and not p["resolved"]:
            p["resolved"]         = True
            p["resolved_chapter"] = resolved_chapter
            updated = True
            break

    if updated:
        summary["promises"] = promises
        save_l3_summary(project_id, chapter_num, summary)

    return updated


# ─── Закрытия обещаний поздними главами ──────────────────────────────────────
#
# Отметка «обещание закрыто главой M» живёт в L3 главы-источника N. Новый L3
# главы N (пересчёт, «Принять» поверх, кнопка L3) писал все её обещания
# открытыми, и поздние главы их заново не закрывали: писателю гл.25 «Фона»
# вернулись бы обещания, закрытые давно, — 38 из 148 (разбор 21.10). Перед
# удалением L3 главы закрытия поздними главами откладываются
# (stash_later_closures), новый L3 сверяется с ними по тексту.

CLOSURE_MATCH = 0.6     # доля общих слов, при которой новое обещание — то же, что прежнее


def _ensure_closures() -> None:
    from .db_core import get_conn
    with get_conn() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS promise_closures (
            project_id INTEGER NOT NULL, source_chapter INTEGER NOT NULL,
            text TEXT NOT NULL, resolved_chapter INTEGER NOT NULL)""")


def _later_closures(promises: list[dict], chapter_num: int) -> list[tuple[str, int]]:
    return [(p["text"], int(p["resolved_chapter"])) for p in promises
            if p.get("resolved") and p.get("resolved_chapter") and int(p["resolved_chapter"]) > chapter_num]


def stash_later_closures(project_id: int, chapter_num: int) -> int:
    """Отложить закрытия обещаний главы поздними главами — перед удалением её L3."""
    summary = get_l3_summary(project_id, chapter_num)
    found = _later_closures(normalize_promises((summary or {}).get("promises", []), chapter_num), chapter_num)
    if not found:
        return 0
    _ensure_closures()
    from .db_core import get_conn
    with get_conn() as conn:
        conn.executemany("INSERT INTO promise_closures VALUES (?,?,?,?)",
                         [(project_id, chapter_num, t, r) for t, r in found])
    return len(found)


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w{4,}", (text or "").lower().replace("ё", "е")))


def carry_later_closures(project_id: int, chapter_num: int, promises: list[dict]) -> int:
    """
    Новым обещаниям главы — прежние отметки «закрыто главой M» (M > главы):
    из её прежнего L3 и отложенных (stash_later_closures). Сверка по словам:
    модель формулирует обещание каждый раз немного иначе. → сколько перенесено.
    """
    old = _later_closures(normalize_promises((get_l3_summary(project_id, chapter_num) or {}).get("promises", []),
                                             chapter_num), chapter_num)
    _ensure_closures()
    from .db_core import get_conn
    with get_conn() as conn:
        old += [(r[0], r[1]) for r in conn.execute(
            "SELECT text, resolved_chapter FROM promise_closures WHERE project_id=? AND source_chapter=?",
            (project_id, chapter_num))]
        conn.execute("DELETE FROM promise_closures WHERE project_id=? AND source_chapter=?",
                     (project_id, chapter_num))
    n = 0
    for text, by in old:
        w = _words(text)
        best = max((p for p in promises if not p.get("resolved")),
                   key=lambda p: len(w & _words(p["text"])) / max(1, len(w | _words(p["text"]))), default=None)
        if best and len(w & _words(best["text"])) / max(1, len(w | _words(best["text"]))) >= CLOSURE_MATCH:
            best["resolved"], best["resolved_chapter"] = True, by
            n += 1
    return n


def reopen_promises(project_id: int, resolved_chapter: int) -> int:
    """
    Снова открыть обещания, которые закрыла глава resolved_chapter, — при её
    откате. Обещания живут в L3 глав-источников, удаление главы их не трогало:
    после отката писатель не видел обещания, которое так и не выполнено.
    """
    from .db_narrative import get_l3_summaries
    n = 0
    for summary in get_l3_summaries(project_id, resolved_chapter, n=10_000):
        ch = summary["chapter_num"]
        promises = normalize_promises(summary.get("promises", []), ch)
        hit = [p for p in promises if p["resolved"] and p.get("resolved_chapter") == resolved_chapter]
        for p in hit:
            p["resolved"], p["resolved_chapter"] = False, None
        if hit:
            save_l3_summary(project_id, ch, dict(summary, promises=promises))
            n += len(hit)
    return n


def _truncation_reason() -> str:
    """Пояснение к отказу, если ответ упёрся в потолок токенов."""
    try:
        from .api import get_last_stop_reason
        if get_last_stop_reason() in ("max_tokens", "length"):
            return (f" — ответ модели оборван лимитом токенов "
                    f"(бюджет {SUMMARY_MAX_TOKENS}); саммари не поместилось")
    except Exception:
        pass
    return ""


def _parse_summary_json(raw: str) -> dict | None:
    """
    Разбор JSON из ответа модели.

    Своей регулярки здесь больше нет. `{.*}` жадно хватала от первой
    скобки до последней и на обрезанном ответе отдавала огрызок, который
    json.loads отвергал. Терпимый разбор — снятие ```json-обрамления,
    <think>-блоков и поиск по балансу скобок — уже написан в
    pipeline_llm.parse_json; вторая, более слабая копия рядом с ним
    ровно тем и опасна, что чинят обычно одну.
    """
    from .pipeline_llm import parse_json
    data = parse_json(raw)
    return data if isinstance(data, dict) and data else None


def generate_l3_summary(project_id: int, chapter_num: int,
                         chapter_text: str, api_call_fn) -> dict | None:
    """
    Сгенерировать и сохранить L3-саммари главы.

    api_call_fn — функция (prompt: str) -> str, вызывающая дешёвую модель.
    Возвращает словарь саммари или None при ошибке.
    """
    if not chapter_text or len(chapter_text.strip()) < 100:
        return None

    # Глава целиком. Было: первые 6000 символов и последние 1500 — «достаточно
    # для саммари». Глава 1 автора 17.10 — 18 тыс. символов: середина (гибель
    # всей команды, разговор, где Павел дочитывает сообщение) до модели не
    # доходила, и Haiku, и Sonnet писали «судьба сотрудников неясна».
    # Потолок — предохранитель от вырожденного ответа, тот же, что у критика.
    from .pipeline_config import CRITIC_TEXT_LIMIT
    text_sample = chapter_text[:CRITIC_TEXT_LIMIT]

    prompt = SUMMARY_PROMPT.format(
        chapter_num=chapter_num,
        chapter_text=text_sample
    )

    try:
        raw = api_call_fn(prompt)

        summary = _parse_summary_json(raw)
        if summary is None and not _truncation_reason():
            # Один повтор: брак JSON бывает случайным — у книги на Sonnet
            # 18.10 L3 главы 12 не разобрался, тот же запрос вторым разом
            # дал чистый JSON. Без повтора глава оставалась без памяти серии.
            # Обрыв по лимиту повтором не лечится — его не повторяем
            log.warning("generate_l3_summary: ответ не разобран, повтор",
                        project_id=project_id, chapter_num=chapter_num)
            raw = api_call_fn(prompt)
            summary = _parse_summary_json(raw)
        if summary is None:
            # Обрыв по лимиту токенов и брак модели выглядят одинаково —
            # оба дают нерабочий JSON. Причину система знает: stop_reason
            # захватывается при вызове. Не сказать её — значит отправить
            # автора искать несуществующую проблему в тексте главы.
            reason = _truncation_reason()
            log.error("generate_l3_summary: ответ не разобран" + reason,
                      project_id=project_id, chapter_num=chapter_num)
            return None
        # Проверяем наличие нужных полей
        for key in ("events", "characters", "conflicts", "promises", "mood"):
            if key not in summary:
                summary[key] = [] if key == "promises" else ""

        # Нормализуем promises в структурированный формат
        summary["promises"] = normalize_promises(summary["promises"], chapter_num)
        # Обещания этой главы, закрытые поздними главами, — закрытыми и остаются
        carry_later_closures(project_id, chapter_num, summary["promises"])

        save_l3_summary(project_id, chapter_num, summary)
        return summary

    except Exception as e:
        log.error("generate_l3_summary failed", exc=e, project_id=project_id, chapter_num=chapter_num)
        return None


def get_l3_context(project_id: int, before_chapter: int, n: int = 3) -> str:
    """
    Сформировать контекстный блок из L3-саммари для вставки в промпт.

    Используется в _build_context() вместо или вместе с raw-текстами глав.
    Возвращает пустую строку если саммари нет.
    """
    summaries = get_l3_summaries(project_id, before_chapter, n)
    if not summaries:
        return ""

    lines = ["ПАМЯТЬ СЕРИИ (L3 — автосаммари предыдущих глав):"]

    for s in summaries:
        ch = s["chapter_num"]
        lines.append(f"\n[Глава {ch}]")
        if s.get("events"):
            lines.append(f"  События: {s['events']}")
        if s.get("characters"):
            lines.append(f"  Персонажи: {s['characters']}")
        if s.get("conflicts"):
            lines.append(f"  Конфликты: {s['conflicts']}")
        promises = normalize_promises(s.get("promises", []), ch)
        active   = get_active_promises(promises)
        if active:
            texts = "; ".join(p["text"] for p in active)
            lines.append(f"  Обещания сюжета: {texts}")
        if s.get("mood"):
            lines.append(f"  Тональность: {s['mood']}")

    return "\n".join(lines)


def has_l3_summary(project_id: int, chapter_num: int) -> bool:
    return get_l3_summary(project_id, chapter_num) is not None


# ─── Batch L3 — пакетная генерация для импортированных проектов ──────────────

def batch_generate_l3(
    project_id: int,
    api_call_fn,
    chapter_nums: list[int] | None = None,
    progress_callback=None,
) -> dict:
    """
    Генерирует L3-саммари для всех глав у которых его нет.

    Параметры:
        project_id        — ID проекта
        api_call_fn       — fn(prompt: str) -> str, вызов дешёвой модели
        chapter_nums      — конкретные номера глав (None = все без саммари)
        progress_callback — fn(current: int, total: int, chapter_num: int)

    Возвращает:
        {
            "generated": [1, 2, 3],   # успешно сгенерировано
            "skipped":   [4, 5],      # уже были саммари или пустые главы
            "failed":    [6],         # ошибка при генерации
        }
    """
    from .db import get_chapters, get_chapter

    all_chapters = get_chapters(project_id)
    if not all_chapters:
        return {"generated": [], "skipped": [], "failed": []}

    if chapter_nums is not None:
        target_set = set(chapter_nums)
        all_chapters = [c for c in all_chapters if c["number"] in target_set]

    generated, skipped, failed = [], [], []

    for idx, chapter in enumerate(all_chapters):
        ch_num       = chapter["number"]
        full_chapter = get_chapter(project_id, ch_num)
        content      = full_chapter.get("content", "") if full_chapter else ""

        if has_l3_summary(project_id, ch_num):
            skipped.append(ch_num)
            continue

        if not content or len(content.strip()) < 100:
            skipped.append(ch_num)
            continue

        if progress_callback:
            progress_callback(idx, len(all_chapters), ch_num)

        try:
            result = generate_l3_summary(project_id, ch_num, content, api_call_fn)
            if result:
                generated.append(ch_num)
            else:
                failed.append(ch_num)
        except Exception as e:
            log.error("batch_generate_l3 chapter failed",
                      exc=e, project_id=project_id, chapter_num=ch_num)
            failed.append(ch_num)

    return {"generated": generated, "skipped": skipped, "failed": failed}
