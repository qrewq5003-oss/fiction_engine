"""
llm_stubs.py — заглушки LLM для тестов.

Живут отдельным модулем, а не в conftest: conftest не импортируется
по имени из тест-модулей, а эти помощники нужны именно импортом.
"""

from unittest.mock import patch

import pytest

# # Позиционный список ответов (side_effect=[gen, critique, judge]) ломается,
# как только пайплайн делает лишний вызов: шаг generate тянет за собой ещё
# и анализ главы, а иногда проверку дрейфа голоса. Список исчерпывается —
# StopIteration, причём в тесте, который проверяет совсем другое.
#
# Диспетчер по системному промпту устойчив к числу вызовов и выражает
# намерение прямо: «на роль критика ответить вот этим».

# Маркеры подобраны так, чтобы работать при любом жанре: системные промпты
# генератора и критика перестраиваются под жанр («Ты — автор коммерческого
# фэнтези…»), поэтому опознавательный признак берётся из неизменной части.
_ROLE_MARKS = (
    # порядок важен: «профессиональный редактор и автор» (редактор) должен
    # проверяться раньше остальных ролей со словом «редактор»
    ("judge",    "главный редактор серии"),
    ("edit",     "профессиональный редактор и автор"),
    ("critique", "литературный редактор"),
    ("generate", "Пишешь художественн"),
)


def llm_role(system: str) -> str:
    """Определить роль вызова по системному промпту."""
    s = system or ""
    for role, mark in _ROLE_MARKS:
        if mark in s:
            return role
    return "other"


def scripted_llm(generate="", critique="", judge="", edit="", other="{}"):
    """
    Мок engine.pipeline._call, отвечающий по роли вызова.

    Значение роли — строка либо список строк. Список расходуется по одному
    ответу на вызов этой роли: так задаются сценарии, где ответ меняется
    между итерациями (критик сначала браковал, после правки принял).
    Когда список исчерпан, повторяется последний элемент — лишний вызов
    не должен ронять тест, который проверяет совсем другое.

    other — ответ для служебных вызовов (анализ главы, дрейф, префлайт).
    По умолчанию пустой JSON: разборщики принимают его без исключения.

    Использование:
        with patch("engine.pipeline._call",
                   side_effect=scripted_llm(generate=TEXT, critique=C, judge=J)):

        # сценарий по итерациям:
        scripted_llm(generate=TEXT, critique=[REJECT, ACCEPT],
                     judge=[REJECT, ACCEPT], edit=EDITED)
    """
    table = {"generate": generate, "critique": critique,
             "judge": judge, "edit": edit, "other": other}
    used = {role: 0 for role in table}

    def _resolve(value, user):
        # значение может быть функцией от текста запроса — так удобнее
        # строить ответ, зависящий от промпта
        return value(user) if callable(value) else value

    def _call(model_value, system, user, max_tokens=6000, prefill=""):
        role = llm_role(system)
        value = table[role]
        if isinstance(value, (list, tuple)):
            if not value:
                return ""
            i = min(used[role], len(value) - 1)
            used[role] += 1
            return _resolve(value[i], user)
        return _resolve(value, user)

    return _call


@pytest.fixture
def no_api_keys():
    """
    Ключей нет — но код не должен из-за этого падать в тестах,
    которые проверяют логику, а не работу с API.
    """
    with patch("engine.pipeline._get_keys", return_value={
        "anthropic": "test", "nano": "test", "openai": "test",
        "gemini": "test", "deepseek": "test",
    }):
        yield
