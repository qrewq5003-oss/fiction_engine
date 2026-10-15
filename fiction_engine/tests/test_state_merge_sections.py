"""Слияние анализа главы в State: память «кто что знает», открытые вопросы, линии."""
from engine.state_merge import (_Changes, _merge_memory, _merge_open_questions,
                                _merge_side_lines, _section_items)

MEMORY_TEMPLATE = ("## КТО ЧТО ЗНАЕТ\n\n### [Имя]\nЗНАЕТ: []\nНЕ_ЗНАЕТ: []\nДУМАЕТ_ЧТО_ЗНАЕТ: []\n\n---\n\n"
                   "## СЕКРЕТЫ И ТАЙНЫ\n\n## ИНФОРМАЦИОННЫЙ БАЛАНС (кто знает больше всех)\n")
PLOT_TEMPLATE = ("## ОСНОВНАЯ ЛИНИЯ\n\nСТАТУС: активна\nГДЕ_СЕЙЧАС: []\nСЛЕДУЮЩИЙ_ШАГ: найти Павла\n\n---\n\n"
                 "## ВТОРОСТЕПЕННЫЕ ЛИНИИ\n\n---\n\n## ОТКРЫТЫЕ ВОПРОСЫ\n\n---\n\n## ЧТО НЕЛЬЗЯ ЗАБЫТЬ\n\n"
                 "## ДЕТАЛИ СЕРИИ\n- гл.1: каска Томаша — наклейка с утёнком\n")


def test_memory_section_created_and_placeholder_removed():
    out = _merge_memory([{"name": "Лукаш", "knows": ["команда погибла", "видит сетку на коже"]}],
                        MEMORY_TEMPLATE, _Changes())
    assert "### Лукаш\nЗНАЕТ:\n- команда погибла\n- видит сетку на коже" in out
    assert "[Имя]" not in out and "## СЕКРЕТЫ И ТАЙНЫ" in out          # раньше знания отбрасывались
    out2 = _merge_memory([{"name": "Павел", "knows": ["Лукаш выжил"]}], out, _Changes())
    assert "### Павел" in out2 and "### Лукаш" in out2


def test_memory_appends_without_repeats_and_caps():
    from engine.state_merge import MEMORY_KNOWS_MAX
    out = _merge_memory([{"name": "Лукаш", "knows": ["факт 0"]}], MEMORY_TEMPLATE, _Changes())
    out = _merge_memory([{"name": "Лукаш", "knows": ["факт 0", "факт 1"]}], out, _Changes())
    assert out.count("- факт 0") == 1 and "- факт 1" in out
    for i in range(2, 40):
        out = _merge_memory([{"name": "Лукаш", "knows": [f"факт {i}"]}], out, _Changes())
    knows = [l for l in out.split("НЕ_ЗНАЕТ")[0].splitlines() if l.startswith("- ")]
    assert len(knows) == MEMORY_KNOWS_MAX and knows[-1] == "- факт 39"


def test_open_questions_go_to_their_section():
    out = _merge_open_questions(["Кто говорил о Завесе?", "Что за красный источник?"], PLOT_TEMPLATE, 2, _Changes())
    assert _section_items(out, "## ОТКРЫТЫЕ ВОПРОСЫ") == ["гл.2: Кто говорил о Завесе?", "гл.2: Что за красный источник?"]
    out = _merge_open_questions(["кто говорил о Завесе?"], out, 3, _Changes())     # повтор не дублируется
    assert len(_section_items(out, "## ОТКРЫТЫЕ ВОПРОСЫ")) == 2
    assert "- гл.1: каска Томаша" in out and "СЛЕДУЮЩИЙ_ШАГ: найти Павла" in out   # остальное не тронуто


def test_side_lines_added_and_closed():
    out = _merge_side_lines({"новые_линии": ["расследование Незвала"]}, PLOT_TEMPLATE, 2, _Changes())
    assert _section_items(out, "## ВТОРОСТЕПЕННЫЕ ЛИНИИ") == ["расследование Незвала (с гл.2)"]
    out = _merge_side_lines({"закрытые_линии": ["Расследование Незвала"]}, out, 5, _Changes())
    assert _section_items(out, "## ВТОРОСТЕПЕННЫЕ ЛИНИИ") == ["расследование Незвала (закрыта в гл.5)"]


def test_empty_or_placeholder_values_change_nothing():
    assert _merge_open_questions(["", "[]"], PLOT_TEMPLATE, 2, _Changes()) == PLOT_TEMPLATE
    assert _merge_side_lines({"новые_линии": []}, PLOT_TEMPLATE, 2, _Changes()) == PLOT_TEMPLATE
    assert _merge_memory([{"name": "Лукаш", "knows": []}], MEMORY_TEMPLATE, _Changes()) == MEMORY_TEMPLATE
