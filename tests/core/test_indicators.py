from __future__ import annotations

from decimal import Decimal

import pytest

from src.core import (
    Candle,
    CandleSeries,
    IndicatorCache,
    calculate_atr,
    calculate_ema,
    calculate_rsi,
    calculate_volume_moving_average,
    calculate_volume_ratio,
)


def _reference_ema(values: list[float], period: int) -> float:
    if len(values) < period:
        raise ValueError("not enough values")
    ema = sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    for price in values[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def _reference_rsi(values: list[float], period: int) -> float:
    if len(values) <= period:
        raise ValueError("not enough values")
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


def _reference_atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    if len(highs) <= period:
        raise ValueError("not enough values")
    true_ranges: list[float] = []
    prev_close = closes[0]
    for high, low, close in zip(highs[1:], lows[1:], closes[1:]):
        range1 = high - low
        range2 = abs(high - prev_close)
        range3 = abs(low - prev_close)
        true_ranges.append(max(range1, range2, range3))
        prev_close = close
    atr = sum(true_ranges[:period]) / period
    for value in true_ranges[period:]:
        atr = ((atr * (period - 1)) + value) / period
    return atr


def test_candle_series_sorted(btc_krw_candles: list[Candle]) -> None:
    series = CandleSeries("BTC_KRW", btc_krw_candles)
    ordered = list(series.candles())
    assert ordered == sorted(ordered, key=lambda candle: candle.timestamp)


def test_indicator_values_match_reference(btc_krw_candles: list[Candle]) -> None:
    subset = btc_krw_candles[:150]
    closes = [float(candle.close) for candle in subset]
    highs = [float(candle.high) for candle in subset]
    lows = [float(candle.low) for candle in subset]

    ema20 = calculate_ema(subset, 20)
    ema60 = calculate_ema(subset, 60)
    rsi14 = calculate_rsi(subset, 14)
    atr14 = calculate_atr(subset, 14)

    assert float(ema20) == pytest.approx(_reference_ema(closes, 20), rel=1e-6)
    assert float(ema60) == pytest.approx(_reference_ema(closes, 60), rel=1e-6)
    assert float(rsi14) == pytest.approx(_reference_rsi(closes, 14), rel=1e-6)
    assert float(atr14) == pytest.approx(_reference_atr(highs, lows, closes, 14), rel=1e-6)


def test_volume_metrics(btc_krw_candles: list[Candle]) -> None:
    subset = btc_krw_candles[:150]
    ma = calculate_volume_moving_average(subset, 10)
    ratio = calculate_volume_ratio(subset, 10)
    volumes = [Decimal(candle.volume) for candle in subset[-10:]]
    expected_ma = sum(volumes) / Decimal("10")
    expected_ratio = Decimal(subset[-1].volume) / expected_ma
    assert ma == expected_ma
    assert ratio == expected_ratio


def test_indicator_cache_reuses_values(btc_krw_candles: list[Candle]) -> None:
    cache = IndicatorCache(max_size=4)
    subset = btc_krw_candles[:120]
    calls = {"ema": 0}

    def compute() -> Decimal:
        calls["ema"] += 1
        return calculate_ema(subset, 20)

    first = cache.get_or_compute("BTC_KRW", "EMA20", 20, subset, compute)
    second = cache.get_or_compute("BTC_KRW", "EMA20", 20, subset, compute)
    assert first == second
    assert calls["ema"] == 1
