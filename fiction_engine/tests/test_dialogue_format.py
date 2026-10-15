"""Формат диалога по серии: тире с абзаца или кавычки — сигнал при смене."""
from engine.text_signals import dialogue_format, series_signals

DASH = "\n".join(["Вера вошла."] + [f"— Реплика {i}, — сказала она." for i in range(6)])
QUOTE = "\n".join(["Вера вошла."] + [f"«Реплика {i}», — сказала она." for i in range(6)])
NARR = "Вера шла по набережной. Было тихо.\n\nОна думала о письме."


def test_format_detection():
    assert dialogue_format(DASH) == "тире"
    assert dialogue_format(QUOTE) == "кавычки"
    assert dialogue_format(NARR) == ""               # без реплик формат не определяем


def test_switch_is_signalled():
    prev = [{"number": 3, "content": DASH}, {"number": 4, "content": DASH}]
    sig = [s for s in series_signals(QUOTE, prev) if "Диалог оформлен" in s]
    assert sig == ["Диалог оформлен в кавычках, а в главах 3–4 — через тире с абзаца: приведите к одному виду."]


def test_same_format_or_no_dialogue_is_quiet():
    prev = [{"number": 3, "content": DASH}]
    assert not [s for s in series_signals(DASH, prev) if "Диалог оформлен" in s]
    assert not [s for s in series_signals(NARR, prev) if "Диалог оформлен" in s]
    assert not [s for s in series_signals(QUOTE, [{"number": 3, "content": NARR}]) if "Диалог оформлен" in s]
