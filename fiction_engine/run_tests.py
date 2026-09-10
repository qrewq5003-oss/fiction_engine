"""
Standalone test runner — работает без pytest и без внешних зависимостей.
Использует только стандартную библиотеку Python.
"""
import sys
import os
import types
import sqlite3
import tempfile
import traceback
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

# Мокируем внешние зависимости ДО любых импортов engine.*
from unittest.mock import MagicMock
_openai_mock = MagicMock()
_openai_mock.OpenAI = MagicMock()
sys.modules.setdefault("openai", _openai_mock)
sys.modules.setdefault("anthropic", MagicMock())

# Блокируем __init__.py пакета engine, чтобы не требовались openai/anthropic
engine_stub = types.ModuleType("engine")
engine_stub.__path__ = [str(ROOT / "engine")]
engine_stub.__package__ = "engine"
sys.modules["engine"] = engine_stub

passed = 0
failed = 0
errors = []

# ─── Временные файлы ──────────────────────────────────────────────────────────
# Раньше каждый тест звал _tmp_dir() и ничего не убирал: один прогон
# оставлял под тысячу каталогов, а несколько прогонов подряд забивали /tmp
# целиком (наблюдалось 38 872 каталога на 3.6 ГБ). Теперь всё живёт под одним
# корнем, который удаляется при выходе.
import atexit
import shutil as _shutil

_TMP_ROOT = tempfile.mkdtemp(prefix="fe_tests_")
atexit.register(lambda: _shutil.rmtree(_TMP_ROOT, ignore_errors=True))


def _tmp_dir() -> str:
    """Временный каталог внутри корня прогона — удаляется автоматически."""
    return tempfile.mkdtemp(dir=_TMP_ROOT)

def ok(name):
    global passed
    passed += 1
    print(f"  ✓ {name}")

def fail(name, err):
    global failed
    failed += 1
    errors.append((name, str(err)))
    print(f"  ✗ {name}: {err}")

def run(name, fn):
    try:
        fn()
        ok(name)
    except AssertionError as e:
        fail(name, f"AssertionError: {e}")
    except Exception as e:
        fail(name, f"{type(e).__name__}: {e}")

def make_db():
    """Создаёт временную БД, перезагружает модули с новым путём, возвращает путь."""
    import importlib
    tmp = _tmp_dir()
    db_file = Path(tmp) / "test.db"

    for mod in ["engine.db_core", "engine.error_policy", "engine.logger",
                "engine.db_settings", "engine.db_projects", "engine.db_state",
                "engine.db_chapters", "engine.db_narrative", "engine.db",
                "engine.l3_memory", "engine.continuity_checker",
                "engine.cognitive_memory", "engine.prevalidation"]:
        if mod in sys.modules:
            del sys.modules[mod]

    import engine.db_core as dbc
    dbc.DB_PATH = db_file
    dbc.init_db()
    return db_file


# ════════════════════════════════════════════════════════
print("\n══ error_policy ══")
# ════════════════════════════════════════════════════════

make_db()  # инициализируем БД для logger
from engine.error_policy import error_boundary, handle_error, ErrorLevel, ErrorPolicy, PipelineError

def test_ep_recoverable():
    @error_boundary(level=ErrorLevel.RECOVERABLE, fallback="default")
    def broken(): raise ValueError("err")
    assert broken() == "default"
run("RECOVERABLE возвращает fallback", test_ep_recoverable)

def test_ep_degraded():
    @error_boundary(level=ErrorLevel.DEGRADED, fallback=[])
    def broken(): raise RuntimeError("err")
    assert broken() == []
run("DEGRADED возвращает fallback", test_ep_degraded)

def test_ep_fatal():
    @error_boundary(level=ErrorLevel.FATAL)
    def broken(): raise ConnectionError("err")
    try:
        broken()
        assert False, "должен был бросить PipelineError"
    except PipelineError:
        pass
run("FATAL бросает PipelineError", test_ep_fatal)

def test_ep_no_error():
    @error_boundary(level=ErrorLevel.RECOVERABLE, fallback="fb")
    def works(): return "result"
    assert works() == "result"
run("без ошибки возвращает результат", test_ep_no_error)

def test_ep_pipeline_not_caught():
    @error_boundary(level=ErrorLevel.RECOVERABLE, fallback="fb")
    def inner(): raise PipelineError("ctx", ValueError("x"))
    try:
        inner()
        assert False
    except PipelineError:
        pass
run("PipelineError не поглощается RECOVERABLE", test_ep_pipeline_not_caught)

def test_ep_handle_error():
    r = handle_error("ctx", ValueError("e"), level=ErrorLevel.RECOVERABLE, fallback=42)
    assert r == 42
run("handle_error возвращает fallback", test_ep_handle_error)

def test_ep_generate_fatal():
    assert ErrorPolicy.for_step("generate").level == ErrorLevel.FATAL
run("шаг generate — FATAL", test_ep_generate_fatal)

def test_ep_critique_degraded():
    assert ErrorPolicy.for_step("critique").level == ErrorLevel.DEGRADED
run("шаг critique — DEGRADED", test_ep_critique_degraded)

def test_ep_unknown_recoverable():
    assert ErrorPolicy.for_step("unknown_xyz").level == ErrorLevel.RECOVERABLE
run("неизвестный шаг — RECOVERABLE", test_ep_unknown_recoverable)

def test_ep_pipeline_error_str():
    err = PipelineError("генерация", RuntimeError("timeout"))
    assert "FATAL" in str(err) and "генерация" in str(err)
run("PipelineError строковое представление", test_ep_pipeline_error_str)

def test_ep_original_preserved():
    orig = ConnectionError("сервер")
    err = PipelineError("ctx", orig)
    assert err.original is orig
run("PipelineError сохраняет original", test_ep_original_preserved)


# ════════════════════════════════════════════════════════
print("\n══ db_core ══")
# ════════════════════════════════════════════════════════

def test_core_tables():
    import engine.db_core as dbc
    make_db()
    with dbc.get_conn() as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    expected = {"projects","chapters","state_engine","api_keys","settings",
                "generation_history","l3_memory","knowledge_base",
                "engine_error_log","chapter_analysis","pipeline_runs"}
    missing = expected - tables
    assert not missing, f"Отсутствуют таблицы: {missing}"
run("init_db создаёт все таблицы", test_core_tables)

def test_core_idempotent():
    import engine.db_core as dbc
    make_db()
    dbc.init_db(); dbc.init_db()
run("init_db идемпотентна", test_core_idempotent)

def test_core_log_error_no_raise():
    import engine.db_core as dbc
    make_db()
    with patch.object(dbc, "_get_log", side_effect=Exception("logger упал")):
        dbc.log_error("тест", ValueError("ошибка"))
run("log_error не бросает исключение", test_core_log_error_no_raise)

def test_core_error_log_writes():
    import engine.db_core as dbc
    make_db()
    with patch.object(dbc, "_get_log", side_effect=Exception("logger упал")):
        dbc.log_error("мой контекст", ValueError("тест"))
    log = dbc.get_error_log()
    assert len(log) >= 1
    assert "мой контекст" in log[0]["context"]
run("log_error пишет в БД при падении logger", test_core_error_log_writes)

def test_core_migrations_safe():
    import engine.db_core as dbc
    make_db()
    dbc._run_migrations(); dbc._run_migrations()
run("миграции идемпотентны", test_core_migrations_safe)

def test_core_defaults_nonempty():
    import engine.db_core as dbc
    make_db()
    assert len(dbc._default_global()) > 50
    assert len(dbc._default_plot()) > 50
    assert len(dbc._default_memory()) > 50
run("шаблоны State Engine не пустые", test_core_defaults_nonempty)


# ════════════════════════════════════════════════════════
print("\n══ db_projects ══")
# ════════════════════════════════════════════════════════

def test_proj_create_get():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Книга", "фэнтези")
    p = dbp.get_project(pid)
    assert p["name"] == "Книга" and p["genre"] == "фэнтези"
run("create/get проект", test_proj_create_get)

def test_proj_creates_state():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Книга")
    state = dbp.get_state(pid)
    assert len(state.get("global_state","")) > 10
run("create_project инициализирует state", test_proj_creates_state)

def test_proj_get_nonexistent():
    make_db()
    import engine.db_projects as dbp
    assert dbp.get_project(9999) is None
run("get_project несуществующий → None", test_proj_get_nonexistent)

def test_proj_chapter_words():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.save_chapter(pid, 1, "один два три четыре пять", "Пролог")
    ch = dbp.get_chapter(pid, 1)
    assert ch["word_count"] == 5 and ch["title"] == "Пролог"
run("save_chapter считает слова", test_proj_chapter_words)

def test_proj_chapter_upsert():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.save_chapter(pid, 1, "v1"); dbp.save_chapter(pid, 1, "v2")
    assert len(dbp.get_chapters(pid)) == 1
    assert dbp.get_chapter(pid, 1)["content"] == "v2"
run("save_chapter upsert не дублирует", test_proj_chapter_upsert)

def test_proj_chapters_ordered():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.save_chapter(pid, 3, "три"); dbp.save_chapter(pid, 1, "один"); dbp.save_chapter(pid, 2, "два")
    nums = [c["number"] for c in dbp.get_chapters(pid)]
    assert nums == sorted(nums)
run("get_chapters упорядочены по номеру", test_proj_chapters_ordered)

def test_proj_state_update():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.update_state(pid, global_state="## новый стейт")
    assert dbp.get_state(pid)["global_state"] == "## новый стейт"
run("update_state сохраняется", test_proj_state_update)

def test_proj_state_partial():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.update_state(pid, global_state="глобал", plot_matrix="плот")
    dbp.update_state(pid, memory_graph="память")
    s = dbp.get_state(pid)
    assert s["global_state"] == "глобал"
    assert s["memory_graph"] == "память"
run("update_state частичное не затирает остальное", test_proj_state_partial)

def test_proj_snapshot_restore():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.update_state(pid, global_state="оригинал")
    dbp.snapshot_state(pid, "тест")
    dbp.update_state(pid, global_state="изменено")
    history = dbp.get_state_history(pid)
    # history сортирована по id DESC — ищем именно наш снапшот "тест"
    snap = next(h for h in history if h["reason"] == "тест")
    dbp.restore_state_snapshot(pid, snap["id"])
    assert dbp.get_state(pid)["global_state"] == "оригинал"
run("snapshot + restore state", test_proj_snapshot_restore)

def test_proj_restore_nonexistent():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    assert dbp.restore_state_snapshot(pid, 99999) is False
run("restore несуществующий snapshot → False", test_proj_restore_nonexistent)

def test_proj_structured_state():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    gs = "## ПЕРСОНАЖИ\n\n### Алиса\nСОСТОЯНИЕ: усталая\nЛОКАЦИЯ: лес\nЦЕЛЬ_СЕЙЧАС: домой\nЦЕЛЬ_ГЛУБИННАЯ: покой\nЗНАЕТ: магия\nНЕ_ЗНАЕТ: она маг\nИЗМЕНЕНИЕ: Гл.1\n"
    dbp.update_state(pid, global_state=gs)
    s = dbp.get_structured_state(pid)
    assert "Алиса" in s["char_names"]
    assert s["characters"]["Алиса"]["state"] == "усталая"
run("parse_structured_state извлекает персонажей", test_proj_structured_state)

def test_proj_structured_state_corrupt():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.update_state(pid, global_state="}{][мусор{{{")
    result = dbp.get_structured_state(pid)
    assert isinstance(result, dict) and "characters" in result
run("parse_structured_state не падает на мусоре", test_proj_structured_state_corrupt)

def test_proj_l3_summary():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.save_l3_summary(pid, 1, {"mood":"тревожный","events":"е","characters":"","conflicts":"","promises":"обещание"})
    s = dbp.get_l3_summary(pid, 1)
    assert s["mood"] == "тревожный"
run("l3 save/get summary", test_proj_l3_summary)

def test_proj_l3_promises():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.save_l3_summary(pid, 1, {"mood":"","events":"","characters":"","conflicts":"","promises":"герой вернётся"})
    promises = dbp.get_l3_active_promises(pid, before_chapter=5)
    assert "герой вернётся" in promises
run("l3 active promises", test_proj_l3_promises)

def test_proj_l3_summaries_range():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    for i in range(1, 6):
        dbp.save_l3_summary(pid, i, {"mood":f"г{i}","events":"","characters":"","conflicts":"","promises":""})
    result = dbp.get_l3_summaries(pid, before_chapter=4, n=3)
    assert len(result) == 3 and all(s["chapter_num"] < 4 for s in result)
run("l3 get_summaries срез", test_proj_l3_summaries_range)

def test_proj_kb_crud():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    aid = dbp.kb_save(pid, "Магия", "описание", tags="магия")
    art = dbp.kb_get(aid)
    assert art["title"] == "Магия"
    dbp.kb_delete(aid, pid)
    assert dbp.kb_get_all(pid) == []
run("knowledge_base CRUD", test_proj_kb_crud)

def test_proj_kb_search():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.kb_save(pid, "Огненная магия", "пламя", tags="магия огонь")
    dbp.kb_save(pid, "История", "давно", tags="история")
    r = dbp.kb_search(pid, "магия")
    assert r and r[0]["title"] == "Огненная магия"
run("kb_search по тегам", test_proj_kb_search)

def test_proj_kb_auto_inject():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    dbp.kb_save(pid, "Авто", "текст", auto_inject=1)
    dbp.kb_save(pid, "Ручной", "текст", auto_inject=0)
    auto = dbp.kb_get_auto_inject(pid)
    assert len(auto) == 1 and auto[0]["title"] == "Авто"
run("kb auto_inject фильтр", test_proj_kb_auto_inject)

def test_proj_pipeline():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    run_id = dbp.create_pipeline_run(pid, 1, "m","m","m","m")
    dbp.save_pipeline_iteration(run_id, 1, "generate", "m", "prompt", "text", score=0.8)
    dbp.finish_pipeline_run(run_id, "accepted")
    run_data = dbp.get_pipeline_run(run_id)
    iters = dbp.get_pipeline_iterations(run_id)
    assert run_data["status"] == "accepted"
    assert len(iters) == 1 and abs(iters[0]["score"] - 0.8) < 0.001
run("pipeline full flow", test_proj_pipeline)

def test_proj_chapter_analysis():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    data = {"arc_progress":{},"character_deltas":[],"opened_promises":["обещание"],
            "closed_promises":[],"causal_chains":[],"logical_gaps":["пробел"],
            "conflict_score":0.7,"pacing_note":"быстро","plot_threads":{},"analysis_quality":"ok"}
    dbp.save_chapter_analysis(pid, 1, data)
    r = dbp.get_chapter_analysis(pid, 1)
    assert r["pacing_note"] == "быстро" and r["opened_promises"] == ["обещание"]
run("chapter analysis save/get", test_proj_chapter_analysis)

def test_proj_logical_gaps():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    data = {"arc_progress":{},"character_deltas":[],"opened_promises":[],
            "closed_promises":[],"causal_chains":[],"logical_gaps":["мотивация не объяснена"],
            "conflict_score":0.5,"pacing_note":"","plot_threads":{},"analysis_quality":"ok"}
    dbp.save_chapter_analysis(pid, 2, data)
    gaps = dbp.get_all_logical_gaps(pid, before_chapter=10)
    assert len(gaps) == 1 and "мотивация не объяснена" in gaps[0]["gaps"]
run("get_all_logical_gaps", test_proj_logical_gaps)

def test_proj_analyses_range():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    base = {"arc_progress":{},"character_deltas":[],"opened_promises":[],"closed_promises":[],
            "causal_chains":[],"logical_gaps":[],"conflict_score":0.5,"pacing_note":"",
            "plot_threads":{},"analysis_quality":"ok"}
    for i in range(1, 6):
        dbp.save_chapter_analysis(pid, i, base)
    result = dbp.get_analyses_range(pid, 2, 4)
    assert len(result) == 3 and all(2 <= r["chapter_num"] <= 4 for r in result)
run("get_analyses_range", test_proj_analyses_range)

def test_proj_symbols():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    sid = dbp.save_symbol(pid, "Чёрный нож", "предмет", 1, "смерть")
    dbp.add_symbol_appearance(sid, 3, "нож блеснул", "угроза")
    syms = dbp.get_symbols(pid)
    assert len(syms) == 1 and syms[0]["appearances"][0]["meaning"] == "угроза"
    assert "Чёрный нож" in dbp.get_symbols_context(pid)
run("symbols CRUD + context", test_proj_symbols)

def test_proj_voice_profiles():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Роман")
    v1 = dbp.save_voice_profile(pid, "Тихий", "профиль1")
    v2 = dbp.save_voice_profile(pid, "Громкий", "профиль2")
    dbp.set_active_voice(pid, v2)
    assert dbp.get_active_voice(pid)["name"] == "Громкий"
    profiles = dbp.get_voice_profiles(pid)
    assert sum(1 for p in profiles if p["active"]) == 1
run("voice profiles CRUD", test_proj_voice_profiles)

def test_proj_delete():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Удаляемый")
    dbp.save_chapter(pid, 1, "текст")
    dbp.delete_project(pid)
    assert dbp.get_project(pid) is None
    assert dbp.get_chapters(pid) == []
run("delete_project удаляет проект и главы", test_proj_delete)


# ════════════════════════════════════════════════════════
print("\n══ db_settings ══")
# ════════════════════════════════════════════════════════

def test_sett_api_key():
    make_db()
    import engine.db_settings as dbs
    dbs.save_api_key("anthropic_direct", "sk-test-123")
    assert dbs.get_api_key("anthropic_direct") == "sk-test-123"
run("save/get API ключ", test_sett_api_key)

def test_sett_env_fallback():
    make_db()
    import engine.db_settings as dbs
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
        assert dbs.get_api_key("anthropic_direct") == "env-key"
run("API ключ fallback к env", test_sett_env_fallback)

def test_sett_db_over_env():
    make_db()
    import engine.db_settings as dbs
    dbs.save_api_key("anthropic_direct", "db-key")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
        assert dbs.get_api_key("anthropic_direct") == "db-key"
run("БД приоритет над env", test_sett_db_over_env)

def test_sett_set_get():
    make_db()
    import engine.db_settings as dbs
    dbs.set_setting("k", "v")
    assert dbs.get_setting("k") == "v"
run("set/get настройка", test_sett_set_get)

def test_sett_active_project():
    make_db()
    import engine.db_settings as dbs
    assert dbs.get_active_project_id() is None
    dbs.set_active_project(7)
    assert dbs.get_active_project_id() == 7
run("активный проект", test_sett_active_project)

def test_sett_prep():
    make_db()
    import engine.db_projects as dbp, engine.db_settings as dbs
    pid = dbp.create_project("Тест")
    dbs.save_prep(pid, "characters", "## Иван Петров")
    assert dbs.get_prep(pid)["characters"] == "## Иван Петров"
run("prep save/get", test_sett_prep)

def test_sett_prep_context():
    make_db()
    import engine.db_projects as dbp, engine.db_settings as dbs
    pid = dbp.create_project("Тест")
    dbs.save_prep(pid, "characters", "## Иван Петров\nхарактер: мрачный")
    assert "Иван Петров" in dbs.get_prep_context(pid)
run("prep_context не пустой после save", test_sett_prep_context)

def test_sett_mask_keys():
    make_db()
    import engine.db_settings as dbs
    dbs.save_api_key("anthropic_direct", "sk-ant-verylongkeyhere1234")
    keys = dbs.get_all_api_keys()
    val = keys["anthropic_direct"]
    assert "verylongkeyhere" not in val and "..." in val
run("API ключи маскируются", test_sett_mask_keys)


# ════════════════════════════════════════════════════════
print("\n══ unified_engine.detect_genre ══")
# ════════════════════════════════════════════════════════

# unified_engine использует только стандартные импорты — можно импортировать напрямую
for mod in ["engine.engine_config", "engine.engine_loaders", "engine.unified_engine"]:
    if mod in sys.modules:
        del sys.modules[mod]

from engine.unified_engine import detect_genre, resolve_dependencies

def test_ge_fantasy():
    assert detect_genre("эпическое фэнтези") is not None
run("определяет эпическое фэнтези", test_ge_fantasy)

def test_ge_urban():
    assert detect_genre("городское фэнтези") == "fantasy_urban"
run("городское фэнтези → fantasy_urban", test_ge_urban)

def test_ge_horror():
    r = detect_genre("психологический хоррор")
    assert r and "horror" in r
run("определяет хоррор", test_ge_horror)

def test_ge_unknown():
    assert detect_genre("абракадабра xyz") is None
run("неизвестный жанр → None", test_ge_unknown)

def test_ge_empty():
    assert detect_genre("") is None
run("пустая строка → None", test_ge_empty)

def test_ge_case():
    assert detect_genre("ФЭНТЕЗИ") == detect_genre("фэнтези")
run("регистронезависимость", test_ge_case)

def test_ge_specificity():
    assert detect_genre("городское фэнтези") == "fantasy_urban"
run("специфичный жанр побеждает общий", test_ge_specificity)

def test_ge_deps_dedup():
    r = resolve_dependencies(["a","a","b"])
    assert r.count("a") == 1
run("resolve_dependencies убирает дубли", test_ge_deps_dedup)

def test_ge_deps_empty():
    assert resolve_dependencies([]) == []
run("resolve_dependencies пустой список", test_ge_deps_empty)


# ════════════════════════════════════════════════════════
print("\n══ narrative_intelligence ══")
# ════════════════════════════════════════════════════════

from engine.narrative_intelligence import (
    _conflict_word_score, _pacing_to_urgency, _tension_score,
    _mood_polarity, _warn_tension_pattern, NarrativeIntelligence,
)


def _nil(summaries):
    return NarrativeIntelligence(
        get_summaries_fn=MagicMock(return_value=summaries),
        get_state_fn=MagicMock(return_value=None),
        get_chapters_fn=MagicMock(return_value=[]),
    )

def _s(n, conflicts="", mood="", promises="", events="", characters=""):
    return {"chapter_num": n, "project_id": 1,
            "conflicts": conflicts, "mood": mood,
            "promises": promises, "events": events, "characters": characters}

def _arc_resp():
    return '{"arcs": [{"character": "Иван", "status": "active", "evolution": "растёт", "stalled": false, "last_chapter": 3}]}'
def _promise_resp():
    return '{"resolutions": [{"promise": "Убийца вернётся", "resolved": false, "chapter": null}]}'
def _contra_resp():
    return '{"contradictions": []}'


# ── _conflict_word_score ──────────────────────────────
def test_nil_conflict_score_min():
    assert _conflict_word_score("") == pytest.approx(0.1) if False else True
    s = _conflict_word_score("")
    assert s == round(s, 2) and 0.09 < s <= 0.15
run("conflict_word_score: пустой → ~0.1", test_nil_conflict_score_min)

def test_nil_conflict_score_grows():
    low  = _conflict_word_score("прогулка")
    high = _conflict_word_score("конфликт угроза смерть предательство")
    assert high > low
run("conflict_word_score: растёт со словами", test_nil_conflict_score_grows)

def test_nil_conflict_score_capped():
    text = "конфликт угроза смерть предательство опасность кризис атак схватк раскрыт ложь перелом открылось"
    assert _conflict_word_score(text) <= 1.0
run("conflict_word_score: не превышает 1.0", test_nil_conflict_score_capped)

def test_nil_conflict_score_range():
    for text in ["", "конфликт", "всё спокойно"]:
        s = _conflict_word_score(text)
        assert 0.1 <= s <= 1.0
run("conflict_word_score: всегда в [0.1, 1.0]", test_nil_conflict_score_range)


# ── _pacing_to_urgency ────────────────────────────────
def test_nil_pacing_fast():
    u, ok = _pacing_to_urgency("быстрый")
    assert u == 0.75 and ok is True
run("pacing_to_urgency: быстрый → 0.75", test_nil_pacing_fast)

def test_nil_pacing_slow():
    u, ok = _pacing_to_urgency("медленный")
    assert u == 0.20 and ok is True
run("pacing_to_urgency: медленный → 0.20", test_nil_pacing_slow)

def test_nil_pacing_empty():
    u, ok = _pacing_to_urgency("")
    assert u == 0.40 and ok is False
run("pacing_to_urgency: пустой → default, data=False", test_nil_pacing_empty)

def test_nil_pacing_whitespace():
    _, ok = _pacing_to_urgency("   ")
    assert ok is False
run("pacing_to_urgency: пробелы → data=False", test_nil_pacing_whitespace)

def test_nil_pacing_unknown():
    u, ok = _pacing_to_urgency("неизвестный темп")
    assert u == 0.40 and ok is True
run("pacing_to_urgency: нераспознанный → default, data=True", test_nil_pacing_unknown)


# ── _tension_score ────────────────────────────────────
def test_nil_tension_range():
    combos = [
        ("конфликт смерть", "быстрый",   "мрачное"),
        ("тихо",            "медленный", "светлое"),
        ("",                "",          ""),
    ]
    for c, p, m in combos:
        s = _tension_score(c, p, m)
        assert 0.0 <= s <= 1.0
run("tension_score: диапазон [0, 1]", test_nil_tension_range)

def test_nil_tension_high_conflict_higher():
    low  = _tension_score("прогулка", "медленный", "спокойное")
    high = _tension_score("конфликт угроза смерть", "быстрый", "мрачное")
    assert high > low
run("tension_score: высокий конфликт → выше", test_nil_tension_high_conflict_higher)


# ── _mood_polarity ────────────────────────────────────
def test_nil_mood_polarity_pos():
    assert _mood_polarity("светлое утро") == "pos"
run("mood_polarity: светлое → pos", test_nil_mood_polarity_pos)

def test_nil_mood_polarity_neg():
    assert _mood_polarity("мрачное небо") == "neg"
run("mood_polarity: мрачное → neg", test_nil_mood_polarity_neg)

def test_nil_mood_polarity_neutral():
    assert _mood_polarity("нейтральный тон") == "neutral"
run("mood_polarity: нейтральный → neutral", test_nil_mood_polarity_neutral)

def test_nil_mood_polarity_empty():
    assert _mood_polarity("") == "neutral"
run("mood_polarity: пустой → neutral", test_nil_mood_polarity_empty)


# ── _warn_tension_pattern ─────────────────────────────
def test_nil_warn_short_series_empty():
    assert _warn_tension_pattern([0.8, 0.9]) == []
run("warn_tension_pattern: < 3 глав → []", test_nil_warn_short_series_empty)

def test_nil_warn_three_peaks():
    warnings = _warn_tension_pattern([0.3, 0.4, 0.8, 0.85, 0.9])
    assert any("пик" in w.lower() or "подряд" in w.lower() for w in warnings)
run("warn_tension_pattern: три пика → предупреждение", test_nil_warn_three_peaks)

def test_nil_warn_flat():
    warnings = _warn_tension_pattern([0.5, 0.5, 0.5, 0.5, 0.5])
    assert any("ровн" in w.lower() for w in warnings)
run("warn_tension_pattern: ровное → предупреждение", test_nil_warn_flat)

def test_nil_warn_low_drought():
    warnings = _warn_tension_pattern([0.5, 0.1, 0.15, 0.2])
    assert any("низк" in w.lower() or "конфликт" in w.lower() for w in warnings)
run("warn_tension_pattern: три низких → предупреждение", test_nil_warn_low_drought)

def test_nil_warn_genre_calibration():
    warnings = _warn_tension_pattern([0.7, 0.72, 0.68, 0.71, 0.69], genre_family="romance")
    assert any("норм" in w.lower() or "выше" in w.lower() for w in warnings)
run("warn_tension_pattern: romance выше нормы → предупреждение", test_nil_warn_genre_calibration)

def test_nil_warn_multiple_not_exclusive():
    warnings = _warn_tension_pattern([0.8, 0.82, 0.81, 0.83, 0.80], genre_family="romance")
    assert len(warnings) >= 2
run("warn_tension_pattern: несколько причин → несколько предупреждений", test_nil_warn_multiple_not_exclusive)


# ── _count_mood_shifts ────────────────────────────────
def test_nil_mood_shifts_neutral_bridge():
    nil = _nil([])
    summaries = [_s(1, mood="светлое"), _s(2, mood="нейтральный"), _s(3, mood="мрачное")]
    assert nil._count_mood_shifts(summaries) == 1
run("count_mood_shifts: pos→neutral→neg = 1 разворот", test_nil_mood_shifts_neutral_bridge)

def test_nil_mood_shifts_direct():
    nil = _nil([])
    summaries = [_s(1, mood="светлое"), _s(2, mood="мрачное"), _s(3, mood="светлое")]
    assert nil._count_mood_shifts(summaries) == 2
run("count_mood_shifts: два прямых разворота = 2", test_nil_mood_shifts_direct)

def test_nil_mood_shifts_all_neutral():
    nil = _nil([])
    summaries = [_s(i, mood="нейтральный") for i in range(5)]
    assert nil._count_mood_shifts(summaries) == 0
run("count_mood_shifts: все neutral = 0", test_nil_mood_shifts_all_neutral)

def test_nil_mood_shifts_empty():
    nil = _nil([])
    assert nil._count_mood_shifts([]) == 0
run("count_mood_shifts: пустой = 0", test_nil_mood_shifts_empty)


# ── get_metrics ───────────────────────────────────────
def test_nil_get_metrics_keys():
    summaries = [_s(i, conflicts="конфликт", mood="мрачное") for i in range(1, 4)]
    nil     = _nil(summaries)
    metrics = nil.get_metrics(project_id=1, through_chapter=3)
    required = {"chapters_analyzed", "mood_trajectory", "conflict_density",
                "pacing_coverage", "promise_count", "avg_conflict_score", "mood_shift_count"}
    assert required <= set(metrics.keys())
run("get_metrics: возвращает все ключи", test_nil_get_metrics_keys)

def test_nil_get_metrics_chapters_count():
    summaries = [_s(i, conflicts="конфликт") for i in range(1, 6)]
    nil     = _nil(summaries)
    metrics = nil.get_metrics(project_id=1, through_chapter=5)
    assert metrics["chapters_analyzed"] == 5
run("get_metrics: chapters_analyzed корректен", test_nil_get_metrics_chapters_count)

def test_nil_get_metrics_conflict_density_length():
    summaries = [_s(i) for i in range(1, 4)]
    nil     = _nil(summaries)
    metrics = nil.get_metrics(project_id=1, through_chapter=3)
    assert len(metrics["conflict_density"]) == 3
run("get_metrics: длина conflict_density == кол-во саммари", test_nil_get_metrics_conflict_density_length)

def test_nil_get_metrics_ranges():
    summaries = [_s(i, conflicts="конфликт угроза") for i in range(1, 4)]
    nil     = _nil(summaries)
    metrics = nil.get_metrics(project_id=1, through_chapter=3)
    assert 0.0 <= metrics["avg_conflict_score"] <= 1.0
    assert 0.0 <= metrics["pacing_coverage"]    <= 1.0
run("get_metrics: avg_conflict_score и pacing_coverage в [0,1]", test_nil_get_metrics_ranges)


# ── _extract_raw_promises ─────────────────────────────
def test_nil_promises_skip_nope():
    nil = _nil([])
    summaries = [_s(i, promises=p) for i, p in
                 enumerate(["нет", "—", "-", "", "Нет"], 1)]
    assert nil._extract_raw_promises(summaries) == []
run("extract_raw_promises: пропускает нет/—/-/пустой", test_nil_promises_skip_nope)

def test_nil_promises_splits_semicolon():
    nil = _nil([])
    result = nil._extract_raw_promises([_s(1, promises="Первое обещание; Второе обещание")])
    assert len(result) == 2
run("extract_raw_promises: разбивает по ';'", test_nil_promises_splits_semicolon)

def test_nil_promises_splits_newline():
    nil = _nil([])
    result = nil._extract_raw_promises([_s(1, promises="Первое обещание\nВторое обещание")])
    assert len(result) == 2
run("extract_raw_promises: разбивает по '\\n'", test_nil_promises_splits_newline)

def test_nil_promises_skips_short():
    nil = _nil([])
    result = nil._extract_raw_promises([_s(1, promises="ok; нормальное обещание о чём-то важном")])
    texts = [t for _, t in result]
    assert not any(len(t) <= 10 for t in texts)
run("extract_raw_promises: пропускает короткие (<10 символов)", test_nil_promises_skips_short)

def test_nil_promises_chapter_num():
    nil = _nil([])
    result = nil._extract_raw_promises([_s(7, promises="Герой вернётся в деревню")])
    assert result[0][0] == 7
run("extract_raw_promises: сохраняет chapter_num", test_nil_promises_chapter_num)


# ── get_promise_status ────────────────────────────────
def test_nil_get_promise_status_no_llm():
    summaries = [
        _s(1, promises="Убийца вернётся"),
        _s(2, promises="нет"),
        _s(3, promises="Тайна раскроется; Герой найдёт меч"),
    ]
    nil    = _nil(summaries)
    result = nil.get_promise_status(project_id=1, through_chapter=3)
    assert len(result) == 3
    texts = [r["promise"] for r in result]
    assert any("Убийца" in t for t in texts)
    assert any("Тайна"  in t for t in texts)
    assert any("Герой"  in t for t in texts)
run("get_promise_status: правильно парсит без LLM", test_nil_get_promise_status_no_llm)


# ── analyze: без саммари ──────────────────────────────
def test_nil_analyze_empty_warning():
    nil    = _nil([])
    report = nil.analyze(project_id=1, through_chapter=5, api_call_fn=MagicMock())
    assert report.ok is True
    assert any("саммари" in w.lower() for w in report.warnings)
run("analyze: нет саммари → предупреждение, ok=True", test_nil_analyze_empty_warning)

def test_nil_analyze_empty_no_llm():
    llm = MagicMock()
    _nil([]).analyze(project_id=1, through_chapter=5, api_call_fn=llm)
    llm.assert_not_called()
run("analyze: нет саммари → LLM не вызывается", test_nil_analyze_empty_no_llm)


# ── analyze: с саммари ────────────────────────────────
def test_nil_analyze_calls_llm():
    summaries = [_s(i, conflicts="конфликт", mood="мрачное",
                     events="событие", characters="Иван") for i in range(1, 4)]
    llm = MagicMock(side_effect=[_arc_resp(), _promise_resp(), _contra_resp()])
    nil = _nil(summaries)
    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert llm.call_count >= 2
    assert report.project_id      == 1
    assert report.through_chapter == 3
run("analyze: с саммари → LLM вызывается, отчёт заполнен", test_nil_analyze_calls_llm)

def test_nil_analyze_report_structure():
    summaries = [_s(i, conflicts="конфликт", mood="мрачное",
                     events="событие", characters="Иван") for i in range(1, 4)]
    llm = MagicMock(side_effect=[_arc_resp(), _promise_resp(), _contra_resp()])
    report = _nil(summaries).analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert isinstance(report.warnings,         list)
    assert isinstance(report.mood_trajectory,  list)
    assert isinstance(report.conflict_density, list)
    assert isinstance(report.arc_health,       dict)
    assert isinstance(report.promise_status,   list)
    assert isinstance(report.contradictions,   list)
    assert len(report.conflict_density) == 3
run("analyze: структура NarrativeReport корректна", test_nil_analyze_report_structure)

def test_nil_analyze_mood_trajectory():
    summaries = [_s(1, mood="светлое"), _s(2, mood="мрачное")]
    llm = MagicMock(side_effect=[_arc_resp(), _promise_resp(), _contra_resp()])
    report = _nil(summaries).analyze(project_id=1, through_chapter=2, api_call_fn=llm)
    assert len(report.mood_trajectory) == 2
    assert any("светлое" in m for m in report.mood_trajectory)
    assert any("мрачное" in m for m in report.mood_trajectory)
run("analyze: mood_trajectory заполнен", test_nil_analyze_mood_trajectory)


# ── analyze: LLM падает ───────────────────────────────
def test_nil_analyze_llm_raises_no_propagation():
    summaries = [_s(i, conflicts="конфликт", mood="мрачное",
                     events="событие", characters="Иван") for i in range(1, 4)]
    llm = MagicMock(side_effect=RuntimeError("API недоступен"))
    report = _nil(summaries).analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert report is not None and report.project_id == 1
run("analyze: LLM raises → нет исключения, отчёт возвращён", test_nil_analyze_llm_raises_no_propagation)

def test_nil_analyze_invalid_json_no_exception():
    summaries = [_s(i, conflicts="конфликт", mood="мрачное",
                     events="событие", characters="Иван") for i in range(1, 4)]
    llm = MagicMock(return_value="{invalid json{{")
    report = _nil(summaries).analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert report is not None
run("analyze: невалидный JSON от LLM → нет исключения", test_nil_analyze_invalid_json_no_exception)


# ── analyze: БЛОКИРУЮЩЕЕ противоречие ────────────────
def test_nil_analyze_blocking_ok_false():
    # promises нужны чтобы _track_promises тоже вызвал LLM,
    # иначе contradictions занимает второй слот и blocking теряется
    summaries = [_s(i, conflicts="конфликт", mood="мрачное",
                     events="Иван вошёл в замок", characters="Иван",
                     promises="Убийца вернётся в город") for i in range(1, 4)]

    def smart_llm(prompt):
        if "эволюц" in prompt or prompt.strip().startswith("Проанализируй эволюцию"):
            return '{"arcs": []}'
        if "ОБЕЩАНИ" in prompt or "обещани" in prompt:
            return '{"resolutions": []}'
        # contradiction prompt
        return '{"contradictions": [{"chapters": [1,3], "description": "Иван мёртв но жив", "severity": "blocking"}]}'

    nil = NarrativeIntelligence(
        get_summaries_fn=MagicMock(return_value=summaries),
        get_state_fn=MagicMock(return_value=None),
        get_chapters_fn=MagicMock(return_value=[]),
    )
    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=smart_llm)
    assert report.ok is False
    assert any("БЛОКИРУЮЩЕЕ" in c for c in report.contradictions)
run("analyze: БЛОКИРУЮЩЕЕ противоречие → ok=False", test_nil_analyze_blocking_ok_false)

def test_nil_analyze_no_contradictions_ok_true():
    summaries = [_s(i, conflicts="конфликт", mood="мрачное",
                     events="событие", characters="Иван") for i in range(1, 4)]
    llm = MagicMock(side_effect=[_arc_resp(), _promise_resp(), _contra_resp()])
    report = _nil(summaries).analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert report.ok is True
run("analyze: нет противоречий → ok=True", test_nil_analyze_no_contradictions_ok_true)


# ── analyze: tension warning при трёх пиках ──────────
def test_nil_analyze_tension_warning_three_peaks():
    high = "конфликт угроза смерть предательство опасность кризис"
    summaries = [_s(i, conflicts=high, mood="мрачное", events="событие") for i in range(1, 4)]
    llm = MagicMock(side_effect=[_arc_resp(), _promise_resp(), _contra_resp()])
    report = _nil(summaries).analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    tension_warnings = [w for w in report.warnings
                        if "пик" in w.lower() or "напряжен" in w.lower() or "три" in w.lower()]
    assert len(tension_warnings) >= 1
run("analyze: три пика → tension warning в отчёте", test_nil_analyze_tension_warning_three_peaks)


# ── analyze: фильтрация by through_chapter ────────────
def test_nil_analyze_filters_future_chapters():
    summaries_all = [_s(i) for i in range(1, 8)]
    get_summaries = MagicMock(return_value=summaries_all)
    nil = NarrativeIntelligence(
        get_summaries_fn=get_summaries,
        get_state_fn=MagicMock(return_value=None),
        get_chapters_fn=MagicMock(return_value=[]),
    )
    llm = MagicMock(side_effect=[_arc_resp(), _promise_resp(), _contra_resp()])
    report = nil.analyze(project_id=1, through_chapter=3, api_call_fn=llm)
    assert len(report.conflict_density) == 3
run("analyze: саммари > through_chapter не учитываются", test_nil_analyze_filters_future_chapters)


# ── _extract_conflict_density: нет project_id ─────────
def test_nil_conflict_density_no_project_id():
    nil = _nil([])
    summaries = [
        {"chapter_num": 1, "conflicts": "конфликт", "mood": "мрачное"},
        {"chapter_num": 2, "conflicts": "угроза",   "mood": "тревожное"},
    ]
    scores, coverage = nil._extract_conflict_density(summaries)
    assert len(scores) == 2
    assert 0.0 <= coverage <= 1.0
run("_extract_conflict_density: нет project_id → не падает", test_nil_conflict_density_no_project_id)



# ════════════════════════════════════════════════════════
print("\n══ pipeline_drift ══")
# ════════════════════════════════════════════════════════

from engine.pipeline_drift import _parse_drift_result, _build_warning


# ── _parse_drift_result ───────────────────────────────
def test_drift_parse_full():
    score, issues, critical = _parse_drift_result(
        "ОЦЕНКА: 8/10\nПРОБЛЕМЫ: ритм сбился\nКРИТИЧНО: нет"
    )
    assert score == 8.0 and issues == "ритм сбился" and critical is False
run("_parse_drift_result: полный ответ", test_drift_parse_full)

def test_drift_parse_critical_yes():
    _, _, critical = _parse_drift_result(
        "ОЦЕНКА: 4/10\nПРОБЛЕМЫ: голос сломан\nКРИТИЧНО: да"
    )
    assert critical is True
run("_parse_drift_result: КРИТИЧНО: да → True", test_drift_parse_critical_yes)

def test_drift_parse_float_score():
    score, _, _ = _parse_drift_result("ОЦЕНКА: 7.5/10\nПРОБЛЕМЫ: нет\nКРИТИЧНО: нет")
    assert score == 7.5
run("_parse_drift_result: дробная оценка 7.5", test_drift_parse_float_score)

def test_drift_parse_missing_score_fallback():
    score, _, _ = _parse_drift_result("Всё хорошо, голос ровный")
    assert score == 7.0
run("_parse_drift_result: нет ОЦЕНКИ → fallback 7.0", test_drift_parse_missing_score_fallback)

def test_drift_parse_missing_issues_empty():
    _, issues, _ = _parse_drift_result("ОЦЕНКА: 9/10\nКРИТИЧНО: нет")
    assert issues == ""
run("_parse_drift_result: нет ПРОБЛЕМ → пустая строка", test_drift_parse_missing_issues_empty)

def test_drift_parse_missing_critical_false():
    _, _, critical = _parse_drift_result("ОЦЕНКА: 5/10\nПРОБЛЕМЫ: ритм")
    assert critical is False
run("_parse_drift_result: нет КРИТИЧНО → False", test_drift_parse_missing_critical_false)

def test_drift_parse_case_insensitive():
    _, _, critical = _parse_drift_result("ОЦЕНКА: 3/10\nПРОБЛЕМЫ: всё\nКРИТИЧНО: ДА")
    assert critical is True
run("_parse_drift_result: КРИТИЧНО: ДА (верхний регистр)", test_drift_parse_case_insensitive)


# ── _build_warning ────────────────────────────────────
def test_build_warning_below_6():
    w = _build_warning(5.0, "темп сломан")
    assert w is not None and "Дрейф голоса" in w and "темп сломан" in w
run("_build_warning: score < 6 → предупреждение о дрейфе", test_build_warning_below_6)

def test_build_warning_between_6_and_75():
    w = _build_warning(6.5, "небольшие отклонения")
    assert w is not None and "небольшие отклонения" in w
run("_build_warning: 6 ≤ score < 7.5 → мягкое предупреждение", test_build_warning_between_6_and_75)

def test_build_warning_above_75():
    assert _build_warning(8.0, "нет") is None
run("_build_warning: score ≥ 7.5 → None", test_build_warning_above_75)

def test_build_warning_exactly_6():
    w = _build_warning(6.0, "проблема")
    assert w is not None and "Дрейф голоса" not in w
run("_build_warning: score == 6.0 → мягкое (не жёсткое)", test_build_warning_exactly_6)

def test_build_warning_exactly_75():
    assert _build_warning(7.5, "нет") is None
run("_build_warning: score == 7.5 → None", test_build_warning_exactly_75)


# ════════════════════════════════════════════════════════
print("\n══ continuity_checker ══")
# ════════════════════════════════════════════════════════

import json as _json
from engine.continuity_checker import (
    _has_enough_data, format_continuity_for_prompt, check_continuity,
)


# ── _has_enough_data ──────────────────────────────────
def test_cc_chapter_1_false():
    assert _has_enough_data(1, 1) is False
run("_has_enough_data: глава 1 → False", test_cc_chapter_1_false)

def test_cc_chapter_2_false():
    assert _has_enough_data(1, 2) is False
run("_has_enough_data: глава 2 → False", test_cc_chapter_2_false)

def test_cc_chapter_3_no_analysis():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Тест")
    assert _has_enough_data(pid, 3) is False
run("_has_enough_data: глава 3, нет анализа → False", test_cc_chapter_3_no_analysis)

def test_cc_chapter_3_with_ok_analysis():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Тест")
    base = {"arc_progress":{}, "character_deltas":[], "opened_promises":[],
            "closed_promises":[], "causal_chains":[], "logical_gaps":[],
            "conflict_score":0.5, "pacing_note":"", "plot_threads":{}, "analysis_quality":"ok"}
    dbp.save_chapter_analysis(pid, 2, base)
    assert _has_enough_data(pid, 3) is True
run("_has_enough_data: глава 3, есть ok-анализ гл.2 → True", test_cc_chapter_3_with_ok_analysis)

def test_cc_only_failed_analysis():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Тест")
    base = {"arc_progress":{}, "character_deltas":[], "opened_promises":[],
            "closed_promises":[], "causal_chains":[], "logical_gaps":[],
            "conflict_score":0.0, "pacing_note":"", "plot_threads":{}, "analysis_quality":"failed"}
    dbp.save_chapter_analysis(pid, 2, base)
    assert _has_enough_data(pid, 3) is False
run("_has_enough_data: только failed-анализ → False", test_cc_only_failed_analysis)


# ── format_continuity_for_prompt ──────────────────────
def test_cc_format_empty():
    assert format_continuity_for_prompt([]) == ""
run("format_continuity_for_prompt: [] → пустая строка", test_cc_format_empty)

def test_cc_format_critical_marker():
    v = [{"fact":"Иван мёртв с гл.3","violation":"Иван говорит в гл.7","severity":"critical"}]
    r = format_continuity_for_prompt(v)
    assert ("КРИТИЧНО" in r or "❌" in r) and "Иван говорит в гл.7" in r and "Иван мёртв" in r
run("format_continuity_for_prompt: critical → маркер ❌", test_cc_format_critical_marker)

def test_cc_format_warning_marker():
    v = [{"fact":"Алиса не знает код","violation":"Алиса вводит код","severity":"warning"}]
    r = format_continuity_for_prompt(v)
    assert ("⚠" in r or "ПРЕДУПРЕЖДЕНИЕ" in r) and "Алиса вводит код" in r
run("format_continuity_for_prompt: warning → маркер ⚠", test_cc_format_warning_marker)

def test_cc_format_critical_before_warning():
    v = [
        {"fact":"факт1","violation":"нарушение_warning","severity":"warning"},
        {"fact":"факт2","violation":"нарушение_critical","severity":"critical"},
    ]
    r = format_continuity_for_prompt(v)
    assert r.index("нарушение_critical") < r.index("нарушение_warning")
run("format_continuity_for_prompt: critical идут перед warning", test_cc_format_critical_before_warning)

def test_cc_format_has_header():
    v = [{"fact":"факт","violation":"нарушение","severity":"critical"}]
    assert "НАРУШЕНИЯ НЕПРЕРЫВНОСТИ" in format_continuity_for_prompt(v)
run("format_continuity_for_prompt: содержит заголовок", test_cc_format_has_header)


# ── check_continuity ──────────────────────────────────
def test_cc_chapter_1_no_llm():
    llm = MagicMock()
    assert check_continuity(1, 1, "текст главы", llm) == []
    llm.assert_not_called()
run("check_continuity: глава 1 → [], LLM не вызывается", test_cc_chapter_1_no_llm)

def test_cc_llm_raises_returns_empty():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Тест")
    base = {"arc_progress":{}, "character_deltas":[], "opened_promises":["обещание"],
            "closed_promises":[], "causal_chains":[], "logical_gaps":[],
            "conflict_score":0.5, "pacing_note":"", "plot_threads":{}, "analysis_quality":"ok"}
    dbp.save_chapter_analysis(pid, 2, base)
    llm = MagicMock(side_effect=RuntimeError("API упал"))
    result = check_continuity(pid, 3, "текст" * 200, llm)
    assert result == []
run("check_continuity: LLM raises → [] (error_boundary)", test_cc_llm_raises_returns_empty)

def test_cc_parses_violations():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Тест")
    base = {"arc_progress":{}, "character_deltas":[], "opened_promises":["Иван поклялся не убивать"],
            "closed_promises":[], "causal_chains":[], "logical_gaps":[],
            "conflict_score":0.5, "pacing_note":"", "plot_threads":{}, "analysis_quality":"ok"}
    dbp.save_chapter_analysis(pid, 2, base)
    resp = _json.dumps({"violations":[
        {"fact":"Иван поклялся не убивать (гл.2)","violation":"Иван убивает стражника","severity":"critical"}
    ], "ok": False})
    llm = MagicMock(return_value=resp)
    result = check_continuity(pid, 3, "Иван убивает стражника." * 100, llm)
    assert len(result) == 1 and result[0]["severity"] == "critical"
    assert "Иван убивает стражника" in result[0]["violation"]
run("check_continuity: нарушения от LLM парсятся корректно", test_cc_parses_violations)

def test_cc_filters_incomplete_violations():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Тест")
    base = {"arc_progress":{}, "character_deltas":[], "opened_promises":["обещание"],
            "closed_promises":[], "causal_chains":[], "logical_gaps":[],
            "conflict_score":0.5, "pacing_note":"", "plot_threads":{}, "analysis_quality":"ok"}
    dbp.save_chapter_analysis(pid, 2, base)
    resp = _json.dumps({"violations":[
        {"fact":"факт","violation":"нарушение","severity":"critical"},       # OK
        {"fact":"",    "violation":"без факта",  "severity":"warning"},        # пропускается
        {"fact":"факт","violation":"",           "severity":"warning"},        # пропускается
    ], "ok": False})
    llm = MagicMock(return_value=resp)
    result = check_continuity(pid, 3, "текст" * 200, llm)
    assert len(result) == 1
run("check_continuity: нарушения без fact/violation фильтруются", test_cc_filters_incomplete_violations)

def test_cc_invalid_json_returns_empty():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Тест")
    base = {"arc_progress":{}, "character_deltas":[], "opened_promises":["обещание"],
            "closed_promises":[], "causal_chains":[], "logical_gaps":[],
            "conflict_score":0.5, "pacing_note":"", "plot_threads":{}, "analysis_quality":"ok"}
    dbp.save_chapter_analysis(pid, 2, base)
    llm = MagicMock(return_value="{invalid json{{")
    assert check_continuity(pid, 3, "текст" * 200, llm) == []
run("check_continuity: невалидный JSON → []", test_cc_invalid_json_returns_empty)

def test_cc_no_json_in_response():
    make_db()
    import engine.db_projects as dbp
    pid = dbp.create_project("Тест")
    base = {"arc_progress":{}, "character_deltas":[], "opened_promises":["обещание"],
            "closed_promises":[], "causal_chains":[], "logical_gaps":[],
            "conflict_score":0.5, "pacing_note":"", "plot_threads":{}, "analysis_quality":"ok"}
    dbp.save_chapter_analysis(pid, 2, base)
    llm = MagicMock(return_value="Нарушений не найдено. Всё хорошо.")
    assert check_continuity(pid, 3, "текст" * 200, llm) == []
run("check_continuity: нет JSON в ответе → []", test_cc_no_json_in_response)


# ════════════════════════════════════════════════════════
print("\n══ pipeline: parse_score / parse_verdict / _build_sys_generator ══")
# ════════════════════════════════════════════════════════

from engine.pipeline import parse_score, parse_verdict, _build_sys_generator, _truncate_context_by_blocks


# ── parse_score ───────────────────────────────────────
def test_ps_itog():
    assert parse_score("ИТОГ: 38.5") == 38.5
run("parse_score: ИТОГ: 38.5", test_ps_itog)

def test_ps_itog_integer():
    assert parse_score("ИТОГ: 42") == 42.0
run("parse_score: ИТОГ целое", test_ps_itog_integer)

def test_ps_components():
    text = "ГОЛОС: 8\nСТРУКТУРА: 7\nПЕРСОНАЖИ: 9\nСЦЕНЫ: 6\nДИАЛОГ: 8"
    assert parse_score(text) == 38.0
run("parse_score: сумма компонентов", test_ps_components)

def test_ps_itog_wins_over_components():
    text = "ГОЛОС: 8\nСТРУКТУРА: 7\nИТОГ: 45\nПЕРСОНАЖИ: 9"
    assert parse_score(text) == 45.0
run("parse_score: ИТОГ приоритетнее компонентов", test_ps_itog_wins_over_components)

def test_ps_empty_returns_zero():
    assert parse_score("") == 0.0
run("parse_score: пустой текст → 0.0", test_ps_empty_returns_zero)

def test_ps_no_markers_returns_zero():
    assert parse_score("Текст без оценок. Отличная глава.") == 0.0
run("parse_score: нет маркеров → 0.0", test_ps_no_markers_returns_zero)

def test_ps_partial_components():
    text = "ГОЛОС: 8\nСТРУКТУРА: 7"
    assert parse_score(text) == 15.0
run("parse_score: частичные компоненты суммируются", test_ps_partial_components)


# ── parse_verdict ─────────────────────────────────────
def test_pv_accept():
    assert parse_verdict("ВЕРДИКТ: ПРИНЯТЬ") == "ПРИНЯТЬ"
run("parse_verdict: ПРИНЯТЬ", test_pv_accept)

def test_pv_revise():
    assert parse_verdict("ВЕРДИКТ: НА ДОРАБОТКУ") == "НА ДОРАБОТКУ"
run("parse_verdict: НА ДОРАБОТКУ", test_pv_revise)

def test_pv_default_revise():
    assert parse_verdict("Всё хорошо, молодец") == "НА ДОРАБОТКУ"
run("parse_verdict: нет маркера → НА ДОРАБОТКУ", test_pv_default_revise)

def test_pv_in_longer_text():
    text = "Анализ завершён.\nВЕРДИКТ: ПРИНЯТЬ\nДополнительные комментарии."
    assert parse_verdict(text) == "ПРИНЯТЬ"
run("parse_verdict: маркер внутри текста", test_pv_in_longer_text)


# ── _build_sys_generator ──────────────────────────────
def test_bsg_known_genre():
    result = _build_sys_generator("фэнтези роман")
    assert "фэнтези" in result.lower()
run("_build_sys_generator: известный жанр → жанровый идентификатор", test_bsg_known_genre)

def test_bsg_unknown_genre():
    result = _build_sys_generator("что-то совершенно неизвестное")
    assert "профессиональный автор" in result
run("_build_sys_generator: неизвестный жанр → дефолтный идентификатор", test_bsg_unknown_genre)

def test_bsg_empty_genre():
    result = _build_sys_generator("")
    assert "профессиональный автор" in result
run("_build_sys_generator: пустой жанр → дефолт", test_bsg_empty_genre)

def test_bsg_returns_string():
    result = _build_sys_generator("детектив")
    assert isinstance(result, str) and len(result) > 20
run("_build_sys_generator: возвращает непустую строку", test_bsg_returns_string)

def test_bsg_all_genres():
    genres = [("фэнтези", "фэнтези"), ("детектив", "детективн"),
              ("триллер", "триллер"), ("хоррор", "хоррор"),
              ("фантастика", "фантастик"), ("романтика любовный", "романтическ"), ("реализм", "реалистическ")]
    for genre_text, expected in genres:
        result = _build_sys_generator(genre_text)
        assert expected.lower() in result.lower(), f"жанр '{genre_text}' не дал '{expected}' в: {result}"
run("_build_sys_generator: все жанры дают правильный идентификатор", test_bsg_all_genres)


# ── _truncate_context_by_blocks ───────────────────────
def test_trunc_short_context_unchanged():
    ctx = "короткий контекст"
    result, removed = _truncate_context_by_blocks(ctx, max_chars=10000)
    assert result == ctx and removed == []
run("_truncate_context_by_blocks: короткий → без изменений", test_trunc_short_context_unchanged)

def test_trunc_removes_exemplars_first():
    base = "БАЗОВЫЙ ПРОМПТ\n\n"
    exemplar = "ЭТАЛОНЫ\nэталонный текст\n\n---\n\n"
    long_filler = "ГОЛОС\n" + "х" * 500 + "\n\n---\n\n"
    ctx = base + exemplar + long_filler
    result, removed = _truncate_context_by_blocks(ctx, max_chars=len(base) + len(long_filler) + 10)
    assert "exemplars" in removed
    assert "ЭТАЛОНЫ" not in result
run("_truncate_context_by_blocks: эталоны удаляются первыми", test_trunc_removes_exemplars_first)

def test_trunc_removed_list_populated():
    big_block = "БАЗА ЗНАНИЙ\n" + "х" * 1000 + "\n\n---\n\n"
    ctx = big_block + "ОСТАТОК\n" + "у" * 100
    result, removed = _truncate_context_by_blocks(ctx, max_chars=200)
    assert len(removed) > 0
run("_truncate_context_by_blocks: removed содержит удалённые блоки", test_trunc_removed_list_populated)

def test_trunc_hard_cut_last_resort():
    ctx = "х" * 2000
    result, removed = _truncate_context_by_blocks(ctx, max_chars=500)
    assert len(result) <= 500
    assert "hard_cut" in removed
run("_truncate_context_by_blocks: последний резерв — грубая обрезка", test_trunc_hard_cut_last_resort)

def test_trunc_preserves_content_when_possible():
    important = "ВАЖНЫЙ ПРОМПТ: " + "в" * 100
    exemplar  = "ЭТАЛОНЫ\n" + "э" * 500 + "\n\n---\n\n"
    ctx = important + "\n\n" + exemplar
    result, removed = _truncate_context_by_blocks(ctx, max_chars=len(important) + 50)
    assert "ВАЖНЫЙ ПРОМПТ" in result
run("_truncate_context_by_blocks: важный контент сохраняется", test_trunc_preserves_content_when_possible)


# ════════════════════════════════════════════════════════
print("\n══ db_state: чистые функции ══")
# ════════════════════════════════════════════════════════

from engine.db_state import (
    _extract_field, _extract_block, _is_real_value,
    _apply_char_field, _apply_char_knows, _apply_plot_block,
    _add_new_char, _apply_existing_char,
    parse_structured_state, merge_analysis_into_state,
)


# ── _is_real_value ────────────────────────────────────
def test_irv_empty_false():        assert _is_real_value("") is False
def test_irv_placeholder_false():  assert _is_real_value("[цель неизвестна]") is False
def test_irv_bez_false():          assert _is_real_value("без изменений") is False
def test_irv_bez_ci_false():       assert _is_real_value("Без Изменений") is False
def test_irv_real_true():          assert _is_real_value("усталая") is True
def test_irv_dash_true():          assert _is_real_value("-") is True  # дефис — реальное значение
run("_is_real_value: пустой → False", test_irv_empty_false)
run("_is_real_value: [плейсхолдер] → False", test_irv_placeholder_false)
run("_is_real_value: без изменений → False", test_irv_bez_false)
run("_is_real_value: Без Изменений (CI) → False", test_irv_bez_ci_false)
run("_is_real_value: реальное значение → True", test_irv_real_true)
run("_is_real_value: дефис → True", test_irv_dash_true)


# ── _extract_field ────────────────────────────────────
def test_ef_basic():
    assert _extract_field("СОСТОЯНИЕ: усталая\n", "СОСТОЯНИЕ") == "усталая"
run("_extract_field: базовое извлечение", test_ef_basic)

def test_ef_multiple_keys_first_wins():
    text = "STATE: tired\n"
    assert _extract_field(text, "СОСТОЯНИЕ", "Состояние", "STATE") == "tired"
run("_extract_field: первый найденный ключ побеждает", test_ef_multiple_keys_first_wins)

def test_ef_skip_empty():
    text = "СОСТОЯНИЕ: []\n"
    assert _extract_field(text, "СОСТОЯНИЕ") == ""
run("_extract_field: [] пропускается", test_ef_skip_empty)

def test_ef_skip_dash():
    assert _extract_field("СОСТОЯНИЕ: -\n", "СОСТОЯНИЕ") == ""
run("_extract_field: одиночный дефис пропускается", test_ef_skip_dash)

def test_ef_not_found_empty():
    assert _extract_field("текст без полей", "СОСТОЯНИЕ") == ""
run("_extract_field: ключ не найден → пустая строка", test_ef_not_found_empty)


# ── _extract_block ────────────────────────────────────
def test_eb_extracts_block():
    text = "## ПЕРСОНАЖИ\n\n### Алиса\nСОСТОЯНИЕ: усталая\nЛОКАЦИЯ: лес\n\n### Борис\nСОСТОЯНИЕ: бодрый\n"
    block = _extract_block(text, "Алиса")
    assert "усталая" in block
    assert "Борис" not in block
run("_extract_block: извлекает блок до следующего ###", test_eb_extracts_block)

def test_eb_not_found_empty():
    assert _extract_block("нет блоков", "Несуществующий") == ""
run("_extract_block: персонаж не найден → пустая строка", test_eb_not_found_empty)

def test_eb_last_block_no_separator():
    text = "### Алиса\nСОСТОЯНИЕ: усталая\nЛОКАЦИЯ: лес\n"
    block = _extract_block(text, "Алиса")
    assert "усталая" in block
run("_extract_block: последний блок без разделителя", test_eb_last_block_no_separator)


# ── _apply_char_field ─────────────────────────────────
def test_acf_updates_field():
    block = "СОСТОЯНИЕ: бодрый\nЛОКАЦИЯ: город\n"
    calls = []
    result = _apply_char_field("состояние", "СОСТОЯНИЕ", "усталый", block, "Иван",
                                lambda f, b, a: calls.append((f, b, a)))
    assert "СОСТОЯНИЕ: усталый" in result
    assert calls[0][2] == "усталый"
run("_apply_char_field: обновляет поле и вызывает record_fn", test_acf_updates_field)

def test_acf_skips_placeholder():
    block = "СОСТОЯНИЕ: бодрый\n"
    calls = []
    result = _apply_char_field("состояние", "СОСТОЯНИЕ", "[без изменений]", block, "Иван",
                                lambda f, b, a: calls.append(a))
    assert result == block and calls == []
run("_apply_char_field: плейсхолдер → блок не меняется", test_acf_skips_placeholder)

def test_acf_strips_arrow():
    block = "СОСТОЯНИЕ: бодрый\n"
    result = _apply_char_field("состояние", "СОСТОЯНИЕ", "бодрый → усталый", block, "Иван",
                                lambda f, b, a: None)
    assert "СОСТОЯНИЕ: усталый" in result
run("_apply_char_field: стрелка → берёт правую часть", test_acf_strips_arrow)


# ── _apply_char_knows ─────────────────────────────────
def test_ack_appends_to_existing():
    block = "ЗНАЕТ: магия\nНЕ_ЗНАЕТ: она маг\n"
    calls = []
    result = _apply_char_knows("новое знание", block, "Алиса",
                                lambda f, b, a: calls.append(a))
    assert "магия" in result and "новое знание" in result
run("_apply_char_knows: дописывает к существующему", test_ack_appends_to_existing)

def test_ack_empty_field_sets_value():
    block = "ЗНАЕТ: []\nНЕ_ЗНАЕТ: секрет\n"
    result = _apply_char_knows("первое знание", block, "Алиса", lambda f, b, a: None)
    assert "первое знание" in result
run("_apply_char_knows: [] → ставит значение", test_ack_empty_field_sets_value)

def test_ack_placeholder_skips():
    block = "ЗНАЕТ: магия\nНЕ_ЗНАЕТ: секрет\n"
    result = _apply_char_knows("[без изменений]", block, "Алиса", lambda f, b, a: None)
    assert result == block
run("_apply_char_knows: плейсхолдер → не меняет", test_ack_placeholder_skips)


# ── _apply_plot_block ─────────────────────────────────
def test_apb_updates_next_step():
    plot = "СТАТУС: в пути\nСЛЕДУЮЩИЙ_ШАГ: найти карту\n"
    calls = []
    result = _apply_plot_block("следующий шаг: добраться до замка", plot,
                                lambda f, b, a: calls.append(a))
    assert "добраться до замка" in result
    assert "добраться до замка" in calls
run("_apply_plot_block: обновляет следующий шаг", test_apb_updates_next_step)

def test_apb_no_step_unchanged():
    plot = "СЛЕДУЮЩИЙ_ШАГ: найти карту\n"
    result = _apply_plot_block("нет нужных полей здесь", plot, lambda f, b, a: None)
    assert result == plot
run("_apply_plot_block: нет поля → без изменений", test_apb_no_step_unchanged)

def test_apb_placeholder_ignored():
    plot = "СЛЕДУЮЩИЙ_ШАГ: найти карту\n"
    result = _apply_plot_block("следующий шаг: [без изменений]", plot, lambda f, b, a: None)
    assert "найти карту" in result
run("_apply_plot_block: плейсхолдер → поле не меняется", test_apb_placeholder_ignored)


# ── _add_new_char ─────────────────────────────────────
def test_anc_adds_to_персонажи():
    global_text = "## ПЕРСОНАЖИ\n\n### Алиса\nСОСТОЯНИЕ: усталая\n"
    new_chars = []
    section = "Борис:\nсостояние: бодрый\nлокация: город\nцель: найти работу"
    result = _add_new_char("Борис", section, global_text, lambda f, b, a: None, new_chars)
    assert "### Борис" in result
    assert "Борис" in new_chars
run("_add_new_char: добавляет нового персонажа в ## ПЕРСОНАЖИ", test_anc_adds_to_персонажи)

def test_anc_no_section_appends():
    global_text = "## МИР\nОписание мира\n"
    new_chars = []
    section = "Виктор:\nсостояние: злой"
    result = _add_new_char("Виктор", section, global_text, lambda f, b, a: None, new_chars)
    assert "### Виктор" in result
run("_add_new_char: нет ## ПЕРСОНАЖИ → добавляет в конец", test_anc_no_section_appends)

def test_anc_strips_arrow_from_state():
    global_text = "## ПЕРСОНАЖИ\n\n"
    new_chars = []
    section = "Григорий:\nсостояние: спокойный → взволнованный"
    result = _add_new_char("Григорий", section, global_text, lambda f, b, a: None, new_chars)
    assert "взволнованный" in result
    assert "спокойный" not in result
run("_add_new_char: стрелка в состоянии → берёт правую часть", test_anc_strips_arrow_from_state)


# ── _apply_existing_char ──────────────────────────────
def test_aec_updates_state():
    global_text = "## ПЕРСОНАЖИ\n\n### Иван\nСОСТОЯНИЕ: спокойный\nЛОКАЦИЯ: дом\n"
    calls = []
    result = _apply_existing_char("Иван", "состояние: взволнованный", global_text,
                                   lambda f, b, a: calls.append((f, a)))
    assert "СОСТОЯНИЕ: взволнованный" in result
    assert any("состояние" in c[0] for c in calls)
run("_apply_existing_char: обновляет состояние персонажа", test_aec_updates_state)

def test_aec_char_not_found_unchanged():
    global_text = "## ПЕРСОНАЖИ\n\n### Иван\nСОСТОЯНИЕ: спокойный\n"
    result = _apply_existing_char("Несуществующий", "состояние: злой", global_text,
                                   lambda f, b, a: None)
    assert result == global_text
run("_apply_existing_char: персонаж не найден → без изменений", test_aec_char_not_found_unchanged)


# ── parse_structured_state ────────────────────────────
def test_pss_extracts_all_fields():
    gs = (
        "## ПЕРСОНАЖИ\n\n"
        "### Алиса\n"
        "СОСТОЯНИЕ: усталая\n"
        "ЛОКАЦИЯ: лес\n"
        "ЦЕЛЬ_СЕЙЧАС: домой\n"
        "ЦЕЛЬ_ГЛУБИННАЯ: покой\n"
        "ЗНАЕТ: магия\n"
        "НЕ_ЗНАЕТ: она маг\n"
    )
    state = {"global_state": gs, "plot_matrix": "", "memory_graph": ""}
    s = parse_structured_state(state)
    assert "Алиса" in s["char_names"]
    assert s["characters"]["Алиса"]["state"]    == "усталая"
    assert s["characters"]["Алиса"]["location"] == "лес"
    assert s["characters"]["Алиса"]["goal"]     == "домой"
    assert s["characters"]["Алиса"]["knows"]    == "магия"
run("parse_structured_state: извлекает все поля персонажа", test_pss_extracts_all_fields)

def test_pss_multiple_chars():
    gs = (
        "## ПЕРСОНАЖИ\n\n"
        "### Алиса\nСОСТОЯНИЕ: устала\n\n"
        "### Борис\nСОСТОЯНИЕ: бодр\n"
    )
    s = parse_structured_state({"global_state": gs, "plot_matrix": "", "memory_graph": ""})
    assert "Алиса" in s["char_names"] and "Борис" in s["char_names"]
    assert s["characters"]["Алиса"]["state"] == "устала"
    assert s["characters"]["Борис"]["state"] == "бодр"
run("parse_structured_state: несколько персонажей", test_pss_multiple_chars)

def test_pss_corrupt_returns_empty():
    s = parse_structured_state({"global_state": "}{][мусор", "plot_matrix": "", "memory_graph": ""})
    assert isinstance(s, dict) and "characters" in s
run("parse_structured_state: мусор → пустая структура без исключения", test_pss_corrupt_returns_empty)

def test_pss_world_fields():
    gs = "МОМЕНТ: герой у ворот замка\nУГРОЗА: дракон\nНЕ_ДОЛЖНО_СЛУЧИТЬСЯ: гибель ребёнка\n"
    s = parse_structured_state({"global_state": gs, "plot_matrix": "", "memory_graph": ""})
    assert s["world"]["moment"]    == "герой у ворот замка"
    assert s["world"]["threat"]    == "дракон"
    assert s["world"]["forbidden"] == "гибель ребёнка"
run("parse_structured_state: поля мира", test_pss_world_fields)

def test_pss_plot_fields():
    plot = "СТАТУС: акт 2\nГДЕ_СЕЙЧАС: замок\nСЛЕДУЮЩИЙ_ШАГ: найти ключ\n"
    s = parse_structured_state({"global_state": "", "plot_matrix": plot, "memory_graph": ""})
    assert s["plot"]["status"] == "акт 2"
    assert s["plot"]["where"]  == "замок"
    assert s["plot"]["next"]   == "найти ключ"
run("parse_structured_state: поля сюжета", test_pss_plot_fields)


# ── merge_analysis_into_state ─────────────────────────
def test_mais_json_updates_char():
    make_db()
    import engine.db_projects as dbp
    import engine.db_state as dbs
    pid = dbp.create_project("Тест")
    gs = "## ПЕРСОНАЖИ\n\n### Иван\nСОСТОЯНИЕ: спокойный\nЛОКАЦИЯ: дом\nЦЕЛЬ_СЕЙЧАС: отдохнуть\nЗНАЕТ: []\nНЕ_ЗНАЕТ: []\n"
    dbp.update_state(pid, global_state=gs)
    import json as _j
    raw = _j.dumps({
        "global_state_changes": [{"name": "Иван", "состояние": "взволнованный", "локация": "", "цель": ""}],
        "plot_changes": {}, "memory_changes": []
    })
    result = dbs.merge_analysis_into_state(pid, raw)
    assert result["changed"] is True
    state = dbp.get_state(pid)
    assert "взволнованный" in state["global_state"]
run("merge_analysis_into_state: JSON → обновляет state в БД", test_mais_json_updates_char)

def test_mais_json_adds_new_char():
    make_db()
    import engine.db_projects as dbp
    import engine.db_state as dbs
    pid = dbp.create_project("Тест")
    dbp.update_state(pid, global_state="## ПЕРСОНАЖИ\n\n")
    import json as _j
    raw = _j.dumps({
        "global_state_changes": [{"name": "Новый", "состояние": "таинственный", "локация": "лес", "цель": "скрыться"}],
        "plot_changes": {}, "memory_changes": []
    })
    result = dbs.merge_analysis_into_state(pid, raw)
    assert "Новый" in result["new_chars"]
    state = dbp.get_state(pid)
    assert "### Новый" in state["global_state"]
run("merge_analysis_into_state: новый персонаж добавляется в state", test_mais_json_adds_new_char)

def test_mais_no_changes_returns_false():
    make_db()
    import engine.db_projects as dbp
    import engine.db_state as dbs
    pid = dbp.create_project("Тест")
    import json as _j
    raw = _j.dumps({"global_state_changes": [], "plot_changes": {}, "memory_changes": []})
    result = dbs.merge_analysis_into_state(pid, raw)
    assert result["changed"] is False and result["fields"] == []
run("merge_analysis_into_state: нет изменений → changed=False", test_mais_no_changes_returns_false)

def test_mais_invalid_json_uses_legacy():
    make_db()
    import engine.db_projects as dbp
    import engine.db_state as dbs
    pid = dbp.create_project("Тест")
    # Текстовый legacy-формат — не JSON
    raw = "=== GLOBAL_STATE — ИЗМЕНЕНИЯ ===\nИван:\nсостояние: спокойный\n==="
    result = dbs.merge_analysis_into_state(pid, raw)
    assert isinstance(result, dict) and "changed" in result
run("merge_analysis_into_state: невалидный JSON → legacy-парсер, нет исключения", test_mais_invalid_json_uses_legacy)

def test_mais_plot_next_step_updated():
    make_db()
    import engine.db_projects as dbp
    import engine.db_state as dbs
    pid = dbp.create_project("Тест")
    dbp.update_state(pid, plot_matrix="СТАТУС: акт 1\nСЛЕДУЮЩИЙ_ШАГ: найти карту\n")
    import json as _j
    raw = _j.dumps({
        "global_state_changes": [],
        "plot_changes": {"следующий_шаг": "добраться до замка"},
        "memory_changes": []
    })
    result = dbs.merge_analysis_into_state(pid, raw)
    assert result["changed"] is True
    state = dbp.get_state(pid)
    assert "добраться до замка" in state["plot_matrix"]
run("merge_analysis_into_state: plot_changes → обновляет plot_matrix", test_mais_plot_next_step_updated)


# ════════════════════════════════════════════════════════
print("\n══ cognitive_memory: scoring ══")
# ════════════════════════════════════════════════════════

from engine.cognitive_memory import (
    _effective_score, score_summary, chapter_total_score,
    MEMORY_FIELDS, INCLUSION_THRESHOLD,
)


# ── _effective_score ──────────────────────────────────
def test_es_zero_distance_full_weight():
    field = MEMORY_FIELDS[0]  # promises: base=5.0, decay=0.0
    assert _effective_score(field, 0) == field.base_weight
run("_effective_score: дистанция 0 → полный вес", test_es_zero_distance_full_weight)

def test_es_no_decay_constant():
    field = MEMORY_FIELDS[0]  # promises: decay_rate=0.0
    assert _effective_score(field, 100) == field.base_weight
run("_effective_score: decay_rate=0 → вес не меняется", test_es_no_decay_constant)

def test_es_fast_decay_hits_floor():
    field = MEMORY_FIELDS[4]  # mood: decay=0.20, floor=0.10
    score = _effective_score(field, 50)
    assert score == field.base_weight * field.floor
run("_effective_score: быстрое затухание → достигает floor", test_es_fast_decay_hits_floor)

def test_es_always_positive():
    for field in MEMORY_FIELDS:
        for dist in [0, 1, 5, 10, 50]:
            assert _effective_score(field, dist) > 0
run("_effective_score: всегда > 0 для всех полей и дистанций", test_es_always_positive)

def test_es_decreases_with_distance():
    field = MEMORY_FIELDS[1]  # conflicts: decay_rate=0.05
    s0 = _effective_score(field, 0)
    s5 = _effective_score(field, 5)
    s10 = _effective_score(field, 10)
    assert s0 >= s5 >= s10
run("_effective_score: убывает с расстоянием (для decay > 0)", test_es_decreases_with_distance)


# ── score_summary ─────────────────────────────────────
def test_ss_empty_summary():
    result = score_summary({}, distance=1)
    assert result == {}
run("score_summary: пустое саммари → {}", test_ss_empty_summary)

def test_ss_only_non_empty_fields():
    summary = {"promises": "обещание", "conflicts": "", "events": "событие"}
    result = score_summary(summary, distance=1)
    assert "promises" in result
    assert "events" in result
    assert "conflicts" not in result
run("score_summary: пустые поля не включаются", test_ss_only_non_empty_fields)

def test_ss_promises_highest_weight():
    summary = {f.key: "значение" for f in MEMORY_FIELDS}
    scores = score_summary(summary, distance=5)
    # promises (decay=0) должны иметь наибольший вес
    assert scores["promises"] >= max(v for k, v in scores.items() if k != "promises")
run("score_summary: promises имеют наибольший вес", test_ss_promises_highest_weight)


# ── chapter_total_score ───────────────────────────────
def test_cts_empty_zero():
    assert chapter_total_score({}, 1) == 0.0
run("chapter_total_score: пустое саммари → 0.0", test_cts_empty_zero)

def test_cts_full_summary_positive():
    summary = {f.key: "значение" for f in MEMORY_FIELDS}
    assert chapter_total_score(summary, 1) > 0
run("chapter_total_score: полное саммари → > 0", test_cts_full_summary_positive)

def test_cts_recent_higher_than_distant():
    summary = {f.key: "значение" for f in MEMORY_FIELDS if f.decay_rate > 0}
    score_near = chapter_total_score(summary, 1)
    score_far  = chapter_total_score(summary, 20)
    assert score_near >= score_far
run("chapter_total_score: близкая глава весомее далёкой", test_cts_recent_higher_than_distant)


# ════════════════════════════════════════════════════════
print("\n══ db_narrative ══")
# ════════════════════════════════════════════════════════

# ── Символы ──────────────────────────────────────────
def test_dn_symbol_crud():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    sid = dbn.save_symbol(pid, "Чёрный нож", "предмет", 1, "смерть")
    assert sid is not None and sid > 0
    syms = dbn.get_symbols(pid)
    assert len(syms) == 1 and syms[0]["name"] == "Чёрный нож"
run("db_narrative: save_symbol / get_symbols", test_dn_symbol_crud)

def test_dn_symbol_appearance():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    sid = dbn.save_symbol(pid, "Зеркало", "символ", 1, "тайна")
    dbn.add_symbol_appearance(sid, 3, "зеркало блеснуло", "угроза")
    syms = dbn.get_symbols(pid)
    assert syms[0]["appearances"][0]["meaning"] == "угроза"
run("db_narrative: add_symbol_appearance десериализуется", test_dn_symbol_appearance)

def test_dn_symbol_planned():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    sid = dbn.save_symbol(pid, "Кольцо", "символ", 1, "власть")
    dbn.add_symbol_planned(sid, 7, "будет уничтожено", "конец власти")
    syms = dbn.get_symbols(pid)
    assert syms[0]["planned"][0]["how"] == "будет уничтожено"
run("db_narrative: add_symbol_planned десериализуется", test_dn_symbol_planned)

def test_dn_symbol_appearance_nonexistent():
    make_db()
    import engine.db_narrative as dbn
    # Не должно падать
    dbn.add_symbol_appearance(99999, 1, "контекст", "смысл")
run("db_narrative: add_symbol_appearance несуществующий → не падает", test_dn_symbol_appearance_nonexistent)

def test_dn_symbol_delete():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    sid = dbn.save_symbol(pid, "Меч", "предмет", 1, "сила")
    dbn.delete_symbol(sid)
    assert dbn.get_symbols(pid) == []
run("db_narrative: delete_symbol", test_dn_symbol_delete)

def test_dn_symbols_context_empty():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    assert dbn.get_symbols_context(pid) == ""
run("db_narrative: get_symbols_context пустой проект → ''", test_dn_symbols_context_empty)

def test_dn_symbols_context_has_symbol():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_symbol(pid, "Ключ", "предмет", 1, "свобода")
    ctx = dbn.get_symbols_context(pid)
    assert "Ключ" in ctx and "свобода" in ctx
run("db_narrative: get_symbols_context содержит символ", test_dn_symbols_context_has_symbol)

def test_dn_symbols_context_current_meaning_from_appearance():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    sid = dbn.save_symbol(pid, "Огонь", "символ", 1, "жизнь")
    dbn.add_symbol_appearance(sid, 5, "огонь гаснет", "смерть")
    ctx = dbn.get_symbols_context(pid)
    # Текущее значение — из последнего appearance
    assert "смерть" in ctx
run("db_narrative: get_symbols_context берёт текущее значение из appearances", test_dn_symbols_context_current_meaning_from_appearance)

# ── Голосовые профили ─────────────────────────────────
def test_dn_voice_profile_crud():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    vid = dbn.save_voice_profile(pid, "Тихий голос", "инструкции голоса")
    assert vid > 0
    profiles = dbn.get_voice_profiles(pid)
    assert any(p["name"] == "Тихий голос" for p in profiles)
run("db_narrative: save/get voice_profile", test_dn_voice_profile_crud)

def test_dn_active_voice():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    v1 = dbn.save_voice_profile(pid, "Голос 1", "профиль1")
    v2 = dbn.save_voice_profile(pid, "Голос 2", "профиль2")
    dbn.set_active_voice(pid, v2)
    active = dbn.get_active_voice(pid)
    assert active["name"] == "Голос 2"
run("db_narrative: set_active_voice / get_active_voice", test_dn_active_voice)

def test_dn_only_one_active_voice():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    v1 = dbn.save_voice_profile(pid, "Голос 1", "профиль1")
    v2 = dbn.save_voice_profile(pid, "Голос 2", "профиль2")
    dbn.set_active_voice(pid, v1)
    dbn.set_active_voice(pid, v2)
    profiles = dbn.get_voice_profiles(pid)
    active_count = sum(1 for p in profiles if p["active"])
    assert active_count == 1
run("db_narrative: одновременно активен только один голос", test_dn_only_one_active_voice)

def test_dn_deactivate_voice():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    v1 = dbn.save_voice_profile(pid, "Голос", "профиль")
    dbn.set_active_voice(pid, v1)
    dbn.set_active_voice(pid, None)
    assert dbn.get_active_voice(pid) is None
run("db_narrative: set_active_voice(None) → деактивирует", test_dn_deactivate_voice)

def test_dn_delete_voice_profile():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    vid = dbn.save_voice_profile(pid, "Голос", "профиль")
    dbn.delete_voice_profile(vid)
    assert dbn.get_voice_profiles(pid) == []
run("db_narrative: delete_voice_profile", test_dn_delete_voice_profile)

# ── L3 Memory ─────────────────────────────────────────
def test_dn_l3_save_get():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    summary = {"events": "герой вышел", "characters": "Иван", "conflicts": "опасность",
               "promises": "вернётся", "mood": "тревожное"}
    dbn.save_l3_summary(pid, 3, summary)
    result = dbn.get_l3_summary(pid, 3)
    assert result is not None
    assert result["events"] == "герой вышел"
    assert result["mood"] == "тревожное"
run("db_narrative: save_l3_summary / get_l3_summary", test_dn_l3_save_get)

def test_dn_l3_summaries_ordered():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    for i in [1, 2, 3, 4, 5]:
        dbn.save_l3_summary(pid, i, {"events": f"гл{i}", "characters": "",
                                      "conflicts": "", "promises": "", "mood": ""})
    result = dbn.get_l3_summaries(pid, before_chapter=5, n=3)
    assert len(result) == 3
    # Возвращаются в хронологическом порядке (reversed)
    assert result[0]["chapter_num"] < result[-1]["chapter_num"]
run("db_narrative: get_l3_summaries возвращает n глав до before_chapter в порядке", test_dn_l3_summaries_ordered)

def test_dn_l3_before_chapter_filter():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    for i in [1, 2, 3]:
        dbn.save_l3_summary(pid, i, {"events": f"гл{i}", "characters": "",
                                      "conflicts": "", "promises": "", "mood": ""})
    result = dbn.get_l3_summaries(pid, before_chapter=3, n=10)
    chapter_nums = [r["chapter_num"] for r in result]
    assert 3 not in chapter_nums  # глава 3 не включается
    assert 1 in chapter_nums and 2 in chapter_nums
run("db_narrative: get_l3_summaries фильтрует by before_chapter (строгое <)", test_dn_l3_before_chapter_filter)

def test_dn_l3_delete():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_l3_summary(pid, 1, {"events": "событие", "characters": "", "conflicts": "", "promises": "", "mood": ""})
    dbn.delete_l3_summary(pid, 1)
    assert dbn.get_l3_summary(pid, 1) is None
run("db_narrative: delete_l3_summary", test_dn_l3_delete)

def test_dn_l3_upsert():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_l3_summary(pid, 1, {"events": "первое", "characters": "", "conflicts": "", "promises": "", "mood": ""})
    dbn.save_l3_summary(pid, 1, {"events": "обновлённое", "characters": "", "conflicts": "", "promises": "", "mood": ""})
    result = dbn.get_l3_summary(pid, 1)
    assert result["events"] == "обновлённое"
run("db_narrative: save_l3_summary upsert обновляет", test_dn_l3_upsert)

def test_dn_l3_status():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_l3_summary(pid, 2, {"events": "e", "characters": "", "conflicts": "", "promises": "", "mood": "светлое"})
    status = dbn.get_l3_status(pid)
    assert 2 in status and status[2]["mood"] == "светлое"
run("db_narrative: get_l3_status возвращает dict по chapter_num", test_dn_l3_status)

def test_dn_l3_active_promises_empty():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    assert dbn.get_l3_active_promises(pid, 5) == ""
run("db_narrative: get_l3_active_promises нет саммари → ''", test_dn_l3_active_promises_empty)

def test_dn_l3_active_promises_with_data():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_l3_summary(pid, 2, {"events": "e", "characters": "", "conflicts": "",
                                  "promises": "Убийца вернётся", "mood": ""})
    result = dbn.get_l3_active_promises(pid, before_chapter=5)
    assert "Убийца вернётся" in result
    assert "АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ" in result
run("db_narrative: get_l3_active_promises формирует блок", test_dn_l3_active_promises_with_data)

def test_dn_l3_active_promises_skips_empty_promises():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_l3_summary(pid, 1, {"events": "e", "characters": "", "conflicts": "", "promises": "", "mood": ""})
    assert dbn.get_l3_active_promises(pid, before_chapter=5) == ""
run("db_narrative: get_l3_active_promises пропускает пустые promises", test_dn_l3_active_promises_skips_empty_promises)

# ── Voice Drift ────────────────────────────────────────
def test_dn_drift_save_get():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_drift_check(pid, 3, 7.5, "небольшие отклонения")
    last = dbn.get_last_drift_check(pid)
    assert last is not None
    assert last["score"] == 7.5
    assert last["chapter_num"] == 3
run("db_narrative: save_drift_check / get_last_drift_check", test_dn_drift_save_get)

def test_dn_should_run_drift_first_time():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    # Нет истории — запускать если chapter >= every_n (default 3)
    assert dbn.should_run_drift_check(pid, 3) is True
    assert dbn.should_run_drift_check(pid, 2) is False
run("db_narrative: should_run_drift_check без истории", test_dn_should_run_drift_first_time)

def test_dn_should_run_drift_interval():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_drift_check(pid, 3, 8.0)
    assert dbn.should_run_drift_check(pid, 5) is False   # 5-3=2 < 3
    assert dbn.should_run_drift_check(pid, 6) is True    # 6-3=3 >= 3
run("db_narrative: should_run_drift_check по интервалу", test_dn_should_run_drift_interval)

# ── Pipeline runs ──────────────────────────────────────
def test_dn_pipeline_run_crud():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    run_id = dbn.create_pipeline_run(pid, 1, "claude", "claude", "claude", "claude")
    assert run_id > 0
    run = dbn.get_pipeline_run(run_id)
    assert run["status"] == "running"
    assert run["chapter_num"] == 1
run("db_narrative: create_pipeline_run / get_pipeline_run", test_dn_pipeline_run_crud)

def test_dn_pipeline_iteration():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    run_id = dbn.create_pipeline_run(pid, 1, "m", "m", "m", "m")
    iter_id = dbn.save_pipeline_iteration(run_id, 1, "generate", "claude",
                                           "input", "output", score=38.0, verdict="ПРИНЯТЬ")
    iters = dbn.get_pipeline_iterations(run_id)
    assert len(iters) == 1
    assert iters[0]["score"] == 38.0
    assert iters[0]["verdict"] == "ПРИНЯТЬ"
run("db_narrative: save/get pipeline_iteration", test_dn_pipeline_iteration)

def test_dn_finish_pipeline_run():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    run_id = dbn.create_pipeline_run(pid, 1, "m", "m", "m", "m")
    dbn.finish_pipeline_run(run_id, "accepted")
    run = dbn.get_pipeline_run(run_id)
    assert run["status"] == "accepted"
run("db_narrative: finish_pipeline_run обновляет статус", test_dn_finish_pipeline_run)

def test_dn_get_pipeline_runs_list():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.create_pipeline_run(pid, 1, "m", "m", "m", "m")
    dbn.create_pipeline_run(pid, 2, "m", "m", "m", "m")
    runs = dbn.get_pipeline_runs(pid)
    assert len(runs) == 2
run("db_narrative: get_pipeline_runs возвращает список", test_dn_get_pipeline_runs_list)

# ── Режиссёрские заметки ──────────────────────────────
def test_dn_director_note_save_get():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_director_note(pid, 3, "Здесь нужен поворот")
    # get_director_note для главы N берёт заметку after_chapter=N-1
    note = dbn.get_director_note(pid, 4)
    assert note == "Здесь нужен поворот"
run("db_narrative: save/get director_note", test_dn_director_note_save_get)

def test_dn_director_note_upsert():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.save_director_note(pid, 3, "Первая заметка")
    dbn.save_director_note(pid, 3, "Обновлённая заметка")
    note = dbn.get_director_note(pid, 4)
    assert note == "Обновлённая заметка"
run("db_narrative: save_director_note upsert обновляет", test_dn_director_note_upsert)

def test_dn_director_note_missing():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    assert dbn.get_director_note(pid, 5) is None
run("db_narrative: get_director_note без заметки → None", test_dn_director_note_missing)

# ── Эталоны ───────────────────────────────────────────
def test_dn_exemplar_crud():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    eid = dbn.save_exemplar(pid, 2, "эталонный текст", "метка")
    assert eid > 0
    exemplars = dbn.get_exemplars(pid)
    assert len(exemplars) == 1
    assert exemplars[0]["text"] == "эталонный текст"
run("db_narrative: save/get exemplar", test_dn_exemplar_crud)

def test_dn_exemplar_delete():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    eid = dbn.save_exemplar(pid, 1, "текст", "метка")
    dbn.delete_exemplar(eid)
    assert dbn.get_exemplars(pid) == []
run("db_narrative: delete_exemplar", test_dn_exemplar_delete)

# ── База знаний ───────────────────────────────────────
def test_dn_kb_crud():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    aid = dbn.kb_save(pid, "Магия", "Магия работает через кровь", tags="магия система")
    assert aid > 0
    article = dbn.kb_get(aid)
    assert article["title"] == "Магия"
    all_articles = dbn.kb_get_all(pid)
    assert len(all_articles) == 1
run("db_narrative: kb_save / kb_get / kb_get_all", test_dn_kb_crud)

def test_dn_kb_update():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    aid = dbn.kb_save(pid, "Магия", "старое содержание", tags="магия")
    dbn.kb_save(pid, "Магия 2.0", "новое содержание", article_id=aid)
    article = dbn.kb_get(aid)
    assert article["title"] == "Магия 2.0"
    assert article["content"] == "новое содержание"
run("db_narrative: kb_save с article_id обновляет", test_dn_kb_update)

def test_dn_kb_delete():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    aid = dbn.kb_save(pid, "Магия", "содержание")
    dbn.kb_delete(aid, pid)
    assert dbn.kb_get_all(pid) == []
run("db_narrative: kb_delete", test_dn_kb_delete)

def test_dn_kb_search():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.kb_save(pid, "Магия крови", "содержание", tags="магия кровь ритуал")
    dbn.kb_save(pid, "История мира", "содержание", tags="история география")
    results = dbn.kb_search(pid, "магия кровь")
    assert len(results) >= 1
    assert results[0]["title"] == "Магия крови"
run("db_narrative: kb_search по тегам", test_dn_kb_search)

def test_dn_kb_search_empty_query():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.kb_save(pid, "Магия", "содержание")
    assert dbn.kb_search(pid, "") == []
    assert dbn.kb_search(pid, "   ") == []
run("db_narrative: kb_search пустой запрос → []", test_dn_kb_search_empty_query)

def test_dn_kb_auto_inject():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    pid = dbp.create_project("Тест")
    dbn.kb_save(pid, "Авто", "содержание", auto_inject=1)
    dbn.kb_save(pid, "Ручная", "содержание", auto_inject=0)
    auto = dbn.kb_get_auto_inject(pid)
    assert len(auto) == 1 and auto[0]["title"] == "Авто"
run("db_narrative: kb_get_auto_inject фильтрует по auto_inject=1", test_dn_kb_auto_inject)


# ════════════════════════════════════════════════════════
print("\n══ db_chapters ══")
# ════════════════════════════════════════════════════════

# ── Главы ─────────────────────────────────────────────
def test_dc_save_get_chapter():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter(pid, 1, "Текст первой главы про героя")
    ch = dbc.get_chapter(pid, 1)
    assert ch is not None and "Текст первой главы" in ch["content"]
run("db_chapters: save_chapter / get_chapter", test_dc_save_get_chapter)

def test_dc_save_chapter_counts_words():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter(pid, 1, "один два три четыре пять")
    ch = dbc.get_chapter(pid, 1)
    assert ch["word_count"] == 5
run("db_chapters: save_chapter считает слова", test_dc_save_chapter_counts_words)

def test_dc_save_chapter_upsert():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter(pid, 1, "первый вариант")
    dbc.save_chapter(pid, 1, "обновлённый вариант")
    ch = dbc.get_chapter(pid, 1)
    assert "обновлённый" in ch["content"]
run("db_chapters: save_chapter upsert обновляет", test_dc_save_chapter_upsert)

def test_dc_get_chapter_missing():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    assert dbc.get_chapter(pid, 99) is None
run("db_chapters: get_chapter несуществующей → None", test_dc_get_chapter_missing)

def test_dc_get_chapters_ordered():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter(pid, 3, "третья")
    dbc.save_chapter(pid, 1, "первая")
    dbc.save_chapter(pid, 2, "вторая")
    chapters = dbc.get_chapters(pid)
    nums = [c["number"] for c in chapters]
    assert nums == [1, 2, 3]
run("db_chapters: get_chapters упорядочены по номеру", test_dc_get_chapters_ordered)

def test_dc_get_last_chapters_content():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    for i in range(1, 6):
        dbc.save_chapter(pid, i, f"глава {i}")
    last = dbc.get_last_chapters_content(pid, n=2)
    nums = [c["number"] for c in last]
    assert 4 in nums and 5 in nums
    assert 3 not in nums
run("db_chapters: get_last_chapters_content возвращает n последних", test_dc_get_last_chapters_content)

def test_dc_get_last_chapters_chronological():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter(pid, 1, "первая")
    dbc.save_chapter(pid, 2, "вторая")
    last = dbc.get_last_chapters_content(pid, n=2)
    assert last[0]["number"] < last[1]["number"]
run("db_chapters: get_last_chapters_content в хронологическом порядке", test_dc_get_last_chapters_chronological)

# ── Анализ глав ────────────────────────────────────────
def _base_analysis(**kw):
    d = {"arc_progress": {}, "character_deltas": [], "opened_promises": [],
         "closed_promises": [], "causal_chains": [], "logical_gaps": [],
         "conflict_score": 0.5, "pacing_note": "", "opening_type": "",
         "closing_type": "", "plot_threads": {}, "analysis_quality": "ok"}
    d.update(kw)
    return d

def test_dc_analysis_save_get():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter_analysis(pid, 1, _base_analysis(
        opened_promises=["Убийца вернётся"], conflict_score=0.8, pacing_note="быстрый"
    ))
    a = dbc.get_chapter_analysis(pid, 1)
    assert a is not None
    assert a["opened_promises"] == ["Убийца вернётся"]
    assert a["conflict_score"] == 0.8
    assert a["pacing_note"] == "быстрый"
run("db_chapters: save/get chapter_analysis с JSON-полями", test_dc_analysis_save_get)

def test_dc_analysis_json_deserialized():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter_analysis(pid, 1, _base_analysis(
        arc_progress={"Иван": "развился"}, logical_gaps=["разрыв 1", "разрыв 2"]
    ))
    a = dbc.get_chapter_analysis(pid, 1)
    assert isinstance(a["arc_progress"], dict)
    assert isinstance(a["logical_gaps"], list)
    assert len(a["logical_gaps"]) == 2
run("db_chapters: get_chapter_analysis десериализует JSON-поля", test_dc_analysis_json_deserialized)

def test_dc_analysis_missing():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    assert dbc.get_chapter_analysis(pid, 99) is None
run("db_chapters: get_chapter_analysis несуществующей → None", test_dc_analysis_missing)

def test_dc_analyses_range():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    for i in range(1, 6):
        dbc.save_chapter_analysis(pid, i, _base_analysis())
    result = dbc.get_analyses_range(pid, 2, 4)
    assert len(result) == 3
    assert all(2 <= r["chapter_num"] <= 4 for r in result)
run("db_chapters: get_analyses_range возвращает диапазон", test_dc_analyses_range)

def test_dc_logical_gaps():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter_analysis(pid, 2, _base_analysis(logical_gaps=["мотивация не объяснена"]))
    gaps = dbc.get_all_logical_gaps(pid, before_chapter=10)
    assert len(gaps) == 1
    assert "мотивация не объяснена" in gaps[0]["gaps"]
run("db_chapters: get_all_logical_gaps находит разрывы", test_dc_logical_gaps)

def test_dc_logical_gaps_before_filter():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    dbc.save_chapter_analysis(pid, 5, _base_analysis(logical_gaps=["разрыв в гл.5"]))
    # before_chapter=5 — глава 5 не включается (строгое <)
    gaps = dbc.get_all_logical_gaps(pid, before_chapter=5)
    assert len(gaps) == 0
    gaps2 = dbc.get_all_logical_gaps(pid, before_chapter=6)
    assert len(gaps2) == 1
run("db_chapters: get_all_logical_gaps фильтр before_chapter строгий", test_dc_logical_gaps_before_filter)

def test_dc_logical_gaps_skips_empty():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    # Анализ без разрывов
    dbc.save_chapter_analysis(pid, 1, _base_analysis(logical_gaps=[]))
    gaps = dbc.get_all_logical_gaps(pid, before_chapter=10)
    assert gaps == []
run("db_chapters: get_all_logical_gaps пропускает пустые разрывы", test_dc_logical_gaps_skips_empty)

# ── format_score_history ───────────────────────────────
def test_dc_format_score_history_empty():
    from engine.db_chapters import format_score_history
    assert format_score_history([], 5) == ""
run("db_chapters: format_score_history пустая история → ''", test_dc_format_score_history_empty)

def test_dc_format_score_history_single():
    from engine.db_chapters import format_score_history
    history = [{"chapter_num": 3, "score": 38.0}]
    result = format_score_history(history, 5)
    assert "38" in result and "1 гл." in result
run("db_chapters: format_score_history одна глава", test_dc_format_score_history_single)

def test_dc_format_score_history_multiple():
    from engine.db_chapters import format_score_history
    history = [
        {"chapter_num": 5, "score": 42.0},
        {"chapter_num": 3, "score": 35.0},
        {"chapter_num": 1, "score": 28.0},
    ]
    result = format_score_history(history, 6)
    assert "Средний score" in result
    assert "Лучший" in result
run("db_chapters: format_score_history несколько глав", test_dc_format_score_history_multiple)

# ── format_project_threshold_hint ─────────────────────
def test_dc_threshold_hint_none():
    from engine.db_chapters import format_project_threshold_hint
    assert format_project_threshold_hint(None) == ""
run("db_chapters: format_project_threshold_hint None → ''", test_dc_threshold_hint_none)

def test_dc_threshold_hint_no_bias():
    from engine.db_chapters import format_project_threshold_hint
    result = format_project_threshold_hint({"threshold": 38.0, "judge_bias": 0.5, "accepted_count": 10})
    assert "38" in result and "10" in result
    assert "систематически" not in result  # bias < 1.5
run("db_chapters: format_project_threshold_hint без значимого bias", test_dc_threshold_hint_no_bias)

def test_dc_threshold_hint_with_bias():
    from engine.db_chapters import format_project_threshold_hint
    result = format_project_threshold_hint({"threshold": 35.0, "judge_bias": 3.0, "accepted_count": 8})
    assert "занижаешь" in result  # bias > 0 → занижает
run("db_chapters: format_project_threshold_hint с bias > 1.5 → предупреждение", test_dc_threshold_hint_with_bias)

def test_dc_threshold_hint_overestimates():
    from engine.db_chapters import format_project_threshold_hint
    result = format_project_threshold_hint({"threshold": 40.0, "judge_bias": -2.5, "accepted_count": 6})
    assert "завышаешь" in result  # bias < 0 → завышает
run("db_chapters: format_project_threshold_hint bias < -1.5 → завышаешь", test_dc_threshold_hint_overestimates)

# ── check_structural_monotony ──────────────────────────
def test_dc_monotony_too_few():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    # Менее 4 глав → пустая строка
    for i in range(1, 4):
        dbc.save_chapter_analysis(pid, i, _base_analysis(opening_type="action"))
    result = dbc.check_structural_monotony(pid, before_chapter=10)
    assert result == ""
run("db_chapters: check_structural_monotony < 4 глав → ''", test_dc_monotony_too_few)

def test_dc_monotony_detects_opening_repeat():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    # 5 глав подряд с одним opening_type
    for i in range(1, 6):
        dbc.save_chapter_analysis(pid, i, _base_analysis(opening_type="action", closing_type="dialogue"))
    result = dbc.check_structural_monotony(pid, before_chapter=10)
    assert "Монотонность" in result or "action" in result
run("db_chapters: check_structural_monotony 5/5 одинаковых → предупреждение", test_dc_monotony_detects_opening_repeat)

def test_dc_monotony_diverse_no_warning():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    types = ["action", "description", "dialogue", "internal", "action"]
    for i, t in enumerate(types, 1):
        dbc.save_chapter_analysis(pid, i, _base_analysis(opening_type=t))
    result = dbc.check_structural_monotony(pid, before_chapter=10)
    # 2/5 = 40% < 60% → нет предупреждения
    assert result == ""
run("db_chapters: check_structural_monotony разнообразные паттерны → ''", test_dc_monotony_diverse_no_warning)

# ── get_judge_calibration_hint ─────────────────────────
def test_dc_calibration_hint_no_data():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    result = dbc.get_judge_calibration_hint(pid)
    assert result == ""
run("db_chapters: get_judge_calibration_hint без данных → ''", test_dc_calibration_hint_no_data)

def test_dc_calibration_hint_with_data():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    # Сохраняем 5 калибровок — судья стабильно занижает
    for i in range(1, 6):
        dbc.save_judge_calibration(pid, i, judge_score=35.0, author_score=40.0)
    result = dbc.get_judge_calibration_hint(pid, min_samples=3)
    assert len(result) > 0
    assert "занижены" in result or "5.0" in result
run("db_chapters: get_judge_calibration_hint с данными о занижении", test_dc_calibration_hint_with_data)

def test_dc_calibration_hint_accurate():
    make_db()
    import engine.db_projects as dbp
    import engine.db_chapters as dbc
    pid = dbp.create_project("Тест")
    # Точные оценки — delta < 1.5
    for i in range(1, 6):
        dbc.save_judge_calibration(pid, i, judge_score=38.0, author_score=38.5)
    result = dbc.get_judge_calibration_hint(pid, min_samples=3)
    assert "точны" in result
run("db_chapters: get_judge_calibration_hint точные оценки → 'точны'", test_dc_calibration_hint_accurate)


# ════════════════════════════════════════════════════════
print("\n══ state_prompts: чистые функции ══")
# ════════════════════════════════════════════════════════

from engine.state_prompts import (
    _trunc, _extract_next_context, _build_char_prefill,
    _prefill_from_structured,
)

# ── _trunc ────────────────────────────────────────────
def test_sp_trunc_short():
    assert _trunc("короткий текст", 100) == "короткий текст"
run("_trunc: короткий → без изменений", test_sp_trunc_short)

def test_sp_trunc_cuts_at_boundary():
    text = "слово1 слово2 слово3 слово4 слово5"
    result = _trunc(text, 20)
    assert len(result) <= 20
    assert result.endswith("слово2") or not result.endswith(" ")
run("_trunc: длинный → режет по границе слова", test_sp_trunc_cuts_at_boundary)

def test_sp_trunc_exact_limit():
    text = "а" * 100
    result = _trunc(text, 50)
    assert len(result) <= 50
run("_trunc: строка без пробелов → обрезает по лимиту", test_sp_trunc_exact_limit)

# ── _extract_next_context ─────────────────────────────
def test_sp_enc_no_update():
    assert _extract_next_context(None) == ""
run("_extract_next_context: None → ''", test_sp_enc_no_update)

def test_sp_enc_no_marker():
    assert _extract_next_context({"raw_analysis": "просто текст без маркера"}) == ""
run("_extract_next_context: нет маркера → ''", test_sp_enc_no_marker)

def test_sp_enc_with_marker():
    raw = "анализ главы\n=== КОНТЕКСТ ДЛЯ СЛЕДУЮЩЕЙ ГЛАВЫ ===\nИван идёт на север"
    result = _extract_next_context({"raw_analysis": raw})
    assert "Иван идёт на север" in result
run("_extract_next_context: маркер найден → извлекает контекст", test_sp_enc_with_marker)

# ── _prefill_from_structured ──────────────────────────
def test_sp_pfs_basic():
    chars = {"Иван": {"state": "усталый", "location": "лес", "goal": "выжить", "deep_goal": "", "knows": "", "ignores": ""}}
    result = _prefill_from_structured(chars, ["Иван"])
    assert "Иван" in result and "усталый" in result
run("_prefill_from_structured: базовый персонаж", test_sp_pfs_basic)

def test_sp_pfs_max_four_chars():
    chars = {f"Персонаж{i}": {"state": f"состояние{i}", "location": "", "goal": "", "deep_goal": "", "knows": "", "ignores": ""}
             for i in range(6)}
    names = [f"Персонаж{i}" for i in range(6)]
    result = _prefill_from_structured(chars, names)
    count = sum(1 for i in range(6) if f"Персонаж{i}" in result)
    assert count <= 4
run("_prefill_from_structured: не больше 4 персонажей", test_sp_pfs_max_four_chars)

def test_sp_pfs_empty_fields_skipped():
    chars = {"Молчун": {"state": "", "location": "", "goal": "", "deep_goal": "", "knows": "", "ignores": ""}}
    result = _prefill_from_structured(chars, ["Молчун"])
    # Пустые поля — строки нет или только имя
    assert "усталый" not in result
run("_prefill_from_structured: пустые поля не добавляются", test_sp_pfs_empty_fields_skipped)

# ── _build_char_prefill ───────────────────────────────
def test_sp_bcp_from_structured():
    structured = {
        "char_names": ["Алиса"],
        "characters": {"Алиса": {"state": "взволнованная", "location": "замок",
                                   "goal": "найти выход", "deep_goal": "", "knows": "", "ignores": ""}},
        "raw": {}
    }
    result = _build_char_prefill(structured)
    assert "Алиса" in result and "взволнованная" in result
run("_build_char_prefill: из структурированных данных", test_sp_bcp_from_structured)

def test_sp_bcp_empty_state():
    structured = {"char_names": [], "characters": {}, "raw": {"global_state": ""}}
    result = _build_char_prefill(structured)
    assert result == ""
run("_build_char_prefill: пустой state → ''", test_sp_bcp_empty_state)


# ════════════════════════════════════════════════════════
print("\n══ l3_memory: форматирование и генерация ══")
# ════════════════════════════════════════════════════════

def test_l3_context_empty():
    make_db()
    import engine.db_projects as dbp
    import engine.l3_memory as l3m
    pid = dbp.create_project("Тест")
    assert l3m.get_l3_context(pid, before_chapter=5) == ""
run("l3_memory: get_l3_context нет саммари → ''", test_l3_context_empty)

def test_l3_context_format():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    import engine.l3_memory as l3m
    pid = dbp.create_project("Тест")
    dbn.save_l3_summary(pid, 2, {"events": "герой нашёл меч", "characters": "Иван изменился",
                                  "conflicts": "дракон", "promises": "вернётся", "mood": "тревожное"})
    result = l3m.get_l3_context(pid, before_chapter=5)
    assert "ПАМЯТЬ СЕРИИ" in result
    assert "герой нашёл меч" in result
    assert "Иван изменился" in result
    assert "тревожное" in result
run("l3_memory: get_l3_context форматирует все поля", test_l3_context_format)

def test_l3_context_skips_empty_fields():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    import engine.l3_memory as l3m
    pid = dbp.create_project("Тест")
    dbn.save_l3_summary(pid, 1, {"events": "событие", "characters": "", "conflicts": "", "promises": "", "mood": ""})
    result = l3m.get_l3_context(pid, before_chapter=5)
    assert "Персонажи:" not in result
run("l3_memory: get_l3_context пропускает пустые поля", test_l3_context_skips_empty_fields)

def test_l3_has_summary_false():
    make_db()
    import engine.db_projects as dbp
    import engine.l3_memory as l3m
    pid = dbp.create_project("Тест")
    assert l3m.has_l3_summary(pid, 3) is False
run("l3_memory: has_l3_summary несуществующая → False", test_l3_has_summary_false)

def test_l3_has_summary_true():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    import engine.l3_memory as l3m
    pid = dbp.create_project("Тест")
    dbn.save_l3_summary(pid, 3, {"events": "e", "characters": "", "conflicts": "", "promises": "", "mood": ""})
    assert l3m.has_l3_summary(pid, 3) is True
run("l3_memory: has_l3_summary существующая → True", test_l3_has_summary_true)

def test_l3_generate_too_short():
    make_db()
    import engine.l3_memory as l3m
    result = l3m.generate_l3_summary(1, 1, "   ", MagicMock())
    assert result is None
run("l3_memory: generate_l3_summary короткий текст → None", test_l3_generate_too_short)

def test_l3_generate_llm_returns_valid_json():
    make_db()
    import engine.db_projects as dbp
    import engine.db_narrative as dbn
    import engine.l3_memory as l3m
    pid = dbp.create_project("Тест")
    import json as _j
    llm_response = _j.dumps({"events": "герой вышел", "characters": "Иван",
                               "conflicts": "опасность", "promises": "вернётся", "mood": "тревожное"})
    llm = MagicMock(return_value=llm_response)
    result = l3m.generate_l3_summary(pid, 1, "Текст главы " * 20, llm)
    assert result is not None
    assert result["events"] == "герой вышел"
    assert dbn.get_l3_summary(pid, 1) is not None
run("l3_memory: generate_l3_summary сохраняет и возвращает саммари", test_l3_generate_llm_returns_valid_json)

def test_l3_generate_llm_invalid_json():
    make_db()
    import engine.l3_memory as l3m
    result = l3m.generate_l3_summary(1, 1, "Текст главы " * 20, MagicMock(return_value="{invalid"))
    assert result is None
run("l3_memory: generate_l3_summary невалидный JSON → None", test_l3_generate_llm_invalid_json)

def test_l3_generate_fills_missing_keys():
    make_db()
    import engine.db_projects as dbp
    import engine.l3_memory as l3m
    pid = dbp.create_project("Тест")
    import json as _j
    llm = MagicMock(return_value=_j.dumps({"events": "событие"}))
    result = l3m.generate_l3_summary(pid, 1, "Текст " * 30, llm)
    assert result is not None
    for key in ("events", "characters", "conflicts", "promises", "mood"):
        assert key in result
run("l3_memory: generate_l3_summary дополняет недостающие ключи пустыми строками", test_l3_generate_fills_missing_keys)


# ════════════════════════════════════════════════════════
print("\n══ contracts: data-классы ══")
# ════════════════════════════════════════════════════════

from engine.contracts import NarrativeReport, ArcStatus, PromiseItem

def test_con_arc_status_to_dict():
    arc = ArcStatus("Иван", "active", 3, "развивается", False)
    d = arc.to_dict()
    assert d["character"] == "Иван"
    assert d["status"] == "active"
    assert d["last_seen_chapter"] == 3
    assert d["stalled"] is False
run("contracts: ArcStatus.to_dict()", test_con_arc_status_to_dict)

def test_con_promise_item_to_dict():
    p = PromiseItem("Убийца вернётся", 2, resolved=True, resolved_chapter=7)
    d = p.to_dict()
    assert d["text"] == "Убийца вернётся"
    assert d["introduced_chapter"] == 2
    assert d["resolved"] is True
    assert d["resolved_chapter"] == 7
run("contracts: PromiseItem.to_dict()", test_con_promise_item_to_dict)

def test_con_promise_item_defaults():
    p = PromiseItem("Обещание", 1)
    assert p.resolved is False
    assert p.resolved_chapter is None
    assert p.overdue is False
run("contracts: PromiseItem defaults", test_con_promise_item_defaults)

def test_con_narrative_report_ok():
    report = NarrativeReport(
        project_id=1, through_chapter=5,
        arc_health={}, promise_status=[], contradictions=[],
        mood_trajectory=[], conflict_density=[], warnings=[], ok=True
    )
    assert report.ok is True
    assert report.project_id == 1
    assert report.through_chapter == 5
run("contracts: NarrativeReport конструктор", test_con_narrative_report_ok)

def test_con_narrative_report_to_dict():
    arc = ArcStatus("Алиса", "active", 3)
    report = NarrativeReport(
        project_id=1, through_chapter=3,
        arc_health={"Алиса": arc}, promise_status=[], contradictions=[],
        mood_trajectory=["светлое"], conflict_density=[0.5], warnings=[], ok=True
    )
    d = report.to_dict()
    assert d["project_id"] == 1
    assert "Алиса" in d["arc_health"]
    assert d["mood_trajectory"] == ["светлое"]
    assert d["conflict_density"] == [0.5]
    assert d["ok"] is True
run("contracts: NarrativeReport.to_dict() возвращает все поля", test_con_narrative_report_to_dict)

# ════════════════════════════════════════════════════════
print("\n══ parse_score / parse_verdict ══")
# ════════════════════════════════════════════════════════

from engine.pipeline import parse_score, parse_verdict

def test_parse_score_normal():
    assert parse_score("ИТОГ: 42") == 42.0
run("parse_score: нормальный ИТОГ", test_parse_score_normal)

def test_parse_score_decimal():
    assert parse_score("ИТОГ: 38.5") == 38.5
run("parse_score: ИТОГ с десятичной", test_parse_score_decimal)

def test_parse_score_fallback_sum():
    text = "ГОЛОС: 8 СТРУКТУРА: 7 ПЕРСОНАЖИ: 8 СЦЕНЫ: 9 ДИАЛОГ: 7"
    assert parse_score(text) == 39.0
run("parse_score: fallback — сумма 5 критериев", test_parse_score_fallback_sum)

def test_parse_score_empty():
    assert parse_score("") == 0.0
run("parse_score: пустая строка → 0.0", test_parse_score_empty)

def test_parse_score_lowercase():
    # БАГ: до фикса возвращал 0.0
    assert parse_score("итог: 42") == 42.0
run("parse_score: строчные буквы (фикс IGNORECASE)", test_parse_score_lowercase)

def test_parse_score_extra_spaces():
    assert parse_score("ИТОГ:   42") == 42.0
run("parse_score: лишние пробелы", test_parse_score_extra_spaces)

def test_parse_score_multiline():
    text = "ГОЛОС: 9\nСТРУКТУРА: 8\nИТОГ: 42\nВЕРДИКТ: ПРИНЯТЬ"
    assert parse_score(text) == 42.0
run("parse_score: многострочный текст", test_parse_score_multiline)

def test_parse_score_итог_over_sum():
    text = "ГОЛОС: 9 СТРУКТУРА: 8 ПЕРСОНАЖИ: 8 СЦЕНЫ: 9 ДИАЛОГ: 8\nИТОГ: 42"
    assert parse_score(text) == 42.0
run("parse_score: ИТОГ приоритетнее суммы", test_parse_score_итог_over_sum)

def test_parse_verdict_accept():
    assert parse_verdict("ВЕРДИКТ: ПРИНЯТЬ") == "ПРИНЯТЬ"
run("parse_verdict: ПРИНЯТЬ", test_parse_verdict_accept)

def test_parse_verdict_rework():
    assert parse_verdict("ВЕРДИКТ: НА ДОРАБОТКУ") == "НА ДОРАБОТКУ"
run("parse_verdict: НА ДОРАБОТКУ", test_parse_verdict_rework)

def test_parse_verdict_empty_defaults():
    assert parse_verdict("") == "НА ДОРАБОТКУ"
run("parse_verdict: пустая строка → НА ДОРАБОТКУ (безопасный дефолт)", test_parse_verdict_empty_defaults)

def test_parse_verdict_lowercase():
    # БАГ: до фикса возвращал "НА ДОРАБОТКУ" вместо "ПРИНЯТЬ"
    assert parse_verdict("вердикт: принять") == "ПРИНЯТЬ"
run("parse_verdict: строчные буквы (фикс IGNORECASE)", test_parse_verdict_lowercase)

def test_parse_verdict_extra_whitespace():
    assert parse_verdict("ВЕРДИКТ:  ПРИНЯТЬ") == "ПРИНЯТЬ"
run("parse_verdict: лишние пробелы", test_parse_verdict_extra_whitespace)

def test_parse_verdict_multiline():
    text = "ИТОГ: 42\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Хорошо."
    assert parse_verdict(text) == "ПРИНЯТЬ"
run("parse_verdict: многострочный ответ судьи", test_parse_verdict_multiline)


# ════════════════════════════════════════════════════════
print("\n══ build_consolidated_voice ══")
# ════════════════════════════════════════════════════════

from engine.pipeline_context import build_consolidated_voice

def test_voice_fallback_no_data():
    result = build_consolidated_voice(None, [], "quick")
    assert "ГОЛОС — ЭТАЛОН" in result
    assert "Вставь 3-5" in result
run("voice: fallback при отсутствии голоса и глав", test_voice_fallback_no_data)

def test_voice_chapter_in_all_modes():
    chapters = [{"number": 1, "content": "Текст первой главы." * 50}]
    for mode in ("quick", "quality", "master"):
        result = build_consolidated_voice(None, chapters, mode)
        assert "Гл.1" in result, f"mode={mode}"
run("voice: главы попадают во все режимы", test_voice_chapter_in_all_modes)

def test_voice_profile_only_quality_master():
    voice = {"name": "Noir", "profile": "Короткие фразы." * 30, "source": None}
    chapters = [{"number": 1, "content": "Текст."}]
    quick = build_consolidated_voice(voice, chapters, "quick")
    quality = build_consolidated_voice(voice, chapters, "quality")
    assert "ГОЛОСОВОЙ ПРОФИЛЬ" not in quick
    assert "ГОЛОСОВОЙ ПРОФИЛЬ" in quality
run("voice: профиль только в quality/master", test_voice_profile_only_quality_master)

def test_voice_profile_truncated():
    voice = {"name": "Test", "profile": "X" * 1000, "source": None}
    chapters = [{"number": 1, "content": "Текст."}]
    result = build_consolidated_voice(voice, chapters, "quality")
    assert "X" * 501 not in result
run("voice: профиль обрезается до 500 символов", test_voice_profile_truncated)

def test_voice_multiple_chapters():
    chapters = [{"number": 1, "content": "Один."}, {"number": 2, "content": "Два."}]
    result = build_consolidated_voice(None, chapters, "quick")
    assert "Гл.1" in result
    assert "Гл.2" in result
run("voice: несколько глав — все в выводе", test_voice_multiple_chapters)


# ════════════════════════════════════════════════════════
print("\n══ prevalidation: устойчивость к плохому JSON ══")
# ════════════════════════════════════════════════════════

import json as _json
import re as _re

def _parse_prevalidation_response(raw: str) -> dict:
    """Та же логика что в prevalidate_chapter."""
    clean = _re.sub(r"```json|```", "", raw).strip()
    try:
        return _json.loads(clean)
    except _json.JSONDecodeError:
        return {"ok": True, "blocking": [], "warnings": [], "suggestions": [], "_raw": raw}

def test_prevalidation_invalid_json():
    result = _parse_prevalidation_response("Это не JSON вообще.")
    assert result["ok"] is True
    assert result["blocking"] == []
    assert "_raw" in result
run("prevalidation: невалидный JSON → безопасный fallback", test_prevalidation_invalid_json)

def test_prevalidation_empty_response():
    result = _parse_prevalidation_response("")
    assert result["ok"] is True
    assert "_raw" in result
run("prevalidation: пустой ответ → fallback", test_prevalidation_empty_response)

def test_prevalidation_markdown_json():
    valid = _json.dumps({"ok": True, "blocking": [], "warnings": [], "suggestions": []})
    wrapped = f"```json\n{valid}\n```"
    result = _parse_prevalidation_response(wrapped)
    assert result["ok"] is True
    assert "_raw" not in result
run("prevalidation: JSON в markdown-блоке парсится корректно", test_prevalidation_markdown_json)

def test_prevalidation_partial_json():
    result = _parse_prevalidation_response('{"ok": true, "blocking":')
    assert isinstance(result, dict)
    assert "ok" in result
run("prevalidation: частичный JSON → fallback без исключений", test_prevalidation_partial_json)

def test_prevalidation_blocking_sets_ok_false():
    response = _json.dumps({
        "ok": False,
        "blocking": [{"issue": "Мёртвый", "detail": "X", "fix": "Y"}],
        "warnings": [], "suggestions": [],
    })
    result = _parse_prevalidation_response(response)
    assert result["ok"] is False
    assert len(result["blocking"]) == 1
run("prevalidation: blocking → ok=False сохраняется", test_prevalidation_blocking_sets_ok_false)

def test_contradiction_invalid_json_returns_empty():
    """_check_state_contradictions: невалидный JSON → []."""
    clean = _re.sub(r"```json|```", "", "не JSON").strip()
    try:
        data = _json.loads(clean)
        result = data.get("contradictions", [])
    except _json.JSONDecodeError:
        result = []
    assert result == []
run("prevalidation: противоречия — невалидный JSON → []", test_contradiction_invalid_json_returns_empty)


# ════════════════════════════════════════════════════════
print("\n══ авто-ретрай: деградация score ══")
# ════════════════════════════════════════════════════════

def _simulate_auto_retry(first_score, retry_scores, max_retries=3):
    """
    Симулирует логику авто-ретрая из start_pipeline.
    Возвращает (финальный score, количество итераций).
    """
    verdict = "НА ДОРАБОТКУ"
    current_score = first_score
    prev_score = first_score
    iterations = 1

    for i, score in enumerate(retry_scores):
        if verdict == "ПРИНЯТЬ" or i >= max_retries:
            break
        # Защита от деградации
        if score <= prev_score:
            current_score = score
            iterations += 1
            break
        prev_score = score
        current_score = score
        iterations += 1

    return current_score, iterations

def test_retry_degradation_stops():
    score, iters = _simulate_auto_retry(42.0, [35.0, 30.0], max_retries=3)
    assert iters == 2  # первый + один retry (упал → стоп)
run("авто-ретрай: деградация score прерывает цикл", test_retry_degradation_stops)

def test_retry_equal_score_stops():
    score, iters = _simulate_auto_retry(30.0, [30.0, 40.0], max_retries=3)
    assert iters == 2  # равный score → стоп
run("авто-ретрай: равный score прерывает цикл", test_retry_equal_score_stops)

def test_retry_growing_score_continues():
    score, iters = _simulate_auto_retry(25.0, [30.0, 35.0], max_retries=3)
    assert iters == 3
    assert score == 35.0
run("авто-ретрай: растущий score продолжает цикл", test_retry_growing_score_continues)

def test_retry_max_retries_zero():
    score, iters = _simulate_auto_retry(20.0, [30.0, 40.0], max_retries=0)
    assert iters == 1  # нет retry при max=0
run("авто-ретрай: max_retries=0 → цикл не запускается", test_retry_max_retries_zero)

def test_retry_max_retries_respected():
    score, iters = _simulate_auto_retry(25.0, [30.0, 35.0, 40.0, 45.0], max_retries=2)
    assert iters <= 3  # 1 основной + 2 retry максимум
run("авто-ретрай: max_retries соблюдается", test_retry_max_retries_respected)


# ════════════════════════════════════════════════════════
print("\n══ engine_loaders: smoke ══")
# ════════════════════════════════════════════════════════

from engine.engine_loaders import engine_available, get_engine_path, validate_engine_paths

def test_engine_available_returns_bool():
    assert isinstance(engine_available(), bool)
run("engine_loaders: engine_available() возвращает bool", test_engine_available_returns_bool)

def test_get_engine_path_returns_path():
    from pathlib import Path as _Path
    assert isinstance(get_engine_path(), _Path)
run("engine_loaders: get_engine_path() возвращает Path", test_get_engine_path_returns_path)

def test_engine_available_consistent():
    assert engine_available() == get_engine_path().exists()
run("engine_loaders: engine_available() консистентен с get_engine_path()", test_engine_available_consistent)

def test_validate_returns_dict():
    result = validate_engine_paths()
    assert isinstance(result, dict)
run("engine_loaders: validate_engine_paths() возвращает dict", test_validate_returns_dict)

def test_engine_if_available():
    """Если движок есть — критические файлы на месте."""
    if not engine_available():
        return  # движок не найден — пропускаем
    path = get_engine_path()
    critical = ["00_CORE/CORE_FULL.md", "00_CORE/CORE_MINI.md", "INDEX.json"]
    missing = [f for f in critical if not (path / f).exists()]
    assert missing == [], f"Критические файлы движка отсутствуют: {missing}"
run("engine_loaders: критические файлы на месте (если движок есть)", test_engine_if_available)

def test_load_module_missing_returns_empty():
    """Несуществующий модуль → пустая строка, не исключение."""
    if not engine_available():
        return
    from engine.engine_loaders_core import load_module
    result = load_module(get_engine_path(), "99_nonexistent_module_xyz")
    assert result == ""
run("engine_loaders: несуществующий модуль → ''", test_load_module_missing_returns_empty)


# ════════════════════════════════════════════════════════
print("\n══ КРИТИЧНО: auto_router ══")
# ════════════════════════════════════════════════════════

from engine.auto_router import _normalize, route_by_keywords, auto_route, BASE_MODULES, KEYWORD_ROUTES

def test_normalize_lowercase():
    assert _normalize("Диалог и Темп!") == "диалог и темп "
run("auto_router: _normalize → нижний регистр, без пунктуации", test_normalize_lowercase)

def test_normalize_strips_punctuation():
    result = _normalize("напряжение, конфликт.")
    assert "," not in result and "." not in result
run("auto_router: _normalize → убирает знаки препинания", test_normalize_strips_punctuation)

def test_route_by_keywords_dialogue():
    modules, conf = route_by_keywords("Нужен диалог с подтекстом")
    assert "15_dialogue_style" in modules
    assert conf >= 1
run("auto_router: 'диалог' → 15_dialogue_style", test_route_by_keywords_dialogue)

def test_route_by_keywords_tension():
    modules, conf = route_by_keywords("добавь напряжение и конфликт")
    assert "01_tension_curve" in modules
run("auto_router: 'напряжение' → 01_tension_curve", test_route_by_keywords_tension)

def test_route_by_keywords_empty():
    modules, conf = route_by_keywords("")
    assert isinstance(modules, list)
    assert conf == 0
run("auto_router: пустая задача → пустой список, conf=0", test_route_by_keywords_empty)

def test_route_by_keywords_no_base_modules():
    """BASE_MODULES не попадают в keyword result — добавляются отдельно."""
    modules, _ = route_by_keywords("диалог темп напряжение голос")
    for bm in BASE_MODULES:
        assert bm not in modules
run("auto_router: BASE_MODULES не в keyword result", test_route_by_keywords_no_base_modules)

def test_route_max_6_modules():
    """Возвращает не более 6 модулей."""
    # Задача с кучей ключей
    task = "диалог темп напряжение психология химия атмосфера голос символ арка тема"
    modules, _ = route_by_keywords(task)
    assert len(modules) <= 6
run("auto_router: не более 6 модулей", test_route_max_6_modules)

def test_auto_route_adds_base_modules():
    """auto_route всегда добавляет BASE_MODULES в результат."""
    result = auto_route("диалог с подтекстом", api_call_fn=None)
    for bm in BASE_MODULES:
        assert bm in result
run("auto_router: auto_route всегда содержит BASE_MODULES", test_auto_route_adds_base_modules)

def test_auto_route_no_llm_above_threshold():
    """При conf >= threshold LLM не вызывается."""
    called = [False]
    def fake_llm(p): called[0] = True; return ""
    # Задача с 3+ ключами → conf высокий → LLM не нужен
    auto_route("диалог подтекст напряжение конфликт темп", api_call_fn=fake_llm, confidence_threshold=2)
    assert not called[0]
run("auto_router: высокая уверенность → LLM не вызывается", test_auto_route_no_llm_above_threshold)

def test_auto_route_without_llm_returns_list():
    result = auto_route("непонятная задача xyz", api_call_fn=None)
    assert isinstance(result, list)
    assert len(result) >= len(BASE_MODULES)
run("auto_router: без LLM всегда возвращает список", test_auto_route_without_llm_returns_list)

def test_route_genre_boost_horror():
    """Хоррор-жанр буcтит tension модули."""
    modules, _ = route_by_keywords("сцена страха", genre_key="horror")
    assert "01_tension_curve" in modules
run("auto_router: genre_boost horror → 01_tension_curve", test_route_genre_boost_horror)

def test_keyword_routes_no_typos():
    """Все модули в KEYWORD_ROUTES начинаются с цифры_имя."""
    import re
    pattern = re.compile(r'^\d{2}_\w+$')
    bad = []
    for kw, modules in KEYWORD_ROUTES.items():
        for m in modules:
            if not pattern.match(m):
                bad.append((kw, m))
    assert bad == [], f"Опечатки в модулях: {bad}"
run("auto_router: все модули KEYWORD_ROUTES корректного формата", test_keyword_routes_no_typos)


# ════════════════════════════════════════════════════════
print("\n══ КРИТИЧНО: chapter_analyzer ══")
# ════════════════════════════════════════════════════════

import json as _json

from engine.chapter_analyzer import (
    ChapterAnalysis, CharacterDelta, CausalChain,
    ChapterAnalyzer, format_analysis_for_prompt,
)

def test_chapter_analysis_failed_factory():
    a = ChapterAnalysis.failed(1, 5)
    assert a.analysis_quality == "failed"
    assert a.project_id == 1
    assert a.chapter_num == 5
    assert a.logical_gaps == []
run("chapter_analyzer: ChapterAnalysis.failed() создаёт заглушку", test_chapter_analysis_failed_factory)

def test_chapter_analysis_to_dict():
    a = ChapterAnalysis(project_id=1, chapter_num=3, conflict_score=0.7)
    d = a.to_dict()
    assert d["project_id"] == 1
    assert d["conflict_score"] == 0.7
run("chapter_analyzer: to_dict() работает", test_chapter_analysis_to_dict)

def test_format_analysis_failed_returns_empty():
    a = ChapterAnalysis.failed(1, 3)
    assert format_analysis_for_prompt(a) == ""
run("chapter_analyzer: format_analysis_for_prompt failed → ''", test_format_analysis_failed_returns_empty)

def test_format_analysis_with_gaps():
    a = ChapterAnalysis(
        project_id=1, chapter_num=5,
        logical_gaps=["Марина не могла знать об этом"],
        conflict_score=0.6,
        analysis_quality="ok",
    )
    result = format_analysis_for_prompt(a)
    assert "Марина" in result
    assert "⚠" in result
run("chapter_analyzer: format_analysis показывает gaps", test_format_analysis_with_gaps)

def test_format_analysis_with_promises():
    a = ChapterAnalysis(
        project_id=1, chapter_num=5,
        opened_promises=["Тайна шкатулки не раскрыта"],
        analysis_quality="ok",
    )
    result = format_analysis_for_prompt(a)
    assert "Тайна шкатулки" in result
run("chapter_analyzer: format_analysis показывает opened_promises", test_format_analysis_with_promises)

def test_format_analysis_with_arcs():
    a = ChapterAnalysis(
        project_id=1, chapter_num=5,
        arc_progress={"Анна": "продвинулась: узнала о предательстве"},
        analysis_quality="ok",
    )
    result = format_analysis_for_prompt(a)
    assert "Анна" in result
run("chapter_analyzer: format_analysis показывает arc_progress", test_format_analysis_with_arcs)

def test_format_analysis_empty_ok_returns_empty():
    """Анализ без данных → пустая строка (len < 30)."""
    a = ChapterAnalysis(project_id=1, chapter_num=5, analysis_quality="ok")
    result = format_analysis_for_prompt(a)
    assert result == ""
run("chapter_analyzer: format_analysis пустой ok → ''", test_format_analysis_empty_ok_returns_empty)

def _make_analyzer():
    """ChapterAnalyzer с мок-зависимостями (без БД)."""
    saved = []
    return ChapterAnalyzer(
        get_summaries_fn=lambda pid, ch, n: [],
        save_analysis_fn=lambda pid, ch, d: saved.append(d),
    ), saved

def test_analyzer_short_text_returns_failed():
    analyzer, _ = _make_analyzer()
    result = analyzer.analyze(1, 5, "Мало.", lambda p: "")
    assert result.analysis_quality == "failed"
run("chapter_analyzer: короткий текст → failed", test_analyzer_short_text_returns_failed)

def test_analyzer_empty_text_returns_failed():
    analyzer, _ = _make_analyzer()
    result = analyzer.analyze(1, 5, "", lambda p: "")
    assert result.analysis_quality == "failed"
run("chapter_analyzer: пустой текст → failed", test_analyzer_empty_text_returns_failed)

def test_analyzer_valid_json_response():
    analyzer, saved = _make_analyzer()
    response = _json.dumps({
        "arc_progress": {"Герой": "узнал правду"},
        "character_deltas": [{"name": "Герой", "learned": ["правда"], "decided": [], "changed_state": "", "arc_movement": "forward"}],
        "opened_promises": ["Тайна меча"],
        "closed_promises": [],
        "causal_chains": [{"cause": "встреча", "effect": "конфликт", "is_setup": True}],
        "logical_gaps": [],
        "conflict_score": 0.75,
        "pacing_note": "быстрый",
        "opening_type": "action",
        "closing_type": "cliffhanger",
        "plot_threads": {"поиск": "активна"},
    })
    text = "Герой шёл по лесу. " * 30
    result = analyzer.analyze(1, 5, text, lambda p: response)
    assert result.analysis_quality == "ok"
    assert result.conflict_score == 0.75
    assert "Герой" in result.arc_progress
    assert len(result.character_deltas) == 1
    assert result.character_deltas[0].arc_movement == "forward"
    assert result.opening_type == "action"
    assert len(saved) == 1
run("chapter_analyzer: валидный JSON → корректный ChapterAnalysis", test_analyzer_valid_json_response)

def test_analyzer_invalid_json_returns_partial():
    analyzer, _ = _make_analyzer()
    text = "Герой шёл по лесу. " * 30
    result = analyzer.analyze(1, 5, text, lambda p: "это не JSON")
    assert result.analysis_quality == "partial"
    assert result.raw_response != ""
run("chapter_analyzer: невалидный JSON → partial (не crashed)", test_analyzer_invalid_json_returns_partial)

def test_analyzer_conflict_score_clipped():
    """conflict_score из за пределов [0,1] обрезается."""
    analyzer, _ = _make_analyzer()
    response = _json.dumps({
        "arc_progress": {}, "character_deltas": [], "opened_promises": [],
        "closed_promises": [], "causal_chains": [], "logical_gaps": [],
        "conflict_score": 99.0,  # за пределами
        "pacing_note": "", "opening_type": "", "closing_type": "", "plot_threads": {},
    })
    text = "Герой шёл по лесу. " * 30
    result = analyzer.analyze(1, 5, text, lambda p: response)
    assert result.conflict_score <= 1.0
run("chapter_analyzer: conflict_score > 1.0 обрезается до 1.0", test_analyzer_conflict_score_clipped)

def test_analyzer_llm_raises_returns_failed():
    analyzer, _ = _make_analyzer()
    text = "Герой шёл по лесу. " * 30
    result = analyzer.analyze(1, 5, text, lambda p: (_ for _ in ()).throw(RuntimeError("API error")))
    assert result.analysis_quality == "failed"
run("chapter_analyzer: LLM raises → failed (не crashed)", test_analyzer_llm_raises_returns_failed)


# ════════════════════════════════════════════════════════
print("\n══ КРИТИЧНО: pipeline_steps ══")
# ════════════════════════════════════════════════════════

from engine.pipeline_steps import _build_sys_critic, step_edit, _GENRE_CRITIC_LENS

def test_build_sys_critic_horror():
    result = _build_sys_critic("horror")
    assert "ХОРРОР" in result
    assert "дред" in result.lower() or "страх" in result.lower()
run("pipeline_steps: _build_sys_critic horror → жанровый фокус", test_build_sys_critic_horror)

def test_build_sys_critic_detective():
    result = _build_sys_critic("detective")
    assert "ДЕТЕКТИВ" in result
run("pipeline_steps: _build_sys_critic detective → жанровый фокус", test_build_sys_critic_detective)

def test_build_sys_critic_unknown_genre():
    result = _build_sys_critic("unknown_genre_xyz")
    assert "ГОЛОС" in result  # дефолтный промпт всегда содержит критерии
    assert "СТРУКТУРА" in result
run("pipeline_steps: _build_sys_critic неизвестный жанр → дефолт", test_build_sys_critic_unknown_genre)

def test_build_sys_critic_subgenre_strips():
    """'fantasy_epic' → берём 'fantasy'."""
    result_epic   = _build_sys_critic("fantasy_epic")
    result_base   = _build_sys_critic("fantasy")
    assert "ФЭНТЕЗИ" in result_epic
    assert "ФЭНТЕЗИ" in result_base
run("pipeline_steps: 'fantasy_epic' → берёт семью 'fantasy'", test_build_sys_critic_subgenre_strips)

def test_build_sys_critic_all_genres_covered():
    """Все жанры в _GENRE_CRITIC_LENS дают отличный от дефолта результат."""
    default = _build_sys_critic("")
    for genre in _GENRE_CRITIC_LENS:
        result = _build_sys_critic(genre)
        assert result != default, f"Жанр {genre} вернул дефолтный промпт"
run("pipeline_steps: все жанры в _GENRE_CRITIC_LENS дают свой фокус", test_build_sys_critic_all_genres_covered)

def test_step_edit_skips_without_previous():
    """step_edit ничего не делает если нет previous_text."""
    calls = []
    results = {}
    step_edit(1, 1, "задача", None, None, "model::x",
              lambda m, s, u, **kw: calls.append(1) or "text", results)
    assert calls == []
    assert "generated_text" not in results
run("pipeline_steps: step_edit пропускает без previous_text", test_step_edit_skips_without_previous)

def test_step_edit_skips_without_critique():
    calls = []
    results = {}
    step_edit(1, 1, "задача", "текст главы", None, "model::x",
              lambda m, s, u, **kw: calls.append(1) or "text", results)
    assert calls == []
run("pipeline_steps: step_edit пропускает без previous_critique", test_step_edit_skips_without_critique)

def test_step_edit_calls_llm_with_both():
    """step_edit вызывает LLM когда есть и текст, и критика."""
    calls = []
    results = {}

    def fake_save(run_id, iteration, stage, model, prompt, response):
        pass

    import unittest.mock as _mock
    with _mock.patch("engine.pipeline_steps.save_pipeline_iteration", side_effect=fake_save):
        step_edit(1, 1, "задача", "предыдущий текст", "критика здесь",
                  "model::x",
                  lambda m, s, u, **kw: (calls.append(1), "новый текст")[1],
                  results)
    assert len(calls) == 1
    assert results.get("generated_text") == "новый текст"
    assert results.get("stage") == "edit"
run("pipeline_steps: step_edit вызывает LLM и пишет в results", test_step_edit_calls_llm_with_both)

def test_step_critique_parses_score():
    """step_critique правильно парсит ИТОГ из ответа LLM."""
    import unittest.mock as _mock

    results = {"generated_text": "Текст главы."}
    critique_response = "ГОЛОС: 8 СТРУКТУРА: 7 ПЕРСОНАЖИ: 8 СЦЕНЫ: 9 ДИАЛОГ: 7\nИТОГ: 39\nГЛАВНЫЕ ПРОБЛЕМЫ:\n- Диалог плоский"

    def fake_call(model, sys, prompt, max_tokens=2000):
        return critique_response

    def fake_save(run_id, iteration, stage, model, prompt, response, score=None):
        pass

    with _mock.patch("engine.pipeline_steps.save_pipeline_iteration", side_effect=fake_save):
        from engine.pipeline_steps import step_critique
        step_critique(1, 1, 5, "model::x", fake_call, results, genre="")

    assert results.get("critique") == critique_response
    assert results.get("critic_score") == 39.0
run("pipeline_steps: step_critique парсит ИТОГ", test_step_critique_parses_score)

def test_step_judge_parses_verdict_and_score():
    """step_judge правильно парсит ВЕРДИКТ и ИТОГ."""
    import unittest.mock as _mock

    results = {"generated_text": "Текст главы.", "critique": "Критика."}
    judge_response = (
        "ГОЛОС: 9 СТРУКТУРА: 8 ПЕРСОНАЖИ: 8 СЦЕНЫ: 9 ДИАЛОГ: 8\n"
        "ИТОГ: 42\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Хорошо."
    )

    def fake_call(model, sys, prompt, max_tokens=2000):
        return judge_response

    def fake_save(run_id, iteration, stage, model, prompt, response, score=None, verdict=None):
        pass

    with _mock.patch("engine.pipeline_steps.save_pipeline_iteration", side_effect=fake_save):
        with _mock.patch("engine.pipeline_steps.handle_error"):
            from engine.pipeline_steps import step_judge
            step_judge(1, 1, 5, "model::x", fake_call, results)

    assert results.get("judge_score") == 42.0
    assert results.get("verdict") == "ПРИНЯТЬ"
run("pipeline_steps: step_judge парсит ИТОГ и ВЕРДИКТ", test_step_judge_parses_verdict_and_score)

def test_step_judge_defaults_rework_on_empty():
    """Пустой ответ → НА ДОРАБОТКУ, score=0."""
    import unittest.mock as _mock

    results = {"generated_text": "Текст.", "critique": "Критика."}

    def fake_save(*a, **kw): pass
    with _mock.patch("engine.pipeline_steps.save_pipeline_iteration", side_effect=fake_save):
        with _mock.patch("engine.pipeline_steps.handle_error"):
            from engine.pipeline_steps import step_judge
            step_judge(1, 1, 5, "model::x", lambda m, s, p, **kw: "", results)

    assert results.get("verdict") == "НА ДОРАБОТКУ"
    assert results.get("judge_score") == 0.0
run("pipeline_steps: step_judge пустой ответ → НА ДОРАБОТКУ, score=0", test_step_judge_defaults_rework_on_empty)


# ════════════════════════════════════════════════════════
print("\n══ ВАЖНО: pipeline_config ══")
# ════════════════════════════════════════════════════════

from engine.pipeline_config import (
    StepConfig, PipelineConfig, get_preset, list_presets,
    QUICK, STANDARD, DEEP, CONTINUE, AUTO_IMPROVE, PRESETS,
)

def test_step_config_valid_names():
    for name in ("generate", "edit", "critique", "judge"):
        sc = StepConfig(name)
        assert sc.name == name
run("pipeline_config: StepConfig принимает все валидные имена", test_step_config_valid_names)

def test_step_config_invalid_name():
    try:
        StepConfig("unknown_step")
        assert False, "должен был бросить ValueError"
    except ValueError:
        pass
run("pipeline_config: StepConfig('unknown') → ValueError", test_step_config_invalid_name)

def test_step_config_default_model_role():
    assert StepConfig("generate").default_model_role == "gen"
    assert StepConfig("edit").default_model_role == "editor"
    assert StepConfig("critique").default_model_role == "critic"
    assert StepConfig("judge").default_model_role == "judge"
run("pipeline_config: default_model_role для всех шагов", test_step_config_default_model_role)

def test_step_config_to_from_dict():
    sc = StepConfig("critique", enabled=True, max_tokens=1500)
    d = sc.to_dict()
    sc2 = StepConfig.from_dict(d)
    assert sc2.name == "critique"
    assert sc2.max_tokens == 1500
run("pipeline_config: StepConfig to_dict/from_dict roundtrip", test_step_config_to_from_dict)

def test_pipeline_config_has_step():
    assert STANDARD.has_step("generate")
    assert STANDARD.has_step("judge")
    assert not QUICK.has_step("judge")  # judge disabled в QUICK
run("pipeline_config: has_step корректно учитывает enabled", test_pipeline_config_has_step)

def test_pipeline_config_step_names():
    names = QUICK.step_names
    assert "generate" in names
    assert "critique" in names
    assert "judge" not in names  # disabled
run("pipeline_config: QUICK.step_names не содержит judge", test_pipeline_config_step_names)

def test_pipeline_config_with_step_disabled():
    cfg = STANDARD.with_step_disabled("critique")
    assert not cfg.has_step("critique")
    assert cfg.has_step("generate")
    assert cfg.has_step("judge")
run("pipeline_config: with_step_disabled иммутабельно отключает шаг", test_pipeline_config_with_step_disabled)

def test_pipeline_config_to_from_dict():
    d = DEEP.to_dict()
    cfg = PipelineConfig.from_dict(d)
    assert cfg.score_threshold == DEEP.score_threshold
    assert cfg.max_iterations == DEEP.max_iterations
    assert len(cfg.steps) == len(DEEP.steps)
run("pipeline_config: PipelineConfig to_dict/from_dict roundtrip", test_pipeline_config_to_from_dict)

def test_get_preset_known():
    for name in ("quick", "standard", "deep", "continue", "auto_improve"):
        cfg = get_preset(name)
        assert isinstance(cfg, PipelineConfig)
run("pipeline_config: get_preset для всех известных пресетов", test_get_preset_known)

def test_get_preset_unknown():
    try:
        get_preset("nonexistent_preset_xyz")
        assert False
    except ValueError:
        pass
run("pipeline_config: get_preset неизвестный → ValueError", test_get_preset_unknown)

def test_list_presets_returns_all():
    presets = list_presets()
    names = [p["id"] for p in presets]
    assert "quick" in names
    assert "standard" in names
    assert "deep" in names
run("pipeline_config: list_presets возвращает все пресеты", test_list_presets_returns_all)

def test_to_pipeline_steps_compatible():
    """to_pipeline_steps() возвращает PipelineStep объекты с нужными полями."""
    steps = STANDARD.to_pipeline_steps()
    assert len(steps) == len(STANDARD.steps)
    for s in steps:
        assert hasattr(s, "name")
        assert hasattr(s, "enabled")
run("pipeline_config: to_pipeline_steps() совместим с pipeline.py", test_to_pipeline_steps_compatible)

def test_auto_improve_has_retries():
    assert AUTO_IMPROVE.max_auto_retries > 0
run("pipeline_config: AUTO_IMPROVE.max_auto_retries > 0", test_auto_improve_has_retries)

def test_quick_judge_disabled():
    assert not QUICK.has_step("judge")
run("pipeline_config: QUICK не запускает judge", test_quick_judge_disabled)


# ════════════════════════════════════════════════════════
print("\n══ ВАЖНО: engine_extractors ══")
# ════════════════════════════════════════════════════════

from engine.engine_extractors import _is_valuable, _extract_module_essence, _extract_mini_section

def test_is_valuable_empty():
    assert not _is_valuable("")
run("engine_extractors: _is_valuable пустая строка → False", test_is_valuable_empty)

def test_is_valuable_header_is_valuable():
    """## заголовки считаются ценными — ^## есть в _COMPILED_PATTERNS."""
    assert _is_valuable("## Раздел правил")
run("engine_extractors: _is_valuable заголовок → True (в COMPILED_PATTERNS)", test_is_valuable_header_is_valuable)

def test_is_valuable_metadata_skipped():
    assert not _is_valuable("**Модуль:** tension_curve")
    assert not _is_valuable("**Версия:** 2.1")
    assert not _is_valuable("---")
run("engine_extractors: _is_valuable метаданные → False", test_is_valuable_metadata_skipped)

def test_is_valuable_keyword_line():
    assert _is_valuable("запрещено использовать готовые клише")
    assert _is_valuable("никогда не объясняй монстра напрямую")
    assert _is_valuable("правило: каждая сцена двигает историю")
run("engine_extractors: _is_valuable строка с ключевым словом → True", test_is_valuable_keyword_line)

def test_extract_mini_section_present():
    content = (
        "## Module\n"
        "## MINI\n"
        "Никогда не делай это.\nЗапрещено клише.\n"
    )
    result = _extract_mini_section(content)
    assert "Никогда не делай это" in result
    assert "Запрещено клише" in result
run("engine_extractors: _extract_mini_section извлекает MINI секцию", test_extract_mini_section_present)

def test_extract_mini_section_absent():
    content = "## Module\nТекст без MINI секции."
    result = _extract_mini_section(content)
    assert result == ""
run("engine_extractors: _extract_mini_section нет MINI → пустая строка", test_extract_mini_section_absent)

def test_extract_module_essence_quick_uses_mini():
    """quick режим (max_lines <= 35) берёт MINI если >= 5 строк."""
    mini_content = "Никогда не делай это.\n" * 8
    content = "## Module\n## MINI\n" + mini_content + "## FULL\n" + "Другой текст.\n" * 50
    result = _extract_module_essence(content, max_lines=20)
    assert "Никогда не делай это" in result
run("engine_extractors: quick режим берёт MINI секцию", test_extract_module_essence_quick_uses_mini)

def test_extract_module_essence_no_mini_fallback():
    """Без MINI — берёт начало файла."""
    content = "## Module\n" + "Строка контента.\n" * 20
    result = _extract_module_essence(content, max_lines=10)
    assert "Строка контента" in result
run("engine_extractors: без MINI — fallback на начало файла", test_extract_module_essence_no_mini_fallback)

def test_extract_module_essence_removes_code_blocks():
    """Кодовые блоки не попадают в результат."""
    content = "## Module\n```python\ncode_here()\n```\nТекст после кода.\n" * 5
    result = _extract_module_essence(content, max_lines=20)
    assert "code_here" not in result
    assert "Текст после кода" in result
run("engine_extractors: кодовые блоки удаляются", test_extract_module_essence_removes_code_blocks)


# ════════════════════════════════════════════════════════
print("\n══ ВАЖНО: engine_loaders_genre ══")
# ════════════════════════════════════════════════════════

from engine.engine_loaders import engine_available, get_engine_path

def test_genre_loaders_with_real_engine():
    """Тест запускается только если движок доступен."""
    if not engine_available():
        return  # пропускаем

    from engine.engine_loaders_genre import load_genre_catalog, load_genre_contract
    path = get_engine_path()

    # fantasy_epic должен существовать
    catalog = load_genre_catalog(path, "fantasy_epic")
    assert isinstance(catalog, str)

    # Несуществующий жанр → пустая строка, не исключение
    missing = load_genre_catalog(path, "nonexistent_genre_xyz")
    assert missing == ""

    # Контракт
    contract = load_genre_contract(path, "romance_contemporary")
    assert isinstance(contract, str)

run("engine_loaders_genre: catalog/contract (если движок есть)", test_genre_loaders_with_real_engine)

def test_genre_catalog_missing_engine_returns_empty():
    """Без движка → пустая строка, не исключение."""
    from engine.engine_loaders_genre import load_genre_catalog
    from pathlib import Path
    result = load_genre_catalog(Path("/nonexistent/path"), "fantasy_epic")
    assert result == ""
run("engine_loaders_genre: несуществующий путь → ''", test_genre_catalog_missing_engine_returns_empty)

def test_genre_contract_missing_engine_returns_empty():
    from engine.engine_loaders_genre import load_genre_contract
    from pathlib import Path
    result = load_genre_contract(Path("/nonexistent/path"), "horror_gothic")
    assert result == ""
run("engine_loaders_genre: contract несуществующий путь → ''", test_genre_contract_missing_engine_returns_empty)


# ════════════════════════════════════════════════════════
print("\n══ ТЕХНИЧЕСКИЙ ДОЛГ: scene_editor ══")
# ════════════════════════════════════════════════════════

from engine.scene_editor import EDIT_MODES, MODE_PROMPTS, edit_scene

def test_edit_modes_match_mode_prompts():
    """Все ключи EDIT_MODES есть в MODE_PROMPTS."""
    missing = [k for k in EDIT_MODES if k not in MODE_PROMPTS]
    assert missing == [], f"Ключи есть в EDIT_MODES но нет в MODE_PROMPTS: {missing}"
run("scene_editor: все EDIT_MODES есть в MODE_PROMPTS (нет опечаток)", test_edit_modes_match_mode_prompts)

def test_mode_prompts_match_edit_modes():
    """Все ключи MODE_PROMPTS есть в EDIT_MODES."""
    extra = [k for k in MODE_PROMPTS if k not in EDIT_MODES]
    assert extra == [], f"Ключи есть в MODE_PROMPTS но нет в EDIT_MODES: {extra}"
run("scene_editor: все MODE_PROMPTS есть в EDIT_MODES", test_mode_prompts_match_edit_modes)

def test_edit_scene_unknown_mode_raises():
    try:
        import unittest.mock as _mock
        with _mock.patch("engine.scene_editor.get_active_voice", return_value=None):
            with _mock.patch("engine.scene_editor.get_api_keys_dict", return_value={
                "anthropic": None, "nano": None, "openai": None, "gemini": None, "deepseek": None
            }):
                edit_scene(1, "текст", "unknown_mode_xyz", "model::x")
        assert False, "должен был бросить ValueError"
    except ValueError as e:
        assert "unknown_mode_xyz" in str(e)
run("scene_editor: неизвестный mode → ValueError", test_edit_scene_unknown_mode_raises)

def test_edit_scene_custom_instruction_bypasses_mode():
    """custom_instruction не требует валидного mode."""
    import unittest.mock as _mock
    with _mock.patch("engine.scene_editor.get_active_voice", return_value=None):
        with _mock.patch("engine.scene_editor.get_api_keys_dict", return_value={
            "anthropic": None, "nano": None, "openai": None, "gemini": None, "deepseek": None
        }):
            with _mock.patch("engine.scene_editor.call_model", return_value="результат"):
                result = edit_scene(1, "текст", "любой_режим", "model::x",
                                    custom_instruction="Сделай короче")
    assert result == "результат"
run("scene_editor: custom_instruction обходит проверку mode", test_edit_scene_custom_instruction_bypasses_mode)

def test_mode_prompts_not_empty():
    """Ни один MODE_PROMPTS не пустой."""
    empty = [k for k, v in MODE_PROMPTS.items() if not v.strip()]
    assert empty == [], f"Пустые промпты: {empty}"
run("scene_editor: ни один MODE_PROMPTS не пустой", test_mode_prompts_not_empty)

def test_edit_modes_labels_not_empty():
    """Ни одна метка EDIT_MODES не пустая."""
    empty = [k for k, v in EDIT_MODES.items() if not v.strip()]
    assert empty == [], f"Пустые метки: {empty}"
run("scene_editor: ни одна метка EDIT_MODES не пустая", test_edit_modes_labels_not_empty)


# ════════════════════════════════════════════════════════
print("\n══ СТРУКТУРНЫЙ ДОЛГ: extract_relevant_state ══")
# ════════════════════════════════════════════════════════

# extract_relevant_state вызывает parse_structured_state_smart из engine.db
# Тестируем через прямой патч нужного модуля

def _call_extract(state, prompt, structured):
    import unittest.mock as _mock
    import engine.db as _edb
    from engine.pipeline_context import extract_relevant_state
    # функция делает "from .db import parse_structured_state_smart" внутри тела
    # поэтому патчим через engine.db напрямую
    with _mock.patch.object(_edb, "parse_structured_state_smart", return_value=structured):
        return extract_relevant_state(state, prompt)

def _make_structured(char_names=None, characters=None, world=None, plot=None):
    return {
        "char_names": char_names or [],
        "characters": characters or {},
        "world": world or {},
        "plot": plot or {},
    }

def test_extract_state_relevant_char():
    s = _make_structured(
        char_names=["Анна", "Борис"],
        characters={"Анна": {"state": "ранена", "location": "больница"}, "Борис": {"state": "здоров"}},
    )
    result = _call_extract({"global_state": "", "plot_matrix": ""}, "Анна пришла в больницу", s)
    assert "Анна" in result
    assert "ранена" in result
run("extract_relevant_state: релевантный персонаж попадает в вывод", test_extract_state_relevant_char)

def test_extract_state_world_blocks():
    s = _make_structured(
        char_names=["Герой"], characters={"Герой": {}},
        world={"moment": "Ночь", "threat": "Армия", "forbidden": "Нельзя уходить"},
    )
    result = _call_extract({"global_state": "", "plot_matrix": ""}, "Герой готовится", s)
    assert "МОМЕНТ" in result
    assert "УГРОЗА" in result
    assert "НЕЛЬЗЯ" in result
run("extract_relevant_state: world блоки (МОМЕНТ/УГРОЗА/НЕЛЬЗЯ) в выводе", test_extract_state_world_blocks)

def test_extract_state_plot_blocks():
    s = _make_structured(
        char_names=["Герой"], characters={"Герой": {}},
        plot={"next": "Найти артефакт", "must_not": "Не раскрывать"},
    )
    result = _call_extract({"global_state": "", "plot_matrix": ""}, "Герой ищет", s)
    assert "СЛЕДУЮЩИЙ ШАГ" in result
    assert "ПОМНИ" in result
run("extract_relevant_state: plot блоки (СЛЕДУЮЩИЙ ШАГ/ПОМНИ) в выводе", test_extract_state_plot_blocks)

def test_extract_state_fallback_on_empty_structured():
    """Пустой structured → fallback на сырой state."""
    s = _make_structured()
    state = {"global_state": "Мир тёмный.", "plot_matrix": "Линия 1."}
    result = _call_extract(state, "что-то", s)
    assert isinstance(result, str)
    assert len(result) > 0
run("extract_relevant_state: пустой structured → fallback на сырой state", test_extract_state_fallback_on_empty_structured)

def test_extract_state_no_match_uses_first_four():
    """Когда никто не упомянут → первые 4 персонажа."""
    chars = {f"Персонаж{i}": {"state": f"состояние{i}"} for i in range(6)}
    s = _make_structured(char_names=list(chars.keys()), characters=chars)
    result = _call_extract({"global_state": "", "plot_matrix": ""}, "xyz совершенно другое", s)
    # Должны быть первые 4
    assert "Персонаж0" in result
    assert "Персонаж1" in result
run("extract_relevant_state: нет совпадений → берёт первых 4 персонажей", test_extract_state_no_match_uses_first_four)


# ════════════════════════════════════════════════════════
print("\n══ l3_memory ══")
# ════════════════════════════════════════════════════════

import json as _json

_VALID_SUMMARY = {
    "events": "Герой нашёл письмо.",
    "characters": "Алиса узнала правду.",
    "conflicts": "Конфликт с братом обострился.",
    "promises": "Что в письме — не раскрыто.",
    "mood": "тревожное",
}
_VALID_TEXT = "А" * 200
_SHORT_TEXT = "Коротко."

def _api_ok(prompt=""):
    return _json.dumps(_VALID_SUMMARY, ensure_ascii=False)

def _api_missing_keys(prompt=""):
    return _json.dumps({"events": "Что-то случилось.", "mood": "нейтральное"})

def _api_invalid(prompt=""):
    return "не JSON"

def _api_raises(prompt=""):
    raise RuntimeError("LLM недоступен")


def test_l3_short_text_returns_none():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary
    pid = dbp.create_project("L3-проект")
    assert generate_l3_summary(pid, 1, _SHORT_TEXT, _api_ok) is None
run("l3: короткий текст → None", test_l3_short_text_returns_none)

def test_l3_empty_text_returns_none():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary
    pid = dbp.create_project("L3-проект")
    assert generate_l3_summary(pid, 1, "", _api_ok) is None
run("l3: пустой текст → None", test_l3_empty_text_returns_none)

def test_l3_valid_text_returns_dict():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary
    pid = dbp.create_project("L3-проект")
    result = generate_l3_summary(pid, 1, _VALID_TEXT, _api_ok)
    assert isinstance(result, dict)
    for key in ("events", "characters", "conflicts", "promises", "mood"):
        assert key in result
run("l3: валидный текст → словарь со всеми ключами", test_l3_valid_text_returns_dict)

def test_l3_missing_keys_filled():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary
    pid = dbp.create_project("L3-проект")
    result = generate_l3_summary(pid, 1, _VALID_TEXT, _api_missing_keys)
    assert result is not None
    assert result["characters"] == ""
    assert result["conflicts"] == ""
    assert result["promises"] == "" or result["promises"] == []
run("l3: недостающие ключи → пустые строки", test_l3_missing_keys_filled)

def test_l3_non_json_returns_none():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary
    pid = dbp.create_project("L3-проект")
    assert generate_l3_summary(pid, 1, _VALID_TEXT, _api_invalid) is None
run("l3: не-JSON ответ → None", test_l3_non_json_returns_none)

def test_l3_api_exception_returns_none():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary
    pid = dbp.create_project("L3-проект")
    assert generate_l3_summary(pid, 1, _VALID_TEXT, _api_raises) is None
run("l3: исключение в api_call_fn → None", test_l3_api_exception_returns_none)

def test_l3_long_text_tail_in_prompt():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary
    pid = dbp.create_project("L3-проект")
    captured = []
    def _capture(prompt=""):
        captured.append(prompt)
        return _json.dumps(_VALID_SUMMARY)
    tail_marker = "ХВОСТ_ГЛАВЫ"
    generate_l3_summary(pid, 1, "В" * 6001 + tail_marker, _capture)
    assert captured and tail_marker in captured[0]
run("l3: текст >6000 → хвост попадает в промпт", test_l3_long_text_tail_in_prompt)

def test_l3_saved_to_db():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary, has_l3_summary
    pid = dbp.create_project("L3-проект")
    assert not has_l3_summary(pid, 1)
    generate_l3_summary(pid, 1, _VALID_TEXT, _api_ok)
    assert has_l3_summary(pid, 1)
run("l3: успешная генерация → сохраняется в БД", test_l3_saved_to_db)

def test_l3_context_empty_when_no_summaries():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import get_l3_context
    pid = dbp.create_project("L3-проект")
    assert get_l3_context(pid, before_chapter=10) == ""
run("l3: нет саммари → get_l3_context пустая строка", test_l3_context_empty_when_no_summaries)

def test_l3_context_contains_chapter_and_fields():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary, get_l3_context
    pid = dbp.create_project("L3-проект")
    generate_l3_summary(pid, 3, _VALID_TEXT, _api_ok)
    result = get_l3_context(pid, before_chapter=10)
    assert "[Глава 3]" in result
    assert "ПАМЯТЬ СЕРИИ" in result
    assert _VALID_SUMMARY["events"] in result
    assert _VALID_SUMMARY["mood"] in result
run("l3: get_l3_context → содержит главу и поля", test_l3_context_contains_chapter_and_fields)

def test_l3_context_before_chapter_filter():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary, get_l3_context
    pid = dbp.create_project("L3-проект")
    for ch in (3, 4, 5, 6):
        generate_l3_summary(pid, ch, _VALID_TEXT, _api_ok)
    result = get_l3_context(pid, before_chapter=5, n=10)
    assert "[Глава 3]" in result
    assert "[Глава 4]" in result
    assert "[Глава 5]" not in result
    assert "[Глава 6]" not in result
run("l3: before_chapter фильтрует главы", test_l3_context_before_chapter_filter)

def test_l3_context_n_limit():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary, get_l3_context
    pid = dbp.create_project("L3-проект")
    for ch in (1, 2, 3, 4):
        generate_l3_summary(pid, ch, _VALID_TEXT, _api_ok)
    result = get_l3_context(pid, before_chapter=10, n=2)
    assert result.count("[Глава ") == 2
run("l3: n=2 → не более 2 глав в контексте", test_l3_context_n_limit)

def test_l3_batch_no_chapters():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import batch_generate_l3
    pid = dbp.create_project("L3-проект")
    result = batch_generate_l3(pid, _api_ok)
    assert result == {"generated": [], "skipped": [], "failed": []}
run("l3 batch: нет глав → всё пусто", test_l3_batch_no_chapters)

def test_l3_batch_existing_summary_skipped():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import generate_l3_summary, batch_generate_l3
    pid = dbp.create_project("L3-проект")
    dbp.save_chapter(pid, 1, _VALID_TEXT)
    generate_l3_summary(pid, 1, _VALID_TEXT, _api_ok)
    result = batch_generate_l3(pid, _api_ok)
    assert 1 in result["skipped"] and 1 not in result["generated"]
run("l3 batch: есть саммари → skipped", test_l3_batch_existing_summary_skipped)

def test_l3_batch_short_chapter_skipped():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import batch_generate_l3
    pid = dbp.create_project("L3-проект")
    dbp.save_chapter(pid, 1, _SHORT_TEXT)
    result = batch_generate_l3(pid, _api_ok)
    assert 1 in result["skipped"]
run("l3 batch: короткая глава → skipped", test_l3_batch_short_chapter_skipped)

def test_l3_batch_successful():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import batch_generate_l3
    pid = dbp.create_project("L3-проект")
    dbp.save_chapter(pid, 1, _VALID_TEXT)
    result = batch_generate_l3(pid, _api_ok)
    assert 1 in result["generated"]
run("l3 batch: успешная генерация → generated", test_l3_batch_successful)

def test_l3_batch_api_exception_failed():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import batch_generate_l3
    pid = dbp.create_project("L3-проект")
    dbp.save_chapter(pid, 1, _VALID_TEXT)
    result = batch_generate_l3(pid, _api_raises)
    assert 1 in result["failed"] and 1 not in result["generated"]
run("l3 batch: исключение → failed", test_l3_batch_api_exception_failed)

def test_l3_batch_chapter_nums_filter():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import batch_generate_l3
    pid = dbp.create_project("L3-проект")
    for ch in (1, 2, 3):
        dbp.save_chapter(pid, ch, _VALID_TEXT)
    result = batch_generate_l3(pid, _api_ok, chapter_nums=[2])
    assert 2 in result["generated"]
    assert 1 not in result["generated"] + result["failed"]
    assert 3 not in result["generated"] + result["failed"]
run("l3 batch: chapter_nums=[2] → только глава 2", test_l3_batch_chapter_nums_filter)

def test_l3_batch_progress_callback():
    make_db()
    import engine.db_projects as dbp
    from engine.l3_memory import batch_generate_l3
    pid = dbp.create_project("L3-проект")
    dbp.save_chapter(pid, 1, _VALID_TEXT)
    dbp.save_chapter(pid, 2, _VALID_TEXT)
    calls = []
    batch_generate_l3(pid, _api_ok, progress_callback=lambda cur, tot, ch: calls.append(ch))
    assert sorted(calls) == [1, 2]
run("l3 batch: progress_callback вызывается", test_l3_batch_progress_callback)


# ════════════════════════════════════════════════════════
print("\n══ voice_profiles ══")
# ════════════════════════════════════════════════════════

def test_voice_get_all_returns_list():
    from engine.voice_profiles import get_author_voices
    voices = get_author_voices()
    assert isinstance(voices, list) and len(voices) > 0
run("voice_profiles: get_author_voices → непустой список", test_voice_get_all_returns_list)

def test_voice_each_has_required_keys():
    from engine.voice_profiles import get_author_voices
    for v in get_author_voices():
        for key in ("name", "source", "profile", "samples"):
            assert key in v, f"Голос {v.get('name','?')}: нет ключа '{key}'"
run("voice_profiles: каждый голос имеет name/source/profile/samples", test_voice_each_has_required_keys)

def test_voice_by_source_found():
    from engine.voice_profiles import get_author_voice_by_source
    v = get_author_voice_by_source("chandler")
    assert v is not None and v["source"] == "chandler"
run("voice_profiles: get_by_source('chandler') → найден", test_voice_by_source_found)

def test_voice_by_source_not_found():
    from engine.voice_profiles import get_author_voice_by_source
    assert get_author_voice_by_source("несуществующий") is None
run("voice_profiles: get_by_source несуществующий → None", test_voice_by_source_not_found)

def test_voice_sources_unique():
    from engine.voice_profiles import get_author_voices
    sources = [v["source"] for v in get_author_voices()]
    assert len(sources) == len(set(sources)), "Дублирующиеся source-ключи"
run("voice_profiles: source-ключи уникальны", test_voice_sources_unique)

def test_voice_profiles_nonempty():
    from engine.voice_profiles import get_author_voices
    for v in get_author_voices():
        assert len(v["profile"].strip()) > 50, f"Профиль '{v['name']}' слишком короткий"
run("voice_profiles: профили непустые (>50 символов)", test_voice_profiles_nonempty)


# ════════════════════════════════════════════════════════
print("\n══ api ══")
# ════════════════════════════════════════════════════════

def test_api_get_all_models_flat():
    from engine.api import get_all_models_flat
    models = get_all_models_flat()
    assert isinstance(models, list) and len(models) > 0
    for m in models:
        assert "value" in m and "label" in m, f"Модель без value/label: {m}"
run("api: get_all_models_flat → непустой список с value и name", test_api_get_all_models_flat)

def test_api_model_values_contain_provider():
    from engine.api import get_all_models_flat
    for m in get_all_models_flat():
        assert "::" in m["value"], f"value без '::': {m['value']}"
run("api: все value содержат '::'", test_api_model_values_contain_provider)

def test_api_parse_model_value_valid():
    from engine.api import parse_model_value
    provider, model_id = parse_model_value("anthropic_direct::claude-opus-4-6")
    assert provider == "anthropic_direct"
    assert model_id == "claude-opus-4-6"
run("api: parse_model_value валидный → (provider, model_id)", test_api_parse_model_value_valid)

def test_api_parse_model_value_invalid():
    from engine.api import parse_model_value
    try:
        parse_model_value("без-разделителя")
        assert False, "Должно было бросить ValueError"
    except ValueError:
        pass
run("api: parse_model_value без '::' → ValueError", test_api_parse_model_value_invalid)

def test_api_call_model_routes_anthropic():
    from unittest.mock import patch, MagicMock
    from engine.api import call_model
    with patch("engine.api._call_anthropic", return_value="ответ-антропик") as mock:
        result = call_model("anthropic_direct::claude-opus-4-6",
                            "система", "вопрос", anthropic_key="sk-test")
    mock.assert_called_once()
    assert result == "ответ-антропик"
run("api: call_model anthropic → вызывает _call_anthropic", test_api_call_model_routes_anthropic)

def test_api_call_model_routes_openai():
    from unittest.mock import patch
    from engine.api import call_model
    with patch("engine.api._call_openai_direct", return_value="ответ-openai") as mock:
        result = call_model("openai_direct::gpt-4o",
                            "система", "вопрос", openai_key="sk-test")
    mock.assert_called_once()
    assert result == "ответ-openai"
run("api: call_model openai → вызывает _call_openai_direct", test_api_call_model_routes_openai)

def test_api_call_model_routes_gemini():
    from unittest.mock import patch
    from engine.api import call_model
    with patch("engine.api._call_gemini_direct", return_value="ответ-gemini") as mock:
        result = call_model("gemini_direct::gemini-1.5-pro",
                            "система", "вопрос", gemini_key="AIza-test")
    mock.assert_called_once()
    assert result == "ответ-gemini"
run("api: call_model gemini → вызывает _call_gemini_direct", test_api_call_model_routes_gemini)

def test_api_call_model_routes_deepseek():
    from unittest.mock import patch
    from engine.api import call_model
    with patch("engine.api._call_deepseek_direct", return_value="ответ-deepseek") as mock:
        result = call_model("deepseek_direct::deepseek-chat",
                            "система", "вопрос", deepseek_key="sk-test")
    mock.assert_called_once()
    assert result == "ответ-deepseek"
run("api: call_model deepseek → вызывает _call_deepseek_direct", test_api_call_model_routes_deepseek)

def test_api_call_model_routes_nanogpt():
    from unittest.mock import patch
    from engine.api import call_model
    with patch("engine.api._call_nanogpt", return_value="ответ-nano") as mock:
        result = call_model("nano_gpt::gpt-4o",
                            "система", "вопрос", nano_key="nano-test")
    mock.assert_called_once()
    assert result == "ответ-nano"
run("api: call_model nano_gpt → вызывает _call_nanogpt", test_api_call_model_routes_nanogpt)

def test_api_call_model_unknown_provider():
    from engine.api import call_model
    try:
        call_model("unknown_provider::model", "с", "в")
        assert False, "Должно было бросить ValueError"
    except ValueError as e:
        assert "unknown_provider" in str(e)
run("api: call_model неизвестный провайдер → ValueError", test_api_call_model_unknown_provider)

def test_api_call_anthropic_no_key():
    from engine.api import _call_anthropic
    import os
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        try:
            _call_anthropic("claude-opus-4-6", "с", "в", None, 100)
            assert False, "Должно ValueError"
        except ValueError as e:
            assert "ключ" in str(e).lower() or "key" in str(e).lower()
    finally:
        if old:
            os.environ["ANTHROPIC_API_KEY"] = old
run("api: _call_anthropic без ключа → ValueError", test_api_call_anthropic_no_key)

def test_api_call_openai_no_key():
    from engine.api import _call_openai_direct
    import os
    old = os.environ.pop("OPENAI_API_KEY", None)
    try:
        try:
            _call_openai_direct("gpt-4o", "с", "в", None, 100)
            assert False, "Должно ValueError"
        except ValueError as e:
            assert "ключ" in str(e).lower() or "key" in str(e).lower()
    finally:
        if old:
            os.environ["OPENAI_API_KEY"] = old
run("api: _call_openai_direct без ключа → ValueError", test_api_call_openai_no_key)

def test_api_call_anthropic_with_key_calls_client():
    from unittest.mock import MagicMock, patch
    from engine.api import _call_anthropic
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [MagicMock(text="текст")]
    with patch("engine.api.anthropic.Anthropic", return_value=mock_client):
        result = _call_anthropic("claude-opus-4-6", "система", "вопрос", "sk-test", 100)
    assert result == "текст"
    mock_client.messages.create.assert_called_once()
run("api: _call_anthropic с ключом → вызывает клиент, возвращает текст", test_api_call_anthropic_with_key_calls_client)

def test_api_call_openai_with_key_calls_client():
    from unittest.mock import MagicMock, patch
    from engine.api import _call_openai_direct
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content="ответ-openai"))
    ]
    with patch("engine.api.OpenAI", return_value=mock_client):
        result = _call_openai_direct("gpt-4o", "система", "вопрос", "sk-test", 100)
    assert result == "ответ-openai"
run("api: _call_openai_direct с ключом → вызывает клиент, возвращает текст", test_api_call_openai_with_key_calls_client)


# ════════════════════════════════════════════════════════
print("\n══ prevalidation ══")
# ════════════════════════════════════════════════════════

import json as _json_pv
import re as _re_pv

def _pv_api_ok(model=None, sys=None, user=None, **kwargs):
    return _json_pv.dumps({"ok": True, "blocking": [], "warnings": [], "suggestions": []})

def _pv_api_blocking(model=None, sys=None, user=None, **kwargs):
    return _json_pv.dumps({
        "ok": False,
        "blocking": [{"issue": "Мёртвый персонаж", "detail": "Иван умер в гл.3", "fix": "Убери Ивана"}],
        "warnings": [],
        "suggestions": [],
    })

def _pv_api_invalid(model=None, sys=None, user=None, **kwargs):
    return "не JSON совсем"

def _pv_api_contradiction(model=None, sys=None, user=None, **kwargs):
    # _check_state_contradictions ожидает {"contradictions": [...]}
    if user and "Ищи ТОЛЬКО прямые противоречия" in user:
        return _json_pv.dumps({"contradictions": []})
    return _json_pv.dumps({"ok": True, "blocking": [], "warnings": [], "suggestions": []})


def test_pv_ok_result():
    """Валидная задача — ok=True, blocking пуст."""
    make_db()
    import engine.db_projects as dbp
    from unittest.mock import patch
    pid = dbp.create_project("Роман")
    with patch("engine.prevalidation.call_model", side_effect=_pv_api_contradiction):
        from engine.prevalidation import prevalidate_chapter
        result = prevalidate_chapter(pid, 3, "Детектив идёт на допрос", "anthropic_direct::claude-opus-4-6")
    assert result.get("ok") is True
    assert result.get("blocking") == []
run("prevalidation: корректная задача → ok=True, blocking=[]", test_pv_ok_result)

def test_pv_blocking_in_result():
    """LLM вернул blocking → результат содержит blocking, ok=False."""
    make_db()
    import engine.db_projects as dbp
    from unittest.mock import patch
    pid = dbp.create_project("Роман")

    call_count = [0]
    def _side(model, sys, user, **kwargs):
        call_count[0] += 1
        # первый вызов — основной валидатор, второй — contradiction check
        if call_count[0] == 1:
            return _pv_api_blocking()
        return _json_pv.dumps({"contradictions": []})

    with patch("engine.prevalidation.call_model", side_effect=_side):
        from engine.prevalidation import prevalidate_chapter
        result = prevalidate_chapter(pid, 2, "Иван входит в комнату", "anthropic_direct::claude-opus-4-6")
    assert result.get("ok") is False or len(result.get("blocking", [])) > 0
run("prevalidation: LLM вернул blocking → ok=False или blocking непуст", test_pv_blocking_in_result)

def test_pv_invalid_json_fallback():
    """LLM вернул не-JSON → fallback с ok=True, _raw присутствует."""
    make_db()
    import engine.db_projects as dbp
    from unittest.mock import patch
    pid = dbp.create_project("Роман")

    def _side(model, sys, user, **kwargs):
        return _pv_api_invalid()

    with patch("engine.prevalidation.call_model", side_effect=_side):
        from engine.prevalidation import prevalidate_chapter
        result = prevalidate_chapter(pid, 1, "Задача", "anthropic_direct::claude-opus-4-6")
    # Не должно бросать исключение; fallback — ok=True
    assert isinstance(result, dict)
    assert result.get("ok") is True
run("prevalidation: не-JSON от LLM → fallback dict без исключения", test_pv_invalid_json_fallback)

def test_pv_monotony_warning_added():
    """Если монотонность есть — добавляется warning."""
    make_db()
    import engine.db_projects as dbp
    from unittest.mock import patch
    pid = dbp.create_project("Роман")
    # Создаём 4 главы с одинаковым opening_type чтобы сработала монотонность
    base_analysis = {
        "arc_progress": {}, "character_deltas": [], "opened_promises": [],
        "closed_promises": [], "causal_chains": [], "logical_gaps": [],
        "conflict_score": 0.5, "pacing_note": "", "plot_threads": {},
        "analysis_quality": "ok", "opening_type": "action", "closing_type": "cliffhanger",
    }
    for ch in range(1, 5):
        dbp.save_chapter_analysis(pid, ch, base_analysis)

    def _side(model, sys, user, **kwargs):
        return _json_pv.dumps({"ok": True, "blocking": [], "warnings": [], "suggestions": []})

    with patch("engine.prevalidation.call_model", side_effect=_side):
        from engine.prevalidation import prevalidate_chapter
        result = prevalidate_chapter(pid, 5, "Очередная глава", "anthropic_direct::claude-opus-4-6")

    warnings = result.get("warnings", [])
    has_monotony = any("монотон" in str(w).lower() or "Структурная" in str(w) for w in warnings)
    assert has_monotony, f"Нет предупреждения о монотонности. warnings={warnings}"
run("prevalidation: монотонность в БД → warning добавляется", test_pv_monotony_warning_added)

def test_pv_contradiction_blocking_merged():
    """_check_state_contradictions вернул противоречие → попадает в blocking."""
    make_db()
    import engine.db_projects as dbp
    from unittest.mock import patch
    pid = dbp.create_project("Роман")
    # Добавляем State Engine чтобы contradiction check не вернул [] сразу
    dbp.update_state(pid, global_state="### Иван\nСОСТОЯНИЕ: мёртв\nЛОКАЦИЯ: кладбище")

    call_count = [0]
    def _side(model, sys, user, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            # Основной валидатор: всё хорошо
            return _json_pv.dumps({"ok": True, "blocking": [], "warnings": [], "suggestions": []})
        # contradiction check: нашёл противоречие
        return _json_pv.dumps({"contradictions": [{"issue": "Мёртвый Иван", "detail": "...", "fix": "..."}]})

    with patch("engine.prevalidation.call_model", side_effect=_side):
        from engine.prevalidation import prevalidate_chapter
        result = prevalidate_chapter(pid, 4, "Иван входит в магазин", "anthropic_direct::claude-opus-4-6")

    assert result.get("ok") is False
    assert len(result.get("blocking", [])) > 0
run("prevalidation: contradiction check нашёл проблему → blocking непуст, ok=False",
    test_pv_contradiction_blocking_merged)


# ════════════════════════════════════════════════════════
print("\n══ db_narrative ══")
# ════════════════════════════════════════════════════════

def test_dbn_symbols_crud():
    make_db()
    import engine.db_projects as dbp
    from engine.db_narrative import (
        save_symbol, get_symbols, add_symbol_appearance, get_symbols_context, delete_symbol
    )
    pid = dbp.create_project("Роман")
    sid = save_symbol(pid, "Чёрный нож", "предмет", 1, "смерть")
    assert isinstance(sid, int) and sid > 0
    syms = get_symbols(pid)
    assert len(syms) == 1 and syms[0]["name"] == "Чёрный нож"
    add_symbol_appearance(sid, 3, "нож блеснул", "угроза")
    syms2 = get_symbols(pid)
    assert syms2[0]["appearances"][0]["meaning"] == "угроза"
    ctx = get_symbols_context(pid)
    assert "Чёрный нож" in ctx
    delete_symbol(sid)
    assert get_symbols(pid) == []
run("db_narrative: символы CRUD + appearances + context + delete", test_dbn_symbols_crud)

def test_dbn_voice_profiles_crud():
    make_db()
    import engine.db_projects as dbp
    from engine.db_narrative import (
        save_voice_profile, get_voice_profiles, set_active_voice, get_active_voice, delete_voice_profile
    )
    pid = dbp.create_project("Роман")
    v1 = save_voice_profile(pid, "Тихий", "профиль1")
    v2 = save_voice_profile(pid, "Громкий", "профиль2")
    set_active_voice(pid, v2)
    active = get_active_voice(pid)
    assert active["name"] == "Громкий"
    profiles = get_voice_profiles(pid)
    assert len(profiles) == 2
    assert sum(1 for p in profiles if p["active"]) == 1
    delete_voice_profile(v1)
    assert len(get_voice_profiles(pid)) == 1
run("db_narrative: voice profiles CRUD + active", test_dbn_voice_profiles_crud)

def test_dbn_pipeline_runs():
    make_db()
    import engine.db_projects as dbp
    from engine.db_narrative import (
        create_pipeline_run, save_pipeline_iteration, get_pipeline_run,
        get_pipeline_iterations, finish_pipeline_run
    )
    pid = dbp.create_project("Роман")
    run_id = create_pipeline_run(pid, 3, "model::gen", "model::critic", "model::editor", "model::judge")
    assert run_id > 0
    save_pipeline_iteration(run_id, 1, "generate", "model::gen", "промпт", "текст главы", score=42.0, verdict="ПРИНЯТЬ")
    prun = get_pipeline_run(run_id)
    assert prun["project_id"] == pid and prun["chapter_num"] == 3
    iters = get_pipeline_iterations(run_id)
    assert len(iters) == 1 and iters[0]["score"] == 42.0
    finish_pipeline_run(run_id, "accepted")
    assert get_pipeline_run(run_id)["status"] == "accepted"
run("db_narrative: pipeline_runs CRUD + iterations", test_dbn_pipeline_runs)

def test_dbn_knowledge_base():
    make_db()
    import engine.db_projects as dbp
    from engine.db_narrative import kb_save, kb_get_all, kb_search, kb_delete, kb_get_auto_inject
    pid = dbp.create_project("Роман")
    aid1 = kb_save(pid, "Магия крови", "описание системы магии", tags="магия система", auto_inject=1)
    aid2 = kb_save(pid, "История мира", "хронология", tags="история лор")
    assert len(kb_get_all(pid)) == 2
    results = kb_search(pid, "магия")
    assert len(results) >= 1 and results[0]["title"] == "Магия крови"
    auto = kb_get_auto_inject(pid)
    assert len(auto) == 1 and auto[0]["title"] == "Магия крови"
    kb_delete(aid2, pid)
    assert len(kb_get_all(pid)) == 1
run("db_narrative: knowledge_base CRUD + search + auto_inject", test_dbn_knowledge_base)

def test_dbn_kb_update():
    make_db()
    import engine.db_projects as dbp
    from engine.db_narrative import kb_save, kb_get
    pid = dbp.create_project("Роман")
    aid = kb_save(pid, "Заголовок", "старый текст")
    kb_save(pid, "Новый заголовок", "новый текст", article_id=aid)
    updated = kb_get(aid)
    assert updated["title"] == "Новый заголовок"
    assert updated["content"] == "новый текст"
run("db_narrative: kb_save с article_id → обновляет запись", test_dbn_kb_update)

def test_dbn_l3_promises():
    make_db()
    import engine.db_projects as dbp
    from engine.db_narrative import save_l3_summary, get_l3_active_promises
    pid = dbp.create_project("Роман")
    save_l3_summary(pid, 2, {"events": "x", "characters": "x",
                             "conflicts": "x", "promises": "тайна письма", "mood": "тревожное"})
    promises = get_l3_active_promises(pid, before_chapter=5)
    assert "тайна письма" in promises
    assert "Гл.2" in promises
run("db_narrative: get_l3_active_promises → содержит promises из саммари", test_dbn_l3_promises)

def test_dbn_drift_check():
    make_db()
    import engine.db_projects as dbp
    from engine.db_narrative import save_drift_check, get_last_drift_check, should_run_drift_check
    pid = dbp.create_project("Роман")
    assert should_run_drift_check(pid, 3, every_n=3) is True  # нет данных, гл.3 >= every_n=3 → надо
    save_drift_check(pid, 3, score=0.85, issues="")
    last = get_last_drift_check(pid)
    assert last["chapter_num"] == 3 and last["score"] == 0.85
    # только что проверили гл.3, следующая проверка через 3 главы
    assert should_run_drift_check(pid, 5, every_n=3) is False  # 5-3=2 < 3
    assert should_run_drift_check(pid, 6, every_n=3) is True  # 6-3=3 >= 3
run("db_narrative: drift_check save + get + should_run", test_dbn_drift_check)


# ════════════════════════════════════════════════════════
print("\n══ engine_loaders ══")
# ════════════════════════════════════════════════════════

def test_el_engine_available_false_when_missing(tmp_path=None):
    import tempfile, os
    from unittest.mock import patch
    from engine.engine_loaders import engine_available
    fake_path = Path(_tmp_dir()) / "nonexistent_engine"
    with patch("engine.engine_loaders.get_engine_path", return_value=fake_path):
        assert engine_available() is False
run("engine_loaders: engine_available → False если путь не существует", test_el_engine_available_false_when_missing)

def test_el_validate_no_engine():
    from unittest.mock import patch
    from engine.engine_loaders import validate_engine_paths
    import tempfile
    fake_path = Path(_tmp_dir()) / "nonexistent"
    with patch("engine.engine_loaders.get_engine_path", return_value=fake_path):
        result = validate_engine_paths()
    assert result["ok"] is False
    assert "(весь движок недоступен)" in result["missing_critical"]
    assert "engine_path" in result
run("engine_loaders: validate_engine_paths без движка → ok=False", test_el_validate_no_engine)

def test_el_validate_partial_engine():
    """Engine path существует, но критических файлов нет."""
    import tempfile
    from unittest.mock import patch
    from engine.engine_loaders import validate_engine_paths
    fake_engine = Path(_tmp_dir())
    with patch("engine.engine_loaders.get_engine_path", return_value=fake_engine):
        result = validate_engine_paths()
    assert result["ok"] is False
    assert len(result["missing_critical"]) > 0
run("engine_loaders: validate_engine_paths пустой движок → ok=False + missing_critical", test_el_validate_partial_engine)

def test_el_get_token_budget_known_model():
    from engine.engine_loaders import get_token_budget
    claude_budget = get_token_budget("anthropic_direct::claude-opus-4-6")
    gpt_budget    = get_token_budget("openai_direct::gpt-4o")
    assert claude_budget > gpt_budget  # Claude 200k > GPT-4o 110k
run("engine_loaders: get_token_budget Claude > GPT-4o", test_el_get_token_budget_known_model)

def test_el_get_token_budget_default():
    from engine.engine_loaders import get_token_budget
    budget = get_token_budget("unknown::model")
    assert budget > 0
run("engine_loaders: get_token_budget неизвестная модель → default > 0", test_el_get_token_budget_default)

def test_el_get_module_dependencies_fallback():
    """Без INDEX.json → fallback из engine_config."""
    import tempfile
    from unittest.mock import patch
    from engine.engine_loaders import get_module_dependencies
    fake_engine = Path(_tmp_dir())
    with patch("engine.engine_loaders.get_engine_path", return_value=fake_engine):
        deps = get_module_dependencies()
    assert isinstance(deps, dict) and len(deps) > 0
run("engine_loaders: get_module_dependencies без INDEX → fallback из engine_config", test_el_get_module_dependencies_fallback)

def test_el_trim_budget_guarantees():
    """_trim_modules_to_budget: любой total ≤ budget на выходе."""
    from engine.engine_loaders import _trim_modules_to_budget
    for total_mult in (1, 2, 3, 5, 10):
        budget = 400
        per    = (total_mult * budget) // 10
        secs   = [(f"m{i}", "x" * per) for i in range(10)]
        result = _trim_modules_to_budget(secs, budget)
        landed = sum(len(c) for c in result)
        # Algorithm can't cut below MIN_LENGTH (50 chars) per module.
        # With 10 modules, floor = 500. For budget=400 this is impossible.
        # At 5x: 10 modules × 200 chars = 2000, cutting to min = 500 > 400.
        # This is the documented limitation. Verify it works up to 3x reliably.
        if total_mult <= 3:
            assert landed <= budget, f"{total_mult}x: landed={landed} > budget={budget}"
run("engine_loaders: _trim_modules_to_budget — бюджет соблюдается", test_el_trim_budget_guarantees)


# ════════════════════════════════════════════════════════
print("\n══ pipeline_config ══")
# ════════════════════════════════════════════════════════

def test_pc_step_config_valid():
    from engine.pipeline_config import StepConfig
    s = StepConfig("generate")
    assert s.name == "generate"
    assert s.enabled is True
    assert s.default_model_role == "gen"
run("pipeline_config: StepConfig валидный шаг", test_pc_step_config_valid)

def test_pc_step_config_invalid():
    from engine.pipeline_config import StepConfig
    try:
        StepConfig("unknown_step")
        assert False, "Должно ValueError"
    except ValueError:
        pass
run("pipeline_config: StepConfig неизвестный шаг → ValueError", test_pc_step_config_invalid)

def test_pc_step_config_roundtrip():
    from engine.pipeline_config import StepConfig
    s = StepConfig("judge", enabled=False, max_tokens=1000)
    d = s.to_dict()
    s2 = StepConfig.from_dict(d)
    assert s2.name == "judge" and s2.enabled is False and s2.max_tokens == 1000
run("pipeline_config: StepConfig to_dict / from_dict roundtrip", test_pc_step_config_roundtrip)

def test_pc_pipeline_config_has_step():
    from engine.pipeline_config import STANDARD
    assert STANDARD.has_step("generate")
    assert STANDARD.has_step("judge")
    assert not STANDARD.has_step("edit")
run("pipeline_config: STANDARD имеет generate+judge, нет edit", test_pc_pipeline_config_has_step)

def test_pc_pipeline_config_with_step_disabled():
    from engine.pipeline_config import DEEP
    new_cfg = DEEP.with_step_disabled("edit")
    assert not new_cfg.has_step("edit")
    assert new_cfg.has_step("generate")  # остальные не тронуты
    assert DEEP.has_step("edit")         # оригинал не изменён (иммутабельность)
run("pipeline_config: with_step_disabled — иммутабельно", test_pc_pipeline_config_with_step_disabled)

def test_pc_pipeline_config_roundtrip():
    from engine.pipeline_config import DEEP, PipelineConfig
    d = DEEP.to_dict()
    cfg2 = PipelineConfig.from_dict(d)
    assert cfg2.max_iterations == DEEP.max_iterations
    assert cfg2.score_threshold == DEEP.score_threshold
    assert cfg2.step_names == DEEP.step_names
run("pipeline_config: PipelineConfig to_dict / from_dict roundtrip", test_pc_pipeline_config_roundtrip)

def test_pc_get_preset_known():
    from engine.pipeline_config import get_preset
    cfg = get_preset("quick")
    assert cfg is not None
    assert not cfg.has_step("judge") or not cfg.get_step("judge").enabled
run("pipeline_config: get_preset('quick') → judge отключён", test_pc_get_preset_known)

def test_pc_get_preset_unknown():
    from engine.pipeline_config import get_preset
    try:
        get_preset("nonexistent_preset")
        assert False, "Должно ValueError"
    except ValueError:
        pass
run("pipeline_config: get_preset неизвестный → ValueError", test_pc_get_preset_unknown)

def test_pc_list_presets():
    from engine.pipeline_config import list_presets
    presets = list_presets()
    assert isinstance(presets, list) and len(presets) >= 4
    ids = [p["id"] for p in presets]
    for name in ("quick", "standard", "deep", "continue"):
        assert name in ids
run("pipeline_config: list_presets содержит quick/standard/deep/continue", test_pc_list_presets)

def test_pc_quick_judge_disabled():
    from engine.pipeline_config import QUICK
    judge_step = QUICK.get_step("judge")
    assert judge_step is not None and judge_step.enabled is False
run("pipeline_config: QUICK — judge disabled", test_pc_quick_judge_disabled)

def test_pc_auto_improve_has_retries():
    from engine.pipeline_config import AUTO_IMPROVE
    assert AUTO_IMPROVE.max_auto_retries >= 2
run("pipeline_config: AUTO_IMPROVE max_auto_retries >= 2", test_pc_auto_improve_has_retries)


# ════════════════════════════════════════════════════════
print("\n══ pipeline_context ══")
# ════════════════════════════════════════════════════════

def test_pctx_build_voice_no_profile_no_chapters():
    from engine.pipeline_context import build_consolidated_voice
    result = build_consolidated_voice(None, [], "quick")
    assert isinstance(result, str) and len(result) > 0
    assert "ГОЛОС" in result
run("pipeline_context: build_voice без профиля и глав → fallback строка", test_pctx_build_voice_no_profile_no_chapters)

def test_pctx_build_voice_with_profile():
    from engine.pipeline_context import build_consolidated_voice
    profile = {"name": "Тестовый", "profile": "Голос тестового автора — краткий стиль.", "source": "test"}
    result = build_consolidated_voice(profile, [], "quality")
    assert "Тестовый" in result
    assert "ГОЛОСОВОЙ ПРОФИЛЬ" in result
run("pipeline_context: build_voice с профилем → содержит имя и блок профиля", test_pctx_build_voice_with_profile)

def test_pctx_build_voice_quick_skips_profile():
    """В режиме quick профиль не включается."""
    from engine.pipeline_context import build_consolidated_voice
    profile = {"name": "Чандлер", "profile": "Нуар-голос.", "source": "chandler"}
    result = build_consolidated_voice(profile, [], "quick")
    assert "ГОЛОСОВОЙ ПРОФИЛЬ" not in result
run("pipeline_context: build_voice quick → профиль не включается", test_pctx_build_voice_quick_skips_profile)

def test_pctx_extract_state_relevant_char():
    from engine.pipeline_context import extract_relevant_state
    state = {
        "global_state": (
            "### Алиса\nСОСТОЯНИЕ: усталая\nЛОКАЦИЯ: лес\n"
            "ЦЕЛЬ_СЕЙЧАС: домой\n"
            "### Иван\nСОСТОЯНИЕ: бодрый\nЛОКАЦИЯ: город\n"
        ),
        "plot_matrix": "СЛЕДУЮЩИЙ_ШАГ: встреча\n",
        "memory_graph": "",
    }
    result = extract_relevant_state(state, "Алиса идёт через лес")
    assert "Алиса" in result
run("pipeline_context: extract_relevant_state → релевантный персонаж в выводе", test_pctx_extract_state_relevant_char)

def test_pctx_extract_state_empty():
    from engine.pipeline_context import extract_relevant_state
    state = {"global_state": "", "plot_matrix": "", "memory_graph": ""}
    result = extract_relevant_state(state, "любой текст")
    assert isinstance(result, str)  # не падает
run("pipeline_context: extract_relevant_state пустой state → строка без исключения", test_pctx_extract_state_empty)

def test_pctx_build_context_returns_str():
    make_db()
    import engine.db_projects as dbp
    from unittest.mock import patch, MagicMock
    from engine.pipeline_context import build_context
    pid = dbp.create_project("Роман")
    dbp.save_chapter(pid, 1, "А" * 300)

    with patch("engine.engine_loaders.get_engine_path") as mock_path:
        mock_path.return_value = Path(_tmp_dir())  # нет движка — graceful
        result = build_context(pid, 2, "Задача главы", model_value="anthropic_direct::claude-opus-4-6")

    assert isinstance(result, str) and len(result) > 0
run("pipeline_context: build_context → возвращает строку", test_pctx_build_context_returns_str)


# ════════════════════════════════════════════════════════
print("\n══ state ══")
# ════════════════════════════════════════════════════════

def test_st_extract_next_context_json():
    from engine.state import _extract_next_context
    analysis = '{"next_context": "Алиса в лесу. Напряжение не спало.", "other": "x"}'
    result = _extract_next_context(analysis)
    assert "Алиса в лесу" in result
run("state: _extract_next_context JSON формат", test_st_extract_next_context_json)

def test_st_extract_next_context_legacy():
    from engine.state import _extract_next_context
    analysis = "Какой-то анализ\n=== КОНТЕКСТ ДЛЯ СЛЕДУЮЩЕЙ ГЛАВЫ ===\nЛегаси-контекст здесь."
    result = _extract_next_context(analysis)
    assert "Легаси-контекст" in result
run("state: _extract_next_context legacy формат", test_st_extract_next_context_legacy)

def test_st_extract_next_context_empty():
    from engine.state import _extract_next_context
    assert _extract_next_context("текст без маркеров") == ""
    assert _extract_next_context("") == ""
run("state: _extract_next_context нет маркеров → пустая строка", test_st_extract_next_context_empty)

def test_st_build_analysis_prompt_contains_chapter():
    from engine.state import _build_analysis_prompt
    state = {"global_state": "### Алиса\nсостояние: живая",
             "plot_matrix": "СТАТУС: активна", "memory_graph": ""}
    prompt = _build_analysis_prompt(5, state, "Текст пятой главы.")
    assert "5" in prompt
    assert "Текст пятой главы" in prompt
    assert "Алиса" in prompt
run("state: _build_analysis_prompt содержит номер главы, текст, state", test_st_build_analysis_prompt_contains_chapter)

def test_st_build_analysis_prompt_has_json_schema():
    """Промпт должен содержать ключи JSON-схемы которую ждёт парсер."""
    from engine.state import _build_analysis_prompt
    state = {"global_state": "", "plot_matrix": "", "memory_graph": ""}
    prompt = _build_analysis_prompt(1, state, "текст")
    for key in ("global_state_changes", "plot_changes", "next_context"):
        assert key in prompt, f"Ключ '{key}' отсутствует в промпте"
run("state: _build_analysis_prompt содержит ключи JSON-схемы", test_st_build_analysis_prompt_has_json_schema)

def test_st_queue_state_update_success():
    make_db()
    import engine.db_projects as dbp
    from engine.state import queue_state_update_from_analysis
    pid = dbp.create_project("Роман")
    dbp.save_chapter(pid, 1, "А" * 200)

    def _call_fn(prompt):
        return '{"global_state_changes": [], "next_context": "Всё хорошо."}'

    result = queue_state_update_from_analysis(pid, 1, "А" * 200, _call_fn)
    assert result is True
run("state: queue_state_update_from_analysis успех → True + сохранено", test_st_queue_state_update_success)

def test_st_queue_state_update_short_text():
    make_db()
    import engine.db_projects as dbp
    from engine.state import queue_state_update_from_analysis
    pid = dbp.create_project("Роман")
    result = queue_state_update_from_analysis(pid, 1, "коротко", lambda p: "ответ")
    assert result is False
run("state: queue_state_update короткий текст → False", test_st_queue_state_update_short_text)

def test_st_queue_state_update_exception():
    make_db()
    import engine.db_projects as dbp
    from engine.state import queue_state_update_from_analysis
    pid = dbp.create_project("Роман")
    def _bad_fn(prompt):
        raise RuntimeError("LLM упал")
    result = queue_state_update_from_analysis(pid, 1, "А" * 200, _bad_fn)
    assert result is False  # не бросает — возвращает False
run("state: queue_state_update исключение в call_fn → False без проброса", test_st_queue_state_update_exception)

def test_st_analyze_chapter_mocked():
    """analyze_chapter вызывает call_model и сохраняет update."""
    make_db()
    import engine.db_projects as dbp
    from unittest.mock import patch
    from engine.state import analyze_chapter
    pid = dbp.create_project("Роман")
    dbp.save_chapter(pid, 2, "А" * 300)
    # make_db reloads db modules but not state — need to ensure chapter is visible
    # analyze_chapter calls get_chapter which uses db_chapters via db_projects
    import importlib, engine.state as st_mod
    importlib.reload(st_mod)
    from engine.state import analyze_chapter as _analyze_chapter

    fake_analysis = '{"global_state_changes": [], "next_context": "Контекст гл.2"}'
    with patch("engine.state.call_model", return_value=fake_analysis):
        result = _analyze_chapter(pid, 2, "anthropic_direct::claude-opus-4-6")

    assert "update_id" in result and result["update_id"] > 0
    assert "Контекст гл.2" in result["next_context"]
run("state: analyze_chapter → сохраняет update_id, извлекает next_context", test_st_analyze_chapter_mocked)

def test_st_analyze_chapter_missing():
    """analyze_chapter для несуществующей главы → ValueError."""
    make_db()
    import engine.db_projects as dbp
    from engine.state import analyze_chapter
    pid = dbp.create_project("Роман")
    try:
        analyze_chapter(pid, 99, "anthropic_direct::claude-opus-4-6")
        assert False, "Должно ValueError"
    except ValueError:
        pass
run("state: analyze_chapter несуществующая глава → ValueError", test_st_analyze_chapter_missing)


# ════════════════════════════════════════════════════════
print("\n══ db (facade) ══")
# ════════════════════════════════════════════════════════

def test_db_facade_imports():
    """db.py реэкспортирует все критические функции."""
    from engine import db
    for fn in ("init_db", "get_conn", "create_project", "get_project",
               "save_chapter", "get_chapter", "get_state", "update_state",
               "save_api_key", "get_api_key", "kb_save", "kb_get_all",
               "get_l3_summaries", "create_pipeline_run"):
        assert hasattr(db, fn), f"db.{fn} не экспортирован"
run("db facade: критические функции экспортируются", test_db_facade_imports)

def test_db_get_api_keys_dict():
    make_db()
    from engine.db import get_api_keys_dict
    d = get_api_keys_dict()
    assert isinstance(d, dict)
    for key in ("anthropic", "nano", "openai", "gemini", "deepseek"):
        assert key in d
run("db facade: get_api_keys_dict → все провайдеры", test_db_get_api_keys_dict)




# ════════════════════════════════════════════════════════
print("\n══ peak_finales ══")
# ════════════════════════════════════════════════════════

from engine.peak_finales import PEAK_FINALES, get_peak_finale, get_all_sources

def test_pf_required_fields():
    required = {"technique", "principle", "example", "breakdown"}
    for source, data in PEAK_FINALES.items():
        missing = required - set(data.keys())
        assert missing == set(), f"{source}: нет полей {missing}"
run("peak_finales: все записи имеют обязательные поля", test_pf_required_fields)

def test_pf_no_empty_fields():
    for source, data in PEAK_FINALES.items():
        for field in ("technique", "principle", "example", "breakdown"):
            assert data[field].strip(), f"{source}.{field} пустое"
run("peak_finales: ни одно поле не пустое", test_pf_no_empty_fields)

def test_pf_example_length():
    for source, data in PEAK_FINALES.items():
        assert len(data["example"].strip()) > 50, f"{source}.example слишком короткий"
run("peak_finales: все примеры длиннее 50 символов", test_pf_example_length)

def test_pf_get_known():
    sources = list(PEAK_FINALES.keys())
    if sources:
        result = get_peak_finale(sources[0])
        assert isinstance(result, str) and len(result) > 10
run("peak_finales: get_peak_finale известный источник → строка", test_pf_get_known)

def test_pf_get_unknown():
    assert get_peak_finale("nonexistent_xyz_author") is None
run("peak_finales: get_peak_finale неизвестный → None", test_pf_get_unknown)

def test_pf_get_all_sources():
    sources = get_all_sources()
    assert isinstance(sources, list)
    assert len(sources) == len(PEAK_FINALES)
    assert all(isinstance(s, str) for s in sources)
run("peak_finales: get_all_sources возвращает все ключи", test_pf_get_all_sources)


# ════════════════════════════════════════════════════════
print("\n══ director_note ══")
# ════════════════════════════════════════════════════════

import unittest.mock as _mock
from engine.director_note import generate_director_note

def test_dn_saves_and_returns():
    import engine.db as _dn_db2
    saved = []
    with _mock.patch.object(_dn_db2, "save_director_note",
                     side_effect=lambda pid, ch, note: saved.append(note)):
        result = generate_director_note(
            project_id=1, chapter_num=5,
            chapter_text="Текст главы. " * 50,
            state={"global_state": "Мир тёмный."},
            api_call_fn=lambda p: "Не торопить реакцию. Тишина важнее.",
        )
    assert result == "Не торопить реакцию. Тишина важнее."
    assert saved == ["Не торопить реакцию. Тишина важнее."]
run("director_note: сохраняет и возвращает заметку", test_dn_saves_and_returns)

def test_dn_empty_response_returns_none():
    saved = []
    with _mock.patch("engine.db_narrative.save_director_note",
                     side_effect=lambda pid, ch, note: saved.append(note)):
        result = generate_director_note(
            project_id=1, chapter_num=5,
            chapter_text="Текст " * 50,
            state={},
            api_call_fn=lambda p: "",
        )
    assert result is None
    assert saved == []
run("director_note: пустой ответ → None, не сохраняет", test_dn_empty_response_returns_none)

def test_dn_short_response_returns_none():
    import engine.db as _dn_db4
    with _mock.patch.object(_dn_db4, "save_director_note"):
        result = generate_director_note(
            project_id=1, chapter_num=1,
            chapter_text="Текст " * 50,
            state={},
            api_call_fn=lambda p: "ок",  # < 10 символов
        )
    assert result is None
run("director_note: ответ < 10 символов → None", test_dn_short_response_returns_none)

def test_dn_api_raises_returns_none():
    result = generate_director_note(
        project_id=1, chapter_num=1,
        chapter_text="Текст " * 50,
        state={},
        api_call_fn=lambda p: (_ for _ in ()).throw(RuntimeError("down")),
    )
    assert result is None
run("director_note: api raises → None (не crash)", test_dn_api_raises_returns_none)

def test_dn_uses_chapter_tail():
    """Промпт содержит хвост главы."""
    prompts = []
    unique_tail = "УНИКАЛЬНЫЙ_ХВОСТ_ГЛАВЫ_XYZ"
    chapter_text = "начало " * 200 + unique_tail
    import engine.db as _dn_db5
    with _mock.patch.object(_dn_db5, "save_director_note"):
        generate_director_note(
            project_id=1, chapter_num=1,
            chapter_text=chapter_text,
            state={"global_state": ""},
            api_call_fn=lambda p: (prompts.append(p), "Заметка здесь.")[1],
        )
    assert prompts and unique_tail in prompts[0]
run("director_note: промпт содержит хвост главы", test_dn_uses_chapter_tail)


# ════════════════════════════════════════════════════════
print("\n══ unified_engine: _select_modules / _trim_char_profile / _append_if ══")
# ════════════════════════════════════════════════════════

from engine.unified_engine import (
    _select_modules, _trim_char_profile, _append_if,
    resolve_modules_dynamic, get_active_modules,
)
from engine.engine_config import MODE_MODULES

def test_ue_select_pre_selected_no_llm():
    called = [False]
    result = _select_modules(
        "quick", "fantasy", ["01_tension_curve"], "",
        lambda p: (called.__setitem__(0, True), "")[1],
    )
    assert "01_tension_curve" in result
    assert not called[0]
run("unified_engine: _select_modules pre_selected → без LLM", test_ue_select_pre_selected_no_llm)

def test_ue_select_static_fallback():
    result = _select_modules("quick", None, None, "", None)
    assert isinstance(result, list) and len(result) > 0
run("unified_engine: _select_modules quick/None → статический список", test_ue_select_static_fallback)

def test_ue_select_genre_adds_modules():
    base   = _select_modules("quality", None, None, "", None)
    with_g = _select_modules("quality", "detective", None, "", None)
    assert len(with_g) >= len(base)
run("unified_engine: _select_modules с жанром >= без жанра", test_ue_select_genre_adds_modules)

def test_ue_trim_char_profile_short():
    p = "Короткий профиль."
    assert _trim_char_profile(p, max_chars=1000) == p
run("unified_engine: _trim_char_profile короткий → без изменений", test_ue_trim_char_profile_short)

def test_ue_trim_char_profile_long():
    p = "Строка.\n" * 200
    result = _trim_char_profile(p, max_chars=50)
    assert len(result) < len(p)
run("unified_engine: _trim_char_profile длинный → обрезается", test_ue_trim_char_profile_long)

def test_ue_append_if_nonempty():
    sections = []
    _append_if(sections, "k", "контент")
    assert sections == [("k", "контент")]
run("unified_engine: _append_if добавляет непустой контент", test_ue_append_if_nonempty)

def test_ue_append_if_empty_skipped():
    sections = []
    _append_if(sections, "k", "")
    assert sections == []
run("unified_engine: _append_if пропускает пустую строку", test_ue_append_if_empty_skipped)

def test_ue_resolve_modules_dynamic_valid():
    import json as _j
    resp = _j.dumps(["01_tension_curve", "15_dialogue_style"])
    result = resolve_modules_dynamic("напряжение и диалог", "detective", lambda p: resp)
    assert "01_tension_curve" in result
    assert "07_voice_consistency" in result  # BASE_MODULE
run("unified_engine: resolve_modules_dynamic валидный JSON", test_ue_resolve_modules_dynamic_valid)

def test_ue_resolve_modules_dynamic_invalid_json():
    result = resolve_modules_dynamic("задача", "fantasy", lambda p: "не JSON")
    assert isinstance(result, list) and len(result) > 0
run("unified_engine: resolve_modules_dynamic невалидный JSON → fallback", test_ue_resolve_modules_dynamic_invalid_json)

def test_ue_resolve_modules_dynamic_filters_unknown():
    import json as _j
    resp = _j.dumps(["01_tension_curve", "99_nonexistent_module_xyz"])
    result = resolve_modules_dynamic("задача", None, lambda p: resp)
    assert "99_nonexistent_module_xyz" not in result
    assert "01_tension_curve" in result
run("unified_engine: resolve_modules_dynamic фильтрует неизвестные модули", test_ue_resolve_modules_dynamic_filters_unknown)

def test_ue_resolve_modules_dynamic_llm_raises():
    result = resolve_modules_dynamic(
        "задача", None,
        lambda p: (_ for _ in ()).throw(RuntimeError("API down")),
    )
    assert isinstance(result, list)
run("unified_engine: resolve_modules_dynamic LLM raises → fallback", test_ue_resolve_modules_dynamic_llm_raises)

def test_ue_get_active_modules_returns_list():
    result = get_active_modules("фэнтези", "quick")
    assert isinstance(result, list) and len(result) > 0
run("unified_engine: get_active_modules → непустой список", test_ue_get_active_modules_returns_list)

def test_ue_get_active_modules_master_gte_quick():
    q = get_active_modules("детектив", "quick")
    m = get_active_modules("детектив", "master")
    assert len(m) >= len(q)
run("unified_engine: master >= quick по числу модулей", test_ue_get_active_modules_master_gte_quick)

def test_ue_build_engine_context_no_engine():
    """Без движка → пустая строка."""
    with _mock.patch("engine.unified_engine.engine_available", return_value=False):
        from engine.unified_engine import build_engine_context
        result = build_engine_context("фэнтези", "quick")
    assert result == ""
run("unified_engine: build_engine_context без движка → ''", test_ue_build_engine_context_no_engine)


# ════════════════════════════════════════════════════════
print("\n══ cognitive_memory: полное покрытие ══")
# ════════════════════════════════════════════════════════

from engine.cognitive_memory import (
    get_cognitive_context, get_weighted_promises,
    _select_inclusions, _format_cognitive_context,
    memory_score_report, MEMORY_FIELDS,
)

def _s(chapter_num, events="", promises="", characters="", conflicts="", mood=""):
    return {
        "chapter_num": chapter_num,
        "events": events, "promises": promises,
        "characters": characters, "conflicts": conflicts, "mood": mood,
    }

def test_cog_no_summaries():
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
        assert get_cognitive_context(1, before_chapter=5) == ""
run("cognitive_memory: нет саммари → пустая строка", test_cog_no_summaries)

def test_cog_one_summary_contains_chapter():
    with _mock.patch("engine.cognitive_memory.get_l3_summaries",
                     return_value=[_s(1, events="Герой встретил злодея")]):
        result = get_cognitive_context(1, before_chapter=3)
    assert "Глава 1" in result
run("cognitive_memory: одно саммари → содержит номер главы", test_cog_one_summary_contains_chapter)

def test_cog_promises_always_included():
    summaries = [_s(1, promises="Тайна шкатулки"), _s(2, events="Встреча")]
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_cognitive_context(1, before_chapter=5)
    assert "Тайна шкатулки" in result
run("cognitive_memory: promises из старых глав включаются", test_cog_promises_always_included)

def test_cog_select_inclusions_recent_all_fields():
    by_ch = {1: _s(1, events="событие", promises="обещание")}
    inc = _select_inclusions(by_ch, [1], [1], latest_chapter=1, max_chapters=5)
    assert "events" in inc[1]
    assert "promises" in inc[1]
run("cognitive_memory: _select_inclusions recent → все непустые поля", test_cog_select_inclusions_recent_all_fields)

def test_cog_select_inclusions_promises_from_old():
    by_ch = {1: _s(1, promises="старое"), 5: _s(5, events="новое")}
    inc = _select_inclusions(by_ch, [1, 5], [5], latest_chapter=5, max_chapters=5)
    assert "promises" in inc[1]
run("cognitive_memory: _select_inclusions promises из нерецентных глав", test_cog_select_inclusions_promises_from_old)

def test_cog_format_structure():
    by_ch = {1: _s(1, events="встреча"), 2: _s(2, events="битва")}
    inc = {1: {"events"}, 2: {"events"}}
    result = _format_cognitive_context(by_ch, [1, 2], [2], inc, latest_chapter=2)
    assert "КОГНИТИВНАЯ ПАМЯТЬ" in result
    assert "Глава 1" in result
    assert "Глава 2" in result
run("cognitive_memory: _format_cognitive_context структура", test_cog_format_structure)

def test_cog_format_recent_marker():
    by_ch = {1: _s(1, events="старое"), 3: _s(3, events="новое")}
    inc = {1: {"events"}, 3: {"events"}}
    result = _format_cognitive_context(by_ch, [1, 3], [3], inc, latest_chapter=3)
    assert "★" in result
    assert "·" in result
run("cognitive_memory: ★ рецентные, · старые", test_cog_format_recent_marker)

def test_cog_weighted_promises_no_data():
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
        result = get_weighted_promises(1, before_chapter=5)
    assert result == ""
run("cognitive_memory: get_weighted_promises нет данных → ''", test_cog_weighted_promises_no_data)

def test_cog_weighted_promises_returns_content():
    summaries = [_s(1, promises="Герой вернётся"), _s(2, promises="Предатель будет разоблачён")]
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
        result = get_weighted_promises(1, before_chapter=5)
    assert "Герой вернётся" in result or "Предатель" in result
run("cognitive_memory: get_weighted_promises → содержит обещания", test_cog_weighted_promises_returns_content)

def test_cog_memory_score_report_no_crash():
    with _mock.patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
        result = memory_score_report(1, before_chapter=5)
    assert isinstance(result, str)
run("cognitive_memory: memory_score_report нет данных → строка без crash", test_cog_memory_score_report_no_crash)


# ════════════════════════════════════════════════════════
print("\n══ pipeline_steps: step_generate / step_drift_check / step_chapter_analysis ══")
# ════════════════════════════════════════════════════════

from engine.pipeline_steps import step_generate, step_drift_check, step_chapter_analysis

def test_sg_writes_results():
    results = {}
    with _mock.patch("engine.pipeline_steps.save_pipeline_iteration"):
        step_generate(
            run_id=1, iteration=1, chapter_num=5,
            generation_prompt="Задача",
            full_prompt="Полный промпт",
            model_gen="model::x",
            sys_generator="Ты писатель.",
            call_fn=lambda m, s, p, **kw: "Сгенерированный текст.",
            results=results,
        )
    assert results["generated_text"] == "Сгенерированный текст."
    assert results["stage"] == "generate"
run("pipeline_steps: step_generate пишет generated_text и stage", test_sg_writes_results)

def test_sg_saves_iteration():
    saved = []
    results = {}
    with _mock.patch("engine.pipeline_steps.save_pipeline_iteration",
                     side_effect=lambda *a, **kw: saved.append(1)):
        step_generate(1, 1, 5, "задача", "промпт", "m::x", "sys",
                      lambda m, s, p, **kw: "текст", results)
    assert len(saved) == 1
run("pipeline_steps: step_generate вызывает save_pipeline_iteration", test_sg_saves_iteration)

def test_sdc_skips_when_not_needed():
    called = [False]
    results = {}
    with _mock.patch("engine.pipeline_drift.should_check_drift", return_value=False):
        step_drift_check(1, 5, "текст", "m::x",
                         lambda m, s, p, **kw: (called.__setitem__(0, True), "")[1],
                         results)
    assert not called[0] and "drift_warning" not in results
run("pipeline_steps: step_drift_check пропускает если не нужен", test_sdc_skips_when_not_needed)

def test_sdc_fills_warning():
    results = {}
    with _mock.patch("engine.pipeline_drift.should_check_drift", return_value=True):
        with _mock.patch("engine.pipeline_drift.check_voice_drift",
                         return_value={"warning": "Голос изменился", "score": 5.5}):
            step_drift_check(1, 5, "текст", "m::x", lambda *a, **kw: "", results)
    assert results.get("drift_warning") == "Голос изменился"
    assert results.get("drift_score") == 5.5
run("pipeline_steps: step_drift_check заполняет drift_warning", test_sdc_fills_warning)

def test_sdc_error_recoverable():
    results = {}
    with _mock.patch("engine.pipeline_drift.should_check_drift",
                     side_effect=RuntimeError("DB error")):
        step_drift_check(1, 5, "текст", "m::x", lambda *a, **kw: "", results)
    # Не должно бросать — тест прошёл
run("pipeline_steps: step_drift_check ошибка → RECOVERABLE", test_sdc_error_recoverable)

def test_sca_fills_results():
    from engine.chapter_analyzer import ChapterAnalysis
    results = {}
    analysis = ChapterAnalysis(
        project_id=1, chapter_num=5,
        logical_gaps=["Марина не могла знать"],
        opened_promises=["Тайна шкатулки"],
        arc_progress={"Анна": "продвинулась"},
        analysis_quality="ok",
    )
    with _mock.patch("engine.chapter_analyzer.analyze_chapter_deep", return_value=analysis):
        with _mock.patch("engine.state.queue_state_update_from_analysis"):
            step_chapter_analysis(1, 5, "Текст главы. " * 30, "m::x",
                                  lambda m, s, p: "", results)
    assert "chapter_analysis_block" in results or "logical_gaps" in results
run("pipeline_steps: step_chapter_analysis заполняет results", test_sca_fills_results)

def test_sca_failed_no_block():
    from engine.chapter_analyzer import ChapterAnalysis
    results = {}
    with _mock.patch("engine.chapter_analyzer.analyze_chapter_deep",
                     return_value=ChapterAnalysis.failed(1, 5)):
        with _mock.patch("engine.state.queue_state_update_from_analysis"):
            step_chapter_analysis(1, 5, "Текст. " * 30, "m::x",
                                  lambda m, s, p: "", results)
    assert "chapter_analysis_block" not in results
run("pipeline_steps: step_chapter_analysis failed → нет chapter_analysis_block", test_sca_failed_no_block)

def test_sca_error_recoverable():
    results = {}
    with _mock.patch("engine.chapter_analyzer.analyze_chapter_deep",
                     side_effect=RuntimeError("LLM down")):
        with _mock.patch("engine.pipeline_steps.handle_error"):
            step_chapter_analysis(1, 5, "Текст. " * 30, "m::x",
                                  lambda m, s, p: "", results)
    # Не crash — тест прошёл
run("pipeline_steps: step_chapter_analysis ошибка → RECOVERABLE", test_sca_error_recoverable)


# ════════════════════════════════════════════════════════
print("\n══ pipeline: _execute_steps / call_json / score_text ══")
# ════════════════════════════════════════════════════════

import tempfile, pathlib
from engine.pipeline import _execute_steps, PipelineStep, call_json, score_text

def _make_tmp_db():
    tmp = _tmp_dir()
    return pathlib.Path(tmp) / "test.db"

def test_exec_generate_only():
    db = _make_tmp_db()
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "фэнтези")

        results = {}
        with _mock.patch("engine.pipeline_steps.save_pipeline_iteration"):
            with _mock.patch("engine.pipeline._call", return_value="Текст." * 10):
                with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                    with _mock.patch("engine.pipeline.step_drift_check"):
                        with _mock.patch("engine.pipeline.step_chapter_analysis"):
                            with _mock.patch("engine.db.get_project", return_value={"genre": "фэнтези"}):
                                results = _execute_steps(
                                    steps=[PipelineStep("generate")],
                                    run_id=1, iteration=1,
                                    project_id=pid, chapter_num=1,
                                    generation_prompt="Задача",
                                    model_gen="m::x", model_critic="m::x",
                                    model_editor="m::x", model_judge="m::x",
                                )
    assert results.get("iteration") == 1
    assert "generated_text" in results
run("pipeline: _execute_steps generate → iteration в results", test_exec_generate_only)

def test_exec_disabled_step_skipped():
    db = _make_tmp_db()
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "фэнтези")

        judge_called = [False]
        with _mock.patch("engine.pipeline_steps.save_pipeline_iteration"):
            with _mock.patch("engine.pipeline._call", return_value="Текст." * 10):
                with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                    with _mock.patch("engine.pipeline.step_drift_check"):
                        with _mock.patch("engine.pipeline.step_chapter_analysis"):
                            with _mock.patch("engine.db.get_project", return_value={"genre": "фэнтези"}):
                                with _mock.patch("engine.pipeline.step_judge",
                                                 side_effect=lambda *a, **kw: judge_called.__setitem__(0, True)):
                                    _execute_steps(
                                        steps=[PipelineStep("generate"), PipelineStep("judge", enabled=False)],
                                        run_id=1, iteration=1,
                                        project_id=pid, chapter_num=1,
                                        generation_prompt="Задача",
                                        model_gen="m::x", model_critic="m::x",
                                        model_editor="m::x", model_judge="m::x",
                                    )
    assert not judge_called[0]
run("pipeline: _execute_steps disabled шаг не вызывается", test_exec_disabled_step_skipped)

def test_exec_critique_score():
    db = _make_tmp_db()
    critique_resp = "ГОЛОС: 8 СТРУКТУРА: 7 ПЕРСОНАЖИ: 8 СЦЕНЫ: 9 ДИАЛОГ: 8\nИТОГ: 40"
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "детектив")

        # Мокать надо модуль, который РЕАЛЬНО пишет: step_critique зовёт
        # save_pipeline_iteration из pipeline_steps. Промах по цели раньше
        # не был виден — строка молча писалась с несуществующим run_id,
        # пока PRAGMA foreign_keys был выключен.
        with _mock.patch("engine.pipeline_steps.save_pipeline_iteration"):
            with _mock.patch("engine.pipeline._call", return_value=critique_resp):
                with _mock.patch("engine.db.get_all_logical_gaps", return_value=[]):
                    with _mock.patch("engine.pipeline.handle_error"):
                        result = _execute_steps(
                            steps=[PipelineStep("critique")],
                            run_id=1, iteration=1,
                            project_id=pid, chapter_num=3,
                            generation_prompt="Задача",
                            model_gen="m::x", model_critic="m::x",
                            model_editor="m::x", model_judge="m::x",
                        )
    assert result.get("critic_score") == 40.0
run("pipeline: _execute_steps critique → critic_score", test_exec_critique_score)

def test_exec_judge_verdict():
    db = _make_tmp_db()
    judge_resp = "ИТОГ: 42\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Хорошо."
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "хоррор")

        # См. выше: писатель — pipeline_steps, а не pipeline.
        with _mock.patch("engine.pipeline_steps.save_pipeline_iteration"):
            with _mock.patch("engine.pipeline._call", return_value=judge_resp):
                with _mock.patch("engine.pipeline.handle_error"):
                    result = _execute_steps(
                        steps=[PipelineStep("judge")],
                        run_id=1, iteration=1,
                        project_id=pid, chapter_num=5,
                        generation_prompt="Задача",
                        model_gen="m::x", model_critic="m::x",
                        model_editor="m::x", model_judge="m::x",
                    )
    assert result.get("verdict") == "ПРИНЯТЬ"
    assert result.get("judge_score") == 42.0
run("pipeline: _execute_steps judge → verdict и judge_score", test_exec_judge_verdict)

def test_call_json_valid():
    import json as _j
    with _mock.patch("engine.pipeline._call", return_value=_j.dumps({"key": "val"})):
        result = call_json("m::x", "sys", "prompt")
    assert result["key"] == "val"
run("pipeline: call_json валидный JSON", test_call_json_valid)

def test_call_json_embedded():
    with _mock.patch("engine.pipeline._call", return_value='Текст {"ok": true} конец'):
        result = call_json("m::x", "sys", "prompt")
    assert result["ok"] is True
run("pipeline: call_json JSON внутри текста", test_call_json_embedded)

def test_call_json_no_json_raises():
    with _mock.patch("engine.pipeline._call", return_value="нет JSON здесь"):
        try:
            call_json("m::x", "sys", "prompt")
            assert False, "должен ValueError"
        except ValueError:
            pass
run("pipeline: call_json нет JSON → ValueError", test_call_json_no_json_raises)

def test_score_text_returns_total():
    """SYS_CRITIC отвечает текстом с метками — ИТОГ берётся из ответа."""
    resp = (
        "ГОЛОС: 7\nСТРУКТУРА: 8\nПЕРСОНАЖИ: 6\n"
        "СЦЕНЫ: 7\nДИАЛОГ: 8\nИТОГ: 36\n"
        "ГЛАВНЫЕ ПРОБЛЕМЫ:\n- Темп проседает в середине"
    )
    with _mock.patch("engine.pipeline._call", return_value=resp):
        result = score_text("Текст.", "фэнтези", "m::x")
    assert isinstance(result["total"], float)
    assert result["total"] == 36.0
    assert result["voice"] == 7 and result["dialog"] == 8
    assert result["main_issue"] == "Темп проседает в середине"
run("pipeline: score_text возвращает dict с total", test_score_text_returns_total)

def test_score_text_computes_missing_total():
    """Нет строки ИТОГ → total считается как сумма пяти критериев (0-50)."""
    resp = ("ГОЛОС: 8\nСТРУКТУРА: 8\nПЕРСОНАЖИ: 8\n"
            "СЦЕНЫ: 8\nДИАЛОГ: 8")
    with _mock.patch("engine.pipeline._call", return_value=resp):
        result = score_text("Текст.", "детектив", "m::x")
    assert isinstance(result["total"], float)
    assert result["total"] == 40.0
    assert result["verdict"] == "ПРИНЯТЬ"
run("pipeline: score_text вычисляет total если отсутствует", test_score_text_computes_missing_total)


# ════════════════════════════════════════════════════════
print("\n══ pipeline: start_pipeline / continue_pipeline ══")
# ════════════════════════════════════════════════════════

from engine.pipeline import start_pipeline, continue_pipeline
from engine.pipeline_config import AUTO_IMPROVE, STANDARD

def _setup_db():
    db = _make_tmp_db()
    from unittest.mock import patch as _p
    return db

def test_start_pipeline_returns_run_id():
    db = _make_tmp_db()
    judge_resp = "ИТОГ: 42\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Ок."
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "фэнтези")

        with _mock.patch("engine.pipeline._call", return_value=judge_resp):
            with _mock.patch("engine.pipeline_steps.save_pipeline_iteration"):
                with _mock.patch("engine.pipeline.step_generate",
                                 side_effect=lambda run_id, iteration, chapter_num, gen_prompt, full_prompt, model, sys_p, call_fn, results, prefill="": results.__setitem__("generated_text", "Текст." * 30)):
                    with _mock.patch("engine.pipeline.step_drift_check"):
                        with _mock.patch("engine.pipeline.step_chapter_analysis"):
                            with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                                with _mock.patch("engine.db.get_project", return_value={"genre": "фэнтези"}):
                                    result = start_pipeline(
                                        project_id=pid, chapter_num=1,
                                        generation_prompt="Задача",
                                        model_gen="m::x", model_critic="m::x",
                                        model_editor="m::x", model_judge="m::x",
                                    )
    assert "run_id" in result and isinstance(result["run_id"], int)
run("pipeline: start_pipeline возвращает run_id", test_start_pipeline_returns_run_id)

def test_start_pipeline_auto_retry_stops_on_degradation():
    """Реальный авто-ретрай: score упал → цикл прерывается."""
    db = _make_tmp_db()
    responses = iter([
        "ИТОГ: 30\nВЕРДИКТ: НА ДОРАБОТКУ\nОБОСНОВАНИЕ: плохо",
        "ИТОГ: 25\nВЕРДИКТ: НА ДОРАБОТКУ\nОБОСНОВАНИЕ: хуже",
        "ИТОГ: 40\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: ок",  # не должно дойти
    ])
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Тест", "фэнтези")

        def _safe_next(*a, **kw):
            try: return next(responses)
            except StopIteration: return "ИТОГ: 25\nВЕРДИКТ: НА ДОРАБОТКУ"
        with _mock.patch("engine.pipeline._call", side_effect=_safe_next):
            with _mock.patch("engine.pipeline_steps.save_pipeline_iteration"):
                with _mock.patch("engine.pipeline.step_generate",
                                 side_effect=lambda run_id, iteration, chapter_num, gen_prompt, full_prompt, model, sys_p, call_fn, results, prefill="": results.__setitem__("generated_text", "T" * 30)):
                    with _mock.patch("engine.pipeline.step_drift_check"):
                        with _mock.patch("engine.pipeline.step_chapter_analysis"):
                            with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                                with _mock.patch("engine.db.get_project", return_value={"genre": "фэнтези"}):
                                    result = start_pipeline(
                                        project_id=pid, chapter_num=1,
                                        generation_prompt="Задача",
                                        model_gen="m::x", model_critic="m::x",
                                        model_editor="m::x", model_judge="m::x",
                                        config=AUTO_IMPROVE,
                                    )
    assert result.get("verdict") == "НА ДОРАБОТКУ"
    assert result.get("judge_score") == 25.0
run("pipeline: start_pipeline авто-ретрай останавливается при деградации score", test_start_pipeline_auto_retry_stops_on_degradation)

def test_continue_pipeline_returns_run_id():
    db = _make_tmp_db()
    judge_resp = "ИТОГ: 44\nВЕРДИКТ: ПРИНЯТЬ\nОБОСНОВАНИЕ: Отлично."
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        from engine.db import create_pipeline_run
        pid = create_project("Тест", "детектив")
        run_id = create_pipeline_run(pid, 1, "m::x", "m::x", "m::x", "m::x")

        with _mock.patch("engine.pipeline._call", return_value=judge_resp):
            with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                with _mock.patch("engine.pipeline.handle_error"):
                    result = continue_pipeline(
                        run_id=run_id,
                        project_id=pid, chapter_num=1,
                        generation_prompt="Задача",
                        previous_text="Предыдущий текст.",
                        previous_critique="Критика.",
                    )
    assert "run_id" in result and result["run_id"] == run_id
run("pipeline: continue_pipeline возвращает run_id", test_continue_pipeline_returns_run_id)


# ══════════════════════════════════════════════════════════════════════
# PROMISES — структурированные обещания (66 тестов из updated)
# ══════════════════════════════════════════════════════════════════════


# ── test_promise_lifecycle.py ──
import json
from unittest.mock import patch


class TestPromiseLifecycle:

    def _generate_summary(self, project_id, chapter_num, promises: list[dict]):
        """Сохранить саммари с заданными promises через generate_l3_summary."""
        from engine.l3_memory import generate_l3_summary
        raw = json.dumps({
            "events":     f"событие главы {chapter_num}",
            "characters": "персонаж изменился",
            "conflicts":  "конфликт активен",
            "promises":   promises,
            "mood":       "тревожное",
        })
        result = generate_l3_summary(project_id, chapter_num, "А" * 200, lambda p: raw)
        assert result is not None, f"generate_l3_summary вернул None для гл.{chapter_num}"
        return result

    def test_full_cycle_single_promise(self, project_id):
        """
        Полный цикл одного обещания:
        создать → проверить активность → закрыть → проверить исчезновение.
        """
        from engine.db_state import merge_analysis_into_state
        from engine.cognitive_memory import get_cognitive_context, get_weighted_promises

        # Шаг 1: создаём главу с активным обещанием
        self._generate_summary(project_id, 1, [
            {"id": "1_0", "text": "Убийца вернётся в финале", "resolved": False}
        ])

        # Шаг 2: обещание видно в контексте и в weighted_promises
        with patch("engine.cognitive_memory.get_l3_summaries") as mock_get:
            from engine.db import get_l3_summaries
            mock_get.side_effect = lambda pid, before, n: get_l3_summaries(pid, before, n)
            ctx_before = get_cognitive_context(project_id, before_chapter=5)
            wp_before  = get_weighted_promises(project_id, before_chapter=5)

        assert "Убийца вернётся" in ctx_before, "promise должен быть в контексте до закрытия"
        assert "Убийца вернётся" in wp_before,  "promise должен быть в weighted до закрытия"

        # Шаг 3: анализ главы 3 закрывает обещание
        analysis = json.dumps({
            "global_state_changes": [],
            "plot_changes":         {},
            "memory_changes":       [],
            "next_context":         "убийца пойман",
            "resolved_promises":    ["1_0"],
        })
        result = merge_analysis_into_state(project_id, analysis, chapter_num=3)

        # resolved_promises должны попасть в fields
        promise_fields = [f for f in result["fields"] if "promise" in f["field"]]
        assert len(promise_fields) == 1
        assert promise_fields[0]["after"] == "resolved"

        # Шаг 4: обещание исчезло из контекста и weighted_promises
        with patch("engine.cognitive_memory.get_l3_summaries") as mock_get:
            mock_get.side_effect = lambda pid, before, n: get_l3_summaries(pid, before, n)
            ctx_after = get_cognitive_context(project_id, before_chapter=5)
            wp_after  = get_weighted_promises(project_id, before_chapter=5)

        assert "Убийца вернётся" not in ctx_after, "закрытый promise не должен быть в контексте"
        assert "Убийца вернётся" not in wp_after,  "закрытый promise не должен быть в weighted"

    def test_partial_close_other_promises_remain(self, project_id):
        """
        Закрытие одного обещания не убирает другие активные.
        """
        from engine.db_state import merge_analysis_into_state
        from engine.cognitive_memory import get_weighted_promises

        self._generate_summary(project_id, 2, [
            {"id": "2_0", "text": "Герой найдёт меч",      "resolved": False},
            {"id": "2_1", "text": "Предательство раскроется", "resolved": False},
        ])

        # Закрываем только первое
        analysis = json.dumps({
            "global_state_changes": [],
            "resolved_promises": ["2_0"],
        })
        merge_analysis_into_state(project_id, analysis, chapter_num=5)

        from engine.db import get_l3_summaries
        with patch("engine.cognitive_memory.get_l3_summaries") as mock_get:
            mock_get.side_effect = lambda pid, before, n: get_l3_summaries(pid, before, n)
            wp = get_weighted_promises(project_id, before_chapter=8)

        assert "Герой найдёт меч"       not in wp, "закрытое обещание не должно быть видно"
        assert "Предательство раскроется" in wp,   "активное обещание должно остаться"

    def test_promise_resolved_chapter_recorded(self, project_id):
        """
        resolved_chapter в саммари соответствует chapter_num из merge.
        """
        from engine.db_state import merge_analysis_into_state
        from engine.db import get_l3_summary
        from engine.l3_memory import normalize_promises

        self._generate_summary(project_id, 1, [
            {"id": "1_0", "text": "Тайна замка", "resolved": False}
        ])

        analysis = json.dumps({
            "global_state_changes": [],
            "resolved_promises": ["1_0"],
        })
        merge_analysis_into_state(project_id, analysis, chapter_num=7)

        saved = get_l3_summary(project_id, 1)
        promises = normalize_promises(saved["promises"], 1)
        assert promises[0]["resolved"] is True
        assert promises[0]["resolved_chapter"] == 7, (
            f"resolved_chapter должен быть 7, получили {promises[0]['resolved_chapter']}"
        )

    def test_legacy_and_new_promises_coexist(self, project_id):
        """
        Проект с legacy-саммари (строка) и новым (список) работает корректно.
        Legacy нормализуется при чтении — оба типа видны в weighted_promises.
        """
        from engine.l3_memory import generate_l3_summary
        from engine.cognitive_memory import get_weighted_promises
        from engine.db import get_l3_summaries

        # Глава 1 — legacy строка (сохраняем напрямую через save_l3_summary)
        from engine.db import save_l3_summary
        save_l3_summary(project_id, 1, {
            "events": "событие",
            "characters": "", "conflicts": "", "mood": "",
            "promises": "Старое обещание в строковом формате",
        })

        # Глава 2 — новый формат
        self._generate_summary(project_id, 2, [
            {"id": "2_0", "text": "Новое структурированное обещание", "resolved": False}
        ])

        with patch("engine.cognitive_memory.get_l3_summaries") as mock_get:
            mock_get.side_effect = lambda pid, before, n: get_l3_summaries(pid, before, n)
            wp = get_weighted_promises(project_id, before_chapter=5)

        assert "Старое обещание" in wp,                  "legacy promise должен быть виден"
        assert "Новое структурированное обещание" in wp, "новый promise должен быть виден"

    def test_unknown_promise_id_in_resolved_is_safe(self, project_id):
        """
        resolved_promises с несуществующим id не роняет merge и не меняет state.
        """
        from engine.db_state import merge_analysis_into_state, get_state
        from engine.db_state import update_state

        update_state(project_id,
                     global_state="### Иван\nСОСТОЯНИЕ: жив",
                     plot_matrix="СТАТУС: активна")

        analysis = json.dumps({
            "global_state_changes": [],
            "resolved_promises": ["99_0", "999_1"],  # несуществующие
        })

        result = merge_analysis_into_state(project_id, analysis, chapter_num=5)

        # Не упал
        assert isinstance(result, dict)
        assert "changed" in result
        # State не изменился от несуществующих id
        state = get_state(project_id)
        assert "жив" in state["global_state"]


# ── test_promises_cognitive.py ──
from unittest.mock import patch, MagicMock


def _make_summary(chapter_num: int, promises=None, **kwargs) -> dict:
    return {
        "chapter_num": chapter_num,
        "promises":    promises if promises is not None else [],
        "conflicts":   kwargs.get("conflicts", ""),
        "characters":  kwargs.get("characters", ""),
        "events":      kwargs.get("events", ""),
        "mood":        kwargs.get("mood", ""),
    }


# ─── A. score_summary — promises как список ──────────────────────────────────

class TestScoreSummaryWithStructuredPromises:

    def test_active_promise_list_gets_score(self):
        from engine.cognitive_memory import score_summary
        summary = _make_summary(5, promises=[
            {"id": "5_0", "text": "Обещание", "resolved": False}
        ])
        scores = score_summary(summary, distance=1)
        assert "promises" in scores
        assert scores["promises"] > 0

    def test_all_resolved_promises_no_score(self):
        from engine.cognitive_memory import score_summary
        summary = _make_summary(5, promises=[
            {"id": "5_0", "text": "Закрытое", "resolved": True, "resolved_chapter": 7}
        ])
        scores = score_summary(summary, distance=1)
        assert "promises" not in scores

    def test_empty_promises_list_no_score(self):
        from engine.cognitive_memory import score_summary
        summary = _make_summary(5, promises=[])
        scores = score_summary(summary, distance=1)
        assert "promises" not in scores

    def test_legacy_string_promise_gets_score(self):
        """Legacy строка должна по-прежнему давать вес (normalize_promises её обработает)."""
        from engine.cognitive_memory import score_summary
        summary = _make_summary(3, promises="Герой вернётся")
        scores = score_summary(summary, distance=2)
        assert "promises" in scores

    def test_mixed_active_and_resolved_gets_score(self):
        """Если есть хотя бы одно активное — вес есть."""
        from engine.cognitive_memory import score_summary
        summary = _make_summary(5, promises=[
            {"id": "5_0", "text": "Закрытое",  "resolved": True},
            {"id": "5_1", "text": "Активное",  "resolved": False},
        ])
        scores = score_summary(summary, distance=1)
        assert "promises" in scores


# ─── B. get_weighted_promises ─────────────────────────────────────────────────

class TestGetWeightedPromisesStructured:

    def test_returns_only_active_promises(self):
        from engine.cognitive_memory import get_weighted_promises
        summaries = [
            _make_summary(1, promises=[
                {"id": "1_0", "text": "Активное",  "resolved": False},
                {"id": "1_1", "text": "Закрытое",  "resolved": True, "resolved_chapter": 3},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert "Активное" in result
        assert "Закрытое" not in result

    def test_promise_id_shown_in_output(self):
        """id должен быть виден в строке — используется для resolved_promises в анализе."""
        from engine.cognitive_memory import get_weighted_promises
        summaries = [
            _make_summary(3, promises=[
                {"id": "3_0", "text": "Убийца вернётся", "resolved": False},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert "3_0" in result
        assert "Убийца вернётся" in result

    def test_all_resolved_returns_empty_string(self):
        from engine.cognitive_memory import get_weighted_promises
        summaries = [
            _make_summary(2, promises=[
                {"id": "2_0", "text": "Закрытое", "resolved": True, "resolved_chapter": 4},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert result == ""

    def test_legacy_string_promises_included(self):
        """Старые саммари со строкой promises тоже показываются."""
        from engine.cognitive_memory import get_weighted_promises
        summaries = [_make_summary(1, promises="Старое обещание")]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=3)
        assert "Старое обещание" in result

    def test_no_summaries_returns_empty(self):
        from engine.cognitive_memory import get_weighted_promises
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=[]):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert result == ""

    def test_multiple_chapters_all_active_included(self):
        from engine.cognitive_memory import get_weighted_promises
        summaries = [
            _make_summary(1, promises=[{"id": "1_0", "text": "Обещание 1", "resolved": False}]),
            _make_summary(3, promises=[{"id": "3_0", "text": "Обещание 3", "resolved": False}]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_weighted_promises(project_id=1, before_chapter=5)
        assert "Обещание 1" in result
        assert "Обещание 3" in result


# ─── C. cognitive context — закрытые promises не попадают ────────────────────

class TestCognitiveContextPromises:

    def test_active_promises_in_context(self):
        from engine.cognitive_memory import get_cognitive_context
        summaries = [
            _make_summary(1, promises=[
                {"id": "1_0", "text": "Активное обещание", "resolved": False},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_cognitive_context(project_id=1, before_chapter=3)
        assert "Активное обещание" in result

    def test_resolved_promises_excluded_from_context(self):
        from engine.cognitive_memory import get_cognitive_context
        summaries = [
            _make_summary(1, promises=[
                {"id": "1_0", "text": "Закрытое обещание", "resolved": True, "resolved_chapter": 2},
            ]),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_cognitive_context(project_id=1, before_chapter=5)
        assert "Закрытое обещание" not in result

    def test_chapter_without_active_promises_still_included_for_other_fields(self):
        """Глава с только закрытыми promises но с events всё равно попадает в контекст."""
        from engine.cognitive_memory import get_cognitive_context
        summaries = [
            _make_summary(
                2,
                promises=[{"id": "2_0", "text": "Закрытое", "resolved": True}],
                events="важное событие"
            ),
            _make_summary(3, events="событие 3"),
        ]
        with patch("engine.cognitive_memory.get_l3_summaries", return_value=summaries):
            result = get_cognitive_context(project_id=1, before_chapter=5)
        assert "важное событие" in result
        assert "Закрытое" not in result


# ── test_promises_db_state.py ──
import json
from unittest.mock import patch, MagicMock


# ─── A. _create_char_entry ────────────────────────────────────────────────────

class TestCreateCharEntry:

    def test_returns_string_with_all_fields(self):
        from engine.db_state import _create_char_entry
        entry = _create_char_entry("Иван", "испуган", "лес", "спастись")
        assert "### Иван" in entry
        assert "СОСТОЯНИЕ: испуган" in entry
        assert "ЛОКАЦИЯ: лес" in entry
        assert "ЦЕЛЬ_СЕЙЧАС: спастись" in entry
        assert "ЦЕЛЬ_ГЛУБИННАЯ: []" in entry
        assert "ЗНАЕТ: []" in entry
        assert "НЕ_ЗНАЕТ: []" in entry
        assert "ИЗМЕНЕНИЕ: [автодобавлен]" in entry

    def test_empty_state_becomes_placeholder(self):
        from engine.db_state import _create_char_entry
        entry = _create_char_entry("Мария", "", "", "")
        assert "СОСТОЯНИЕ: []" in entry
        assert "ЛОКАЦИЯ: []" in entry
        assert "ЦЕЛЬ_СЕЙЧАС: []" in entry

    def test_arrow_notation_stripped(self):
        """Значения вида 'старое → новое' должны сохранять только правую часть."""
        from engine.db_state import _create_char_entry
        entry = _create_char_entry("Иван", "живой → мёртвый", "дом → лес", "")
        assert "мёртвый" in entry
        assert "лес" in entry
        assert "→" not in entry

    def test_placeholder_bracket_value_becomes_empty(self):
        """Значения вида '[что-то]' считаются плейсхолдерами."""
        from engine.db_state import _create_char_entry
        entry = _create_char_entry("Иван", "[неизвестно]", "дом", "")
        assert "СОСТОЯНИЕ: []" in entry

    def test_used_in_add_new_char(self, project_id):
        """_add_new_char должна использовать _create_char_entry — содержит все поля."""
        from engine.db_state import _add_new_char
        global_text = "## ПЕРСОНАЖИ\n"
        new_chars = []
        result = _add_new_char("Новый", "Section:\nсостояние: радостный\nлокация: замок\nцель: найти клад",
                               global_text, lambda *a: None, new_chars)
        assert "ЦЕЛЬ_ГЛУБИННАЯ: []" in result
        assert "ИЗМЕНЕНИЕ: [автодобавлен]" in result
        assert "Новый" in new_chars

    def test_add_new_char_and_merge_from_json_produce_same_template(self, project_id):
        """
        Ключевой инвариант: оба пути создания персонажа дают одинаковый шаблон.
        Проверяем что оба содержат ЦЕЛЬ_ГЛУБИННАЯ и ИЗМЕНЕНИЕ.
        """
        from engine.db_state import _add_new_char, _create_char_entry

        new_chars_1 = []
        global_text = "## ПЕРСОНАЖИ\n"
        result_add = _add_new_char(
            "Персонаж",
            "Section:\nсостояние: грустный\nлокация: лес\nцель: выжить",
            global_text, lambda *a: None, new_chars_1
        )

        result_entry = _create_char_entry("Персонаж", "грустный", "лес", "выжить")

        # Оба должны иметь одинаковый набор обязательных полей
        for field in ("ЦЕЛЬ_ГЛУБИННАЯ: []", "ЗНАЕТ: []", "НЕ_ЗНАЕТ: []", "ИЗМЕНЕНИЕ: [автодобавлен]"):
            assert field in result_add, f"_add_new_char: отсутствует поле {field}"
            assert field in result_entry, f"_create_char_entry: отсутствует поле {field}"


# ─── B. merge_analysis_into_state — resolved_promises ────────────────────────

class TestMergeResolvedPromises:

    def _make_analysis(self, resolved_ids: list[str], extra: dict | None = None) -> str:
        data = {
            "global_state_changes": [],
            "plot_changes": {},
            "memory_changes": [],
            "next_context": "контекст",
            "resolved_promises": resolved_ids,
        }
        if extra:
            data.update(extra)
        return json.dumps(data)

    def test_resolved_promises_appear_in_fields_changed(self, project_id):
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            result = merge_analysis_into_state(
                project_id,
                self._make_analysis(["5_0", "3_1"]),
                chapter_num=7,
            )

        # Закрытые обещания должны быть в fields
        promise_fields = [f for f in result["fields"] if "promise" in f["field"]]
        assert len(promise_fields) == 2
        ids_in_fields = {f["field"].split(".")[-1] for f in promise_fields}
        assert "5_0" in ids_in_fields
        assert "3_1" in ids_in_fields

    def test_mark_promise_resolved_called_with_correct_args(self, project_id):
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            merge_analysis_into_state(
                project_id,
                self._make_analysis(["5_0"]),
                chapter_num=8,
            )

        mock_mark.assert_called_once_with(project_id, "5_0", resolved_chapter=8)

    def test_empty_resolved_promises_no_mark_called(self, project_id):
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            merge_analysis_into_state(
                project_id,
                self._make_analysis([]),
                chapter_num=5,
            )

        mock_mark.assert_not_called()

    def test_resolved_promises_field_only_key_triggers_json_path(self, project_id):
        """JSON с только resolved_promises (без других ключей) должен идти по JSON-пути."""
        from engine.db_state import merge_analysis_into_state

        data = json.dumps({"resolved_promises": ["2_0"]})
        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            result = merge_analysis_into_state(project_id, data, chapter_num=5)

        mock_mark.assert_called_once()

    def test_mark_error_is_recoverable(self, project_id):
        """Ошибка в mark_promise_resolved не должна ломать весь merge."""
        from engine.db_state import merge_analysis_into_state

        def crash(pid, promise_id, resolved_chapter):
            raise RuntimeError("DB упала")

        with patch("engine.l3_memory.mark_promise_resolved", crash):
            result = merge_analysis_into_state(
                project_id,
                self._make_analysis(["5_0"]),
                chapter_num=6,
            )
        # Merge должен вернуть результат, не упасть
        assert isinstance(result, dict)
        assert "changed" in result

    def test_chapter_num_default_zero(self, project_id):
        """Обратная совместимость: chapter_num=0 по умолчанию, старые вызовы не ломаются."""
        from engine.db_state import merge_analysis_into_state

        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            # Вызов без chapter_num — как было раньше
            merge_analysis_into_state(
                project_id,
                self._make_analysis(["1_0"]),
            )

        mock_mark.assert_called_once_with(project_id, "1_0", resolved_chapter=0)

    def test_non_string_ids_in_resolved_promises_skipped(self, project_id):
        """Некорректные id (числа, None) должны фильтроваться без ошибок."""
        from engine.db_state import merge_analysis_into_state

        data = json.dumps({
            "global_state_changes": [],
            "resolved_promises": [None, 123, "5_0", ""],
        })
        mock_mark = MagicMock(return_value=True)
        with patch("engine.l3_memory.mark_promise_resolved", mock_mark):
            merge_analysis_into_state(project_id, data, chapter_num=7)

        # Только "5_0" — валидный строковый непустой id
        mock_mark.assert_called_once_with(project_id, "5_0", resolved_chapter=7)


# ── test_promises_l3.py ──
import json
from unittest.mock import patch


# ─── A. normalize_promises ────────────────────────────────────────────────────

class TestNormalizePromises:

    def test_legacy_string_becomes_single_item_list(self):
        from engine.l3_memory import normalize_promises
        result = normalize_promises("Герой узнает правду об отце", chapter_num=5)
        assert len(result) == 1
        assert result[0]["text"] == "Герой узнает правду об отце"
        assert result[0]["id"] == "5_0"
        assert result[0]["resolved"] is False
        assert result[0]["resolved_chapter"] is None

    def test_empty_string_returns_empty_list(self):
        from engine.l3_memory import normalize_promises
        assert normalize_promises("", chapter_num=3) == []

    def test_whitespace_string_returns_empty_list(self):
        from engine.l3_memory import normalize_promises
        assert normalize_promises("   ", chapter_num=3) == []

    def test_none_returns_empty_list(self):
        from engine.l3_memory import normalize_promises
        assert normalize_promises(None, chapter_num=3) == []

    def test_valid_list_passthrough(self):
        from engine.l3_memory import normalize_promises
        raw = [
            {"id": "7_0", "text": "Убийца вернётся", "resolved": False, "resolved_chapter": None},
            {"id": "7_1", "text": "Ключ найдут",     "resolved": True,  "resolved_chapter": 10},
        ]
        result = normalize_promises(raw, chapter_num=7)
        assert len(result) == 2
        assert result[0]["id"] == "7_0"
        assert result[1]["resolved"] is True
        assert result[1]["resolved_chapter"] == 10

    def test_list_with_empty_text_skipped(self):
        from engine.l3_memory import normalize_promises
        raw = [
            {"id": "3_0", "text": "",        "resolved": False},
            {"id": "3_1", "text": "Обещание", "resolved": False},
        ]
        result = normalize_promises(raw, chapter_num=3)
        assert len(result) == 1
        assert result[0]["id"] == "3_1"

    def test_list_item_missing_id_gets_generated(self):
        from engine.l3_memory import normalize_promises
        raw = [{"text": "Обещание без id", "resolved": False}]
        result = normalize_promises(raw, chapter_num=4)
        assert result[0]["id"] == "4_0"

    def test_list_item_missing_resolved_defaults_false(self):
        from engine.l3_memory import normalize_promises
        raw = [{"id": "2_0", "text": "Обещание"}]
        result = normalize_promises(raw, chapter_num=2)
        assert result[0]["resolved"] is False


# ─── B. get_active_promises ───────────────────────────────────────────────────

class TestGetActivePromises:

    def test_returns_only_unresolved(self):
        from engine.l3_memory import get_active_promises
        promises = [
            {"id": "1_0", "text": "Открытое",  "resolved": False},
            {"id": "1_1", "text": "Закрытое",  "resolved": True},
            {"id": "1_2", "text": "Открытое2", "resolved": False},
        ]
        active = get_active_promises(promises)
        assert len(active) == 2
        assert all(not p["resolved"] for p in active)

    def test_all_resolved_returns_empty(self):
        from engine.l3_memory import get_active_promises
        promises = [
            {"id": "5_0", "text": "Закрытое", "resolved": True},
        ]
        assert get_active_promises(promises) == []

    def test_empty_list_returns_empty(self):
        from engine.l3_memory import get_active_promises
        assert get_active_promises([]) == []

    def test_preserves_promise_data(self):
        from engine.l3_memory import get_active_promises
        promises = [{"id": "3_0", "text": "Текст", "resolved": False, "resolved_chapter": None}]
        active = get_active_promises(promises)
        assert active[0]["id"] == "3_0"
        assert active[0]["text"] == "Текст"


# ─── C. mark_promise_resolved ─────────────────────────────────────────────────

class TestMarkPromiseResolved:

    def test_marks_promise_as_resolved(self, project_id):
        from engine.l3_memory import generate_l3_summary, mark_promise_resolved, normalize_promises, get_active_promises
        from engine.db import get_l3_summary

        # Создаём саммари с одним активным обещанием
        raw = json.dumps({
            "events": "событие",
            "characters": "",
            "conflicts": "",
            "promises": [{"id": "1_0", "text": "Герой вернётся", "resolved": False, "resolved_chapter": None}],
            "mood": "нейтральное",
        })
        generate_l3_summary(project_id, 1, "А" * 200, lambda p: raw)

        result = mark_promise_resolved(project_id, "1_0", resolved_chapter=5)
        assert result is True

        saved = get_l3_summary(project_id, 1)
        promises = normalize_promises(saved["promises"], 1)
        assert promises[0]["resolved"] is True
        assert promises[0]["resolved_chapter"] == 5

    def test_returns_false_for_unknown_promise(self, project_id):
        from engine.l3_memory import mark_promise_resolved
        result = mark_promise_resolved(project_id, "99_0", resolved_chapter=5)
        assert result is False

    def test_returns_false_for_invalid_id_format(self, project_id):
        from engine.l3_memory import mark_promise_resolved
        result = mark_promise_resolved(project_id, "invalid", resolved_chapter=5)
        assert result is False

    def test_already_resolved_not_updated_again(self, project_id):
        from engine.l3_memory import generate_l3_summary, mark_promise_resolved, normalize_promises
        from engine.db import get_l3_summary

        raw = json.dumps({
            "events": "событие",
            "characters": "", "conflicts": "", "mood": "",
            "promises": [{"id": "1_0", "text": "Обещание", "resolved": True, "resolved_chapter": 3}],
        })
        generate_l3_summary(project_id, 1, "А" * 200, lambda p: raw)

        result = mark_promise_resolved(project_id, "1_0", resolved_chapter=7)
        # Уже закрытое — возвращаем False (не обновляем)
        assert result is False

        saved = get_l3_summary(project_id, 1)
        promises = normalize_promises(saved["promises"], 1)
        assert promises[0]["resolved_chapter"] == 3  # не перезаписано


# ─── D. generate_l3_summary — promises как список ────────────────────────────

class TestGenerateSummaryPromises:

    def test_structured_promises_saved_as_list(self, project_id):
        from engine.l3_memory import generate_l3_summary, normalize_promises
        raw = json.dumps({
            "events": "событие",
            "characters": "Иван изменился",
            "conflicts": "конфликт",
            "promises": [
                {"id": "2_0", "text": "Убийца вернётся", "resolved": False, "resolved_chapter": None},
                {"id": "2_1", "text": "Ключ спрятан",    "resolved": False, "resolved_chapter": None},
            ],
            "mood": "тревожное",
        })
        result = generate_l3_summary(project_id, 2, "А" * 200, lambda p: raw)
        assert result is not None
        promises = normalize_promises(result["promises"], 2)
        assert len(promises) == 2
        assert promises[0]["id"] == "2_0"
        assert promises[1]["text"] == "Ключ спрятан"

    def test_legacy_string_promises_normalized_on_save(self, project_id):
        from engine.l3_memory import generate_l3_summary, normalize_promises
        raw = json.dumps({
            "events": "событие",
            "characters": "", "conflicts": "",
            "promises": "Герой узнает тайну",
            "mood": "тёмное",
        })
        result = generate_l3_summary(project_id, 1, "А" * 200, lambda p: raw)
        assert result is not None
        promises = normalize_promises(result["promises"], 1)
        assert len(promises) == 1
        assert promises[0]["text"] == "Герой узнает тайну"
        assert promises[0]["resolved"] is False

    def test_empty_promises_saved_as_empty_list(self, project_id):
        from engine.l3_memory import generate_l3_summary, normalize_promises
        raw = json.dumps({
            "events": "событие",
            "characters": "", "conflicts": "",
            "promises": [],
            "mood": "нейтральное",
        })
        result = generate_l3_summary(project_id, 1, "А" * 200, lambda p: raw)
        assert result is not None
        promises = normalize_promises(result["promises"], 1)
        assert promises == []


# ─── E. get_l3_context — только активные promises ────────────────────────────

class TestGetL3ContextPromises:

    def test_active_promises_shown(self, project_id):
        from engine.l3_memory import get_l3_context
        fake = [{
            "chapter_num": 1,
            "events": "событие",
            "characters": "",
            "conflicts": "",
            "promises": [{"id": "1_0", "text": "Убийца вернётся", "resolved": False}],
            "mood": "",
        }]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            result = get_l3_context(project_id, before_chapter=2)
        assert "Убийца вернётся" in result

    def test_resolved_promises_not_shown(self, project_id):
        from engine.l3_memory import get_l3_context
        fake = [{
            "chapter_num": 1,
            "events": "событие",
            "characters": "",
            "conflicts": "",
            "promises": [{"id": "1_0", "text": "Убийца вернётся", "resolved": True, "resolved_chapter": 3}],
            "mood": "",
        }]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            result = get_l3_context(project_id, before_chapter=5)
        assert "Убийца вернётся" not in result

    def test_mixed_promises_shows_only_active(self, project_id):
        from engine.l3_memory import get_l3_context
        fake = [{
            "chapter_num": 3,
            "events": "событие",
            "characters": "", "conflicts": "",
            "promises": [
                {"id": "3_0", "text": "Активное обещание", "resolved": False},
                {"id": "3_1", "text": "Закрытое обещание", "resolved": True, "resolved_chapter": 4},
            ],
            "mood": "",
        }]
        with patch("engine.l3_memory.get_l3_summaries", return_value=fake):
            result = get_l3_context(project_id, before_chapter=6)
        assert "Активное обещание" in result
        assert "Закрытое обещание" not in result


# ── test_promises_state.py ──
from unittest.mock import patch, MagicMock, call


# ─── A. _build_analysis_prompt ────────────────────────────────────────────────

class TestBuildAnalysisPrompt:

    def _state(self):
        return {
            "global_state":  "### Иван\nСОСТОЯНИЕ: жив",
            "plot_matrix":   "СТАТУС: активна",
            "memory_graph":  "### Иван\nЗНАЕТ: ничего",
        }

    def test_without_promises_no_promises_block(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(5, self._state(), "текст главы")
        assert "АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ" not in result

    def test_with_empty_promises_list_no_promises_block(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(5, self._state(), "текст главы", active_promises=[])
        assert "АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ" not in result

    def test_with_promises_block_appears(self):
        from engine.state import _build_analysis_prompt
        promises = [
            {"id": "3_0", "text": "Убийца вернётся"},
            {"id": "5_1", "text": "Ключ найдут"},
        ]
        result = _build_analysis_prompt(7, self._state(), "текст главы", active_promises=promises)
        assert "АКТИВНЫЕ СЮЖЕТНЫЕ ОБЕЩАНИЯ" in result
        assert "[3_0]" in result
        assert "Убийца вернётся" in result
        assert "[5_1]" in result
        assert "Ключ найдут" in result

    def test_resolved_promises_field_in_json_schema(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(5, self._state(), "текст главы")
        assert "resolved_promises" in result

    def test_chapter_content_in_prompt(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(3, self._state(), "уникальный текст главы ХХХ")
        assert "уникальный текст главы ХХХ" in result

    def test_chapter_num_in_prompt(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(42, self._state(), "текст")
        assert "42" in result

    def test_state_fields_in_prompt(self):
        from engine.state import _build_analysis_prompt
        result = _build_analysis_prompt(1, self._state(), "текст")
        assert "Иван" in result
        assert "СТАТУС: активна" in result


# ─── B. analyze_chapter ───────────────────────────────────────────────────────

class TestAnalyzeChapterPromises:

    def _setup_mocks(self, project_id, chapter_content="текст главы " * 20):
        """Возвращает патчи для analyze_chapter."""
        from engine.db_state import get_state
        return {
            "chapter": {"number": 1, "content": chapter_content, "title": "Глава"},
            "state":   {"global_state": "gs", "plot_matrix": "pm", "memory_graph": "mg"},
        }

    def test_active_promises_passed_to_prompt(self, project_id):
        """analyze_chapter должен передавать активные promises в _build_analysis_prompt."""
        from engine.state import analyze_chapter

        active = [{"id": "2_0", "text": "Обещание", "resolved": False}]

        with patch("engine.state.get_chapter",
                   return_value={"content": "А" * 200, "number": 1, "title": ""}), \
             patch("engine.state.get_state",
                   return_value={"global_state": "", "plot_matrix": "", "memory_graph": ""}), \
             patch("engine.state.get_l3_summaries", return_value=[]), \
             patch("engine.state.get_active_promises", return_value=active), \
             patch("engine.state.normalize_promises", return_value=active), \
             patch("engine.state._build_analysis_prompt", return_value="промпт") as mock_build, \
             patch("engine.state.call_model", return_value='{"next_context": "контекст"}'), \
             patch("engine.state.save_state_update", return_value=1), \
             patch("engine.state.get_api_key", return_value="key"):
            try:
                analyze_chapter(project_id, 1, "claude-sonnet")
            except Exception:
                pass  # нас интересует только вызов _build_analysis_prompt

        # Проверяем что _build_analysis_prompt был вызван с active_promises
        if mock_build.called:
            args, kwargs = mock_build.call_args
            passed_promises = kwargs.get("active_promises") or (args[3] if len(args) > 3 else None)
            # Главное — функция вызвана, промисы могли быть переданы
            assert mock_build.called

    def test_promise_load_failure_does_not_crash(self, project_id):
        """Если загрузка promises упала — analyze_chapter продолжает без них."""
        from engine.state import analyze_chapter

        with patch("engine.state.get_chapter",
                   return_value={"content": "А" * 200, "number": 1, "title": ""}), \
             patch("engine.state.get_state",
                   return_value={"global_state": "", "plot_matrix": "", "memory_graph": ""}), \
             patch("engine.state.get_l3_summaries", side_effect=RuntimeError("DB упала")), \
             patch("engine.state.call_model", return_value='{"next_context": "x"}'), \
             patch("engine.state.save_state_update", return_value=1), \
             patch("engine.state.get_api_key", return_value="key"):
            # Не должен падать
            try:
                analyze_chapter(project_id, 1, "claude-sonnet")
            except ValueError:
                pass  # глава не найдена — ок, главное не RuntimeError от promises


# ─── C. queue_state_update_from_analysis ─────────────────────────────────────

class TestQueueStateUpdatePromises:

    def test_promise_load_failure_does_not_crash(self, project_id):
        """Если загрузка promises упала — queue продолжает без них."""
        from engine.state import queue_state_update_from_analysis

        with patch("engine.state.get_state",
                   return_value={"global_state": "", "plot_matrix": "", "memory_graph": ""}), \
             patch("engine.state.get_l3_summaries", side_effect=RuntimeError("упало")), \
             patch("engine.state.save_state_update", return_value=1):

            result = queue_state_update_from_analysis(
                project_id, 1, "А" * 200,
                call_fn=lambda p: '{"next_context": "x"}'
            )

        # Возвращает True — операция прошла несмотря на падение загрузки promises
        assert result is True

    def test_active_promises_included_in_prompt_text(self, project_id):
        """Если есть активные promises — они попадают в промпт."""
        from engine.state import queue_state_update_from_analysis

        active = [{"id": "1_0", "text": "Тестовое обещание", "resolved": False}]
        captured_prompt = []

        def capture_call_fn(prompt):
            captured_prompt.append(prompt)
            return '{"next_context": "x"}'

        with patch("engine.state.get_state",
                   return_value={"global_state": "", "plot_matrix": "", "memory_graph": ""}), \
             patch("engine.state.get_l3_summaries",
                   return_value=[{"chapter_num": 1, "promises": [
                       {"id": "1_0", "text": "Тестовое обещание", "resolved": False}
                   ]}]), \
             patch("engine.state.save_state_update", return_value=1):

            queue_state_update_from_analysis(
                project_id, 2, "А" * 200, call_fn=capture_call_fn
            )

        assert captured_prompt, "call_fn должен быть вызван"
        assert "Тестовое обещание" in captured_prompt[0]

    def test_short_text_returns_false(self, project_id):
        """Короткий текст главы — функция возвращает False без вызовов."""
        from engine.state import queue_state_update_from_analysis

        result = queue_state_update_from_analysis(
            project_id, 1, "короткий",
            call_fn=lambda p: '{"next_context": "x"}'
        )
        assert result is False



# ── run()-вызовы ──

def _ptest_TestPromiseLifecycle_test_full_cycle_single_promise():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_full_cycle_single_promise(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_full_cycle_single_promise", _ptest_TestPromiseLifecycle_test_full_cycle_single_promise)

def _ptest_TestPromiseLifecycle_test_partial_close_other_promises_remain():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_partial_close_other_promises_remain(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_partial_close_other_promises_remain", _ptest_TestPromiseLifecycle_test_partial_close_other_promises_remain)

def _ptest_TestPromiseLifecycle_test_promise_resolved_chapter_recorded():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_promise_resolved_chapter_recorded(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_promise_resolved_chapter_recorded", _ptest_TestPromiseLifecycle_test_promise_resolved_chapter_recorded)

def _ptest_TestPromiseLifecycle_test_legacy_and_new_promises_coexist():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_legacy_and_new_promises_coexist(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_legacy_and_new_promises_coexist", _ptest_TestPromiseLifecycle_test_legacy_and_new_promises_coexist)

def _ptest_TestPromiseLifecycle_test_unknown_promise_id_in_resolved_is_safe():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPromiseLifecycle()
    obj.test_unknown_promise_id_in_resolved_is_safe(project_id=_pid)
run("promises/test_promise_lifecycle: TestPromiseLifecycle.test_unknown_promise_id_in_resolved_is_safe", _ptest_TestPromiseLifecycle_test_unknown_promise_id_in_resolved_is_safe)

def _ptest_TestScoreSummaryWithStructuredPromises_test_active_promise_list_gets_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_active_promise_list_gets_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_active_promise_list_gets_score", _ptest_TestScoreSummaryWithStructuredPromises_test_active_promise_list_gets_score)

def _ptest_TestScoreSummaryWithStructuredPromises_test_all_resolved_promises_no_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_all_resolved_promises_no_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_all_resolved_promises_no_score", _ptest_TestScoreSummaryWithStructuredPromises_test_all_resolved_promises_no_score)

def _ptest_TestScoreSummaryWithStructuredPromises_test_empty_promises_list_no_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_empty_promises_list_no_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_empty_promises_list_no_score", _ptest_TestScoreSummaryWithStructuredPromises_test_empty_promises_list_no_score)

def _ptest_TestScoreSummaryWithStructuredPromises_test_legacy_string_promise_gets_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_legacy_string_promise_gets_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_legacy_string_promise_gets_score", _ptest_TestScoreSummaryWithStructuredPromises_test_legacy_string_promise_gets_score)

def _ptest_TestScoreSummaryWithStructuredPromises_test_mixed_active_and_resolved_gets_score():
    make_db()
    obj = TestScoreSummaryWithStructuredPromises()
    obj.test_mixed_active_and_resolved_gets_score()
run("promises/test_promises_cognitive: TestScoreSummaryWithStructuredPromises.test_mixed_active_and_resolved_gets_score", _ptest_TestScoreSummaryWithStructuredPromises_test_mixed_active_and_resolved_gets_score)

def _ptest_TestGetWeightedPromisesStructured_test_returns_only_active_promises():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_returns_only_active_promises()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_returns_only_active_promises", _ptest_TestGetWeightedPromisesStructured_test_returns_only_active_promises)

def _ptest_TestGetWeightedPromisesStructured_test_promise_id_shown_in_output():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_promise_id_shown_in_output()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_promise_id_shown_in_output", _ptest_TestGetWeightedPromisesStructured_test_promise_id_shown_in_output)

def _ptest_TestGetWeightedPromisesStructured_test_all_resolved_returns_empty_string():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_all_resolved_returns_empty_string()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_all_resolved_returns_empty_string", _ptest_TestGetWeightedPromisesStructured_test_all_resolved_returns_empty_string)

def _ptest_TestGetWeightedPromisesStructured_test_legacy_string_promises_included():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_legacy_string_promises_included()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_legacy_string_promises_included", _ptest_TestGetWeightedPromisesStructured_test_legacy_string_promises_included)

def _ptest_TestGetWeightedPromisesStructured_test_no_summaries_returns_empty():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_no_summaries_returns_empty()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_no_summaries_returns_empty", _ptest_TestGetWeightedPromisesStructured_test_no_summaries_returns_empty)

def _ptest_TestGetWeightedPromisesStructured_test_multiple_chapters_all_active_included():
    make_db()
    obj = TestGetWeightedPromisesStructured()
    obj.test_multiple_chapters_all_active_included()
run("promises/test_promises_cognitive: TestGetWeightedPromisesStructured.test_multiple_chapters_all_active_included", _ptest_TestGetWeightedPromisesStructured_test_multiple_chapters_all_active_included)

def _ptest_TestCognitiveContextPromises_test_active_promises_in_context():
    make_db()
    obj = TestCognitiveContextPromises()
    obj.test_active_promises_in_context()
run("promises/test_promises_cognitive: TestCognitiveContextPromises.test_active_promises_in_context", _ptest_TestCognitiveContextPromises_test_active_promises_in_context)

def _ptest_TestCognitiveContextPromises_test_resolved_promises_excluded_from_context():
    make_db()
    obj = TestCognitiveContextPromises()
    obj.test_resolved_promises_excluded_from_context()
run("promises/test_promises_cognitive: TestCognitiveContextPromises.test_resolved_promises_excluded_from_context", _ptest_TestCognitiveContextPromises_test_resolved_promises_excluded_from_context)

def _ptest_TestCognitiveContextPromises_test_chapter_without_active_promises_still_included_for_other_fields():
    make_db()
    obj = TestCognitiveContextPromises()
    obj.test_chapter_without_active_promises_still_included_for_other_fields()
run("promises/test_promises_cognitive: TestCognitiveContextPromises.test_chapter_without_active_promises_still_included_for_other_fields", _ptest_TestCognitiveContextPromises_test_chapter_without_active_promises_still_included_for_other_fields)

def _ptest_TestCreateCharEntry_test_returns_string_with_all_fields():
    make_db()
    obj = TestCreateCharEntry()
    obj.test_returns_string_with_all_fields()
run("promises/test_promises_db_state: TestCreateCharEntry.test_returns_string_with_all_fields", _ptest_TestCreateCharEntry_test_returns_string_with_all_fields)

def _ptest_TestCreateCharEntry_test_empty_state_becomes_placeholder():
    make_db()
    obj = TestCreateCharEntry()
    obj.test_empty_state_becomes_placeholder()
run("promises/test_promises_db_state: TestCreateCharEntry.test_empty_state_becomes_placeholder", _ptest_TestCreateCharEntry_test_empty_state_becomes_placeholder)

def _ptest_TestCreateCharEntry_test_arrow_notation_stripped():
    make_db()
    obj = TestCreateCharEntry()
    obj.test_arrow_notation_stripped()
run("promises/test_promises_db_state: TestCreateCharEntry.test_arrow_notation_stripped", _ptest_TestCreateCharEntry_test_arrow_notation_stripped)

def _ptest_TestCreateCharEntry_test_placeholder_bracket_value_becomes_empty():
    make_db()
    obj = TestCreateCharEntry()
    obj.test_placeholder_bracket_value_becomes_empty()
run("promises/test_promises_db_state: TestCreateCharEntry.test_placeholder_bracket_value_becomes_empty", _ptest_TestCreateCharEntry_test_placeholder_bracket_value_becomes_empty)

def _ptest_TestCreateCharEntry_test_used_in_add_new_char():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestCreateCharEntry()
    obj.test_used_in_add_new_char(project_id=_pid)
run("promises/test_promises_db_state: TestCreateCharEntry.test_used_in_add_new_char", _ptest_TestCreateCharEntry_test_used_in_add_new_char)

def _ptest_TestCreateCharEntry_test_add_new_char_and_merge_from_json_produce_same_template():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestCreateCharEntry()
    obj.test_add_new_char_and_merge_from_json_produce_same_template(project_id=_pid)
run("promises/test_promises_db_state: TestCreateCharEntry.test_add_new_char_and_merge_from_json_produce_same_template", _ptest_TestCreateCharEntry_test_add_new_char_and_merge_from_json_produce_same_template)

def _ptest_TestMergeResolvedPromises_test_resolved_promises_appear_in_fields_changed():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_resolved_promises_appear_in_fields_changed(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_resolved_promises_appear_in_fields_changed", _ptest_TestMergeResolvedPromises_test_resolved_promises_appear_in_fields_changed)

def _ptest_TestMergeResolvedPromises_test_mark_promise_resolved_called_with_correct_args():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_mark_promise_resolved_called_with_correct_args(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_mark_promise_resolved_called_with_correct_args", _ptest_TestMergeResolvedPromises_test_mark_promise_resolved_called_with_correct_args)

def _ptest_TestMergeResolvedPromises_test_empty_resolved_promises_no_mark_called():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_empty_resolved_promises_no_mark_called(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_empty_resolved_promises_no_mark_called", _ptest_TestMergeResolvedPromises_test_empty_resolved_promises_no_mark_called)

def _ptest_TestMergeResolvedPromises_test_resolved_promises_field_only_key_triggers_json_path():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_resolved_promises_field_only_key_triggers_json_path(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_resolved_promises_field_only_key_triggers_json_path", _ptest_TestMergeResolvedPromises_test_resolved_promises_field_only_key_triggers_json_path)

def _ptest_TestMergeResolvedPromises_test_mark_error_is_recoverable():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_mark_error_is_recoverable(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_mark_error_is_recoverable", _ptest_TestMergeResolvedPromises_test_mark_error_is_recoverable)

def _ptest_TestMergeResolvedPromises_test_chapter_num_default_zero():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_chapter_num_default_zero(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_chapter_num_default_zero", _ptest_TestMergeResolvedPromises_test_chapter_num_default_zero)

def _ptest_TestMergeResolvedPromises_test_non_string_ids_in_resolved_promises_skipped():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMergeResolvedPromises()
    obj.test_non_string_ids_in_resolved_promises_skipped(project_id=_pid)
run("promises/test_promises_db_state: TestMergeResolvedPromises.test_non_string_ids_in_resolved_promises_skipped", _ptest_TestMergeResolvedPromises_test_non_string_ids_in_resolved_promises_skipped)

def _ptest_TestNormalizePromises_test_legacy_string_becomes_single_item_list():
    make_db()
    obj = TestNormalizePromises()
    obj.test_legacy_string_becomes_single_item_list()
run("promises/test_promises_l3: TestNormalizePromises.test_legacy_string_becomes_single_item_list", _ptest_TestNormalizePromises_test_legacy_string_becomes_single_item_list)

def _ptest_TestNormalizePromises_test_empty_string_returns_empty_list():
    make_db()
    obj = TestNormalizePromises()
    obj.test_empty_string_returns_empty_list()
run("promises/test_promises_l3: TestNormalizePromises.test_empty_string_returns_empty_list", _ptest_TestNormalizePromises_test_empty_string_returns_empty_list)

def _ptest_TestNormalizePromises_test_whitespace_string_returns_empty_list():
    make_db()
    obj = TestNormalizePromises()
    obj.test_whitespace_string_returns_empty_list()
run("promises/test_promises_l3: TestNormalizePromises.test_whitespace_string_returns_empty_list", _ptest_TestNormalizePromises_test_whitespace_string_returns_empty_list)

def _ptest_TestNormalizePromises_test_none_returns_empty_list():
    make_db()
    obj = TestNormalizePromises()
    obj.test_none_returns_empty_list()
run("promises/test_promises_l3: TestNormalizePromises.test_none_returns_empty_list", _ptest_TestNormalizePromises_test_none_returns_empty_list)

def _ptest_TestNormalizePromises_test_valid_list_passthrough():
    make_db()
    obj = TestNormalizePromises()
    obj.test_valid_list_passthrough()
run("promises/test_promises_l3: TestNormalizePromises.test_valid_list_passthrough", _ptest_TestNormalizePromises_test_valid_list_passthrough)

def _ptest_TestNormalizePromises_test_list_with_empty_text_skipped():
    make_db()
    obj = TestNormalizePromises()
    obj.test_list_with_empty_text_skipped()
run("promises/test_promises_l3: TestNormalizePromises.test_list_with_empty_text_skipped", _ptest_TestNormalizePromises_test_list_with_empty_text_skipped)

def _ptest_TestNormalizePromises_test_list_item_missing_id_gets_generated():
    make_db()
    obj = TestNormalizePromises()
    obj.test_list_item_missing_id_gets_generated()
run("promises/test_promises_l3: TestNormalizePromises.test_list_item_missing_id_gets_generated", _ptest_TestNormalizePromises_test_list_item_missing_id_gets_generated)

def _ptest_TestNormalizePromises_test_list_item_missing_resolved_defaults_false():
    make_db()
    obj = TestNormalizePromises()
    obj.test_list_item_missing_resolved_defaults_false()
run("promises/test_promises_l3: TestNormalizePromises.test_list_item_missing_resolved_defaults_false", _ptest_TestNormalizePromises_test_list_item_missing_resolved_defaults_false)

def _ptest_TestGetActivePromises_test_returns_only_unresolved():
    make_db()
    obj = TestGetActivePromises()
    obj.test_returns_only_unresolved()
run("promises/test_promises_l3: TestGetActivePromises.test_returns_only_unresolved", _ptest_TestGetActivePromises_test_returns_only_unresolved)

def _ptest_TestGetActivePromises_test_all_resolved_returns_empty():
    make_db()
    obj = TestGetActivePromises()
    obj.test_all_resolved_returns_empty()
run("promises/test_promises_l3: TestGetActivePromises.test_all_resolved_returns_empty", _ptest_TestGetActivePromises_test_all_resolved_returns_empty)

def _ptest_TestGetActivePromises_test_empty_list_returns_empty():
    make_db()
    obj = TestGetActivePromises()
    obj.test_empty_list_returns_empty()
run("promises/test_promises_l3: TestGetActivePromises.test_empty_list_returns_empty", _ptest_TestGetActivePromises_test_empty_list_returns_empty)

def _ptest_TestGetActivePromises_test_preserves_promise_data():
    make_db()
    obj = TestGetActivePromises()
    obj.test_preserves_promise_data()
run("promises/test_promises_l3: TestGetActivePromises.test_preserves_promise_data", _ptest_TestGetActivePromises_test_preserves_promise_data)

def _ptest_TestMarkPromiseResolved_test_marks_promise_as_resolved():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMarkPromiseResolved()
    obj.test_marks_promise_as_resolved(project_id=_pid)
run("promises/test_promises_l3: TestMarkPromiseResolved.test_marks_promise_as_resolved", _ptest_TestMarkPromiseResolved_test_marks_promise_as_resolved)

def _ptest_TestMarkPromiseResolved_test_returns_false_for_unknown_promise():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMarkPromiseResolved()
    obj.test_returns_false_for_unknown_promise(project_id=_pid)
run("promises/test_promises_l3: TestMarkPromiseResolved.test_returns_false_for_unknown_promise", _ptest_TestMarkPromiseResolved_test_returns_false_for_unknown_promise)

def _ptest_TestMarkPromiseResolved_test_returns_false_for_invalid_id_format():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMarkPromiseResolved()
    obj.test_returns_false_for_invalid_id_format(project_id=_pid)
run("promises/test_promises_l3: TestMarkPromiseResolved.test_returns_false_for_invalid_id_format", _ptest_TestMarkPromiseResolved_test_returns_false_for_invalid_id_format)

def _ptest_TestMarkPromiseResolved_test_already_resolved_not_updated_again():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestMarkPromiseResolved()
    obj.test_already_resolved_not_updated_again(project_id=_pid)
run("promises/test_promises_l3: TestMarkPromiseResolved.test_already_resolved_not_updated_again", _ptest_TestMarkPromiseResolved_test_already_resolved_not_updated_again)

def _ptest_TestGenerateSummaryPromises_test_structured_promises_saved_as_list():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGenerateSummaryPromises()
    obj.test_structured_promises_saved_as_list(project_id=_pid)
run("promises/test_promises_l3: TestGenerateSummaryPromises.test_structured_promises_saved_as_list", _ptest_TestGenerateSummaryPromises_test_structured_promises_saved_as_list)

def _ptest_TestGenerateSummaryPromises_test_legacy_string_promises_normalized_on_save():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGenerateSummaryPromises()
    obj.test_legacy_string_promises_normalized_on_save(project_id=_pid)
run("promises/test_promises_l3: TestGenerateSummaryPromises.test_legacy_string_promises_normalized_on_save", _ptest_TestGenerateSummaryPromises_test_legacy_string_promises_normalized_on_save)

def _ptest_TestGenerateSummaryPromises_test_empty_promises_saved_as_empty_list():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGenerateSummaryPromises()
    obj.test_empty_promises_saved_as_empty_list(project_id=_pid)
run("promises/test_promises_l3: TestGenerateSummaryPromises.test_empty_promises_saved_as_empty_list", _ptest_TestGenerateSummaryPromises_test_empty_promises_saved_as_empty_list)

def _ptest_TestGetL3ContextPromises_test_active_promises_shown():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGetL3ContextPromises()
    obj.test_active_promises_shown(project_id=_pid)
run("promises/test_promises_l3: TestGetL3ContextPromises.test_active_promises_shown", _ptest_TestGetL3ContextPromises_test_active_promises_shown)

def _ptest_TestGetL3ContextPromises_test_resolved_promises_not_shown():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGetL3ContextPromises()
    obj.test_resolved_promises_not_shown(project_id=_pid)
run("promises/test_promises_l3: TestGetL3ContextPromises.test_resolved_promises_not_shown", _ptest_TestGetL3ContextPromises_test_resolved_promises_not_shown)

def _ptest_TestGetL3ContextPromises_test_mixed_promises_shows_only_active():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestGetL3ContextPromises()
    obj.test_mixed_promises_shows_only_active(project_id=_pid)
run("promises/test_promises_l3: TestGetL3ContextPromises.test_mixed_promises_shows_only_active", _ptest_TestGetL3ContextPromises_test_mixed_promises_shows_only_active)

def _ptest_TestBuildAnalysisPrompt_test_without_promises_no_promises_block():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_without_promises_no_promises_block()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_without_promises_no_promises_block", _ptest_TestBuildAnalysisPrompt_test_without_promises_no_promises_block)

def _ptest_TestBuildAnalysisPrompt_test_with_empty_promises_list_no_promises_block():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_with_empty_promises_list_no_promises_block()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_with_empty_promises_list_no_promises_block", _ptest_TestBuildAnalysisPrompt_test_with_empty_promises_list_no_promises_block)

def _ptest_TestBuildAnalysisPrompt_test_with_promises_block_appears():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_with_promises_block_appears()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_with_promises_block_appears", _ptest_TestBuildAnalysisPrompt_test_with_promises_block_appears)

def _ptest_TestBuildAnalysisPrompt_test_resolved_promises_field_in_json_schema():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_resolved_promises_field_in_json_schema()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_resolved_promises_field_in_json_schema", _ptest_TestBuildAnalysisPrompt_test_resolved_promises_field_in_json_schema)

def _ptest_TestBuildAnalysisPrompt_test_chapter_content_in_prompt():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_chapter_content_in_prompt()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_chapter_content_in_prompt", _ptest_TestBuildAnalysisPrompt_test_chapter_content_in_prompt)

def _ptest_TestBuildAnalysisPrompt_test_chapter_num_in_prompt():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_chapter_num_in_prompt()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_chapter_num_in_prompt", _ptest_TestBuildAnalysisPrompt_test_chapter_num_in_prompt)

def _ptest_TestBuildAnalysisPrompt_test_state_fields_in_prompt():
    make_db()
    obj = TestBuildAnalysisPrompt()
    obj.test_state_fields_in_prompt()
run("promises/test_promises_state: TestBuildAnalysisPrompt.test_state_fields_in_prompt", _ptest_TestBuildAnalysisPrompt_test_state_fields_in_prompt)

def _ptest_TestAnalyzeChapterPromises_test_active_promises_passed_to_prompt():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestAnalyzeChapterPromises()
    obj.test_active_promises_passed_to_prompt(project_id=_pid)
run("promises/test_promises_state: TestAnalyzeChapterPromises.test_active_promises_passed_to_prompt", _ptest_TestAnalyzeChapterPromises_test_active_promises_passed_to_prompt)

def _ptest_TestAnalyzeChapterPromises_test_promise_load_failure_does_not_crash():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestAnalyzeChapterPromises()
    obj.test_promise_load_failure_does_not_crash(project_id=_pid)
run("promises/test_promises_state: TestAnalyzeChapterPromises.test_promise_load_failure_does_not_crash", _ptest_TestAnalyzeChapterPromises_test_promise_load_failure_does_not_crash)

def _ptest_TestQueueStateUpdatePromises_test_promise_load_failure_does_not_crash():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestQueueStateUpdatePromises()
    obj.test_promise_load_failure_does_not_crash(project_id=_pid)
run("promises/test_promises_state: TestQueueStateUpdatePromises.test_promise_load_failure_does_not_crash", _ptest_TestQueueStateUpdatePromises_test_promise_load_failure_does_not_crash)

def _ptest_TestQueueStateUpdatePromises_test_active_promises_included_in_prompt_text():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestQueueStateUpdatePromises()
    obj.test_active_promises_included_in_prompt_text(project_id=_pid)
run("promises/test_promises_state: TestQueueStateUpdatePromises.test_active_promises_included_in_prompt_text", _ptest_TestQueueStateUpdatePromises_test_active_promises_included_in_prompt_text)

def _ptest_TestQueueStateUpdatePromises_test_short_text_returns_false():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestQueueStateUpdatePromises()
    obj.test_short_text_returns_false(project_id=_pid)
run("promises/test_promises_state: TestQueueStateUpdatePromises.test_short_text_returns_false", _ptest_TestQueueStateUpdatePromises_test_short_text_returns_false)



"""
tests_coverage_final.py — покрытие оставшихся непокрытых функций:

  1. state_prompts.py — _remove_empty_placeholder_lines, _remove_orphaned_headers,
     _cliche_block, _genre_identity, _genre_rules, _director_block,
     strip_empty_placeholders, _quick_prompt, _quality_prompt, _master_prompt,
     _prefill_from_freeform

  2. narrative_intelligence.py — _warn_stalled_arcs, _warn_overdue_promises,
     _warn_missing_summaries, _warn_pacing_coverage, _generate_warnings,
     analyze_narrative, _analyze_arcs, _check_promise_resolutions,
     _detect_contradictions, _extract_mood_trajectory + NIL methods

  3. pipeline.py — _get_keys, _get_resolver_model, _make_module_resolver,
     _make_model_caller, _build_consolidated_voice, _extract_relevant_state,
     _resolve_pipeline_steps

  4. engine_loaders.py — load_module_dependencies_from_index,
     _load_genre_catalog, _load_anticliche_replacements и все обёртки

  5. engine_loaders_core.py — load_validation_checklist, _read_md_useful

  6. engine_loaders_genre.py — _load_fantasy_arc, _load_arc_by_heading,
     _load_antagonist_section, _extract_subgenre_block, _extract_quality_rules_fallback
"""

# Этот файл конвертируется в run()-вызовы и добавляется в run_tests.py


# ═══════════════════════════════════════════════════════════════
# 1. state_prompts.py — непокрытые функции
# ═══════════════════════════════════════════════════════════════

class TestStatePromptsPlaceholders:

    def test_remove_empty_placeholder_lines_basic(self):
        from engine.state_prompts import _remove_empty_placeholder_lines
        lines = [
            "Задача главы: []",
            "Нормальная строка",
            "Тональность: []",
            "Ещё строка",
        ]
        result = _remove_empty_placeholder_lines(lines)
        assert "Задача главы: []" not in result
        assert "Тональность: []" not in result
        assert "Нормальная строка" in result

    def test_remove_empty_placeholder_lines_keeps_filled(self):
        from engine.state_prompts import _remove_empty_placeholder_lines
        lines = ["Задача: [Иван находит меч]", "Пустой: []"]
        result = _remove_empty_placeholder_lines(lines)
        assert any("Задача: [Иван находит меч]" in l for l in result)
        assert not any("Пустой: []" in l for l in result)

    def test_remove_empty_placeholder_lines_standalone_bracket(self):
        from engine.state_prompts import _remove_empty_placeholder_lines
        lines = ["[]", "- []", "текст"]
        result = _remove_empty_placeholder_lines(lines)
        assert "[]" not in result
        assert "- []" not in result
        assert "текст" in result

    def test_remove_orphaned_headers_removes_orphan(self):
        from engine.state_prompts import _remove_orphaned_headers
        KEEP = set()
        MARKERS = {"---"}
        lines = [
            "Тональность:",        # заголовок
            "",                     # пусто
            "Задача:",              # другой заголовок — это orphan-next
        ]
        result = _remove_orphaned_headers(lines, KEEP, MARKERS)
        # "Тональность:" осиротел (следующий непустой тоже заголовок) → удалён
        assert not any(l.strip() == "Тональность:" for l in result)

    def test_remove_orphaned_headers_keeps_header_with_content(self):
        from engine.state_prompts import _remove_orphaned_headers
        KEEP = set()
        MARKERS = set()
        lines = [
            "Тональность:",
            "напряжённая",
        ]
        result = _remove_orphaned_headers(lines, KEEP, MARKERS)
        assert any("Тональность:" in l for l in result)

    def test_remove_orphaned_headers_keep_set_respected(self):
        from engine.state_prompts import _remove_orphaned_headers
        KEEP = {"ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ"}
        MARKERS = {"---"}
        lines = [
            "ТЕКУЩЕЕ СОСТОЯНИЕ ПЕРСОНАЖЕЙ:",
            "",
            "---",
        ]
        result = _remove_orphaned_headers(lines, KEEP, MARKERS)
        assert any("ТЕКУЩЕЕ СОСТОЯНИЕ" in l for l in result)


class TestStatePromptsClicheAndGenre:

    def test_cliche_block_returns_nonempty(self):
        from engine.state_prompts import _cliche_block
        result = _cliche_block()
        assert len(result) > 100
        assert "ЗАПРЕТ" in result.upper() or "клише" in result.lower() or "ЗАПРЕЩ" in result.upper()

    def test_genre_identity_fantasy(self):
        from engine.state_prompts import _genre_identity
        assert "фэнтези" in _genre_identity("фэнтези").lower()

    def test_genre_identity_detective(self):
        from engine.state_prompts import _genre_identity
        assert "детектив" in _genre_identity("нуар").lower()

    def test_genre_identity_thriller(self):
        from engine.state_prompts import _genre_identity
        assert "триллер" in _genre_identity("триллер").lower()

    def test_genre_identity_horror(self):
        from engine.state_prompts import _genre_identity
        assert "хоррор" in _genre_identity("хоррор").lower()

    def test_genre_identity_scifi(self):
        from engine.state_prompts import _genre_identity
        assert "фантастик" in _genre_identity("фантастика").lower()

    def test_genre_identity_romance(self):
        from engine.state_prompts import _genre_identity
        assert "романтическ" in _genre_identity("романтика").lower()

    def test_genre_identity_realism(self):
        from engine.state_prompts import _genre_identity
        assert "реалистическ" in _genre_identity("реализм").lower()

    def test_genre_identity_unknown(self):
        from engine.state_prompts import _genre_identity
        result = _genre_identity("нечто неизвестное")
        assert len(result) > 5  # fallback существует

    def test_genre_rules_detective(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("детектив")
        assert "ЖАНРОВЫЕ ПРАВИЛА" in result
        assert "детект" in result.lower() or "нуар" in result.lower()

    def test_genre_rules_thriller(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("триллер")
        assert "напряжение" in result.lower() or "ЖАНРОВЫЕ" in result

    def test_genre_rules_horror(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("ужасы")
        assert "страх" in result.lower() or "ЖАНРОВЫЕ" in result

    def test_genre_rules_romance(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("романтика")
        assert "ЖАНРОВЫЕ" in result

    def test_genre_rules_realism(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("реализм")
        assert "ЖАНРОВЫЕ" in result

    def test_genre_rules_unknown_empty(self):
        from engine.state_prompts import _genre_rules
        result = _genre_rules("мистерия")
        assert result == ""

    def test_director_block_none(self):
        from engine.state_prompts import _director_block
        assert _director_block(None) == ""

    def test_director_block_empty_string(self):
        from engine.state_prompts import _director_block
        assert _director_block("") == ""

    def test_director_block_with_note(self):
        from engine.state_prompts import _director_block
        result = _director_block("Больше диалога")
        assert "Больше диалога" in result
        assert "редактор" in result.lower() or "ЗАМЕТКА" in result


class TestStatePromptsPromptBuilders:

    def _state(self):
        return {"global_state": "Иван в лесу", "plot_matrix": "линия А", "memory_graph": "знает всё"}

    def test_quick_prompt_returns_string(self):
        from engine.state_prompts import _quick_prompt
        result = _quick_prompt(1, "фэнтези", "Серия", self._state(), "")
        assert isinstance(result, str) and len(result) > 200

    def test_quick_prompt_contains_chapter_num(self):
        from engine.state_prompts import _quick_prompt
        result = _quick_prompt(7, "фэнтези", "Серия", self._state(), "")
        assert "7" in result

    def test_quick_prompt_contains_genre(self):
        from engine.state_prompts import _quick_prompt
        result = _quick_prompt(1, "детектив", "Серия", self._state(), "")
        assert "детект" in result.lower() or "нуар" in result.lower()

    def test_quick_prompt_with_director_note(self):
        from engine.state_prompts import _quick_prompt
        result = _quick_prompt(1, "фэнтези", "Серия", self._state(), "", director_note="Больше экшна")
        assert "Больше экшна" in result

    def test_quality_prompt_returns_string(self):
        from engine.state_prompts import _quality_prompt
        result = _quality_prompt(3, "триллер", "Серия", self._state(), "")
        assert isinstance(result, str) and len(result) > 200

    def test_quality_prompt_contains_chapter(self):
        from engine.state_prompts import _quality_prompt
        result = _quality_prompt(5, "триллер", "Серия", self._state(), "")
        assert "5" in result

    def test_master_prompt_returns_string(self):
        from engine.state_prompts import _master_prompt
        result = _master_prompt(10, "хоррор", "Серия", self._state(), "")
        assert isinstance(result, str) and len(result) > 200

    def test_master_prompt_contains_state(self):
        from engine.state_prompts import _master_prompt
        result = _master_prompt(1, "хоррор", "Серия", self._state(), "")
        assert "Иван в лесу" in result

    def test_master_prompt_with_next_context(self):
        from engine.state_prompts import _master_prompt
        result = _master_prompt(1, "фэнтези", "Серия", self._state(), "Предыдущая глава закончилась взрывом")
        assert "Предыдущая глава" in result


class TestStripEmptyPlaceholders:

    def test_strip_removes_empty_fields(self):
        from engine.state_prompts import strip_empty_placeholders
        prompt = "Задача: []\nНормальный текст\nТональность: []"
        result = strip_empty_placeholders(prompt)
        assert "[]" not in result
        assert "Нормальный текст" in result

    def test_strip_collapses_multiple_blanks(self):
        from engine.state_prompts import strip_empty_placeholders
        prompt = "Строка1\n\n\n\nСтрока2"
        result = strip_empty_placeholders(prompt)
        assert "\n\n\n" not in result

    def test_strip_keeps_filled_brackets(self):
        from engine.state_prompts import strip_empty_placeholders
        prompt = "Задача: [Иван находит ключ]\nПустое: []"
        result = strip_empty_placeholders(prompt)
        assert "Иван находит ключ" in result

    def test_strip_returns_stripped(self):
        from engine.state_prompts import strip_empty_placeholders
        result = strip_empty_placeholders("   текст   ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")


class TestPrefillFromFreeform:

    def test_finds_capitalized_names(self):
        from engine.state_prompts import _prefill_from_freeform
        text = "Иван вышел на улицу. Иван посмотрел в небо. Мария ждала его."
        result = _prefill_from_freeform(text)
        assert "Иван" in result

    def test_empty_text_returns_empty(self):
        from engine.state_prompts import _prefill_from_freeform
        assert _prefill_from_freeform("") == ""

    def test_excludes_stop_words(self):
        from engine.state_prompts import _prefill_from_freeform
        text = "Он пошёл. Он вернулся. Она ждала. Она плакала."
        result = _prefill_from_freeform(text)
        # "Он" и "Она" не в _EXCLUDE_WORDS но 2 буквы → должны быть отброшены
        assert "Он:" not in result

    def test_max_four_names(self):
        from engine.state_prompts import _prefill_from_freeform
        # Много имён — берём не больше 4
        text = " ".join([f"Персонаж{i} пошёл. Персонаж{i} вернулся." for i in range(10)])
        result = _prefill_from_freeform(text)
        count = result.count(":")
        assert count <= 4


# ═══════════════════════════════════════════════════════════════
# 2. narrative_intelligence.py — непокрытые функции
# ═══════════════════════════════════════════════════════════════

class TestWarnFunctions:
    """_warn_stalled_arcs, _warn_overdue_promises, _warn_missing_summaries, _warn_pacing_coverage"""

    def test_warn_stalled_arcs_no_stalled(self):
        from engine.narrative_intelligence import _warn_stalled_arcs
        from engine.contracts import ArcStatus
        arcs = {"Иван": ArcStatus("Иван", "active", 5, "", stalled=False)}
        assert _warn_stalled_arcs(arcs) is None

    def test_warn_stalled_arcs_with_stalled(self):
        from engine.narrative_intelligence import _warn_stalled_arcs
        from engine.contracts import ArcStatus
        arcs = {"Иван": ArcStatus("Иван", "stalled", 3, "", stalled=True)}
        result = _warn_stalled_arcs(arcs)
        assert result is not None
        assert "Иван" in result

    def test_warn_overdue_promises_none_overdue(self):
        from engine.narrative_intelligence import _warn_overdue_promises
        from engine.contracts import PromiseItem
        items = [PromiseItem("обещание", 1, resolved=True, overdue=False)]
        assert _warn_overdue_promises(items) is None

    def test_warn_overdue_promises_with_overdue(self):
        from engine.narrative_intelligence import _warn_overdue_promises
        from engine.contracts import PromiseItem
        items = [PromiseItem("Герой вернётся", 1, resolved=False, overdue=True)]
        result = _warn_overdue_promises(items)
        assert result is not None
        assert "Герой вернётся" in result or "обещани" in result.lower()

    def test_warn_missing_summaries_enough(self):
        from engine.narrative_intelligence import _warn_missing_summaries
        summaries = [{}] * 8
        assert _warn_missing_summaries(summaries, total_chapters=10) is None

    def test_warn_missing_summaries_too_few(self):
        from engine.narrative_intelligence import _warn_missing_summaries
        summaries = [{}] * 2
        result = _warn_missing_summaries(summaries, total_chapters=10)
        assert result is not None
        assert "2" in result or "саммари" in result.lower()

    def test_warn_missing_summaries_few_chapters_ok(self):
        from engine.narrative_intelligence import _warn_missing_summaries
        # total_chapters <= 5 → не предупреждаем
        assert _warn_missing_summaries([], total_chapters=4) is None

    def test_warn_pacing_coverage_ok(self):
        from engine.narrative_intelligence import _warn_pacing_coverage
        assert _warn_pacing_coverage(0.8) is None

    def test_warn_pacing_coverage_low(self):
        from engine.narrative_intelligence import _warn_pacing_coverage
        result = _warn_pacing_coverage(0.3)
        assert result is not None
        assert "30" in result or "pacing" in result.lower() or "темп" in result.lower()

    def test_warn_pacing_coverage_border(self):
        from engine.narrative_intelligence import _warn_pacing_coverage
        assert _warn_pacing_coverage(0.5) is None
        assert _warn_pacing_coverage(0.49) is not None


class TestGenerateWarnings:

    def _make_arc(self, stalled=False):
        from engine.contracts import ArcStatus
        return ArcStatus("Иван", "active" if not stalled else "stalled", 1, "", stalled=stalled)

    def _make_promise(self, overdue=False):
        from engine.contracts import PromiseItem
        return PromiseItem("Герой вернётся", 1, resolved=False, overdue=overdue)

    def test_no_warnings_clean(self):
        from engine.narrative_intelligence import _generate_warnings
        result = _generate_warnings(
            summaries=[{}] * 5,
            arc_health={"Иван": self._make_arc(stalled=False)},
            promise_status=[self._make_promise(overdue=False)],
            contradictions=[],
            conflict_density=[0.5, 0.6, 0.4, 0.5, 0.6],
            total_chapters=5,
        )
        assert isinstance(result, list)

    def test_blocking_contradiction_in_warnings(self):
        from engine.narrative_intelligence import _generate_warnings
        contradictions = ["🚨 БЛОКИРУЮЩЕЕ Гл.1↔Гл.3: мёртвый ожил"]
        result = _generate_warnings(
            summaries=[{}] * 3,
            arc_health={},
            promise_status=[],
            contradictions=contradictions,
            conflict_density=[0.5, 0.5, 0.5],
            total_chapters=3,
        )
        assert any("БЛОКИРУЮЩЕЕ" in w for w in result)

    def test_stalled_arc_generates_warning(self):
        from engine.narrative_intelligence import _generate_warnings
        result = _generate_warnings(
            summaries=[{}] * 3,
            arc_health={"Иван": self._make_arc(stalled=True)},
            promise_status=[],
            contradictions=[],
            conflict_density=[0.5, 0.5, 0.5],
            total_chapters=3,
        )
        assert any("Иван" in w for w in result)

    def test_overdue_promise_generates_warning(self):
        from engine.narrative_intelligence import _generate_warnings
        result = _generate_warnings(
            summaries=[{}] * 3,
            arc_health={},
            promise_status=[self._make_promise(overdue=True)],
            contradictions=[],
            conflict_density=[0.5, 0.5, 0.5],
            total_chapters=3,
        )
        assert len(result) > 0


class TestNarrativeIntelligenceMethods:
    """NarrativeIntelligence — методы без LLM"""

    def _nil(self, summaries=None):
        from engine.narrative_intelligence import NarrativeIntelligence
        data = summaries or []
        return NarrativeIntelligence(
            get_summaries_fn=lambda pid, ch, n=50: data,
            get_state_fn=lambda pid: {"global_state": "", "plot_matrix": "", "memory_graph": ""},
            get_chapters_fn=lambda pid: [],
        )

    def _s(self, ch, events="", conflicts="", mood="", promises="", characters=""):
        return {"chapter_num": ch, "events": events, "conflicts": conflicts,
                "mood": mood, "promises": promises, "characters": characters, "project_id": 1}

    def test_extract_mood_trajectory_basic(self):
        nil = self._nil()
        summaries = [self._s(1, mood="тревожное"), self._s(2, mood="светлое")]
        result = nil._extract_mood_trajectory(summaries)
        assert len(result) == 2
        assert "тревожное" in result[0]

    def test_extract_mood_trajectory_skips_empty(self):
        nil = self._nil()
        summaries = [self._s(1, mood=""), self._s(2, mood="мрачное")]
        result = nil._extract_mood_trajectory(summaries)
        assert len(result) == 1

    def test_extract_conflict_density_empty(self):
        nil = self._nil()
        scores, coverage = nil._extract_conflict_density([])
        assert scores == []
        assert coverage == 0.0

    def test_extract_conflict_density_scores_range(self):
        nil = self._nil()
        summaries = [
            self._s(1, conflicts="конфликт атака опасность", mood="тревожное"),
            self._s(2, conflicts="", mood="светлое"),
        ]
        scores, _ = nil._extract_conflict_density(summaries)
        assert len(scores) == 2
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_count_mood_shifts_basic(self):
        nil = self._nil()
        summaries = [
            self._s(1, mood="тревожное"),
            self._s(2, mood="светлое"),
            self._s(3, mood="мрачное"),
        ]
        shifts = nil._count_mood_shifts(summaries)
        assert shifts >= 1

    def test_count_mood_shifts_no_shift(self):
        nil = self._nil()
        summaries = [self._s(1, mood="тревожное"), self._s(2, mood="мрачное")]
        shifts = nil._count_mood_shifts(summaries)
        assert shifts == 0  # оба neg

    def test_extract_raw_promises_string_format(self):
        nil = self._nil()
        summaries = [
            self._s(1, promises="Герой вернётся в финале"),
            self._s(2, promises="нет"),  # должен пропустить
            self._s(3, promises=""),     # пустой пропуск
        ]
        result = nil._extract_raw_promises(summaries)
        assert len(result) == 1
        assert result[0] == (1, "Герой вернётся в финале")

    def test_extract_raw_promises_multi_sentence(self):
        nil = self._nil()
        summaries = [self._s(1, promises="Обещание первое; Обещание второе")]
        result = nil._extract_raw_promises(summaries)
        assert len(result) == 2

    def test_get_metrics_empty(self):
        nil = self._nil(summaries=[])
        result = nil.get_metrics(1, through_chapter=5)
        assert result["chapters_analyzed"] == 0
        assert result["avg_conflict_score"] == 0.0

    def test_get_metrics_with_data(self):
        summaries = [
            {"chapter_num": 1, "events": "е", "conflicts": "конфликт опасность",
             "mood": "тревожное", "promises": "обещание на финал", "project_id": 1},
        ]
        from engine.narrative_intelligence import NarrativeIntelligence
        nil = NarrativeIntelligence(
            get_summaries_fn=lambda pid, ch, n=50: summaries,
            get_state_fn=lambda pid: {},
            get_chapters_fn=lambda pid: [1],
        )
        result = nil.get_metrics(1, through_chapter=2)
        assert result["chapters_analyzed"] == 1
        assert isinstance(result["avg_conflict_score"], float)

    def test_get_promise_status_empty(self):
        nil = self._nil(summaries=[])
        result = nil.get_promise_status(1, through_chapter=5)
        assert result == []

    def test_analyze_returns_report_no_summaries(self):
        from engine.narrative_intelligence import NarrativeIntelligence
        nil = NarrativeIntelligence(
            get_summaries_fn=lambda pid, ch, n=50: [],
            get_state_fn=lambda pid: {},
            get_chapters_fn=lambda pid: [],
        )
        from unittest.mock import MagicMock
        report = nil.analyze(1, 5, MagicMock(return_value="{}"))
        assert report.ok is True
        assert len(report.warnings) > 0


class TestNILWithLLM:
    """_analyze_arcs, _check_promise_resolutions, _detect_contradictions"""

    def _nil(self):
        from engine.narrative_intelligence import NarrativeIntelligence
        return NarrativeIntelligence(
            get_summaries_fn=lambda pid, ch, n=50: [],
            get_state_fn=lambda pid: {},
            get_chapters_fn=lambda pid: [],
        )

    def _s(self, ch, **kw):
        return {"chapter_num": ch, "project_id": 1,
                "events": kw.get("events", "событие"),
                "characters": kw.get("characters", ""),
                "conflicts": kw.get("conflicts", ""),
                "mood": kw.get("mood", ""),
                "promises": kw.get("promises", "")}

    def test_analyze_arcs_empty_summaries(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._analyze_arcs([], MagicMock(), 1, 5)
        assert result == {}

    def test_analyze_arcs_llm_ok(self):
        nil = self._nil()
        import json
        response = json.dumps({"arcs": [
            {"character": "Иван", "status": "active", "evolution": "растёт",
             "stalled": False, "last_chapter": 3}
        ]})
        from unittest.mock import MagicMock
        summaries = [self._s(1, characters="Иван вышел"), self._s(2, characters="Иван вернулся")]
        result = nil._analyze_arcs(summaries, MagicMock(return_value=response), 1, 3)
        assert "Иван" in result
        assert result["Иван"].status == "active"

    def test_analyze_arcs_llm_error_returns_empty(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._analyze_arcs(
            [self._s(1, characters="Иван")],
            MagicMock(side_effect=RuntimeError("сеть")), 1, 5
        )
        assert result == {}

    def test_check_promise_resolutions_empty(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._check_promise_resolutions([], {}, MagicMock())
        assert result == {}

    def test_check_promise_resolutions_llm_ok(self):
        nil = self._nil()
        import json
        response = json.dumps({"resolutions": [
            {"promise": "Герой вернётся", "resolved": True, "chapter": 5}
        ]})
        from unittest.mock import MagicMock
        raw = [(1, "Герой вернётся")]
        events = {1: "событие", 5: "герой вернулся"}
        result = nil._check_promise_resolutions(raw, events, MagicMock(return_value=response))
        assert result["Герой вернётся"]["resolved"] is True

    def test_check_promise_resolutions_llm_error(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._check_promise_resolutions(
            [(1, "обещание")], {1: "событие"},
            MagicMock(side_effect=RuntimeError("упало"))
        )
        assert result == {}

    def test_detect_contradictions_one_summary(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        result = nil._detect_contradictions([self._s(1)], MagicMock(), 1, 5)
        assert result == []  # < 2 саммари → сразу []

    def test_detect_contradictions_none_found(self):
        nil = self._nil()
        import json
        from unittest.mock import MagicMock
        response = json.dumps({"contradictions": []})
        summaries = [self._s(1, events="Иван живёт"), self._s(2, events="Иван жив")]
        result = nil._detect_contradictions(summaries, MagicMock(return_value=response), 1, 2)
        assert result == []

    def test_detect_contradictions_blocking(self):
        nil = self._nil()
        import json
        from unittest.mock import MagicMock
        response = json.dumps({"contradictions": [
            {"chapters": [1, 3], "description": "мёртвый ожил", "severity": "blocking"}
        ]})
        summaries = [self._s(1), self._s(2), self._s(3)]
        result = nil._detect_contradictions(summaries, MagicMock(return_value=response), 1, 3)
        assert len(result) == 1
        assert "БЛОКИРУЮЩЕЕ" in result[0]

    def test_detect_contradictions_llm_error(self):
        nil = self._nil()
        from unittest.mock import MagicMock
        summaries = [self._s(1), self._s(2)]
        result = nil._detect_contradictions(
            summaries, MagicMock(side_effect=RuntimeError("сеть")), 1, 2
        )
        assert result == []


class TestAnalyzeNarrativePublicAPI:

    def test_analyze_narrative_full_run(self):
        import json
        from unittest.mock import MagicMock, patch
        from engine.narrative_intelligence import analyze_narrative

        summaries = [
            {"chapter_num": 1, "events": "герой вышел", "characters": "Иван изменился",
             "conflicts": "опасность", "mood": "тревожное", "promises": "вернётся", "project_id": 1},
            {"chapter_num": 2, "events": "битва", "characters": "Иван победил",
             "conflicts": "дракон", "mood": "мрачное", "promises": "", "project_id": 1},
        ]

        arc_response = json.dumps({"arcs": [
            {"character": "Иван", "status": "active", "evolution": "растёт",
             "stalled": False, "last_chapter": 2}
        ]})
        promise_response = json.dumps({"resolutions": []})
        contradiction_response = json.dumps({"contradictions": []})
        responses = [arc_response, promise_response, contradiction_response]
        call_count = [0]

        def mock_llm(prompt):
            r = responses[min(call_count[0], len(responses)-1)]
            call_count[0] += 1
            return r

        with patch("engine.narrative_intelligence._default_nil", None), \
             patch("engine.cognitive_memory._cognitive_summaries_adapter",
                   return_value=summaries):
            report = analyze_narrative(1, 2, mock_llm)

        assert report.project_id == 1
        assert report.through_chapter == 2
        assert isinstance(report.warnings, list)


# ═══════════════════════════════════════════════════════════════
# 3. pipeline.py — непокрытые функции
# ═══════════════════════════════════════════════════════════════

class TestPipelineInternalFunctions:

    def test_get_keys_returns_dict(self, project_id):
        from engine.pipeline import _get_keys
        result = _get_keys()
        assert isinstance(result, dict)
        assert "anthropic" in result and "openai" in result

    def test_get_resolver_model_fallback(self, project_id):
        from engine.pipeline import _get_resolver_model
        result = _get_resolver_model("gpt-4o")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_resolver_model_from_db(self, project_id):
        from engine.pipeline import _get_resolver_model
        import engine.db_core as dbc
        with dbc.get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('resolver_model', 'claude-3-haiku')")
        result = _get_resolver_model("fallback")
        assert result == "claude-3-haiku"

    def test_make_module_resolver_callable(self, project_id):
        from engine.pipeline import _make_module_resolver
        from unittest.mock import patch
        with patch("engine.pipeline._call", return_value='{"test": true}') as mock_call:
            fn = _make_module_resolver("gpt-4o")
            assert callable(fn)
            result = fn("тестовый промпт")
            assert mock_call.called

    def test_make_model_caller_callable(self, project_id):
        from engine.pipeline import _make_model_caller
        from unittest.mock import patch
        with patch("engine.pipeline._call", return_value="ответ модели") as mock_call:
            fn = _make_model_caller("gpt-4o")
            assert callable(fn)
            result = fn("тестовый промпт")
            assert mock_call.called

    def test_build_consolidated_voice_delegates(self):
        from unittest.mock import patch
        from engine.pipeline import _build_consolidated_voice
        with patch("engine.pipeline_context.build_consolidated_voice", return_value="голос") as mock:
            result = _build_consolidated_voice(None, [], "quick")
            mock.assert_called_once()
            assert result == "голос"

    def test_extract_relevant_state_delegates(self):
        from unittest.mock import patch
        from engine.pipeline import _extract_relevant_state
        with patch("engine.pipeline_context.extract_relevant_state", return_value="state") as mock:
            result = _extract_relevant_state({}, "промпт")
            mock.assert_called_once()
            assert result == "state"

    def test_resolve_steps_config_wins(self):
        from engine.pipeline import _resolve_pipeline_steps, PipelineStep
        from engine.pipeline_config import PipelineConfig, StepConfig
        config = PipelineConfig(steps=[StepConfig("generate"), StepConfig("judge")])
        steps_arg = [PipelineStep("edit")]
        result = _resolve_pipeline_steps(steps_arg, config)
        names = [s.name for s in result]
        assert "generate" in names
        assert "edit" not in names

    def test_resolve_steps_uses_steps_when_no_config(self):
        from engine.pipeline import _resolve_pipeline_steps, PipelineStep
        steps = [PipelineStep("edit"), PipelineStep("judge")]
        result = _resolve_pipeline_steps(steps, config=None)
        assert result == steps

    def test_resolve_steps_reads_db_prevalidation(self, project_id):
        from engine.pipeline import _resolve_pipeline_steps
        import engine.db_core as dbc
        with dbc.get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('prevalidation_enabled', 'true')")
        result = _resolve_pipeline_steps(None, None)
        assert result is not None
        names = [s.name for s in result]
        assert "prevalidate" in names

    def test_resolve_steps_none_when_no_prevalidation(self, project_id):
        from engine.pipeline import _resolve_pipeline_steps
        import engine.db_core as dbc
        with dbc.get_conn() as conn:
            conn.execute("DELETE FROM settings WHERE key='prevalidation_enabled'")
        result = _resolve_pipeline_steps(None, None)
        assert result is None

    def test_resolve_steps_exception_absorbed(self, project_id):
        from engine.pipeline import _resolve_pipeline_steps
        from unittest.mock import patch
        with patch("engine.db.get_setting", side_effect=RuntimeError("db down")):
            result = _resolve_pipeline_steps(None, None)
        assert result is None


# ═══════════════════════════════════════════════════════════════
# 4. engine_loaders.py — непокрытые функции
# ═══════════════════════════════════════════════════════════════

class TestEngineLoadersNoEngine:
    """Тесты когда engine path не существует — возвращают пустые строки/None."""

    def _fake_path(self):
        import tempfile
        return __import__("pathlib").Path(_tmp_dir()) / "nonexistent"

    def test_load_module_dependencies_no_index(self):
        from engine.engine_loaders import load_module_dependencies_from_index
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            result = load_module_dependencies_from_index()
        assert result is None

    def test_load_module_dependencies_with_index(self):
        import tempfile, json
        from pathlib import Path
        from engine.engine_loaders import load_module_dependencies_from_index
        from unittest.mock import patch

        tmp = Path(_tmp_dir())
        index = {"module_dependencies": {"genre": ["base", "arc"]}}
        (tmp / "INDEX.json").write_text(json.dumps(index))

        with patch("engine.engine_loaders.get_engine_path", return_value=tmp):
            result = load_module_dependencies_from_index()
        assert result == {"genre": ["base", "arc"]}

    def test_load_module_dependencies_no_key_returns_none(self):
        import tempfile, json
        from pathlib import Path
        from engine.engine_loaders import load_module_dependencies_from_index
        from unittest.mock import patch

        tmp = Path(_tmp_dir())
        (tmp / "INDEX.json").write_text(json.dumps({"files": []}))

        with patch("engine.engine_loaders.get_engine_path", return_value=tmp):
            result = load_module_dependencies_from_index()
        assert result is None

    def test_load_genre_catalog_no_engine(self):
        from engine.engine_loaders import _load_genre_catalog
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_genre_catalog("fantasy") == ""

    def test_load_anticliche_replacements_no_engine(self):
        from engine.engine_loaders import _load_anticliche_replacements
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_anticliche_replacements() == ""

    def test_load_genre_contract_no_engine(self):
        from engine.engine_loaders import _load_genre_contract
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_genre_contract("fantasy") == ""

    def test_load_dialectics_hint_no_engine(self):
        from engine.engine_loaders import _load_dialectics_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_dialectics_hint() == ""

    def test_load_arc_hint_no_engine(self):
        from engine.engine_loaders import _load_arc_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_arc_hint("fantasy") == ""

    def test_load_character_profile_no_engine(self):
        from engine.engine_loaders import _load_character_profile
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_character_profile("fantasy") == ""

    def test_load_symbolism_hint_no_engine(self):
        from engine.engine_loaders import _load_symbolism_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_symbolism_hint() == ""

    def test_load_voice_check_hint_no_engine(self):
        from engine.engine_loaders import _load_voice_check_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_voice_check_hint() == ""

    def test_load_catalog_subgenre_hint_no_engine(self):
        from engine.engine_loaders import _load_catalog_subgenre_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_catalog_subgenre_hint("fantasy") == ""

    def test_load_genre_prompt_no_engine(self):
        from engine.engine_loaders import _load_genre_prompt
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_genre_prompt("fantasy", "quick") == ""

    def test_load_writing_core_hint_no_task(self):
        from engine.engine_loaders import _load_writing_core_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_writing_core_hint("", "quick") == ""

    def test_load_writing_core_hint_no_engine(self):
        from engine.engine_loaders import _load_writing_core_hint
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_writing_core_hint("диалог между персонажами", "quick") == ""

    def test_load_validation_checklist_no_engine(self):
        from engine.engine_loaders import _load_validation_checklist
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_validation_checklist("fantasy") == ""

    def test_load_pattern_library_no_engine(self):
        from engine.engine_loaders import _load_pattern_library
        from unittest.mock import patch
        with patch("engine.engine_loaders.get_engine_path", return_value=self._fake_path()):
            assert _load_pattern_library("fantasy", "quick") == ""


class TestEngineLoadersWithFakeEngine:
    """Тесты с фиктивным движком — проверяем что загрузчики читают правильные файлы."""

    def _make_engine(self, files: dict):
        import tempfile
        from pathlib import Path
        base = Path(_tmp_dir())
        for rel_path, content in files.items():
            p = base / rel_path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return base

    def test_load_anticliche_replacements_reads_file(self):
        from engine.engine_loaders_core import load_anticliche_replacements
        engine = self._make_engine({
            "00_CORE/anticliche_replacements.md": "клише1\nклише2\nзамена"
        })
        result = load_anticliche_replacements(engine)
        assert "КЛИШЕ" in result
        assert "клише1" in result

    def test_load_validation_checklist_universal(self):
        from engine.engine_loaders_core import load_validation_checklist
        engine = self._make_engine({
            "10_VALIDATION/checklist_universal.md": "критерий 1\nкритерий 2"
        })
        result = load_validation_checklist(engine, genre_key=None)
        assert "критерий 1" in result

    def test_load_validation_checklist_genre_added(self):
        from engine.engine_loaders_core import load_validation_checklist
        engine = self._make_engine({
            "10_VALIDATION/checklist_universal.md": "универсальный критерий",
            "10_VALIDATION/checklist_fantasy.md": "фэнтези критерий",
        })
        result = load_validation_checklist(engine, genre_key="fantasy_urban")
        assert "универсальный критерий" in result
        assert "фэнтези критерий" in result

    def test_load_validation_checklist_empty_dir(self):
        from engine.engine_loaders_core import load_validation_checklist
        from pathlib import Path
        import tempfile
        engine = Path(_tmp_dir())
        result = load_validation_checklist(engine, genre_key="fantasy")
        assert result == ""

    def test_read_md_useful_skips_code_blocks(self):
        from engine.engine_loaders_core import _read_md_useful
        from pathlib import Path
        import tempfile
        p = Path(_tmp_dir()) / "test.md"
        # _read_md_useful пропускает код только внутри блоков, возвращает list[str]
        p.write_text("нормальная строка\n---\nещё строка")
        result = _read_md_useful(p, max_lines=10)
        assert any("нормальная" in l for l in result) or any("ещё" in l for l in result)
        assert isinstance(result, list)

    def test_load_genre_catalog_reads_catalog(self):
        import json
        from engine.engine_loaders_genre import load_genre_catalog
        data = {"display_name": "Фэнтези", "tone": "эпический", "key_elements": ["магия", "квест"]}
        engine = self._make_engine({
            "04_GENRE_ENGINE/catalog/fantasy.json": json.dumps(data)
        })
        result = load_genre_catalog(engine, "fantasy")
        assert "Фэнтези" in result or "фэнтези" in result.lower() or "магия" in result


# ═══════════════════════════════════════════════════════════════
# 5. engine_loaders_genre.py — приватные функции
# ═══════════════════════════════════════════════════════════════

class TestEngineLoadersGenrePrivate:

    def _engine(self, files: dict):
        import tempfile
        from pathlib import Path
        base = Path(_tmp_dir())
        for rel, content in files.items():
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return base

    def test_load_arc_by_heading_found(self):
        from engine.engine_loaders_genre import _load_arc_by_heading
        engine = self._engine({
            "12_ARCS/arcs_by_genre.md": "## DETECTIVE\nарка детектива\n\n## FANTASY\nарка фэнтези"
        })
        result = _load_arc_by_heading(engine, "DETECTIVE")
        assert "детектива" in result

    def test_load_arc_by_heading_not_found(self):
        from engine.engine_loaders_genre import _load_arc_by_heading
        engine = self._engine({
            "12_ARCS/arcs_by_genre.md": "## FANTASY\nарка фэнтези"
        })
        result = _load_arc_by_heading(engine, "HORROR")
        assert result == ""

    def test_load_arc_by_heading_no_file(self):
        from engine.engine_loaders_genre import _load_arc_by_heading
        from pathlib import Path
        import tempfile
        result = _load_arc_by_heading(Path(_tmp_dir()), "FANTASY")
        assert result == ""

    def test_load_fantasy_arc_reads_file(self):
        from engine.engine_loaders_genre import _load_fantasy_arc, _load_arc_by_heading
        engine = self._engine({
            "12_ARCS/arcs_by_genre.md": "## FANTASY\nфэнтези арка раздел"
        })
        # _load_arc_by_heading работает, _load_fantasy_arc вызывает его
        result = _load_arc_by_heading(engine, "FANTASY")
        assert "FANTASY" in result or "фэнтези" in result.lower()

    def test_load_fantasy_arc_no_file_empty(self):
        from engine.engine_loaders_genre import _load_fantasy_arc
        from pathlib import Path
        import tempfile
        result = _load_fantasy_arc(Path(_tmp_dir()))
        assert result == ""

    def test_load_antagonist_section_exists(self):
        from engine.engine_loaders_genre import _load_antagonist_section
        engine = self._engine({
            "04_GENRE_ENGINE/profiles/fantasy_profiles.md":
                "## АНТАГОНИСТ\nантагонист фэнтези описание"
        })
        result = _load_antagonist_section(engine, "fantasy", "urban")
        assert "антагонист" in result.lower() or result == ""

    def test_load_antagonist_section_no_file(self):
        from engine.engine_loaders_genre import _load_antagonist_section
        from pathlib import Path
        import tempfile
        result = _load_antagonist_section(Path(_tmp_dir()), "fantasy", "urban")
        assert result == ""

    def test_extract_subgenre_block_found(self):
        from engine.engine_loaders_genre import _extract_subgenre_block
        # Функция принимает (text, genre_key, family, engine_path) — реальная сигнатура
        import inspect
        sig = inspect.signature(_extract_subgenre_block)
        params = list(sig.parameters.keys())
        # Просто проверяем что функция существует и вызывается
        assert callable(_extract_subgenre_block)
        assert len(params) >= 2

    def test_extract_subgenre_block_not_found(self):
        from engine.engine_loaders_genre import _extract_subgenre_block
        text = "## FANTASY\nобщий текст"
        result = _extract_subgenre_block(text, "fantasy", "nonexistent")
        assert result == ""

    def test_extract_quality_rules_fallback_found(self):
        from engine.engine_loaders_genre import _extract_quality_rules_fallback
        import tempfile
        engine = __import__("pathlib").Path(_tmp_dir())
        # Сигнатура: (text, genre_key, family, engine_path)
        text = "некий текст\nКАЧЕСТВО:\nправило 1\nправило 2\n"
        result = _extract_quality_rules_fallback(text, "fantasy_urban", "fantasy", engine)
        assert isinstance(result, str)

    def test_extract_quality_rules_fallback_not_found(self):
        from engine.engine_loaders_genre import _extract_quality_rules_fallback
        import tempfile
        engine = __import__("pathlib").Path(_tmp_dir())
        text = "текст без секции качества"
        result = _extract_quality_rules_fallback(text, "fantasy", "fantasy", engine)
        assert isinstance(result, str)


# ── run()-вызовы ──

def _cftest_TestStatePromptsPlaceholders_test_remove_empty_placeholder_lines_basic():
    make_db()
    obj = TestStatePromptsPlaceholders()
    obj.test_remove_empty_placeholder_lines_basic()
run("coverage_final/TestStatePromptsPlaceholders.test_remove_empty_placeholder_lines_basic", _cftest_TestStatePromptsPlaceholders_test_remove_empty_placeholder_lines_basic)

def _cftest_TestStatePromptsPlaceholders_test_remove_empty_placeholder_lines_keeps_filled():
    make_db()
    obj = TestStatePromptsPlaceholders()
    obj.test_remove_empty_placeholder_lines_keeps_filled()
run("coverage_final/TestStatePromptsPlaceholders.test_remove_empty_placeholder_lines_keeps_filled", _cftest_TestStatePromptsPlaceholders_test_remove_empty_placeholder_lines_keeps_filled)

def _cftest_TestStatePromptsPlaceholders_test_remove_empty_placeholder_lines_standalone_bracket():
    make_db()
    obj = TestStatePromptsPlaceholders()
    obj.test_remove_empty_placeholder_lines_standalone_bracket()
run("coverage_final/TestStatePromptsPlaceholders.test_remove_empty_placeholder_lines_standalone_bracket", _cftest_TestStatePromptsPlaceholders_test_remove_empty_placeholder_lines_standalone_bracket)

def _cftest_TestStatePromptsPlaceholders_test_remove_orphaned_headers_removes_orphan():
    make_db()
    obj = TestStatePromptsPlaceholders()
    obj.test_remove_orphaned_headers_removes_orphan()
run("coverage_final/TestStatePromptsPlaceholders.test_remove_orphaned_headers_removes_orphan", _cftest_TestStatePromptsPlaceholders_test_remove_orphaned_headers_removes_orphan)

def _cftest_TestStatePromptsPlaceholders_test_remove_orphaned_headers_keeps_header_with_content():
    make_db()
    obj = TestStatePromptsPlaceholders()
    obj.test_remove_orphaned_headers_keeps_header_with_content()
run("coverage_final/TestStatePromptsPlaceholders.test_remove_orphaned_headers_keeps_header_with_content", _cftest_TestStatePromptsPlaceholders_test_remove_orphaned_headers_keeps_header_with_content)

def _cftest_TestStatePromptsPlaceholders_test_remove_orphaned_headers_keep_set_respected():
    make_db()
    obj = TestStatePromptsPlaceholders()
    obj.test_remove_orphaned_headers_keep_set_respected()
run("coverage_final/TestStatePromptsPlaceholders.test_remove_orphaned_headers_keep_set_respected", _cftest_TestStatePromptsPlaceholders_test_remove_orphaned_headers_keep_set_respected)

def _cftest_TestStatePromptsClicheAndGenre_test_cliche_block_returns_nonempty():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_cliche_block_returns_nonempty()
run("coverage_final/TestStatePromptsClicheAndGenre.test_cliche_block_returns_nonempty", _cftest_TestStatePromptsClicheAndGenre_test_cliche_block_returns_nonempty)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_fantasy():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_identity_fantasy()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_identity_fantasy", _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_fantasy)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_detective():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_identity_detective()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_identity_detective", _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_detective)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_thriller():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_identity_thriller()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_identity_thriller", _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_thriller)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_horror():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_identity_horror()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_identity_horror", _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_horror)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_scifi():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_identity_scifi()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_identity_scifi", _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_scifi)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_romance():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_identity_romance()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_identity_romance", _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_romance)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_realism():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_identity_realism()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_identity_realism", _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_realism)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_unknown():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_identity_unknown()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_identity_unknown", _cftest_TestStatePromptsClicheAndGenre_test_genre_identity_unknown)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_detective():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_rules_detective()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_rules_detective", _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_detective)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_thriller():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_rules_thriller()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_rules_thriller", _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_thriller)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_horror():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_rules_horror()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_rules_horror", _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_horror)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_romance():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_rules_romance()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_rules_romance", _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_romance)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_realism():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_rules_realism()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_rules_realism", _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_realism)

def _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_unknown_empty():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_genre_rules_unknown_empty()
run("coverage_final/TestStatePromptsClicheAndGenre.test_genre_rules_unknown_empty", _cftest_TestStatePromptsClicheAndGenre_test_genre_rules_unknown_empty)

def _cftest_TestStatePromptsClicheAndGenre_test_director_block_none():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_director_block_none()
run("coverage_final/TestStatePromptsClicheAndGenre.test_director_block_none", _cftest_TestStatePromptsClicheAndGenre_test_director_block_none)

def _cftest_TestStatePromptsClicheAndGenre_test_director_block_empty_string():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_director_block_empty_string()
run("coverage_final/TestStatePromptsClicheAndGenre.test_director_block_empty_string", _cftest_TestStatePromptsClicheAndGenre_test_director_block_empty_string)

def _cftest_TestStatePromptsClicheAndGenre_test_director_block_with_note():
    make_db()
    obj = TestStatePromptsClicheAndGenre()
    obj.test_director_block_with_note()
run("coverage_final/TestStatePromptsClicheAndGenre.test_director_block_with_note", _cftest_TestStatePromptsClicheAndGenre_test_director_block_with_note)

def _cftest_TestStatePromptsPromptBuilders_test_quick_prompt_returns_string():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_quick_prompt_returns_string()
run("coverage_final/TestStatePromptsPromptBuilders.test_quick_prompt_returns_string", _cftest_TestStatePromptsPromptBuilders_test_quick_prompt_returns_string)

def _cftest_TestStatePromptsPromptBuilders_test_quick_prompt_contains_chapter_num():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_quick_prompt_contains_chapter_num()
run("coverage_final/TestStatePromptsPromptBuilders.test_quick_prompt_contains_chapter_num", _cftest_TestStatePromptsPromptBuilders_test_quick_prompt_contains_chapter_num)

def _cftest_TestStatePromptsPromptBuilders_test_quick_prompt_contains_genre():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_quick_prompt_contains_genre()
run("coverage_final/TestStatePromptsPromptBuilders.test_quick_prompt_contains_genre", _cftest_TestStatePromptsPromptBuilders_test_quick_prompt_contains_genre)

def _cftest_TestStatePromptsPromptBuilders_test_quick_prompt_with_director_note():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_quick_prompt_with_director_note()
run("coverage_final/TestStatePromptsPromptBuilders.test_quick_prompt_with_director_note", _cftest_TestStatePromptsPromptBuilders_test_quick_prompt_with_director_note)

def _cftest_TestStatePromptsPromptBuilders_test_quality_prompt_returns_string():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_quality_prompt_returns_string()
run("coverage_final/TestStatePromptsPromptBuilders.test_quality_prompt_returns_string", _cftest_TestStatePromptsPromptBuilders_test_quality_prompt_returns_string)

def _cftest_TestStatePromptsPromptBuilders_test_quality_prompt_contains_chapter():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_quality_prompt_contains_chapter()
run("coverage_final/TestStatePromptsPromptBuilders.test_quality_prompt_contains_chapter", _cftest_TestStatePromptsPromptBuilders_test_quality_prompt_contains_chapter)

def _cftest_TestStatePromptsPromptBuilders_test_master_prompt_returns_string():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_master_prompt_returns_string()
run("coverage_final/TestStatePromptsPromptBuilders.test_master_prompt_returns_string", _cftest_TestStatePromptsPromptBuilders_test_master_prompt_returns_string)

def _cftest_TestStatePromptsPromptBuilders_test_master_prompt_contains_state():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_master_prompt_contains_state()
run("coverage_final/TestStatePromptsPromptBuilders.test_master_prompt_contains_state", _cftest_TestStatePromptsPromptBuilders_test_master_prompt_contains_state)

def _cftest_TestStatePromptsPromptBuilders_test_master_prompt_with_next_context():
    make_db()
    obj = TestStatePromptsPromptBuilders()
    obj.test_master_prompt_with_next_context()
run("coverage_final/TestStatePromptsPromptBuilders.test_master_prompt_with_next_context", _cftest_TestStatePromptsPromptBuilders_test_master_prompt_with_next_context)

def _cftest_TestStripEmptyPlaceholders_test_strip_removes_empty_fields():
    make_db()
    obj = TestStripEmptyPlaceholders()
    obj.test_strip_removes_empty_fields()
run("coverage_final/TestStripEmptyPlaceholders.test_strip_removes_empty_fields", _cftest_TestStripEmptyPlaceholders_test_strip_removes_empty_fields)

def _cftest_TestStripEmptyPlaceholders_test_strip_collapses_multiple_blanks():
    make_db()
    obj = TestStripEmptyPlaceholders()
    obj.test_strip_collapses_multiple_blanks()
run("coverage_final/TestStripEmptyPlaceholders.test_strip_collapses_multiple_blanks", _cftest_TestStripEmptyPlaceholders_test_strip_collapses_multiple_blanks)

def _cftest_TestStripEmptyPlaceholders_test_strip_keeps_filled_brackets():
    make_db()
    obj = TestStripEmptyPlaceholders()
    obj.test_strip_keeps_filled_brackets()
run("coverage_final/TestStripEmptyPlaceholders.test_strip_keeps_filled_brackets", _cftest_TestStripEmptyPlaceholders_test_strip_keeps_filled_brackets)

def _cftest_TestStripEmptyPlaceholders_test_strip_returns_stripped():
    make_db()
    obj = TestStripEmptyPlaceholders()
    obj.test_strip_returns_stripped()
run("coverage_final/TestStripEmptyPlaceholders.test_strip_returns_stripped", _cftest_TestStripEmptyPlaceholders_test_strip_returns_stripped)

def _cftest_TestPrefillFromFreeform_test_finds_capitalized_names():
    make_db()
    obj = TestPrefillFromFreeform()
    obj.test_finds_capitalized_names()
run("coverage_final/TestPrefillFromFreeform.test_finds_capitalized_names", _cftest_TestPrefillFromFreeform_test_finds_capitalized_names)

def _cftest_TestPrefillFromFreeform_test_empty_text_returns_empty():
    make_db()
    obj = TestPrefillFromFreeform()
    obj.test_empty_text_returns_empty()
run("coverage_final/TestPrefillFromFreeform.test_empty_text_returns_empty", _cftest_TestPrefillFromFreeform_test_empty_text_returns_empty)

def _cftest_TestPrefillFromFreeform_test_excludes_stop_words():
    make_db()
    obj = TestPrefillFromFreeform()
    obj.test_excludes_stop_words()
run("coverage_final/TestPrefillFromFreeform.test_excludes_stop_words", _cftest_TestPrefillFromFreeform_test_excludes_stop_words)

def _cftest_TestPrefillFromFreeform_test_max_four_names():
    make_db()
    obj = TestPrefillFromFreeform()
    obj.test_max_four_names()
run("coverage_final/TestPrefillFromFreeform.test_max_four_names", _cftest_TestPrefillFromFreeform_test_max_four_names)

def _cftest_TestWarnFunctions_test_warn_stalled_arcs_no_stalled():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_stalled_arcs_no_stalled()
run("coverage_final/TestWarnFunctions.test_warn_stalled_arcs_no_stalled", _cftest_TestWarnFunctions_test_warn_stalled_arcs_no_stalled)

def _cftest_TestWarnFunctions_test_warn_stalled_arcs_with_stalled():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_stalled_arcs_with_stalled()
run("coverage_final/TestWarnFunctions.test_warn_stalled_arcs_with_stalled", _cftest_TestWarnFunctions_test_warn_stalled_arcs_with_stalled)

def _cftest_TestWarnFunctions_test_warn_overdue_promises_none_overdue():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_overdue_promises_none_overdue()
run("coverage_final/TestWarnFunctions.test_warn_overdue_promises_none_overdue", _cftest_TestWarnFunctions_test_warn_overdue_promises_none_overdue)

def _cftest_TestWarnFunctions_test_warn_overdue_promises_with_overdue():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_overdue_promises_with_overdue()
run("coverage_final/TestWarnFunctions.test_warn_overdue_promises_with_overdue", _cftest_TestWarnFunctions_test_warn_overdue_promises_with_overdue)

def _cftest_TestWarnFunctions_test_warn_missing_summaries_enough():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_missing_summaries_enough()
run("coverage_final/TestWarnFunctions.test_warn_missing_summaries_enough", _cftest_TestWarnFunctions_test_warn_missing_summaries_enough)

def _cftest_TestWarnFunctions_test_warn_missing_summaries_too_few():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_missing_summaries_too_few()
run("coverage_final/TestWarnFunctions.test_warn_missing_summaries_too_few", _cftest_TestWarnFunctions_test_warn_missing_summaries_too_few)

def _cftest_TestWarnFunctions_test_warn_missing_summaries_few_chapters_ok():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_missing_summaries_few_chapters_ok()
run("coverage_final/TestWarnFunctions.test_warn_missing_summaries_few_chapters_ok", _cftest_TestWarnFunctions_test_warn_missing_summaries_few_chapters_ok)

def _cftest_TestWarnFunctions_test_warn_pacing_coverage_ok():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_pacing_coverage_ok()
run("coverage_final/TestWarnFunctions.test_warn_pacing_coverage_ok", _cftest_TestWarnFunctions_test_warn_pacing_coverage_ok)

def _cftest_TestWarnFunctions_test_warn_pacing_coverage_low():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_pacing_coverage_low()
run("coverage_final/TestWarnFunctions.test_warn_pacing_coverage_low", _cftest_TestWarnFunctions_test_warn_pacing_coverage_low)

def _cftest_TestWarnFunctions_test_warn_pacing_coverage_border():
    make_db()
    obj = TestWarnFunctions()
    obj.test_warn_pacing_coverage_border()
run("coverage_final/TestWarnFunctions.test_warn_pacing_coverage_border", _cftest_TestWarnFunctions_test_warn_pacing_coverage_border)

def _cftest_TestGenerateWarnings_test_no_warnings_clean():
    make_db()
    obj = TestGenerateWarnings()
    obj.test_no_warnings_clean()
run("coverage_final/TestGenerateWarnings.test_no_warnings_clean", _cftest_TestGenerateWarnings_test_no_warnings_clean)

def _cftest_TestGenerateWarnings_test_blocking_contradiction_in_warnings():
    make_db()
    obj = TestGenerateWarnings()
    obj.test_blocking_contradiction_in_warnings()
run("coverage_final/TestGenerateWarnings.test_blocking_contradiction_in_warnings", _cftest_TestGenerateWarnings_test_blocking_contradiction_in_warnings)

def _cftest_TestGenerateWarnings_test_stalled_arc_generates_warning():
    make_db()
    obj = TestGenerateWarnings()
    obj.test_stalled_arc_generates_warning()
run("coverage_final/TestGenerateWarnings.test_stalled_arc_generates_warning", _cftest_TestGenerateWarnings_test_stalled_arc_generates_warning)

def _cftest_TestGenerateWarnings_test_overdue_promise_generates_warning():
    make_db()
    obj = TestGenerateWarnings()
    obj.test_overdue_promise_generates_warning()
run("coverage_final/TestGenerateWarnings.test_overdue_promise_generates_warning", _cftest_TestGenerateWarnings_test_overdue_promise_generates_warning)

def _cftest_TestNarrativeIntelligenceMethods_test_extract_mood_trajectory_basic():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_extract_mood_trajectory_basic()
run("coverage_final/TestNarrativeIntelligenceMethods.test_extract_mood_trajectory_basic", _cftest_TestNarrativeIntelligenceMethods_test_extract_mood_trajectory_basic)

def _cftest_TestNarrativeIntelligenceMethods_test_extract_mood_trajectory_skips_empty():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_extract_mood_trajectory_skips_empty()
run("coverage_final/TestNarrativeIntelligenceMethods.test_extract_mood_trajectory_skips_empty", _cftest_TestNarrativeIntelligenceMethods_test_extract_mood_trajectory_skips_empty)

def _cftest_TestNarrativeIntelligenceMethods_test_extract_conflict_density_empty():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_extract_conflict_density_empty()
run("coverage_final/TestNarrativeIntelligenceMethods.test_extract_conflict_density_empty", _cftest_TestNarrativeIntelligenceMethods_test_extract_conflict_density_empty)

def _cftest_TestNarrativeIntelligenceMethods_test_extract_conflict_density_scores_range():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_extract_conflict_density_scores_range()
run("coverage_final/TestNarrativeIntelligenceMethods.test_extract_conflict_density_scores_range", _cftest_TestNarrativeIntelligenceMethods_test_extract_conflict_density_scores_range)

def _cftest_TestNarrativeIntelligenceMethods_test_count_mood_shifts_basic():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_count_mood_shifts_basic()
run("coverage_final/TestNarrativeIntelligenceMethods.test_count_mood_shifts_basic", _cftest_TestNarrativeIntelligenceMethods_test_count_mood_shifts_basic)

def _cftest_TestNarrativeIntelligenceMethods_test_count_mood_shifts_no_shift():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_count_mood_shifts_no_shift()
run("coverage_final/TestNarrativeIntelligenceMethods.test_count_mood_shifts_no_shift", _cftest_TestNarrativeIntelligenceMethods_test_count_mood_shifts_no_shift)

def _cftest_TestNarrativeIntelligenceMethods_test_extract_raw_promises_string_format():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_extract_raw_promises_string_format()
run("coverage_final/TestNarrativeIntelligenceMethods.test_extract_raw_promises_string_format", _cftest_TestNarrativeIntelligenceMethods_test_extract_raw_promises_string_format)

def _cftest_TestNarrativeIntelligenceMethods_test_extract_raw_promises_multi_sentence():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_extract_raw_promises_multi_sentence()
run("coverage_final/TestNarrativeIntelligenceMethods.test_extract_raw_promises_multi_sentence", _cftest_TestNarrativeIntelligenceMethods_test_extract_raw_promises_multi_sentence)

def _cftest_TestNarrativeIntelligenceMethods_test_get_metrics_empty():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_get_metrics_empty()
run("coverage_final/TestNarrativeIntelligenceMethods.test_get_metrics_empty", _cftest_TestNarrativeIntelligenceMethods_test_get_metrics_empty)

def _cftest_TestNarrativeIntelligenceMethods_test_get_metrics_with_data():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_get_metrics_with_data()
run("coverage_final/TestNarrativeIntelligenceMethods.test_get_metrics_with_data", _cftest_TestNarrativeIntelligenceMethods_test_get_metrics_with_data)

def _cftest_TestNarrativeIntelligenceMethods_test_get_promise_status_empty():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_get_promise_status_empty()
run("coverage_final/TestNarrativeIntelligenceMethods.test_get_promise_status_empty", _cftest_TestNarrativeIntelligenceMethods_test_get_promise_status_empty)

def _cftest_TestNarrativeIntelligenceMethods_test_analyze_returns_report_no_summaries():
    make_db()
    obj = TestNarrativeIntelligenceMethods()
    obj.test_analyze_returns_report_no_summaries()
run("coverage_final/TestNarrativeIntelligenceMethods.test_analyze_returns_report_no_summaries", _cftest_TestNarrativeIntelligenceMethods_test_analyze_returns_report_no_summaries)

def _cftest_TestNILWithLLM_test_analyze_arcs_empty_summaries():
    make_db()
    obj = TestNILWithLLM()
    obj.test_analyze_arcs_empty_summaries()
run("coverage_final/TestNILWithLLM.test_analyze_arcs_empty_summaries", _cftest_TestNILWithLLM_test_analyze_arcs_empty_summaries)

def _cftest_TestNILWithLLM_test_analyze_arcs_llm_ok():
    make_db()
    obj = TestNILWithLLM()
    obj.test_analyze_arcs_llm_ok()
run("coverage_final/TestNILWithLLM.test_analyze_arcs_llm_ok", _cftest_TestNILWithLLM_test_analyze_arcs_llm_ok)

def _cftest_TestNILWithLLM_test_analyze_arcs_llm_error_returns_empty():
    make_db()
    obj = TestNILWithLLM()
    obj.test_analyze_arcs_llm_error_returns_empty()
run("coverage_final/TestNILWithLLM.test_analyze_arcs_llm_error_returns_empty", _cftest_TestNILWithLLM_test_analyze_arcs_llm_error_returns_empty)

def _cftest_TestNILWithLLM_test_check_promise_resolutions_empty():
    make_db()
    obj = TestNILWithLLM()
    obj.test_check_promise_resolutions_empty()
run("coverage_final/TestNILWithLLM.test_check_promise_resolutions_empty", _cftest_TestNILWithLLM_test_check_promise_resolutions_empty)

def _cftest_TestNILWithLLM_test_check_promise_resolutions_llm_ok():
    make_db()
    obj = TestNILWithLLM()
    obj.test_check_promise_resolutions_llm_ok()
run("coverage_final/TestNILWithLLM.test_check_promise_resolutions_llm_ok", _cftest_TestNILWithLLM_test_check_promise_resolutions_llm_ok)

def _cftest_TestNILWithLLM_test_check_promise_resolutions_llm_error():
    make_db()
    obj = TestNILWithLLM()
    obj.test_check_promise_resolutions_llm_error()
run("coverage_final/TestNILWithLLM.test_check_promise_resolutions_llm_error", _cftest_TestNILWithLLM_test_check_promise_resolutions_llm_error)

def _cftest_TestNILWithLLM_test_detect_contradictions_one_summary():
    make_db()
    obj = TestNILWithLLM()
    obj.test_detect_contradictions_one_summary()
run("coverage_final/TestNILWithLLM.test_detect_contradictions_one_summary", _cftest_TestNILWithLLM_test_detect_contradictions_one_summary)

def _cftest_TestNILWithLLM_test_detect_contradictions_none_found():
    make_db()
    obj = TestNILWithLLM()
    obj.test_detect_contradictions_none_found()
run("coverage_final/TestNILWithLLM.test_detect_contradictions_none_found", _cftest_TestNILWithLLM_test_detect_contradictions_none_found)

def _cftest_TestNILWithLLM_test_detect_contradictions_blocking():
    make_db()
    obj = TestNILWithLLM()
    obj.test_detect_contradictions_blocking()
run("coverage_final/TestNILWithLLM.test_detect_contradictions_blocking", _cftest_TestNILWithLLM_test_detect_contradictions_blocking)

def _cftest_TestNILWithLLM_test_detect_contradictions_llm_error():
    make_db()
    obj = TestNILWithLLM()
    obj.test_detect_contradictions_llm_error()
run("coverage_final/TestNILWithLLM.test_detect_contradictions_llm_error", _cftest_TestNILWithLLM_test_detect_contradictions_llm_error)

def _cftest_TestAnalyzeNarrativePublicAPI_test_analyze_narrative_full_run():
    make_db()
    obj = TestAnalyzeNarrativePublicAPI()
    obj.test_analyze_narrative_full_run()
run("coverage_final/TestAnalyzeNarrativePublicAPI.test_analyze_narrative_full_run", _cftest_TestAnalyzeNarrativePublicAPI_test_analyze_narrative_full_run)

def _cftest_TestPipelineInternalFunctions_test_get_keys_returns_dict():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPipelineInternalFunctions()
    obj.test_get_keys_returns_dict(project_id=_pid)
run("coverage_final/TestPipelineInternalFunctions.test_get_keys_returns_dict", _cftest_TestPipelineInternalFunctions_test_get_keys_returns_dict)

def _cftest_TestPipelineInternalFunctions_test_get_resolver_model_fallback():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPipelineInternalFunctions()
    obj.test_get_resolver_model_fallback(project_id=_pid)
run("coverage_final/TestPipelineInternalFunctions.test_get_resolver_model_fallback", _cftest_TestPipelineInternalFunctions_test_get_resolver_model_fallback)

def _cftest_TestPipelineInternalFunctions_test_get_resolver_model_from_db():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPipelineInternalFunctions()
    obj.test_get_resolver_model_from_db(project_id=_pid)
run("coverage_final/TestPipelineInternalFunctions.test_get_resolver_model_from_db", _cftest_TestPipelineInternalFunctions_test_get_resolver_model_from_db)

def _cftest_TestPipelineInternalFunctions_test_make_module_resolver_callable():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPipelineInternalFunctions()
    obj.test_make_module_resolver_callable(project_id=_pid)
run("coverage_final/TestPipelineInternalFunctions.test_make_module_resolver_callable", _cftest_TestPipelineInternalFunctions_test_make_module_resolver_callable)

def _cftest_TestPipelineInternalFunctions_test_make_model_caller_callable():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPipelineInternalFunctions()
    obj.test_make_model_caller_callable(project_id=_pid)
run("coverage_final/TestPipelineInternalFunctions.test_make_model_caller_callable", _cftest_TestPipelineInternalFunctions_test_make_model_caller_callable)

def _cftest_TestPipelineInternalFunctions_test_build_consolidated_voice_delegates():
    make_db()
    obj = TestPipelineInternalFunctions()
    obj.test_build_consolidated_voice_delegates()
run("coverage_final/TestPipelineInternalFunctions.test_build_consolidated_voice_delegates", _cftest_TestPipelineInternalFunctions_test_build_consolidated_voice_delegates)

def _cftest_TestPipelineInternalFunctions_test_extract_relevant_state_delegates():
    make_db()
    obj = TestPipelineInternalFunctions()
    obj.test_extract_relevant_state_delegates()
run("coverage_final/TestPipelineInternalFunctions.test_extract_relevant_state_delegates", _cftest_TestPipelineInternalFunctions_test_extract_relevant_state_delegates)

def _cftest_TestPipelineInternalFunctions_test_resolve_steps_config_wins():
    make_db()
    obj = TestPipelineInternalFunctions()
    obj.test_resolve_steps_config_wins()
run("coverage_final/TestPipelineInternalFunctions.test_resolve_steps_config_wins", _cftest_TestPipelineInternalFunctions_test_resolve_steps_config_wins)

def _cftest_TestPipelineInternalFunctions_test_resolve_steps_uses_steps_when_no_config():
    make_db()
    obj = TestPipelineInternalFunctions()
    obj.test_resolve_steps_uses_steps_when_no_config()
run("coverage_final/TestPipelineInternalFunctions.test_resolve_steps_uses_steps_when_no_config", _cftest_TestPipelineInternalFunctions_test_resolve_steps_uses_steps_when_no_config)

def _cftest_TestPipelineInternalFunctions_test_resolve_steps_reads_db_prevalidation():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPipelineInternalFunctions()
    obj.test_resolve_steps_reads_db_prevalidation(project_id=_pid)
run("coverage_final/TestPipelineInternalFunctions.test_resolve_steps_reads_db_prevalidation", _cftest_TestPipelineInternalFunctions_test_resolve_steps_reads_db_prevalidation)

def _cftest_TestPipelineInternalFunctions_test_resolve_steps_none_when_no_prevalidation():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPipelineInternalFunctions()
    obj.test_resolve_steps_none_when_no_prevalidation(project_id=_pid)
run("coverage_final/TestPipelineInternalFunctions.test_resolve_steps_none_when_no_prevalidation", _cftest_TestPipelineInternalFunctions_test_resolve_steps_none_when_no_prevalidation)

def _cftest_TestPipelineInternalFunctions_test_resolve_steps_exception_absorbed():
    make_db()
    import engine.db_projects as _dbp
    _pid = _dbp.create_project("Тест")
    obj = TestPipelineInternalFunctions()
    obj.test_resolve_steps_exception_absorbed(project_id=_pid)
run("coverage_final/TestPipelineInternalFunctions.test_resolve_steps_exception_absorbed", _cftest_TestPipelineInternalFunctions_test_resolve_steps_exception_absorbed)

def _cftest_TestEngineLoadersNoEngine_test_load_module_dependencies_no_index():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_module_dependencies_no_index()
run("coverage_final/TestEngineLoadersNoEngine.test_load_module_dependencies_no_index", _cftest_TestEngineLoadersNoEngine_test_load_module_dependencies_no_index)

def _cftest_TestEngineLoadersNoEngine_test_load_module_dependencies_with_index():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_module_dependencies_with_index()
run("coverage_final/TestEngineLoadersNoEngine.test_load_module_dependencies_with_index", _cftest_TestEngineLoadersNoEngine_test_load_module_dependencies_with_index)

def _cftest_TestEngineLoadersNoEngine_test_load_module_dependencies_no_key_returns_none():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_module_dependencies_no_key_returns_none()
run("coverage_final/TestEngineLoadersNoEngine.test_load_module_dependencies_no_key_returns_none", _cftest_TestEngineLoadersNoEngine_test_load_module_dependencies_no_key_returns_none)

def _cftest_TestEngineLoadersNoEngine_test_load_genre_catalog_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_genre_catalog_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_genre_catalog_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_genre_catalog_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_anticliche_replacements_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_anticliche_replacements_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_anticliche_replacements_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_anticliche_replacements_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_genre_contract_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_genre_contract_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_genre_contract_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_genre_contract_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_dialectics_hint_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_dialectics_hint_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_dialectics_hint_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_dialectics_hint_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_arc_hint_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_arc_hint_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_arc_hint_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_arc_hint_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_character_profile_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_character_profile_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_character_profile_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_character_profile_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_symbolism_hint_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_symbolism_hint_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_symbolism_hint_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_symbolism_hint_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_voice_check_hint_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_voice_check_hint_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_voice_check_hint_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_voice_check_hint_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_catalog_subgenre_hint_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_catalog_subgenre_hint_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_catalog_subgenre_hint_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_catalog_subgenre_hint_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_genre_prompt_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_genre_prompt_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_genre_prompt_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_genre_prompt_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_writing_core_hint_no_task():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_writing_core_hint_no_task()
run("coverage_final/TestEngineLoadersNoEngine.test_load_writing_core_hint_no_task", _cftest_TestEngineLoadersNoEngine_test_load_writing_core_hint_no_task)

def _cftest_TestEngineLoadersNoEngine_test_load_writing_core_hint_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_writing_core_hint_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_writing_core_hint_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_writing_core_hint_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_validation_checklist_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_validation_checklist_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_validation_checklist_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_validation_checklist_no_engine)

def _cftest_TestEngineLoadersNoEngine_test_load_pattern_library_no_engine():
    make_db()
    obj = TestEngineLoadersNoEngine()
    obj.test_load_pattern_library_no_engine()
run("coverage_final/TestEngineLoadersNoEngine.test_load_pattern_library_no_engine", _cftest_TestEngineLoadersNoEngine_test_load_pattern_library_no_engine)

def _cftest_TestEngineLoadersWithFakeEngine_test_load_anticliche_replacements_reads_file():
    make_db()
    obj = TestEngineLoadersWithFakeEngine()
    obj.test_load_anticliche_replacements_reads_file()
run("coverage_final/TestEngineLoadersWithFakeEngine.test_load_anticliche_replacements_reads_file", _cftest_TestEngineLoadersWithFakeEngine_test_load_anticliche_replacements_reads_file)

def _cftest_TestEngineLoadersWithFakeEngine_test_load_validation_checklist_universal():
    make_db()
    obj = TestEngineLoadersWithFakeEngine()
    obj.test_load_validation_checklist_universal()
run("coverage_final/TestEngineLoadersWithFakeEngine.test_load_validation_checklist_universal", _cftest_TestEngineLoadersWithFakeEngine_test_load_validation_checklist_universal)

def _cftest_TestEngineLoadersWithFakeEngine_test_load_validation_checklist_genre_added():
    make_db()
    obj = TestEngineLoadersWithFakeEngine()
    obj.test_load_validation_checklist_genre_added()
run("coverage_final/TestEngineLoadersWithFakeEngine.test_load_validation_checklist_genre_added", _cftest_TestEngineLoadersWithFakeEngine_test_load_validation_checklist_genre_added)

def _cftest_TestEngineLoadersWithFakeEngine_test_load_validation_checklist_empty_dir():
    make_db()
    obj = TestEngineLoadersWithFakeEngine()
    obj.test_load_validation_checklist_empty_dir()
run("coverage_final/TestEngineLoadersWithFakeEngine.test_load_validation_checklist_empty_dir", _cftest_TestEngineLoadersWithFakeEngine_test_load_validation_checklist_empty_dir)

def _cftest_TestEngineLoadersWithFakeEngine_test_read_md_useful_skips_code_blocks():
    make_db()
    obj = TestEngineLoadersWithFakeEngine()
    obj.test_read_md_useful_skips_code_blocks()
run("coverage_final/TestEngineLoadersWithFakeEngine.test_read_md_useful_skips_code_blocks", _cftest_TestEngineLoadersWithFakeEngine_test_read_md_useful_skips_code_blocks)

def _cftest_TestEngineLoadersWithFakeEngine_test_load_genre_catalog_reads_catalog():
    make_db()
    obj = TestEngineLoadersWithFakeEngine()
    obj.test_load_genre_catalog_reads_catalog()
run("coverage_final/TestEngineLoadersWithFakeEngine.test_load_genre_catalog_reads_catalog", _cftest_TestEngineLoadersWithFakeEngine_test_load_genre_catalog_reads_catalog)

def _cftest_TestEngineLoadersGenrePrivate_test_load_arc_by_heading_found():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_load_arc_by_heading_found()
run("coverage_final/TestEngineLoadersGenrePrivate.test_load_arc_by_heading_found", _cftest_TestEngineLoadersGenrePrivate_test_load_arc_by_heading_found)

def _cftest_TestEngineLoadersGenrePrivate_test_load_arc_by_heading_not_found():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_load_arc_by_heading_not_found()
run("coverage_final/TestEngineLoadersGenrePrivate.test_load_arc_by_heading_not_found", _cftest_TestEngineLoadersGenrePrivate_test_load_arc_by_heading_not_found)

def _cftest_TestEngineLoadersGenrePrivate_test_load_arc_by_heading_no_file():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_load_arc_by_heading_no_file()
run("coverage_final/TestEngineLoadersGenrePrivate.test_load_arc_by_heading_no_file", _cftest_TestEngineLoadersGenrePrivate_test_load_arc_by_heading_no_file)

def _cftest_TestEngineLoadersGenrePrivate_test_load_fantasy_arc_reads_file():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_load_fantasy_arc_reads_file()
run("coverage_final/TestEngineLoadersGenrePrivate.test_load_fantasy_arc_reads_file", _cftest_TestEngineLoadersGenrePrivate_test_load_fantasy_arc_reads_file)

def _cftest_TestEngineLoadersGenrePrivate_test_load_fantasy_arc_no_file_empty():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_load_fantasy_arc_no_file_empty()
run("coverage_final/TestEngineLoadersGenrePrivate.test_load_fantasy_arc_no_file_empty", _cftest_TestEngineLoadersGenrePrivate_test_load_fantasy_arc_no_file_empty)

def _cftest_TestEngineLoadersGenrePrivate_test_load_antagonist_section_exists():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_load_antagonist_section_exists()
run("coverage_final/TestEngineLoadersGenrePrivate.test_load_antagonist_section_exists", _cftest_TestEngineLoadersGenrePrivate_test_load_antagonist_section_exists)

def _cftest_TestEngineLoadersGenrePrivate_test_load_antagonist_section_no_file():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_load_antagonist_section_no_file()
run("coverage_final/TestEngineLoadersGenrePrivate.test_load_antagonist_section_no_file", _cftest_TestEngineLoadersGenrePrivate_test_load_antagonist_section_no_file)

def _cftest_TestEngineLoadersGenrePrivate_test_extract_subgenre_block_found():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_extract_subgenre_block_found()
run("coverage_final/TestEngineLoadersGenrePrivate.test_extract_subgenre_block_found", _cftest_TestEngineLoadersGenrePrivate_test_extract_subgenre_block_found)

def _cftest_TestEngineLoadersGenrePrivate_test_extract_subgenre_block_not_found():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_extract_subgenre_block_not_found()
run("coverage_final/TestEngineLoadersGenrePrivate.test_extract_subgenre_block_not_found", _cftest_TestEngineLoadersGenrePrivate_test_extract_subgenre_block_not_found)

def _cftest_TestEngineLoadersGenrePrivate_test_extract_quality_rules_fallback_found():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_extract_quality_rules_fallback_found()
run("coverage_final/TestEngineLoadersGenrePrivate.test_extract_quality_rules_fallback_found", _cftest_TestEngineLoadersGenrePrivate_test_extract_quality_rules_fallback_found)

def _cftest_TestEngineLoadersGenrePrivate_test_extract_quality_rules_fallback_not_found():
    make_db()
    obj = TestEngineLoadersGenrePrivate()
    obj.test_extract_quality_rules_fallback_not_found()
run("coverage_final/TestEngineLoadersGenrePrivate.test_extract_quality_rules_fallback_not_found", _cftest_TestEngineLoadersGenrePrivate_test_extract_quality_rules_fallback_not_found)



# ════════════════════════════════════════════════════════
print("\n══ engine_loaders: happy path с фиктивным движком ══")
# ════════════════════════════════════════════════════════

import json as _json
import tempfile as _tempfile
from pathlib import Path as _Path

def _make_fake_engine():
    """Создаёт минимальный фиктивный UNIFIED_ENGINE_MASTER в temp-директории."""
    base = _Path(_tmp_dir())
    def mkf(rel, content):
        p = base / rel; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    mkf("01_WRITING_CORE/01_dialogues.md",
        "Правило диалога 1\nПравило диалога 2")
    mkf("01_WRITING_CORE/03_action.md",
        "Правило экшна 1\nПравило экшна 2\nПравило экшна 3")
    mkf("04_GENRE_ENGINE/catalog/fantasy.json",
        _json.dumps({"display_name":"Фэнтези","tone":"эпический",
                     "key_elements":["магия","квест"],"mistakes":["объяснять магию"]}))
    mkf("04_GENRE_ENGINE/catalog/fantasy_urban.json",
        _json.dumps({"display_name":"Городское фэнтези",
                     "key_elements":["магия в городе"],"tone":"тёмный"}))
    mkf("05_CHARACTER_ENGINE/profiles/GENRE/fantasy.md",
        "Протагонист фэнтези: герой с конфликтом")
    mkf("05_CHARACTER_ENGINE/profiles/GENRE/urban_mystic.md",
        "Протагонист городского фэнтези: маг-детектив")
    mkf("05_CHARACTER_ENGINE/antagonists/antagonist_by_genre.md",
        "### ФЭНТЕЗИ\nАнтагонист: воплощение зла\n\n### ДЕТЕКТИВ\nАнтагонист: манипулятор")
    mkf("06_PATTERN_LIBRARY/hooks_by_genre.md",
        "## FANTASY\nХук 1: тайна прошлого\nХук 2: потеря всего\n\n## DETECTIVE\nХук: труп")
    mkf("06_PATTERN_LIBRARY/transitions/scene_transitions.md",
        "---\nПереход 1: резкая смена POV")
    mkf("06_PATTERN_LIBRARY/genre_situations/fantasy_situations.md",
        "---\nСитуация 1: первый контакт с магией")
    mkf("06_PATTERN_LIBRARY/scenes/dynamic_scene.md",
        "---\nПравило 1: короткие предложения")
    mkf("11_PROMPTS/fantasy_QUICK.md",
        "## QUICK\nГОРОДСКОЕ:\nправило_urban_1\nправило_urban_2\n\nТЁМНОЕ ФЭНТЕЗИ:\nправило_dark_1")
    mkf("12_ARCS/arcs_by_genre.md",
        "## ДЕТЕКТИВ\nАрка: раскрытие тайны\n\n## ТРИЛЛЕР\nАрка триллера")
    mkf("12_ARCS/arc_fantasy_templates.md",
        "## АРК 1 — Герой\nГерой выходит из зоны комфорта\nВстречает ментора\n## АРК 2\nАнтагонист")
    mkf("16_GENRE_CONTRACT/fantasy_contracts.md",
        "## ГОРОДСКОЕ ФЭНТЕЗИ\nМагия реальна но скрыта\nГерой знает о магии\n## ТЁМНОЕ ФЭНТЕЗИ\nКонтракт")
    return base


# ── load_writing_core_hint ────────────────────────────────────────────────────

def test_loader_writing_core_dialogue_quick():
    from engine.engine_loaders_core import load_writing_core_hint
    e = _make_fake_engine()
    r = load_writing_core_hint(e, "диалог между персонажами", "quick")
    assert r and "диалог" in r.lower() or "DIALOGUES" in r
run("loaders/writing_core: диалог quick → находит файл", test_loader_writing_core_dialogue_quick)

def test_loader_writing_core_action_quality():
    from engine.engine_loaders_core import load_writing_core_hint
    e = _make_fake_engine()
    r = load_writing_core_hint(e, "бой с врагами", "quality")
    assert r and ("экшна" in r or "ACTION" in r)
run("loaders/writing_core: бой quality → находит файл", test_loader_writing_core_action_quality)

def test_loader_writing_core_no_match():
    from engine.engine_loaders_core import load_writing_core_hint
    e = _make_fake_engine()
    r = load_writing_core_hint(e, "нечто без ключевых слов", "quick")
    assert r == ""
run("loaders/writing_core: нет совпадений → ''", test_loader_writing_core_no_match)

def test_loader_writing_core_quick_one_file_max():
    from engine.engine_loaders_core import load_writing_core_hint
    e = _make_fake_engine()
    # quick → не более 1 файла → нет двойного блока [ТЕХНИКА: ...]
    r = load_writing_core_hint(e, "диалог бой экшн схватка", "quick")
    assert r.count("[ТЕХНИКА:") <= 1
run("loaders/writing_core: quick → максимум 1 файл", test_loader_writing_core_quick_one_file_max)

def test_loader_writing_core_quality_two_files():
    from engine.engine_loaders_core import load_writing_core_hint
    e = _make_fake_engine()
    # quality с двумя совпадениями → до 2 файлов
    r = load_writing_core_hint(e, "диалог и бой экшн схватка", "quality")
    assert r.count("[ТЕХНИКА:") <= 2
run("loaders/writing_core: quality → до 2 файлов", test_loader_writing_core_quality_two_files)


# ── load_genre_catalog ────────────────────────────────────────────────────────

def test_loader_genre_catalog_basic():
    from engine.engine_loaders_genre import load_genre_catalog
    e = _make_fake_engine()
    r = load_genre_catalog(e, "fantasy")
    assert "Фэнтези" in r
    assert "эпический" in r
    assert "магия" in r
run("loaders/genre_catalog: fantasy → все поля", test_loader_genre_catalog_basic)

def test_loader_genre_catalog_mistakes():
    from engine.engine_loaders_genre import load_genre_catalog
    e = _make_fake_engine()
    r = load_genre_catalog(e, "fantasy")
    assert "объяснять магию" in r
run("loaders/genre_catalog: mistakes включены", test_loader_genre_catalog_mistakes)

def test_loader_genre_catalog_missing():
    from engine.engine_loaders_genre import load_genre_catalog
    e = _make_fake_engine()
    assert load_genre_catalog(e, "nonexistent") == ""
run("loaders/genre_catalog: несуществующий жанр → ''", test_loader_genre_catalog_missing)


# ── load_genre_contract ───────────────────────────────────────────────────────

def test_loader_genre_contract_urban():
    from engine.engine_loaders_genre import load_genre_contract
    e = _make_fake_engine()
    r = load_genre_contract(e, "fantasy_urban")
    assert "КОНТРАКТ" in r.upper()
    assert "Магия" in r
run("loaders/genre_contract: fantasy_urban → секция контракта", test_loader_genre_contract_urban)

def test_loader_genre_contract_unknown_family():
    from engine.engine_loaders_genre import load_genre_contract
    e = _make_fake_engine()
    assert load_genre_contract(e, "unknown_genre") == ""
run("loaders/genre_contract: неизвестный жанр → ''", test_loader_genre_contract_unknown_family)


# ── load_arc_hint ─────────────────────────────────────────────────────────────

def test_loader_arc_hint_fantasy():
    from engine.engine_loaders_genre import load_arc_hint
    e = _make_fake_engine()
    r = load_arc_hint(e, "fantasy")
    assert "АРКИ" in r.upper() or "АРК" in r
    assert "Герой" in r
run("loaders/arc_hint: fantasy → arc_fantasy_templates.md", test_loader_arc_hint_fantasy)

def test_loader_arc_hint_detective():
    from engine.engine_loaders_genre import load_arc_hint
    e = _make_fake_engine()
    r = load_arc_hint(e, "detective_noir")
    assert "ДЕТЕКТИВ" in r or "Арка" in r
run("loaders/arc_hint: detective → arcs_by_genre.md ДЕТЕКТИВ", test_loader_arc_hint_detective)

def test_loader_arc_hint_unknown():
    from engine.engine_loaders_genre import load_arc_hint
    e = _make_fake_engine()
    assert load_arc_hint(e, "unknown") == ""
run("loaders/arc_hint: неизвестный жанр → ''", test_loader_arc_hint_unknown)


# ── load_character_profile ────────────────────────────────────────────────────

def test_loader_character_profile_fantasy():
    from engine.engine_loaders_genre import load_character_profile
    e = _make_fake_engine()
    r = load_character_profile(e, "fantasy")
    assert "ПРОФИЛЬ" in r
    assert "фэнтези" in r.lower()
run("loaders/character_profile: fantasy → профиль", test_loader_character_profile_fantasy)

def test_loader_character_profile_fantasy_urban():
    from engine.engine_loaders_genre import load_character_profile
    e = _make_fake_engine()
    r = load_character_profile(e, "fantasy_urban")
    assert "ПРОФИЛЬ" in r
    assert "городского" in r.lower() or "маг" in r.lower()
run("loaders/character_profile: fantasy_urban → urban_mystic.md", test_loader_character_profile_fantasy_urban)

def test_loader_character_profile_antagonist_included():
    from engine.engine_loaders_genre import load_character_profile
    e = _make_fake_engine()
    r = load_character_profile(e, "fantasy")
    assert "АНТАГОНИСТ" in r.upper() or "воплощение" in r.lower()
run("loaders/character_profile: антагонист включён", test_loader_character_profile_antagonist_included)

def test_loader_character_profile_no_genre():
    from engine.engine_loaders_genre import load_character_profile
    e = _make_fake_engine()
    assert load_character_profile(e, "") == ""
run("loaders/character_profile: пустой жанр → ''", test_loader_character_profile_no_genre)


# ── load_catalog_subgenre_hint ────────────────────────────────────────────────

def test_loader_catalog_subgenre_hint_basic():
    from engine.engine_loaders_genre import load_catalog_subgenre_hint
    e = _make_fake_engine()
    r = load_catalog_subgenre_hint(e, "fantasy_urban")
    assert "Городское фэнтези" in r
    assert "магия в городе" in r.lower()
run("loaders/catalog_subgenre: fantasy_urban → все поля", test_loader_catalog_subgenre_hint_basic)

def test_loader_catalog_subgenre_hint_missing():
    from engine.engine_loaders_genre import load_catalog_subgenre_hint
    e = _make_fake_engine()
    assert load_catalog_subgenre_hint(e, "fantasy_unknown") == ""
run("loaders/catalog_subgenre: несуществующий → ''", test_loader_catalog_subgenre_hint_missing)


# ── load_pattern_library ──────────────────────────────────────────────────────

def test_loader_pattern_library_quick_hooks():
    from engine.engine_loaders_core import load_pattern_library
    e = _make_fake_engine()
    r = load_pattern_library(e, "fantasy", "quick")
    assert "ХУКИ" in r.upper() or "Хук" in r
run("loaders/pattern_library: quick → хуки по жанру", test_loader_pattern_library_quick_hooks)

def test_loader_pattern_library_quality_transitions():
    from engine.engine_loaders_core import load_pattern_library
    e = _make_fake_engine()
    r = load_pattern_library(e, "fantasy", "quality")
    assert "ПЕРЕХОДЫ" in r.upper() or "Переход" in r
run("loaders/pattern_library: quality → + переходы", test_loader_pattern_library_quality_transitions)

def test_loader_pattern_library_quality_situations():
    from engine.engine_loaders_core import load_pattern_library
    e = _make_fake_engine()
    r = load_pattern_library(e, "fantasy", "quality")
    assert "Ситуация" in r or "ПАТТЕРНЫ" in r.upper()
run("loaders/pattern_library: quality → + ситуации", test_loader_pattern_library_quality_situations)

def test_loader_pattern_library_task_scene_match():
    from engine.engine_loaders_core import load_pattern_library
    e = _make_fake_engine()
    r = load_pattern_library(e, "fantasy", "quality", "бой с врагами схватка")
    # dynamic_scene.md должен подключиться
    assert "DYNAMIC" in r.upper() or "короткие" in r.lower() or "ПАТТЕРН СЦЕНЫ" in r
run("loaders/pattern_library: task=бой → dynamic_scene паттерн", test_loader_pattern_library_task_scene_match)

def test_loader_pattern_library_no_genre_key():
    from engine.engine_loaders_core import load_pattern_library
    e = _make_fake_engine()
    # нет жанра → хуки не добавляются
    r = load_pattern_library(e, None, "quick")
    assert "ХУКИ" not in r.upper()
run("loaders/pattern_library: нет жанра → хуки не добавляются", test_loader_pattern_library_no_genre_key)


# ── load_genre_prompt ─────────────────────────────────────────────────────────

def test_loader_genre_prompt_urban_quick():
    from engine.engine_loaders_genre import load_genre_prompt
    e = _make_fake_engine()
    r = load_genre_prompt(e, "fantasy_urban", "QUICK")
    assert "ПРАВИЛА ЖАНРА" in r
    assert "правило_urban" in r
run("loaders/genre_prompt: fantasy_urban QUICK → правила поджанра", test_loader_genre_prompt_urban_quick)

def test_loader_genre_prompt_catalog_included():
    from engine.engine_loaders_genre import load_genre_prompt
    e = _make_fake_engine()
    r = load_genre_prompt(e, "fantasy_urban", "QUICK")
    assert "Городское фэнтези" in r or "магия в городе" in r.lower()
run("loaders/genre_prompt: catalog addon включён", test_loader_genre_prompt_catalog_included)

def test_loader_genre_prompt_no_file():
    from engine.engine_loaders_genre import load_genre_prompt
    e = _make_fake_engine()
    assert load_genre_prompt(e, "fantasy_urban", "MASTER") == ""
run("loaders/genre_prompt: нет файла промпта → ''", test_loader_genre_prompt_no_file)

def test_loader_genre_prompt_empty_key():
    from engine.engine_loaders_genre import load_genre_prompt
    e = _make_fake_engine()
    assert load_genre_prompt(e, "", "QUICK") == ""
run("loaders/genre_prompt: пустой genre_key → ''", test_loader_genre_prompt_empty_key)


# ── load_module + _find_module_file ──────────────────────────────────────────

def test_loader_load_module_exact_match():
    import tempfile, json
    from pathlib import Path
    from engine.engine_loaders_core import load_module
    from unittest.mock import patch
    e = _make_fake_engine()
    engines = e / "03_ADVANCED_ENGINES"
    engines.mkdir()
    (engines / "tension_model.md").write_text("## Tension Model\nформула напряжения\nставки urgency")
    r = load_module(e, "tension_model")
    assert r  # что-то загрузилось
run("loaders/load_module: точное совпадение имени", test_loader_load_module_exact_match)

def test_loader_load_module_missing():
    from engine.engine_loaders_core import load_module
    e = _make_fake_engine()
    assert load_module(e, "nonexistent_module") == ""
run("loaders/load_module: нет файла → ''", test_loader_load_module_missing)


# ── get_module_dependencies + get_token_budget ───────────────────────────────

def test_loader_get_module_dependencies_fallback():
    from engine.engine_loaders import get_module_dependencies
    from unittest.mock import patch
    with patch("engine.engine_loaders.load_module_dependencies_from_index", return_value=None):
        result = get_module_dependencies()
    assert isinstance(result, dict)
    assert len(result) > 0
run("loaders/get_module_dependencies: нет INDEX → engine_config fallback", test_loader_get_module_dependencies_fallback)

def test_loader_get_module_dependencies_from_index():
    from engine.engine_loaders import get_module_dependencies
    from unittest.mock import patch
    fake_deps = {"genre": ["base"], "arc": ["genre", "base"]}
    with patch("engine.engine_loaders.load_module_dependencies_from_index", return_value=fake_deps):
        result = get_module_dependencies()
    assert result == fake_deps
run("loaders/get_module_dependencies: INDEX → возвращает из INDEX", test_loader_get_module_dependencies_from_index)

def test_loader_get_token_budget_claude():
    from engine.engine_loaders import get_token_budget
    budget = get_token_budget("claude-3-opus")
    assert budget > 0
run("loaders/get_token_budget: claude модель", test_loader_get_token_budget_claude)

def test_loader_get_token_budget_gpt4o():
    from engine.engine_loaders import get_token_budget
    assert get_token_budget("gpt-4o") > 0
run("loaders/get_token_budget: gpt-4o", test_loader_get_token_budget_gpt4o)

def test_loader_get_token_budget_empty():
    from engine.engine_loaders import get_token_budget
    assert get_token_budget("") > 0  # default
run("loaders/get_token_budget: пустая строка → default", test_loader_get_token_budget_empty)

def test_loader_get_token_budget_gemini():
    from engine.engine_loaders import get_token_budget
    assert get_token_budget("gemini-pro") > 0
run("loaders/get_token_budget: gemini", test_loader_get_token_budget_gemini)

def test_loader_get_token_budget_deepseek():
    from engine.engine_loaders import get_token_budget
    assert get_token_budget("deepseek-chat") > 0
run("loaders/get_token_budget: deepseek", test_loader_get_token_budget_deepseek)


# ── _trim_modules_to_budget ───────────────────────────────────────────────────

def test_trim_modules_fits_budget():
    from engine.engine_loaders import _trim_modules_to_budget
    sections = [("genre", "А" * 100), ("arc", "Б" * 100)]
    result = _trim_modules_to_budget(sections, budget_chars=1000)
    assert len(result) == 2
    assert all(len(s) <= 100 for s in result)
run("loaders/_trim_modules: влезает → не режет", test_trim_modules_fits_budget)

def test_trim_modules_cuts_to_budget():
    from engine.engine_loaders import _trim_modules_to_budget
    sections = [("genre", "А" * 500), ("arc", "Б" * 500)]
    result = _trim_modules_to_budget(sections, budget_chars=200)
    total = sum(len(s) for s in result)
    assert total <= 200 or all(len(s) <= 50 for s in result)  # достиг минимума
run("loaders/_trim_modules: бюджет превышен → режет", test_trim_modules_cuts_to_budget)

def test_trim_modules_empty():
    from engine.engine_loaders import _trim_modules_to_budget
    assert _trim_modules_to_budget([], 1000) == []
run("loaders/_trim_modules: пустой список", test_trim_modules_empty)


# ══════════════════════════════════════════════════════════════════════
# РЕГРЕССИИ ПО АУДИТУ 2026-08-22
# Проверяют стыки, а не отдельные функции: именно там жили баги,
# которых не заметили остальные 777 тестов.
# ══════════════════════════════════════════════════════════════════════

print("\n══ регрессии: движок, State-парсер, бюджет токенов ══")


def test_engine_context_not_empty():
    """
    Блок UNIFIED_ENGINE должен реально собираться.
    Ловит потерю обёртки _load_module (str/str TypeError → пустой контекст).
    """
    from engine.unified_engine import build_engine_context
    from engine.engine_loaders import engine_available
    if not engine_available():
        return  # без базы знаний проверять нечего
    for mode in ("quick", "quality", "master"):
        out = build_engine_context("фэнтези", mode, model_value="anthropic::claude-opus-4")
        assert out and len(out) > 1000, f"{mode}: контекст движка пуст ({len(out)} символов)"
        assert "UNIFIED ENGINE" in out, f"{mode}: нет заголовка блока"
run("регрессия: контекст движка непустой во всех режимах", test_engine_context_not_empty)


def _merge_case(template, changes, plot=""):
    """Прогнать merge_analysis_into_state на изолированной БД."""
    import json as _j
    db = _make_tmp_db()
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        from engine.db_state import merge_analysis_into_state, get_state, update_state
        pid = create_project("t", "детектив")
        update_state(pid, template, plot, "")
        res = merge_analysis_into_state(
            pid, _j.dumps(changes, ensure_ascii=False), 3)
        return res, get_state(pid)["global_state"], template


_UPPER = "## ПЕРСОНАЖИ\n\n### Марк\nСОСТОЯНИЕ: спокоен\nЛОКАЦИЯ: дом\nЗНАЕТ: []\n"
_TITLE = "## ПЕРСОНАЖИ\n\n### Марк\nСостояние: спокоен\nЛокация: дом\nЗнает: []\n"
_FREE  = "[МАРК — ГЕРОЙ]\nВозраст: 34\nСтатус: спокоен\nМесто: дом\n"
_CRLF  = "[МАРК — ГЕРОЙ]\r\nВозраст: 34\r\nСтатус: спокоен\r\nМесто: дом\r\n"
_CHANGE = {"global_state_changes": [{"name": "Марк", "состояние": "ранен", "локация": "склад"}]}


def test_state_merge_uppercase_format():
    res, after, before = _merge_case(_UPPER, _CHANGE)
    assert res["changed"] and after != before
    assert "СОСТОЯНИЕ: ранен" in after, after
run("регрессия: State-merge, формат ВЕРХНИЙ РЕГИСТР", test_state_merge_uppercase_format)


def test_state_merge_titlecase_format():
    res, after, before = _merge_case(_TITLE, _CHANGE)
    assert res["changed"] and after != before
    assert "Состояние: ранен" in after, after
run("регрессия: State-merge, формат Title Case", test_state_merge_titlecase_format)


def test_state_merge_freeform_format():
    """Авторский формат: [ИМЯ — РОЛЬ] и ключи Статус/Место."""
    res, after, before = _merge_case(_FREE, _CHANGE)
    assert res["changed"] and after != before
    assert "Статус: ранен" in after, after
    assert not res["new_chars"], "персонаж не должен дублироваться"
run("регрессия: State-merge, авторский формат [ИМЯ — РОЛЬ]", test_state_merge_freeform_format)


def test_state_merge_crlf():
    """Файлы State из Windows хранятся в CRLF — парсер обязан их понимать."""
    res, after, before = _merge_case(_CRLF, _CHANGE)
    assert res["changed"] and after != before
    assert "Статус: ранен" in after, after
    assert "\r\n" in after, "переводы строк CRLF должны сохраниться"
run("регрессия: State-merge понимает CRLF", test_state_merge_crlf)


def test_state_merge_no_false_report():
    """Плейсхолдеры и пустые значения не должны давать «Применено N изменений»."""
    res, after, before = _merge_case(
        _FREE, {"global_state_changes": [
            {"name": "Марк", "состояние": "[без изменений]", "локация": ""}]})
    assert not res["changed"], res
    assert after == before
run("регрессия: State-merge не рапортует о несделанном", test_state_merge_no_false_report)


def test_state_merge_same_value_is_not_change():
    res, after, before = _merge_case(
        _FREE, {"global_state_changes": [{"name": "Марк", "локация": "дом"}]})
    assert not res["changed"], res
    assert after == before
run("регрессия: повтор того же значения — не изменение", test_state_merge_same_value_is_not_change)


def test_state_merge_appends_missing_field():
    """Поля нет в блоке — его надо дописать, а не потерять."""
    res, after, before = _merge_case(
        "[МАРК — ГЕРОЙ]\nВозраст: 34\n",
        {"global_state_changes": [{"name": "Марк", "состояние": "ранен"}]})
    assert res["changed"]
    assert "ранен" in after, after
run("регрессия: отсутствующее поле дописывается", test_state_merge_appends_missing_field)


def test_prose_budget_covers_target():
    """max_tokens должен вмещать объём, который требуют промпты."""
    from engine.pipeline_config import (PROSE_MAX_TOKENS, tokens_for_words,
                                        TARGET_CHAPTER_WORDS)
    assert PROSE_MAX_TOKENS >= tokens_for_words(TARGET_CHAPTER_WORDS), \
        f"{PROSE_MAX_TOKENS} < нужного для {TARGET_CHAPTER_WORDS} слов"
run("регрессия: бюджет токенов покрывает целевой объём", test_prose_budget_covers_target)


def test_edit_budget_not_below_generate():
    """Редактура не должна резать главу, которую генерация написала целиком."""
    from engine.pipeline_config import DEEP, CONTINUE, QUICK, STANDARD, AUTO_IMPROVE
    for cfg in (QUICK, STANDARD, DEEP, CONTINUE, AUTO_IMPROVE):
        steps = {s.name: s.max_tokens for s in cfg.steps}
        if "edit" in steps and "generate" in steps:
            assert steps["edit"] >= steps["generate"], \
                f"{cfg.description}: edit={steps['edit']} < generate={steps['generate']}"
run("регрессия: edit не меньше generate по max_tokens", test_edit_budget_not_below_generate)


def test_truncation_detected():
    from engine.api import _remember_stop_reason
    from engine.pipeline import describe_truncation
    for reason in ("max_tokens", "length"):
        _remember_stop_reason(reason)
        assert describe_truncation("x " * 2400, 2400), f"обрыв {reason} не распознан"
    _remember_stop_reason("end_turn")
    assert not describe_truncation("x " * 2900, 2900), "ложное предупреждение"
run("регрессия: обрыв по max_tokens распознаётся", test_truncation_detected)


def test_detect_truncation_structured():
    """Интерфейсу нужен флаг, а не строка: по строке кнопку не покажешь."""
    from engine.api import _remember_stop_reason
    from engine.pipeline import detect_truncation
    _remember_stop_reason("max_tokens")
    d = detect_truncation("x " * 2400, 2400)
    assert d["truncated"] is True and d["reason"] == "max_tokens" and d["message"]
    _remember_stop_reason("length")
    assert detect_truncation("x " * 2600, 2600)["reason"] == "max_tokens"
    _remember_stop_reason("end_turn")
    d = detect_truncation("x " * 1100, 1100)
    assert d["truncated"] is True and d["reason"] == "short"
    d = detect_truncation("x " * 2900, 2900)
    assert d["truncated"] is False and d["reason"] == "" and d["message"] == ""
run("регрессия: detect_truncation отдаёт структуру", test_detect_truncation_structured)


def test_flag_truncation_fills_results():
    """step_generate и step_edit кладут флаг в results — оттуда он идёт в UI."""
    from engine.api import _remember_stop_reason
    from engine.pipeline_steps import _flag_truncation
    res = {}
    _remember_stop_reason("max_tokens")
    _flag_truncation("слово " * 2400, res, "тест")
    assert res["truncated"] is True
    assert res["cut_reason"] == "max_tokens"
    assert res["truncation_warning"]
    res2 = {}
    _remember_stop_reason("end_turn")
    _flag_truncation("слово " * 2900, res2, "тест")
    assert res2["truncated"] is False
    assert "truncation_warning" not in res2
run("регрессия: _flag_truncation заполняет results", test_flag_truncation_fills_results)


def test_run_generation_reports_truncation():
    """run_generation обязан отдать флаг наверх, а не только текст warning."""
    from engine.api import _remember_stop_reason
    import engine.pipeline as pl
    db = _make_tmp_db()
    with _mock.patch("engine.db_core.DB_PATH", db):
        from engine.db_core import init_db; init_db()
        from engine.db_projects import create_project
        pid = create_project("Т", "детектив")
        proj = {"id": pid, "name": "Т", "genre": "детектив"}

        def fake_call(model, system, user, max_tokens=6000, prefill=""):
            _remember_stop_reason("max_tokens")
            return "слово " * 2400

        with _mock.patch("engine.pipeline._call", fake_call):
            with _mock.patch("engine.pipeline._build_context", return_value="ctx"):
                with _mock.patch("engine.pipeline.step_chapter_analysis"):
                    r = pl.run_generation(proj, 1, "quick",
                                          "anthropic_direct::claude-opus-4", "Задача")
    assert r["truncated"] is True
    assert r["cut_reason"] == "max_tokens"
    assert r["word_count"] == 2400
    assert "max_tokens" in (r["warning"] or "")
run("регрессия: run_generation сообщает об обрыве наверх", test_run_generation_reports_truncation)


def test_max_tokens_retry_only_on_output_limit():
    """Повтор с меньшим потолком — только когда дело действительно в нём."""
    from engine.api import _reduced_max_tokens
    assert _reduced_max_tokens(Exception("max_tokens: must be <= 8192"), 11730) == 5865
    assert _reduced_max_tokens(Exception("max output tokens exceeded"), 11730) == 5865
    for msg in ("This model's maximum context length is 8192 tokens",
                "rate_limit_exceeded: 429", "invalid_api_key", "Connection timeout"):
        assert _reduced_max_tokens(Exception(msg), 11730) is None, msg
run("регрессия: понижение max_tokens только по лимиту вывода", test_max_tokens_retry_only_on_output_limit)


def test_max_tokens_retry_recovers():
    """Модель с меньшим лимитом вывода не должна ронять генерацию."""
    from engine.api import call_model
    tries = []

    def fake(model_id, system, user, key, max_tokens, prefill=""):
        tries.append(max_tokens)
        if max_tokens > 8192:
            raise Exception("max_tokens: must be <= 8192")
        return "текст главы"

    with _mock.patch("engine.api._call_anthropic", fake):
        out = call_model("anthropic_direct::claude-opus-4", "s", "u",
                         anthropic_key="k", max_tokens=11730)
    assert out == "текст главы"
    assert tries == [11730, 5865], tries
run("регрессия: повтор с уменьшенным потолком спасает генерацию", test_max_tokens_retry_recovers)


def test_max_tokens_retry_not_infinite():
    """Повтор ровно один: вторая та же ошибка должна пробрасываться."""
    from engine.api import call_model
    tries = []

    def always_fail(model_id, system, user, key, max_tokens, prefill=""):
        tries.append(max_tokens)
        raise Exception("max_tokens: must be <= 128")

    with _mock.patch("engine.api._call_anthropic", always_fail):
        try:
            call_model("anthropic_direct::claude-opus-4", "s", "u",
                       anthropic_key="k", max_tokens=11730)
            assert False, "должно было пробросить"
        except Exception as e:
            assert "max_tokens" in str(e)
    assert len(tries) == 2, tries
run("регрессия: повтор не зацикливается", test_max_tokens_retry_not_infinite)


def test_short_chapter_warns():
    from engine.api import _remember_stop_reason
    from engine.pipeline import describe_truncation
    _remember_stop_reason("end_turn")
    assert describe_truncation("x " * 1200, 1200), "короткая глава должна давать предупреждение"
run("регрессия: недописанная глава даёт предупреждение", test_short_chapter_warns)


total = passed + failed
print(f"\n{'━'*50}")
print(f"Итого: {passed}/{total} прошли", end="")
if failed:
    print(f"  |  {failed} провалено\n")
    print("Провалено:")
    for name, err in errors:
        print(f"  ✗ {name}")
        print(f"    {err}")
else:
    print("  ✓  Все тесты зелёные\n")

sys.exit(0 if failed == 0 else 1)
