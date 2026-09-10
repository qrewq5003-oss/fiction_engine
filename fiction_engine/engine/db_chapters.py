"""
db_chapters.py — главы, история генераций, анализ глав, оценки.
"""

import json
from .db_core import get_conn
from .error_policy import error_boundary, handle_error, ErrorLevel


# ─── Главы ───────────────────────────────────────────────────────────────────

# created_at имеет секундную точность: две записи, сделанные подряд,
# получают одинаковую метку, и порядок между ними становится
# произвольным. id (AUTOINCREMENT) даёт устойчивый вторичный ключ —
# без него «последнее обновление» и «свежие правки» врали при любой
# паре записей внутри одной секунды.
def save_chapter(project_id: int, number: int, content: str, title: str = "") -> int:
    words = len(content.split())
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO chapters (project_id, number, title, content, word_count)
               VALUES (?,?,?,?,?)
               ON CONFLICT(project_id, number) DO UPDATE SET
                 title=excluded.title, content=excluded.content,
                 word_count=excluded.word_count""",
            (project_id, number, title, content, words)
        )
        return cur.lastrowid


def get_chapter(project_id: int, number: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM chapters WHERE project_id=? AND number=?",
            (project_id, number)
        ).fetchone()
        return dict(row) if row else None


def get_chapters(project_id: int):
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, number, title, word_count, created_at FROM chapters "
            "WHERE project_id=? ORDER BY number", (project_id,)
        ).fetchall()]


def get_last_chapters_content(project_id: int, n: int = 2) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT number, content FROM chapters WHERE project_id=? "
            "ORDER BY number DESC LIMIT ?", (project_id, n)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]


# ─── История генераций ────────────────────────────────────────────────────────

@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=False)
def save_generation_score(gen_id: int, score: float, details: dict) -> bool:
    with get_conn() as conn:
        conn.execute(
            "UPDATE generation_history SET score=?, score_details=? WHERE id=?",
            (score, json.dumps(details, ensure_ascii=False), gen_id)
        )
    return True


def save_chapter_score(project_id: int, chapter_num: int, details: dict) -> bool:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chapter_scores (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                chapter_num INTEGER NOT NULL,
                total       REAL,
                details     TEXT,
                scored_at   TEXT,
                UNIQUE(project_id, chapter_num)
            )
        """)
        conn.execute(
            """INSERT OR REPLACE INTO chapter_scores
               (project_id, chapter_num, total, details, scored_at)
               VALUES (?,?,?,?,datetime('now'))""",
            (project_id, chapter_num,
             details.get("total"), json.dumps(details, ensure_ascii=False))
        )
    return True


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=[])
def get_generation_history(project_id: int, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, chapter_num, model, mode, word_count, created_at,
                      substr(task, 1, 80) as task_preview
               FROM generation_history
               WHERE project_id=?
               ORDER BY created_at DESC, id DESC LIMIT ?""",
            (project_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
def get_generation_by_id(gen_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM generation_history WHERE id=?", (gen_id,)
        ).fetchone()
    return dict(row) if row else None


def init_generation_history(): pass  # таблица создаётся в db_core.init_db()


# ─── Анализ глав ─────────────────────────────────────────────────────────────

def _parse_analysis_row(d: dict) -> dict:
    """Десериализовать JSON-поля анализа главы."""
    for key in ("arc_progress", "plot_threads"):
        try:
            d[key] = json.loads(d.get(key) or "{}")
        except Exception:
            d[key] = {}
    for key in ("character_deltas", "opened_promises", "closed_promises",
                "causal_chains", "logical_gaps"):
        try:
            d[key] = json.loads(d.get(key) or "[]")
        except Exception:
            d[key] = []
    return d


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=False)
def save_chapter_analysis(project_id: int, chapter_num: int, data: dict) -> bool:
    with get_conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO chapter_analysis
            (project_id, chapter_num, arc_progress, character_deltas,
             opened_promises, closed_promises, causal_chains, logical_gaps,
             conflict_score, pacing_note, opening_type, closing_type,
             plot_threads, analysis_quality, raw_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            project_id, chapter_num,
            json.dumps(data.get("arc_progress", {}),       ensure_ascii=False),
            json.dumps(data.get("character_deltas", []),   ensure_ascii=False),
            json.dumps(data.get("opened_promises", []),    ensure_ascii=False),
            json.dumps(data.get("closed_promises", []),    ensure_ascii=False),
            json.dumps(data.get("causal_chains", []),      ensure_ascii=False),
            json.dumps(data.get("logical_gaps", []),       ensure_ascii=False),
            float(data.get("conflict_score", 0.0)),
            data.get("pacing_note", ""),
            data.get("opening_type", ""),
            data.get("closing_type", ""),
            json.dumps(data.get("plot_threads", {}),       ensure_ascii=False),
            data.get("analysis_quality", "ok"),
            json.dumps(data, ensure_ascii=False)[:8000],
        ))
    return True


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
def get_chapter_analysis(project_id: int, chapter_num: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM chapter_analysis WHERE project_id=? AND chapter_num=?",
            (project_id, chapter_num)
        ).fetchone()
    if not row:
        return None
    return _parse_analysis_row(dict(row))


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=[])
def get_analyses_range(project_id: int, from_chapter: int, to_chapter: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
        SELECT * FROM chapter_analysis
        WHERE project_id=? AND chapter_num BETWEEN ? AND ?
        ORDER BY chapter_num
        """, (project_id, from_chapter, to_chapter)).fetchall()
    return [_parse_analysis_row(dict(row)) for row in rows]


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=[])
def get_all_logical_gaps(project_id: int, before_chapter: int) -> list[dict]:
    """Все незакрытые логические разрывы до указанной главы."""
    with get_conn() as conn:
        rows = conn.execute("""
        SELECT chapter_num, logical_gaps FROM chapter_analysis
        WHERE project_id=? AND chapter_num < ? AND logical_gaps != '[]'
        ORDER BY chapter_num DESC LIMIT 10
        """, (project_id, before_chapter)).fetchall()
    result = []
    for row in rows:
        try:
            gaps = json.loads(row["logical_gaps"] or "[]")
            if gaps:
                result.append({"chapter_num": row["chapter_num"], "gaps": gaps})
        except Exception as e:
            handle_error(f"get_all_logical_gaps: bad JSON in ch{row['chapter_num']}", e,
                         level=ErrorLevel.RECOVERABLE)
    return result


