#!/usr/bin/env python3
"""
Цены моделей и расчёт стоимости вызова.

Зачем. Движок не знал, во что обходится глава. Оценить постфактум было
нечем: ни токенов, ни стоимости никуда не писалось, и на вопрос «сколько
потрачено» приходилось считать вызовы по памяти и умножать на прикидку.

Отдельный модуль, а не константы в pipeline_config: цены меняются
независимо от всего остального и обновляются по документации провайдера.

Точность. Для Anthropic цена известна и считается по токенам из ответа.
Для nano-gpt — перепродавец со своими тарифами: он сам возвращает поле
`cost` в `usage`, и оно используется как есть. Когда ни цены, ни поля
нет, запись всё равно делается: токены известны, а стоимость остаётся
пустой — это честнее, чем подставить выдуманный тариф.
"""

from __future__ import annotations

# Цены Anthropic в долларах за миллион токенов, на 2026-09-22.
# Источник — документация API; сверять при обновлении моделей.
ANTHROPIC_PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5":  (1.00,  5.00),
    "claude-sonnet-5":   (2.00, 10.00),
    "claude-opus-5":     (5.00, 25.00),
    "claude-fable-5-1":  (10.00, 50.00),
}


def _match_price(model_id: str) -> tuple[float, float] | None:
    """
    Цена по идентификатору модели.

    Идентификаторы приходят с датой («claude-haiku-4-5-20251001») и без.
    Сравнение по префиксу, самое длинное совпадение — чтобы
    «claude-opus-5» не поймал «claude-opus-5-…» чужой модели раньше
    точного ключа.
    """
    hits = [(k, v) for k, v in ANTHROPIC_PRICES.items() if model_id.startswith(k)]
    if not hits:
        return None
    return max(hits, key=lambda kv: len(kv[0]))[1]


def estimate_cost(provider: str, model_id: str,
                  input_tokens: int, output_tokens: int,
                  reported_cost: float | None = None) -> float | None:
    """
    Стоимость вызова в долларах. None — посчитать нечем.

    reported_cost (то, что вернул провайдер) имеет приоритет над нашей
    таблицей: провайдер знает свой тариф точнее, включая скидки и
    кеширование.
    """
    if reported_cost is not None and reported_cost > 0:
        return float(reported_cost)

    if provider == "anthropic_direct":
        price = _match_price(model_id)
        if price:
            pin, pout = price
            return input_tokens / 1e6 * pin + output_tokens / 1e6 * pout

    return None
