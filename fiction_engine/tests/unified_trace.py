"""
Какие файлы UNIFIED_ENGINE_MASTER движок реально читает.

Обходит все пути, по которым загрузчики открывают файлы базы: 30 жанров
и «жанр не определён» × 3 режима × задачи, собранные из карт ключевых
слов самих загрузчиков, плюс все модули 03 через pre_selected_modules
(их может выбрать auto_router), чек-листы судьи и каталог жанров.
Общий для теста манифеста и для его обновления.
"""

import builtins
import pathlib
from contextlib import contextmanager


@contextmanager
def _recording(root: pathlib.Path):
    seen: set[str] = set()
    real_read_text, real_open = pathlib.Path.read_text, builtins.open

    def note(target) -> None:
        try:
            seen.add(pathlib.Path(target).resolve().relative_to(root).as_posix())
        except (ValueError, TypeError, OSError):
            pass

    def read_text(self, *a, **k):
        note(self)
        return real_read_text(self, *a, **k)

    def open_(file, *a, **k):
        note(file)
        return real_open(file, *a, **k)

    pathlib.Path.read_text = read_text
    builtins.open = open_
    try:
        yield seen
    finally:
        pathlib.Path.read_text = real_read_text
        builtins.open = real_open


def traced_runtime_files(kb: pathlib.Path) -> set[str]:
    import engine.engine_loaders as loaders
    from engine.engine_config import GENRE_KEYWORDS
    from engine.engine_loaders_core import _PATTERN_SCENE_MAP, _WRITING_CORE_MAP
    from engine.unified_engine import build_engine_context, get_all_genre_options

    kb = kb.resolve()
    real_path = loaders.get_engine_path
    loaders.get_engine_path = lambda: kb
    tasks = [""] + [kws[0] for kws in _WRITING_CORE_MAP.values()] \
                  + [kws[0] for kws in _PATTERN_SCENE_MAP.values()]
    all_modules = sorted(p.stem for p in (kb / "03_ADVANCED_ENGINES").glob("*.md"))
    try:
        with _recording(kb) as seen:
            for genre in [""] + sorted(GENRE_KEYWORDS):
                for mode in ("quick", "quality", "master"):
                    for task in tasks:
                        build_engine_context(genre, mode, "claude", True, task)
                loaders._load_validation_checklist(genre or None)
            for mode in ("quick", "master"):
                build_engine_context("", mode, "claude", True, "",
                                     pre_selected_modules=all_modules)
            get_all_genre_options()
            from engine.voice_profiles import get_genre_voices
            get_genre_voices()      # пресеты голосов на странице /voice
    finally:
        loaders.get_engine_path = real_path
    return seen


def files_on_disk(kb: pathlib.Path) -> dict[str, list[str]]:
    """Все файлы базы по каталогам — в формате поля files в INDEX.json."""
    out: dict[str, list[str]] = {}
    for p in sorted(kb.rglob("*")):
        if p.is_file():
            parent = p.parent.relative_to(kb).as_posix()
            out.setdefault(parent, []).append(p.name)
    return out


def update_index(kb: pathlib.Path) -> None:
    """Пересобрать files, total_files и runtime_files в INDEX.json."""
    import json
    path = kb / "INDEX.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    files = files_on_disk(kb)
    data["files"] = files
    data["total_files"] = sum(len(v) for v in files.values())
    data["runtime_files"] = sorted(traced_runtime_files(kb))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    # python tests/unified_trace.py — обновить манифест после правок базы
    # или загрузчиков; тест test_unified_manifest.py скажет, когда пора
    import sys
    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    update_index(root.parent / "UNIFIED_ENGINE_MASTER")
    print("INDEX.json обновлён")