# ─── История оценок судьи (пункт 3: score calibration) ───────────────────────

@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=[])
def get_judge_score_history(project_id: int, n: int = 10) -> list[dict]:
    """
    Последние n финальных оценок judge по проекту (по одной на главу — лучшая).
    Используется в step_judge чтобы дать судье контекст: «38/50 — выше среднего».
    """
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT r.chapter_num, MAX(i.score) AS score
            FROM pipeline_iterations i
            JOIN pipeline_runs r ON i.run_id = r.id
            WHERE r.project_id = ? AND i.stage = 'judge' AND i.score IS NOT NULL
            GROUP BY r.chapter_num
            ORDER BY r.chapter_num DESC
            LIMIT ?
        """, (project_id, n)).fetchall()
    return [dict(r) for r in rows]


def format_score_history(history: list[dict], current_chapter: int) -> str:
    """
    Форматирует историю оценок в строку для промпта судьи.
    Пример: «Средний score за 8 глав: 34.2. Лучший: 42 (гл.7). Последний: 36 (гл.11).»
    """
    if not history:
        return ""
    scores = [h["score"] for h in history if h["score"] is not None]
    if not scores:
        return ""
    avg   = round(sum(scores) / len(scores), 1)
    best  = max(history, key=lambda h: h["score"] or 0)
    last  = min(history, key=lambda h: h["chapter_num"])  # DESC → последняя глава = min chapter_num в выборке
    parts = [f"Средний score проекта за {len(scores)} гл.: {avg}/50."]
    parts.append(f"Лучший: {best['score']}/50 (гл.{best['chapter_num']}).")
    if last["chapter_num"] != best["chapter_num"]:
        parts.append(f"Последний: {last['score']}/50 (гл.{last['chapter_num']}).")
    return " ".join(parts)


# ─── Правки автора — DATA_DRIVEN_LEARNING (пункт 2) ──────────────────────────

@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=False)
def save_author_edit(
    project_id: int, chapter_num: int, run_id: int,
    original_text: str, accepted_text: str,
    action: str = "accept",
    rejection_reason: str = "",
    judge_score: float = None,
) -> bool:
    """
    Сохранить факт принятия/отклонения итерации pipeline.

    action:
      'accept'      — пользователь принял текст как есть
      'reject'      — отклонил, переделал вручную
      'manual_edit' — принял с правками (original != accepted)

    Через 20+ глав по этой таблице можно извлекать паттерны:
    «что автор систематически убирает, что добавляет».
    """
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO author_edits
                (project_id, chapter_num, run_id, original_text, accepted_text,
                 action, rejection_reason, judge_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (project_id, chapter_num, run_id,
              original_text, accepted_text,
              action, rejection_reason, judge_score))
    return True


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback="")
def get_author_edit_patterns(project_id: int, n: int = 20) -> str:
    """
    Возвращает сырые данные последних n правок в виде строки для LLM-анализа.
    Вызывать по запросу автора: «покажи паттерны моих правок».
    Не используется автоматически — слишком большой контекст.
    """
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT chapter_num, action, rejection_reason, judge_score
            FROM author_edits
            WHERE project_id = ?
            ORDER BY created_at DESC, id DESC LIMIT ?
        """, (project_id, n)).fetchall()
    if not rows:
        return ""
    lines = [f"Гл.{r['chapter_num']} [{r['action']}] score={r['judge_score']} — {r['rejection_reason'] or '—'}"
             for r in rows]
    return "\n".join(lines)


