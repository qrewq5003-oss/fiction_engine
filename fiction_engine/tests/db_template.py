"""
Свежая БД для теста — копией шаблона, а не init_db.

init_db (схема и миграции) — около 50 мс локально и до секунды на раннере
CI, а зовут её перед каждым тестом и в каждом примере Hypothesis. Шаблон
собирается init_db один раз на процесс (у каждого процесса pytest-xdist —
свой), дальше файл копируется: полмиллисекунды.
"""
import shutil
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

_template: Path | None = None


def fresh_db(path: Path) -> None:
    """Положить в path пустую БД с полной схемой."""
    global _template
    if _template is None:
        from engine.db_core import init_db
        tpl = Path(tempfile.mkdtemp(prefix="fe_db_template_")) / "template.db"
        with patch("engine.db_core.DB_PATH", tpl):
            init_db()
        # WAL: всё из журнала — в основной файл, чтобы копировать один файл
        conn = sqlite3.connect(tpl)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        _template = tpl
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(_template, path)
