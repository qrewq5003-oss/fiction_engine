"""
db_narrative.py — нарративные данные проекта.

Ответственность: символы, голосовые профили, L3-память,
дрейф голоса, pipeline, база знаний, эталоны, режиссёрские заметки.
"""

import json
from .db_core import get_conn
from .error_policy import error_boundary, ErrorLevel


# ─── Символы ─────────────────────────────────────────────────────────────────

# created_at имеет секундную точность: две записи, сделанные подряд,
# получают одинаковую метку, и порядок между ними становится
# произвольным. id (AUTOINCREMENT) даёт устойчивый вторичный ключ —
# без него «последнее обновление» и «свежие правки» врали при любой
# паре записей внутри одной секунды.
def _parse_symbol(row) -> dict:
    d = dict(row)
    try:
        d["appearances"] = json.loads(d["appearances"])
    except Exception:
        d["appearances"] = []
    try:
        d["planned"] = json.loads(d["planned"])
    except Exception:
        d["planned"] = []
    return d


def get_symbols(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM symbols WHERE project_id=? ORDER BY introduced_ch, id",
            (project_id,)
        ).fetchall()
    return [_parse_symbol(r) for r in rows]


def save_symbol(project_id: int, name: str, symbol_type: str,
                introduced_ch: int, initial_meaning: str,
                related_chars: str = "", notes: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute("""
            INSERT INTO symbols
            (project_id, name, symbol_type, introduced_ch,
             initial_meaning, related_chars, notes)
            VALUES (?,?,?,?,?,?,?)
        """, (project_id, name, symbol_type, introduced_ch,
              initial_meaning, related_chars, notes))
        return cur.lastrowid


def add_symbol_appearance(project_id: int, symbol_id: int, chapter: int,
                          context: str, meaning: str) -> bool:
    """Дописать появление символа. Символ чужого проекта не трогаем.

    project_id обязателен и стоит первым намеренно: без него вызвать
    нельзя, а значит нельзя и забыть про проект. Раньше функция брала
    один symbol_id, и /symbols/appearance правил чужие символы.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT appearances FROM symbols WHERE id=? AND project_id=?",
            (symbol_id, project_id)
        ).fetchone()
        if not row:
            return False
        try:
            apps = json.loads(row["appearances"])
        except Exception:
            apps = []
        apps.append({"chapter": chapter, "context": context, "meaning": meaning})
        conn.execute(
            "UPDATE symbols SET appearances=? WHERE id=? AND project_id=?",
            (json.dumps(apps, ensure_ascii=False), symbol_id, project_id)
        )
        return True


def add_symbol_planned(project_id: int, symbol_id: int, chapter_approx: int,
                       how: str, meaning: str) -> bool:
    """Запланировать появление символа. Символ чужого проекта не трогаем."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT planned FROM symbols WHERE id=? AND project_id=?",
            (symbol_id, project_id)
        ).fetchone()
        if not row:
            return False
        try:
            planned = json.loads(row["planned"])
        except Exception:
            planned = []
        planned.append({"chapter": chapter_approx, "how": how, "meaning": meaning})
        conn.execute(
            "UPDATE symbols SET planned=? WHERE id=? AND project_id=?",
            (json.dumps(planned, ensure_ascii=False), symbol_id, project_id)
        )
        return True


def delete_symbol(project_id: int, symbol_id: int) -> bool:
    """Удалить символ проекта. Возвращает False, если символ не его."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM symbols WHERE id=? AND project_id=?",
                           (symbol_id, project_id))
        return cur.rowcount > 0


def get_symbols_context(project_id: int) -> str:
    symbols = get_symbols(project_id)
    if not symbols:
        return ""
    lines = ["СИМВОЛЫ И СКВОЗНЫЕ ОБРАЗЫ:"]
    for s in symbols:
        apps = s.get("appearances", [])
        last = apps[-1] if apps else None
        current_meaning = last["meaning"] if last else s["initial_meaning"]
        line = f"— {s['name']} ({s['symbol_type']}): {current_meaning}"
        if s.get("planned"):
            next_p = s["planned"][0]
            line += f" → запланировано гл.{next_p['chapter']}: {next_p['meaning']}"
        lines.append(line)
    return "\n".join(lines)


def init_symbol_tables(): pass  # таблицы создаются в db_core.init_db()


# ─── Голосовые профили ────────────────────────────────────────────────────────

def get_voice_profiles(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM voice_profiles WHERE project_id=? "
            "ORDER BY active DESC, created_at DESC, id DESC",
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def save_voice_profile(project_id: int, name: str, profile: str,
                       samples: str = "", source: str = "custom") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO voice_profiles (project_id, name, source, profile, samples)
               VALUES (?,?,?,?,?)""",
            (project_id, name, source, profile, samples)
        )
        return cur.lastrowid