# ─── Калибровка судьи — Eval Layer ───────────────────────────────────────────

@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=False)
def save_judge_calibration(
    project_id: int,
    chapter_num: int,
    judge_score: float,
    author_score: float,
    note: str = "",
) -> bool:
    """
    Сохранить коррекцию автора к оценке судьи.

    Вызывается из web-endpoint когда автор вручную ставит свою оценку главе.
    Накопленные данные используются в get_judge_calibration_hint():
    судье говорят «ты обычно завышаешь на +3.2 пункта».
    """
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS judge_calibration (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                chapter_num  INTEGER NOT NULL,
                judge_score  REAL NOT NULL,
                author_score REAL NOT NULL,
                delta        REAL GENERATED ALWAYS AS (author_score - judge_score) VIRTUAL,
                note         TEXT DEFAULT '',
                created_at   TEXT DEFAULT (datetime('now')),
                UNIQUE(project_id, chapter_num)
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO judge_calibration
                (project_id, chapter_num, judge_score, author_score, note)
            VALUES (?, ?, ?, ?, ?)
        """, (project_id, chapter_num, judge_score, author_score, note))
    return True


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback="")
def get_judge_calibration_hint(project_id: int, min_samples: int = 3) -> str:
    """
    Возвращает строку-подсказку для SYS_JUDGE на основе накопленных коррекций.

    Нужно минимум min_samples коррекций чтобы вывод был значимым.

    Примеры возвращаемых строк:
    - «Твои оценки обычно завышены на +3.2 пункта по сравнению с авторской оценкой.
       Учти это при выставлении ИТОГ.»
    - «Твои оценки точны (среднее отклонение: +0.8).»
    """
    with get_conn() as conn:
        # Проверяем существование таблицы
        tbl = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='judge_calibration'"
        ).fetchone()
        if not tbl:
            return ""

        rows = conn.execute("""
            SELECT judge_score, author_score
            FROM judge_calibration
            WHERE project_id = ?
            ORDER BY chapter_num DESC
            LIMIT 20
        """, (project_id,)).fetchall()

    if len(rows) < min_samples:
        return ""

    deltas = [r["author_score"] - r["judge_score"] for r in rows]
    avg_delta = sum(deltas) / len(deltas)
    abs_avg   = abs(avg_delta)

    if abs_avg < 1.5:
        return f"Твои оценки точны (среднее отклонение от авторской: {avg_delta:+.1f} пункта)."

    direction = "занижены" if avg_delta > 0 else "завышены"
    return (
        f"Внимание: твои оценки обычно {direction} на {abs_avg:.1f} пункта "
        f"по сравнению с авторской оценкой (на основе {len(rows)} глав). "
        f"Скорректируй ИТОГ соответственно."
    )

@error_boundary(level=ErrorLevel.RECOVERABLE, fallback="")
def check_structural_monotony(project_id: int, before_chapter: int, window: int = 8) -> str:
    """
    Проверяет последние `window` глав на повторяющиеся opening/closing паттерны.
    Возвращает предупреждение если > 60% глав открываются или закрываются одинаково.

    Вызывать в narrative_intelligence или prevalidation.
    """
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT chapter_num, opening_type, closing_type
            FROM chapter_analysis
            WHERE project_id = ? AND chapter_num < ?
              AND (opening_type != '' OR closing_type != '')
            ORDER BY chapter_num DESC LIMIT ?
        """, (project_id, before_chapter, window)).fetchall()

    if len(rows) < 4:
        return ""  # Недостаточно данных

    warnings = []
    from collections import Counter

    openings = [r["opening_type"] for r in rows if r["opening_type"]]
    if len(openings) >= 3:
        top_open, count_open = Counter(openings).most_common(1)[0]
        if count_open / len(openings) >= 0.6:
            warnings.append(
                f"⚠ Монотонность: {count_open} из {len(openings)} последних глав "
                f"открываются через «{top_open}»"
            )

    closings = [r["closing_type"] for r in rows if r["closing_type"]]
    if len(closings) >= 3:
        top_close, count_close = Counter(closings).most_common(1)[0]
        if count_close / len(closings) >= 0.6:
            warnings.append(
                f"⚠ Монотонность: {count_close} из {len(closings)} последних глав "
                f"заканчиваются через «{top_close}»"
            )

    return "\n".join(warnings)


