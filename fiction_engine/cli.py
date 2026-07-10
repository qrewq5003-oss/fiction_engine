#!/usr/bin/env python3
"""
Fiction Engine — терминальный интерфейс.
Используй если не хочешь открывать браузер.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine.db import (init_db, create_project, get_projects, get_project,
                        set_active_project, get_active_project_id,
                        save_chapter, get_chapters, get_chapter,
                        get_state, update_state, get_api_key, save_api_key,
                        get_pending_updates, mark_update_applied)
from engine.api import get_all_models_flat, call_model
from engine.state import analyze_chapter, build_prompt


# ─── Цвета ───────────────────────────────────────────────────────────────────

def c(text, code): return f"\033[{code}m{text}\033[0m"
def bold(t):   return c(t, "1")
def dim(t):    return c(t, "2")
def green(t):  return c(t, "32")
def yellow(t): return c(t, "33")
def cyan(t):   return c(t, "36")
def red(t):    return c(t, "31")
def purple(t): return c(t, "35")


def header(title):
    print(f"\n{bold('─'*50)}")
    print(f"  {bold(cyan(title))}")
    print(f"{bold('─'*50)}")


def success(msg): print(f"  {green('✓')} {msg}")
def warn(msg):    print(f"  {yellow('⚠')} {msg}")
def error(msg):   print(f"  {red('✗')} {msg}")
def info(msg):    print(f"  {dim('›')} {msg}")


def prompt_input(label, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"  {label}{suffix}: ").strip()
    return val or default or ""


def choose(options: list[dict], label="Выбери") -> dict | None:
    """Показать нумерованный список, вернуть выбранный элемент."""
    for i, opt in enumerate(options, 1):
        print(f"  {dim(str(i)+'.'):4} {opt.get('label', opt.get('name', str(opt)))}")
    val = input(f"\n  {label} (номер): ").strip()
    try:
        idx = int(val) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except ValueError:
        pass
    return None


def _require_project() -> int | None:
    """Вернуть ID активного проекта или напечатать ошибку и вернуть None."""
    pid = get_active_project_id()
    if not pid:
        error("Нет активного проекта")
    return pid


# ─── Команды ─────────────────────────────────────────────────────────────────

def cmd_status():
    header("Статус проекта")
    pid = _require_project()
    if not pid:
        warn("Создай проект: python cli.py project new")
        return

    p        = get_project(pid)
    chapters = get_chapters(pid)
    pending  = get_pending_updates(pid)

    print(f"\n  {bold(p['name'])}  {dim(p['genre'] or '')}")
    print(f"  Глав загружено: {bold(str(len(chapters)))}")
    if chapters:
        last = chapters[-1]
        print(f"  Последняя:      Глава {last['number']} ({last['word_count']} сл.)")
    if pending:
        warn(f"Необработанных обновлений State Engine: {len(pending)}")
        info("Запусти: python cli.py state apply")
    print()


def cmd_project_new():
    header("Новый проект")
    name  = prompt_input("Название серии")
    genre = prompt_input("Жанр", "фэнтези")
    if not name:
        error("Название обязательно")
        return
    pid = create_project(name, genre)
    set_active_project(pid)
    success(f"Проект «{name}» создан и активирован")


def cmd_project_list():
    header("Проекты")
    projects  = get_projects()
    active_id = get_active_project_id()
    if not projects:
        warn("Нет проектов")
        return
    for p in projects:
        marker        = green("●") if p["id"] == active_id else dim("○")
        chapters_info = f"  {dim(str(p['last_chapter']) + ' гл.')}" if p.get("last_chapter") else ""
        print(f"  {marker} {bold(p['name'])} {dim(p['genre'] or '')}{chapters_info}")
    print()


def cmd_project_switch():
    header("Переключить проект")
    projects = get_projects()
    if not projects:
        warn("Нет проектов")
        return
    opts   = [{"label": f"{p['name']} ({p['genre'] or 'нет жанра'})", "id": p["id"]} for p in projects]
    choice = choose(opts, "Выбери проект")
    if choice:
        set_active_project(choice["id"])
        success(f"Активирован проект ID {choice['id']}")


def cmd_project(sub: str = "list"):
    """Диспетчер подкоманд project."""
    {"new": cmd_project_new, "switch": cmd_project_switch}.get(sub, cmd_project_list)()


def cmd_chapter_add():
    header("Добавить главу")
    pid = _require_project()
    if not pid:
        return

    existing = get_chapters(pid)
    next_num = (existing[-1]["number"] + 1) if existing else 1
    num      = int(prompt_input("Номер главы", str(next_num)) or next_num)
    title    = prompt_input("Название (Enter = пропустить)")

    print(f"\n  {dim('1. Путь к файлу   2. Ввод текста')}")
    choice = input("  Способ (1/2): ").strip()

    if choice == "1":
        path = prompt_input("Путь к файлу")
        try:
            content = Path(path).read_text(encoding="utf-8")
        except Exception as e:
            error(f"Не могу прочитать файл: {e}")
            return
    else:
        print(f"  {dim('Вставь текст, закончи Ctrl+D:')}")
        lines = []
        try:
            while True:
                lines.append(input())
        except EOFError:
            pass
        content = "\n".join(lines)

    if not content.strip():
        error("Пустой текст")
        return

    save_chapter(pid, num, content, title)
    success(f"Глава {num} сохранена ({len(content.split())} слов)")


def cmd_state_view():
    header("State Engine")
    pid = _require_project()
    if not pid:
        return
    state = get_state(pid)
    print(f"\n{bold('═══ GLOBAL STATE ═══')}")
    print(state["global_state"])
    print(f"\n{bold('═══ PLOT MATRIX ═══')}")
    print(state["plot_matrix"])
    print(f"\n{bold('═══ MEMORY GRAPH ═══')}")
    print(state["memory_graph"])


def cmd_state_analyze():
    header("Анализ главы → обновление State Engine")
    pid = _require_project()
    if not pid:
        return

    chapters = get_chapters(pid)
    if not chapters:
        error("Нет глав")
        return

    print("\n  Доступные главы:")
    for ch in chapters:
        print(f"    {ch['number']}.  {ch['title'] or 'Глава ' + str(ch['number'])}  {dim(str(ch['word_count']) + ' сл.')}")

    num = int(prompt_input("\n  Номер главы для анализа") or "0")
    if not any(c["number"] == num for c in chapters):
        error(f"Глава {num} не найдена")
        return

    model = _pick_analysis_model()
    if not model:
        return

    print(f"\n  {dim('Отправляю запрос...')}")
    try:
        result = analyze_chapter(pid, num, model["value"])
    except Exception as e:
        error(f"Ошибка API: {e}")
        return

    print(f"\n{bold('═══ РЕЗУЛЬТАТ АНАЛИЗА ═══')}")
    print(result["analysis"])
    print(f"\n{bold('═══ КОНТЕКСТ ДЛЯ СЛЕДУЮЩЕЙ ГЛАВЫ ═══')}")
    print(result["next_context"])

    print(f"\n  {yellow('Применить изменения к State Engine? (y/n):')} ", end="")
    if input().strip().lower() == "y":
        mark_update_applied(result["update_id"])
        success("Обновление помечено.")
        info("Открой браузер: http://localhost:5000/state")
    else:
        warn("Обновление отложено. Доступно в браузере: /state")


def _pick_analysis_model() -> dict | None:
    """Выбрать модель для анализа. None если отказ или нет ключа."""
    print(f"\n  {bold('Выбери модель:')}")
    models     = get_all_models_flat()
    top_models = [m for m in models if any(x in m["model_id"] for x in [
        "claude-opus", "claude-sonnet", "gpt-5", "gpt-4.1",
        "gemini-2.5-pro", "deepseek-v3",
    ])][:12]

    choice = choose(top_models, "Модель")
    if not choice:
        error("Не выбрана модель")
        return None

    if not get_api_key(choice["provider"]):
        error(f"Нет API ключа для {choice['provider']}. Добавь: python cli.py keys")
        return None

    return choice


def cmd_prompt_generate():
    header("Генерация промпта")
    pid = _require_project()
    if not pid:
        return

    p        = get_project(pid)
    chapters = get_chapters(pid)
    next_num = (chapters[-1]["number"] + 1) if chapters else 1
    num      = int(prompt_input("Номер главы", str(next_num)) or next_num)

    print("\n  Режим:")
    print("  1. QUICK   — черновик (5 мин)")
    print("  2. QUALITY — важная глава (10-15 мин)")
    print("  3. MASTER  — финал арки (20-30 мин)")
    mode      = {"1": "quick", "2": "quality", "3": "master"}.get(
                    input("  Режим (1/2/3): ").strip(), "quick")
    prompt_text = build_prompt(pid, num, mode, p)

    print(f"\n{bold('═'*60)}")
    print(prompt_text)
    print(f"{bold('═'*60)}")

    out_dir  = Path.home() / "fiction_engine" / "prompts_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"prompt_ch{num:02d}_{mode}.md"
    out_file.write_text(prompt_text)
    success(f"Промпт сохранён: {out_file}")


def cmd_keys():
    header("API ключи")
    from engine.db import get_all_api_keys
    keys = get_all_api_keys()
    if keys:
        for provider, masked in keys.items():
            print(f"  {provider}: {cyan(masked)}")
    else:
        warn("Ключей нет")

    print("\n  1. Добавить Anthropic ключ")
    print("  2. Добавить nano-gpt ключ")
    print("  3. Назад")
    choice = input("  (1/2/3): ").strip()
    key_map = {"1": "anthropic_direct", "2": "nano_gpt"}
    if choice in key_map:
        key = input(f"  Ключ: ").strip()
        if key:
            save_api_key(key_map[choice], key)
            success("Ключ сохранён")


def cmd_web():
    os.system("python web/app.py &")
    info("Открой браузер: http://localhost:5000")


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def _read_prompt_text() -> str:
    """Читать промпт из stdin до двойного Enter или EOF."""
    print(f"\n  {dim('Промпт для генератора (Enter дважды = конец):')}")
    lines = []
    try:
        while True:
            line = input("  ")
            lines.append(line)
            if len(lines) >= 2 and lines[-1] == "" and lines[-2] == "":
                break
    except EOFError:
        pass
    return "\n".join(lines).strip()


def _select_pipeline_models() -> dict | None:
    """
    Показать топ-модели и запросить выбор для каждой роли.
    Возвращает {"gen": ..., "critic": ..., "editor": ..., "judge": ...}
    или None если список пуст.
    """
    all_models = get_all_models_flat()
    top = [m for m in all_models if any(x in m["model_id"] for x in [
        "claude-opus", "claude-sonnet", "gpt-5", "gpt-4.1",
        "gemini-2.5-pro", "deepseek-v3", "kimi-k2",
    ])][:10]

    if not top:
        error("Нет доступных моделей")
        return None

    print(f"\n  {bold('Выбери модели (номер из списка):')}")
    for i, m in enumerate(top, 1):
        print(f"  {dim(str(i)+'.')} {m['label']}")

    def pick(role: str) -> str:
        val = input(f"  {role}: ").strip()
        try:
            return top[int(val) - 1]["value"]
        except (ValueError, IndexError):
            return top[0]["value"]

    print(f"\n  🖊  Генератор:")
    gen    = pick("номер")
    print(f"  🔍 Критик:")
    critic = pick("номер")
    print(f"  ✏️  Редактор:")
    editor = pick("номер")
    print(f"  ⚖️  Судья:")
    judge  = pick("номер")

    return {"gen": gen, "critic": critic, "editor": editor, "judge": judge}


def _show_pipeline_result(result: dict, iteration: int):
    """Вывести результаты одного круга pipeline."""
    print(f"\n{bold(f'═══ ИТЕРАЦИЯ {iteration} ═══')}")
    print(f"\n{bold('📄 ТЕКСТ ГЛАВЫ:')}")
    print(result["generated_text"])
    print(f"\n{bold('🔍 КРИТИКА:')}  балл: {result.get('critic_score', 0)}/50")
    print(result.get("critique", ""))
    print(f"\n{bold('⚖️  ОЦЕНКА СУДЬИ:')}  балл: {result.get('judge_score', 0)}/50")
    print(result.get("judgment", ""))
    verdict       = result.get("verdict", "НА ДОРАБОТКУ")
    verdict_color = green if verdict == "ПРИНЯТЬ" else yellow
    print(f"\n  Вердикт судьи: {verdict_color(verdict)}")


def _pipeline_decision(run_id: int, result: dict,
                        pid: int, chapter_num: int, iteration: int) -> str:
    """
    Спросить решение и выполнить его.
    Возвращает "accept" / "reject" / "continue".
    """
    from engine.pipeline import accept_pipeline, reject_pipeline

    print(f"\n  {bold('Твоё решение:')}")
    print(f"  1. {green('Принять главу')} и сохранить")
    print(f"  2. {yellow('Ещё круг')} редактуры")
    print(f"  3. {red('Отклонить')} pipeline")
    choice = input("  (1/2/3): ").strip()

    if choice == "1":
        accept_pipeline(run_id)
        save_chapter(pid, chapter_num, result["generated_text"],
                     f"Глава {chapter_num} (pipeline, {iteration} итер.)")
        success(f"Глава {chapter_num} принята и сохранена ({iteration} итераций)")
        return "accept"

    if choice == "3":
        reject_pipeline(run_id)
        warn("Pipeline отклонён")
        return "reject"

    return "continue"


def cmd_pipeline():
    header("Pipeline — Генерация → Критика → Редактура → Оценка")
    pid = _require_project()
    if not pid:
        return

    from engine.pipeline import start_pipeline, continue_pipeline

    if not get_api_key("anthropic_direct") and not get_api_key("nano_gpt"):
        error("Нет API ключей. Добавь: python3 cli.py keys")
        return

    chapters    = get_chapters(pid)
    next_num    = (chapters[-1]["number"] + 1) if chapters else 1
    chapter_num = int(prompt_input("Номер главы", str(next_num)) or next_num)

    gen_prompt = _read_prompt_text()
    if not gen_prompt:
        error("Промпт не может быть пустым")
        return

    models = _select_pipeline_models()
    if not models:
        return

    print(f"\n  {dim('Запускаю pipeline...')}")
    try:
        result = start_pipeline(
            project_id=pid, chapter_num=chapter_num,
            generation_prompt=gen_prompt,
            model_gen=models["gen"], model_critic=models["critic"],
            model_editor=models["editor"], model_judge=models["judge"],
        )
    except Exception as e:
        error(f"Ошибка API: {e}")
        return

    iteration = 1
    while True:
        _show_pipeline_result(result, iteration)
        decision = _pipeline_decision(result["run_id"], result, pid, chapter_num, iteration)

        if decision != "continue":
            break

        iteration += 1
        print(f"\n  {dim('Отправляю на редактуру...')}")
        try:
            result = continue_pipeline(
                run_id=result["run_id"], project_id=pid, chapter_num=chapter_num,
                generation_prompt=gen_prompt,
                previous_text=result["generated_text"],
                previous_critique=result.get("critique", ""),
            )
        except Exception as e:
            error(f"Ошибка API: {e}")
            break


# ─── Диспетчер ───────────────────────────────────────────────────────────────

# Единая таблица команд — используется и в argv-режиме, и в меню
COMMANDS: dict[str, callable] = {
    "status":   cmd_status,
    "pipeline": cmd_pipeline,
    "analyze":  cmd_state_analyze,
    "prompt":   cmd_prompt_generate,
    "chapter":  cmd_chapter_add,
    "state":    cmd_state_view,
    "keys":     cmd_keys,
    "web":      cmd_web,
}

# Пункты меню в нужном порядке
MENU = [
    ("status",   "Статус проекта"),
    ("pipeline", "Pipeline — генерация + критика + оценка"),
    ("analyze",  "Анализ главы → обновить State Engine"),
    ("prompt",   "Сгенерировать промпт"),
    ("chapter",  "Добавить главу"),
    ("state",    "Просмотр State Engine"),
    ("projects", "Проекты (список / переключить / новый)"),
    ("keys",     "API ключи"),
    ("web",      "Открыть веб-интерфейс"),
    ("quit",     "Выход"),
]


def _dispatch_argv(args: list[str]):
    """Выполнить команду из аргументов командной строки."""
    cmd = args[0] if args else "status"
    if cmd in ("project", "projects"):
        cmd_project(args[1] if len(args) > 1 else "list")
    elif cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print(f"  Неизвестная команда: {cmd}")
        print(f"  Доступны: {', '.join(COMMANDS)}, project")


def _run_interactive():
    """Интерактивное меню."""
    print(f"\n{bold(purple('  ╔══════════════════════════╗'))}")
    print(f"{bold(purple('  ║   Fiction Engine v1.0    ║'))}")
    print(f"{bold(purple('  ╚══════════════════════════╝'))}")

    while True:
        pid    = get_active_project_id()
        p_name = get_project(pid)["name"] if pid else "нет проекта"
        pending = len(get_pending_updates(pid)) if pid else 0

        print(f"\n  {dim('Проект:')} {bold(cyan(p_name))}", end="")
        if pending:
            print(f"  {yellow(f'⚠ {pending} обновлений')}", end="")
        print()

        for i, (_, label) in enumerate(MENU, 1):
            print(f"  {dim(str(i)+'.')} {label}")

        choice = input(f"\n  {dim('>')} ").strip()
        try:
            cmd = MENU[int(choice) - 1][0]
        except (ValueError, IndexError):
            continue

        if cmd == "quit":
            print(f"\n  {dim('До встречи.')}\n")
            break
        elif cmd == "projects":
            print("\n  1. Список  2. Новый  3. Переключить")
            sub = input("  (1/2/3): ").strip()
            cmd_project({"1": "list", "2": "new", "3": "switch"}.get(sub, "list"))
        elif cmd in COMMANDS:
            COMMANDS[cmd]()


def main():
    init_db()
    if len(sys.argv) > 1:
        _dispatch_argv(sys.argv[1:])
    else:
        _run_interactive()


if __name__ == "__main__":
    main()