def set_active_voice(project_id: int, profile_id: int | None):
    with get_conn() as conn:
        conn.execute("UPDATE voice_profiles SET active=0 WHERE project_id=?", (project_id,))
        if profile_id:
            conn.execute(
                "UPDATE voice_profiles SET active=1 WHERE id=? AND project_id=?",
                (profile_id, project_id)
            )


def get_active_voice(project_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM voice_profiles WHERE project_id=? AND active=1",
            (project_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_voice_profile(project_id: int, profile_id: int) -> bool:
    """Удалить профиль голоса проекта. False — профиль принадлежит другому."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM voice_profiles WHERE id=? AND project_id=?",
                           (profile_id, project_id))
        return cur.rowcount > 0


def init_voice_tables(): pass


# ─── L3 Memory ────────────────────────────────────────────────────────────────

@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=False)
def save_l3_summary(project_id: int, chapter_num: int, summary: dict) -> bool:
    with get_conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO l3_memory
            (project_id, chapter_num, events, characters, conflicts, promises, mood, raw_summary)
        VALUES (?,?,?,?,?,?,?,?)
        """, (
            project_id, chapter_num,
            summary.get("events", ""),
            summary.get("characters", ""),
            summary.get("conflicts", ""),
            (json.dumps(summary.get("promises", []), ensure_ascii=False)
             if isinstance(summary.get("promises"), list)
             else summary.get("promises", "")),
            summary.get("mood", ""),
            json.dumps(summary, ensure_ascii=False),
        ))
    return True


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=[])
def get_l3_summaries(project_id: int, before_chapter: int, n: int = 3) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
        SELECT * FROM l3_memory
        WHERE project_id=? AND chapter_num < ?
        ORDER BY chapter_num DESC LIMIT ?
        """, (project_id, before_chapter, n)).fetchall()
    result = []
    for r in reversed(rows):
        d = dict(r)
        raw_p = d.get("promises", "")
        if isinstance(raw_p, str) and raw_p.startswith("["):
            try:
                d["promises"] = json.loads(raw_p)
            except json.JSONDecodeError:
                # Старый формат — оставляем строкой, её разберёт
                # normalize_promises. Прочие ошибки не глотаем.
                pass
        result.append(d)
    return result


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback=None)
def get_l3_summary(project_id: int, chapter_num: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM l3_memory WHERE project_id=? AND chapter_num=?",
            (project_id, chapter_num)
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    # Десериализуем promises если это JSON-строка (список объектов)
    raw_p = result.get("promises", "")
    if isinstance(raw_p, str) and raw_p.startswith("["):
        try:
            result["promises"] = json.loads(raw_p)
        except json.JSONDecodeError:
            pass          # см. выше: legacy-формат остаётся строкой
    return result


def delete_l3_summary(project_id: int, chapter_num: int):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM l3_memory WHERE project_id=? AND chapter_num=?",
            (project_id, chapter_num)
        )


@error_boundary(level=ErrorLevel.RECOVERABLE, fallback={})
def get_l3_status(project_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT chapter_num, mood, created_at FROM l3_memory WHERE project_id=? ORDER BY chapter_num",
            (project_id,)
        ).fetchall()
    return {r["chapter_num"]: {"mood": r["mood"], "at": r["created_at"]} for r in rows}


def get_l3_active_promises(project_id: int, before_chapter: int, n: int = 5) -> str:
    """
    Поддерживает оба формата поля promises: новый (список) и legacy (строка).
    Показывает только незакрытые обещания.
    """
    from .l3_memory import normalize_promises, get_active_promises as _get_active

    summaries = get_l3_summaries(project_id, before_chapter, n)
    if not summaries:
        return ""

    lines = []
    for s in summaries:
        ch_num   = s["chapter_num"]
        raw      = s.get("promises", [])
        promises = normalize_promises(raw, ch_num)
        active   = _get_active(promises)
        for p in active:
            lines.append(f"Гл.{ch_num}: {p['text']}")

    if not lines:
        return ""
    return "АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ (setup без payoff из предыдущих глав):\n" + "\n".join(lines)


def init_l3_memory(): pass


# ─── Voice Drift ──────────────────────────────────────────────────────────────

def save_drift_check(project_id: int, chapter_num: int,
                     score: float, issues: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO voice_drift_log (project_id, chapter_num, score, issues)
               VALUES (?,?,?,?)""",
            (project_id, chapter_num, score, issues)
        )
        return cur.lastrowid


def get_last_drift_check(project_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM voice_drift_log WHERE project_id=?
               ORDER BY chapter_num DESC LIMIT 1""",
            (project_id,)
        ).fetchone()
    return dict(row) if row else None


def should_run_drift_check(project_id: int, current_chapter: int, every_n: int = 3) -> bool:
    last = get_last_drift_check(project_id)
    if not last:
        return current_chapter >= every_n
    return (current_chapter - last["chapter_num"]) >= every_n


def init_voice_drift_table(): pass


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def create_pipeline_run(project_id: int, chapter_num: int,
                        model_gen: str, model_critic: str,
                        model_editor: str, model_judge: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO pipeline_runs
               (project_id, chapter_num, status, model_gen, model_critic, model_editor, model_judge)
               VALUES (?,?,?,?,?,?,?)""",
            (project_id, chapter_num, 'running',
             model_gen, model_critic, model_editor, model_judge)
        )
        return cur.lastrowid