# ─── Judge threshold calibration по проекту (IDEA 5) ─────────────────────────

@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
def get_project_accept_threshold(project_id: int, min_accepted: int = 5) -> dict | None:
    """
    Вычисляет проектный порог принятия и накопленный bias судьи.

    Требует минимум min_accepted принятых глав — при меньшем числе
    данных недостаточно для стабильных выводов.

    Возвращает:
        {
            "threshold":     float,  # медиана judge_score принятых глав
            "judge_bias":    float,  # среднее (judge_score - threshold)
            "accepted_count": int,
        }
        или None если данных недостаточно.
    """
    from .db_core import get_conn
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT pi.score
            FROM pipeline_runs pr
            JOIN pipeline_iterations pi ON pi.run_id = pr.id
            WHERE pr.project_id = ?
              AND pr.status     = 'accepted'
              AND pi.stage      = 'judge'
              AND pi.score      IS NOT NULL
            ORDER BY pr.id DESC
            LIMIT 20
        """, (project_id,)).fetchall()

    if not rows or len(rows) < min_accepted:
        return None

    scores = sorted(r["score"] for r in rows)
    n = len(scores)
    # Медиана
    mid = n // 2
    median = scores[mid] if n % 2 else (scores[mid - 1] + scores[mid]) / 2

    avg = sum(scores) / n
    bias = round(avg - median, 1)

    return {
        "threshold":      round(median, 1),
        "judge_bias":     bias,
        "accepted_count": n,
    }


def format_project_threshold_hint(threshold_data: dict | None) -> str:
    """
    Форматирует подсказку для SYS_JUDGE на основе get_project_accept_threshold().

    Возвращает пустую строку если данных нет.
    """
    if not threshold_data:
        return ""

    t   = threshold_data["threshold"]
    b   = threshold_data["judge_bias"]
    cnt = threshold_data["accepted_count"]
    accept_floor = max(t - 3.0, 30.0)

    hint = (
        f"СТАНДАРТ ПРОЕКТА (на основе {cnt} принятых глав): "
        f"средний принятый балл — {t}/50. "
        f"Если текущая глава набирает ≥ {accept_floor:.0f} — это приемлемый результат для этого проекта."
    )
    if abs(b) >= 1.5:
        direction = "занижаешь" if b > 0 else "завышаешь"
        hint += f" Внимание: ты систематически {direction} оценки на {abs(b):.1f} пункта."

    return hint
