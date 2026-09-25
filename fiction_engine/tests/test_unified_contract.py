#!/usr/bin/env python3
"""
Контракт между настройками движка и НАСТОЯЩЕЙ базой UNIFIED_ENGINE_MASTER.

Зачем. Загрузчики находят секции базы по текстовым меткам из
engine_config.py. Если метка не совпала с заголовком файла, загрузчик не
падает: он берёт запасной вариант, например начало файла, то есть раздел
ДРУГОГО поджанра. Модель получает чужой контракт как обязательный, а
тесты на синтетических файлах остаются зелёными. Аудит 2026-09-25
(AUDIT_UNIFIED.md, U1, U5, U7) нашёл так 15 контрактов из 30.

Здесь для каждого из 30 жанровых ключей проверяется, что каждый загрузчик
нашёл секцию именно этого поджанра в реальной базе.

Известные поломки перечислены в KNOWN_BROKEN и помечены xfail(strict=True):
набор остаётся зелёным, пока долг не закрыт, а после починки тест
неожиданно проходит, strict превращает это в падение, и запись нужно
удалить из списка. Так список не может устареть молча.

Без базы тест ПАДАЕТ, а не пропускается: пропуск и есть тот зелёный
набор при неработающем движке, от которого этот файл защищает.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

for _mod in ("openai", "anthropic"):
    sys.modules.setdefault(_mod, MagicMock())

from engine.engine_config import (  # noqa: E402
    CHAR_FULL_KEY_MAP,
    GENRE_KEYWORDS,
    SUBGENRE_CONTRACT_LABELS,
)

KB_PATH = Path(__file__).resolve().parents[2] / "UNIFIED_ENGINE_MASTER"

GENRE_KEYS = sorted(GENRE_KEYWORDS)
MODES = ("quick", "quality", "master")


# ─── Известный долг (AUDIT_UNIFIED.md) ───────────────────────────────────────
# Починили — удалите строку: иначе strict-xfail уронит набор.

KNOWN_BROKEN: dict[str, dict[str, str]] = {
    "contract": {
        # Метка не совпадает с заголовком, раздел в файле есть
        "romance_contemporary":   "метка СОВРЕМЕННЫЙ, в файле СОВРЕМЕННАЯ РОМАНТИКА",
        "romance_historical":     "метка ИСТОРИЧЕСКИЙ, в файле ИСТОРИЧЕСКАЯ РОМАНТИКА",
        "romance_paranormal":     "метка ПАРАНОРМАЛЬНЫЙ, в файле ПАРАНОРМАЛЬНАЯ РОМАНТИКА",
        "thriller_survival":      "метка ВЫЖИВАНИЕ, в файле ТРИЛЛЕР ВЫЖИВАНИЯ",
        "horror_survival":        "метка ВЫЖИВАНИЕ, в файле ХОРРОР ВЫЖИВАНИЯ",
        "detective_cozy":         "метка УЮТНЫЙ, в файле КЛАССИЧЕСКИЙ / COZY",
        "scifi_post_apocalyptic": "метка ПОСТАПОКАЛИПСИС, в файле ДИСТОПИЯ",
        # Раздела в файле нет
        "horror_cosmic":           "нет раздела в horror_contracts.md",
        "horror_gothic":           "нет раздела в horror_contracts.md",
        "fantasy_romantic":        "нет раздела в fantasy_contracts.md",
        "fantasy_sword_sorcery":   "нет раздела в fantasy_contracts.md",
        "detective_psychological": "нет раздела в detective_contracts.md",
        "detective_action":        "нет раздела в detective_contracts.md",
        "scifi_cyberpunk":         "нет раздела в scifi_contracts.md",
        "scifi_steampunk":         "нет раздела в scifi_contracts.md",
    },
    "antagonist": {
        "detective_noir":        "ключа НУАР нет в antagonist_by_genre.md",
        "realism_psychological": "ключа РЕАЛИЗМ нет в antagonist_by_genre.md",
        "realism_social":        "ключа РЕАЛИЗМ нет в antagonist_by_genre.md",
        "realism_family_saga":   "ключа РЕАЛИЗМ нет в antagonist_by_genre.md",
    },
    "trim_marker": {
        "anticliche":  "блок пишется «КЛИШЕ → ЗАМЕНЫ», обрезка ищет «АНТИКЛИШЕ»",
        "voice_check": "блок пишется «ПРОВЕРКА ГОЛОСА», обрезка ищет «ГОЛОС — ПРОВЕРКА»",
    },
}


def _cases(check: str, values):
    """Параметры с strict-xfail для записей из KNOWN_BROKEN[check]."""
    broken = KNOWN_BROKEN.get(check, {})
    return [
        pytest.param(v, marks=pytest.mark.xfail(strict=True, reason=broken[v]))
        if v in broken else v
        for v in values
    ]


@pytest.fixture(scope="module")
def kb() -> Path:
    assert KB_PATH.is_dir(), (
        f"UNIFIED_ENGINE_MASTER не найден: {KB_PATH}. "
        "Контракт с базой не проверить — это ошибка, а не пропуск."
    )
    return KB_PATH


def test_known_broken_refers_to_real_keys():
    """Опечатка в KNOWN_BROKEN не должна молча выключать проверку."""
    for check in ("contract", "antagonist"):
        unknown = set(KNOWN_BROKEN[check]) - set(GENRE_KEYS)
        assert not unknown, f"{check}: нет таких жанров {sorted(unknown)}"


# ─── Файлы, на которые ссылается конфиг ──────────────────────────────────────

@pytest.mark.parametrize("genre_key", GENRE_KEYS)
def test_catalog_exists(kb, genre_key):
    assert (kb / "04_GENRE_ENGINE" / "catalog" / f"{genre_key}.json").is_file()


@pytest.mark.parametrize("genre_key", GENRE_KEYS)
def test_character_profile_is_own_file(kb, genre_key):
    """Профиль берётся из своего файла, а не из запасного файла семейства."""
    from engine.engine_loaders_genre import load_character_profile
    fname = CHAR_FULL_KEY_MAP.get(genre_key)
    assert fname, f"{genre_key}: нет записи в CHAR_FULL_KEY_MAP"
    assert (kb / "05_CHARACTER_ENGINE" / "profiles" / "GENRE" / fname).is_file()
    assert load_character_profile(kb, genre_key).strip()


# ─── Секции поджанра ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("genre_key", _cases("contract", GENRE_KEYS))
def test_contract_is_own_subgenre(kb, genre_key):
    """
    Контракт начинается с раздела этого поджанра.

    Запасной путь загрузчика отдаёт начало файла: первой строкой там идёт
    «# Читательский контракт: …», а за ней раздел первого поджанра в файле.
    """
    from engine.engine_loaders_genre import load_genre_contract
    label = SUBGENRE_CONTRACT_LABELS.get(genre_key)
    assert label, f"{genre_key}: нет метки в SUBGENRE_CONTRACT_LABELS"
    lines = load_genre_contract(kb, genre_key).splitlines()
    assert len(lines) > 1, f"{genre_key}: контракт пуст"
    first = lines[1]
    assert first.startswith("## ") and label.upper() in first.upper(), (
        f"{genre_key}: ожидался раздел «{label}», получено «{first}»"
    )


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("genre_key", GENRE_KEYS)
def test_genre_prompt_is_own_subgenre(kb, genre_key, mode):
    """Жанровые правила найдены для поджанра, а не общие правила семейства."""
    from engine.engine_loaders_genre import load_genre_prompt
    out = load_genre_prompt(kb, genre_key, mode)
    assert out.startswith(f"ПРАВИЛА ЖАНРА ({genre_key}):"), (
        f"{genre_key}/{mode}: блок поджанра не найден, начало: {out[:60]!r}"
    )


@pytest.mark.parametrize("genre_key", GENRE_KEYS)
def test_arc_found(kb, genre_key):
    from engine.engine_loaders_genre import load_arc_hint
    assert load_arc_hint(kb, genre_key).strip()


@pytest.mark.parametrize("genre_key", _cases("antagonist", GENRE_KEYS))
def test_antagonist_found(kb, genre_key):
    from engine.engine_loaders_genre import _load_antagonist_section
    family, sub = genre_key.split("_", 1)
    assert _load_antagonist_section(kb, family, sub).strip()


# ─── Маркеры блоков в собранном промпте ──────────────────────────────────────

TRIM_BLOCKS = ["writing_core", "pattern_lib", "symbolism", "voice_check", "anticliche"]


@pytest.fixture(scope="module")
def removed_on_trim(kb):
    """
    Какие блоки обрезка контекста находит в реально собранном блоке движка.

    Обрезка ищет блоки по маркерам. Если маркер разошёлся с заголовком,
    блок нельзя удалить, и при нехватке места срез приходится на State.
    """
    import engine.engine_loaders as loaders
    from engine.pipeline_tasks import _truncate_context_by_blocks
    from engine.unified_engine import build_engine_context

    mp = pytest.MonkeyPatch()
    mp.setattr(loaders, "get_engine_path", lambda: kb)
    try:
        ctx = build_engine_context(
            "классический детектив", "master", model_value="claude",
            include_dialectics=True,
            task_text="диалог на допросе, описание комнаты, финал главы",
        )
    finally:
        mp.undo()
    assert ctx, "блок движка пуст"
    _, removed = _truncate_context_by_blocks(ctx, max_chars=1)
    return set(removed)


@pytest.mark.parametrize("block", _cases("trim_marker", TRIM_BLOCKS))
def test_trim_finds_block(removed_on_trim, block):
    assert block in removed_on_trim