def save_pipeline_iteration(run_id: int, iteration: int, stage: str,
                             model_used: str, input_text: str,
                             output_text: str, score: float = None,
                             verdict: str = None) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO pipeline_iterations
               (run_id, iteration, stage, model_used, input_text, output_text, score, verdict)
               VALUES (?,?,?,?,?,?,?,?)""",
            (run_id, iteration, stage, model_used,
             input_text, output_text, score, verdict)
        )
        return cur.lastrowid


def get_pipeline_run(run_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM pipeline_runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None


def get_pipeline_iterations(run_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pipeline_iterations WHERE run_id=? ORDER BY iteration, id",
            (run_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def finish_pipeline_run(project_id: int, run_id: int, status: str = 'accepted') -> bool:
    """Закрыть запуск pipeline. Запуск чужого проекта не трогаем."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE pipeline_runs SET status=?, finished_at=datetime('now') "
            "WHERE id=? AND project_id=?",
            (status, run_id, project_id)
        )
    return cur.rowcount > 0


def get_pipeline_runs(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.*,
               (SELECT COUNT(*) FROM pipeline_iterations WHERE run_id=r.id AND stage='generate') as iterations
               FROM pipeline_runs r
               WHERE r.project_id=?
               ORDER BY r.created_at DESC, r.id DESC LIMIT 20""",
            (project_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def init_pipeline_tables(): pass


# ─── Режиссёрские заметки ─────────────────────────────────────────────────────

def save_director_note(project_id: int, after_chapter: int, note: str):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO director_notes (project_id, after_chapter, note)
               VALUES (?,?,?)
               ON CONFLICT(project_id, after_chapter) DO UPDATE SET
                 note=excluded.note,
                 created_at=datetime('now')""",
            (project_id, after_chapter, note)
        )


def get_director_note(project_id: int, for_chapter: int) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT note FROM director_notes WHERE project_id=? AND after_chapter=?",
            (project_id, for_chapter - 1)
        ).fetchone()
    return row["note"] if row else None


# ─── Эталонные фрагменты ──────────────────────────────────────────────────────

def save_exemplar(project_id: int, chapter_num: int, text: str, label: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO exemplars (project_id, chapter_num, label, text, created_at) VALUES (?,?,?,?,datetime('now'))",
            (project_id, chapter_num, label, text)
        )
        return cur.lastrowid


def get_exemplars(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM exemplars WHERE project_id=? ORDER BY created_at DESC, id DESC",
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_exemplar(project_id: int, exemplar_id: int) -> bool:
    """Удалить эталон проекта. False — эталон принадлежит другому проекту."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM exemplars WHERE id=? AND project_id=?",
                           (exemplar_id, project_id))
        return cur.rowcount > 0


# ─── База знаний ──────────────────────────────────────────────────────────────

def kb_get_all(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_base WHERE project_id=? ORDER BY title",
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def kb_get(article_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM knowledge_base WHERE id=?", (article_id,)
        ).fetchone()
    return dict(row) if row else None


def kb_save(project_id: int, title: str, content: str,
            tags: str = "", auto_inject: int = 0,
            article_id: int | None = None) -> int:
    with get_conn() as conn:
        if article_id:
            conn.execute(
                """UPDATE knowledge_base
                   SET title=?, content=?, tags=?, auto_inject=?,
                       updated_at=datetime('now')
                   WHERE id=? AND project_id=?""",
                (title, content, tags, auto_inject, article_id, project_id)
            )
            return article_id
        cur = conn.execute(
            """INSERT INTO knowledge_base
               (project_id, title, content, tags, auto_inject)
               VALUES (?,?,?,?,?)""",
            (project_id, title, content, tags, auto_inject)
        )
        return cur.lastrowid


def kb_delete(article_id: int, project_id: int) -> bool:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM knowledge_base WHERE id=? AND project_id=?",
            (article_id, project_id)
        )
    return True


def kb_search(project_id: int, query: str, max_results: int = 3) -> list[dict]:
    if not query or not query.strip():
        return []
    words = [w.lower().strip() for w in query.split() if len(w) > 2]
    if not words:
        return []
    all_articles = kb_get_all(project_id)
    scored = [
        (sum(1 for w in words if w in (art["title"] + " " + art["tags"]).lower()), art)
        for art in all_articles
    ]
    scored = [(s, a) for s, a in scored if s > 0]
    scored.sort(key=lambda x: -x[0])
    return [art for _, art in scored[:max_results]]


def kb_get_auto_inject(project_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM knowledge_base WHERE project_id=? AND auto_inject=1 ORDER BY title",
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]
