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


def generate_l3_summary(project_id: int, chapter_num: int,
                         chapter_text: str, api_call_fn) -> dict | None:
    """
    Сгенерировать и сохранить L3-саммари главы.

    api_call_fn — функция (prompt: str) -> str, вызывающая дешёвую модель.
    Возвращает словарь саммари или None при ошибке.
    """
    if not chapter_text or len(chapter_text.strip()) < 100:
        return None

    # Берём не больше 6000 символов (~1500 токенов) — достаточно для саммари
    text_sample = chapter_text[:6000]
    if len(chapter_text) > 6000:
        # Добавляем хвост — финал главы важен для promises
        text_sample += "\n...\n" + chapter_text[-1500:]

    prompt = SUMMARY_PROMPT.format(
        chapter_num=chapter_num,
        chapter_text=text_sample
    )

    try:
        raw = api_call_fn(prompt)
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not match:
            return None

        summary = json.loads(match.group())
        # Проверяем наличие нужных полей
        for key in ("events", "characters", "conflicts", "promises", "mood"):
            if key not in summary:
                summary[key] = [] if key == "promises" else ""

        # Нормализуем promises в структурированный формат
        summary["promises"] = normalize_promises(summary["promises"], chapter_num)

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
