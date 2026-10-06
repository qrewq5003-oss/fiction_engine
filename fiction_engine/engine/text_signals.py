"""
text_signals.py — проверки готовой главы: сигналы автору, без правки текста.

Зачем. Правило в промпте лечит привычку одной модели: цепочки «…, и …, и …»
— привычка GLM (2.23 на 1000 слов против 0.20 у Kimi и 0.07 у DeepSeek),
сравнения «словно / будто» — DeepSeek (2.51 против 0.86 и 1.06), замер
06.10 (bench/ab-panel-noengine-2026-10-06.json). Модели меняются, и
подгонять промпт под одну неправильно. Проверка самого текста работает при
любом генераторе: она смотрит не на модель, а на то, что получилось.

Пороги — по 9 главам из 10 в наборах базовых глав трёх генераторов панели
(GLM-5.3, Kimi K2.5, DeepSeek V4 Pro, 64 главы): сигнал получает глава,
которая выделяется на фоне остальных, какая бы модель её ни написала.
Штампы, которых в наборах нет вовсе, сигналят с первого случая.

Сигнал — подсказка, а не ошибка: автор решает, править ли.
"""

from __future__ import annotations

import re
from collections import Counter

# Пороги на 1000 слов (p90 по 64 главам панели, 06.10)
SIMILES_PER_1000 = 2.6
NOT_BUT_PER_1000 = 2.5
ELLIPSIS_PER_1000 = 2.4
REPEAT_WORD_PER_1000 = 5.5
REPEAT_WORD_MIN = 12        # в короткой главе пять повторов — ещё не привычка
SAME_START_RUN = 5          # фраз подряд с одного слова; у 9 из 10 глав не больше 4

_SIMILE = re.compile(r"\b(словно|будто|как будто)\b", re.I)
_NOT_BUT = re.compile(r"[^.!?…\n]{0,30}\bне\s+[^.,!?—\n]{1,40},\s+а\s[^.,!?…\n]{0,40}", re.I)
_CLICHE = re.compile(
    r"[^.!?…\n]*\b("
    r"(почувствовал\w*|ощутил\w*)\s+(страх|тревог\w*|радост\w*|облегчени\w*|злост\w*|гнев\w*|"
    r"стыд\w*|боль|грусть|печаль|ужас|отчаяни\w*|надежд\w*)"
    r"|сердце (пропустил\w* удар|сжал\w*|ухнул\w*)|дыхание перехватил\w*|"
    r"холодок пробежал\w*|по спине пробежал\w*"
    r")[^.!?…\n]*", re.I)
_STOP = set(
    "и в во не что он она они его её ее их на с со к по за из у о об от до как это был "
    "была было были так но а же то ли бы ни да нет уже ещё еще только когда если чтобы "
    "потому где там тут здесь всё все весь вся себя себе свой своя свои мне меня мы вы "
    "ты я этот эта эти того тоже очень может можно было есть".split())


def _narration(text: str) -> str:
    return "\n".join(l for l in text.splitlines()
                     if l.strip() and not l.strip().startswith(("—", "–", "-")))


def _example(fragment: str, n: int = 90) -> str:
    s = re.sub(r"\s+", " ", fragment).strip()
    return f"«{s[:n]}{'…' if len(s) > n else ''}»"


def _repeat_word(narr: str, k_words: float) -> str:
    words = re.findall(r"[А-ЯЁа-яё]+", narr)
    caps: Counter[str] = Counter(w.lower() for w in words if w[0].isupper())
    low: Counter[str] = Counter(w for w in words if w.islower())
    # Имя пишется с заглавной чаще, чем со строчной, — имени положено повторяться
    cand = [(n, w) for w, n in low.items()
            if len(w) > 4 and w not in _STOP and caps[w] <= n]
    if not cand:
        return ""
    n, word = max(cand)
    if n >= REPEAT_WORD_MIN and n / k_words > REPEAT_WORD_PER_1000:
        return f"Слово «{word}» повторяется {n} раз — чаще, чем в 9 главах из 10."
    return ""


def _same_start(narr: str) -> str:
    sents = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", narr) if s.strip()]
    best, run, prev, at = 1, 1, None, ""
    for s in sents:
        first = (re.findall(r"[А-ЯЁа-яё]+", s)[:1] or [""])[0].lower()
        run = run + 1 if first and first == prev else 1
        if run > best:
            best, at = run, first
        prev = first
    if best >= SAME_START_RUN:
        return f"{best} фраз подряд начинаются с «{at.capitalize()}» — однообразный ритм."
    return ""


def chapter_signals(text: str) -> list[str]:
    """Сигналы автору по готовой главе. Пусто — глава ничем не выделяется."""
    text = text or ""
    k = max(len(text.split()), 1) / 1000
    narr = _narration(text)
    out: list[str] = []

    sim = _SIMILE.findall(narr)
    if len(sim) / k > SIMILES_PER_1000:
        out.append(f"Сравнений «словно / будто» — {len(sim)}, чаще, чем в 9 главах из 10.")
    nb = _NOT_BUT.findall(narr)
    if len(nb) / k > NOT_BUT_PER_1000:
        out.append(f"Оборотов «не X, а Y» — {len(nb)}, чаще, чем в 9 главах из 10. "
                   f"Например: {_example(nb[0])}.")
    cl = [m.group() for m in _CLICHE.finditer(narr)]
    if cl:
        out.append(f"Штамп эмоции ({len(cl)}): {_example(cl[0])} — чувство названо или "
                   f"передано готовой формулой.")
    ell = text.count("…") + text.count("...")
    if ell / k > ELLIPSIS_PER_1000:
        out.append(f"Многоточий — {ell}, чаще, чем в 9 главах из 10.")
    for note in (_repeat_word(narr, k), _same_start(narr)):
        if note:
            out.append(note)
    # Цепочки «…, и …, и …» — со своей нормой (одна на страницу)
    from .pipeline_steps import and_chains_note
    chains = and_chains_note(text)
    if chains:
        out.append(chains)
    return out
