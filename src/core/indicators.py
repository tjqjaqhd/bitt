"""기술적 지표 계산과 캔들 자료구조를 제공하는 모듈."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from decimal import Decimal, localcontext
from typing import Iterable, Sequence

from src.utils.time_utils import ensure_timezone


@dataclass(frozen=True)
class Candle:
    """단일 캔들(OHLCV) 데이터를 표현한다."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @classmethod
    def from_raw(
        cls,
        symbol: str,
        payload: Sequence[object],
        *,
        tz: tzinfo | str = timezone.utc,
    ) -> "Candle":
        """빗썸 캔들 API 응답 형식을 파싱한다."""

        if len(payload) < 6:
            raise ValueError("캔들 데이터는 최소 6개의 필드를 포함해야 합니다.")
        timestamp_ms = int(payload[0])
        base_ts = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        if isinstance(tz, str):
            ts = ensure_timezone(base_ts, tz)
        else:
            ts = base_ts.astimezone(tz)
        return cls(
            symbol=symbol,
            timestamp=ts,
            open=Decimal(str(payload[1])),
            close=Decimal(str(payload[2])),
            high=Decimal(str(payload[3])),
            low=Decimal(str(payload[4])),
            volume=Decimal(str(payload[5])),
        )


class CandleSeries:
    """정렬된 캔들 시퀀스를 관리한다."""

    def __init__(self, symbol: str, candles: Iterable[Candle] | None = None) -> None:
        self.symbol = symbol
        self._candles: list[Candle] = []
        if candles:
            self.extend(candles)

    def append(self, candle: Candle) -> None:
        if candle.symbol != self.symbol:
            raise ValueError("서로 다른 심볼의 캔들을 한 시퀀스에 추가할 수 없습니다.")
        self._candles.append(candle)
        self._candles.sort(key=lambda item: item.timestamp)

    def extend(self, candles: Iterable[Candle]) -> None:
        for candle in candles:
            self.append(candle)

    def candles(self) -> Sequence[Candle]:
        return tuple(self._candles)

    def tail(self, count: int) -> Sequence[Candle]:
        return tuple(self._candles[-count:])

    def __len__(self) -> int:  # pragma: no cover - 간단한 위임
        return len(self._candles)

    def __iter__(self):  # pragma: no cover - 간단한 위임
        return iter(self._candles)


def _ensure_length(name: str, sequence: Sequence[object], period: int) -> None:
    if len(sequence) < period:
        raise ValueError(f"{name} 계산을 위해 최소 {period}개의 캔들이 필요합니다.")


def _ema(values: Sequence[Decimal], period: int) -> Decimal:
    _ensure_length("EMA", values, period)
    with localcontext() as ctx:
        ctx.prec = 28
        ema = sum(values[:period]) / Decimal(period)
        multiplier = Decimal("2") / (Decimal(period) + 1)
        for price in values[period:]:
            ema = (price - ema) * multiplier + ema
    return ema


def calculate_ema(candles: Sequence[Candle], period: int) -> Decimal:
    """마지막 캔들을 기준으로 EMA 값을 계산한다."""

    closes = [candle.close for candle in candles]
    return _ema(closes, period)


def calculate_rsi(candles: Sequence[Candle], period: int) -> Decimal:
    _ensure_length("RSI", candles, period + 1)
    closes = [candle.close for candle in candles]
    with localcontext() as ctx:
        ctx.prec = 28
        gains: list[Decimal] = []
        losses: list[Decimal] = []
        for i in range(1, period + 1):
            change = closes[i] - closes[i - 1]
            gains.append(max(change, Decimal("0")))
            losses.append(max(-change, Decimal("0")))
        avg_gain = sum(gains) / Decimal(period)
        avg_loss = sum(losses) / Decimal(period)
        for i in range(period + 1, len(closes)):
            change = closes[i] - closes[i - 1]
            gain = max(change, Decimal("0"))
            loss = max(-change, Decimal("0"))
            avg_gain = ((avg_gain * (period - 1)) + gain) / Decimal(period)
            avg_loss = ((avg_loss * (period - 1)) + loss) / Decimal(period)
        if avg_loss == 0:
            return Decimal("100")
        rs = avg_gain / avg_loss
        return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def calculate_atr(candles: Sequence[Candle], period: int) -> Decimal:
    _ensure_length("ATR", candles, period + 1)
    true_ranges: list[Decimal] = []
    with localcontext() as ctx:
        ctx.prec = 28
        prev_close = candles[0].close
        for candle in candles[1:]:
            range1 = candle.high - candle.low
            range2 = abs(candle.high - prev_close)
            range3 = abs(candle.low - prev_close)
            true_ranges.append(max(range1, range2, range3))
            prev_close = candle.close
        atr = sum(true_ranges[:period]) / Decimal(period)
        for tr in true_ranges[period:]:
            atr = ((atr * (period - 1)) + tr) / Decimal(period)
    return atr


def calculate_volume_moving_average(candles: Sequence[Candle], period: int) -> Decimal:
    _ensure_length("거래량 이동평균", candles, period)
    volumes = [candle.volume for candle in candles[-period:]]
    with localcontext() as ctx:
        ctx.prec = 28
        return sum(volumes) / Decimal(period)


def calculate_volume_ratio(candles: Sequence[Candle], period: int) -> Decimal:
    _ensure_length("거래량 비율", candles, period)
    volume_ma = calculate_volume_moving_average(candles, period)
    if volume_ma == 0:
        return Decimal("0")
    with localcontext() as ctx:
        ctx.prec = 28
        return candles[-1].volume / volume_ma


class IndicatorCache:
    """지표 계산 결과를 메모리에서 캐싱한다."""

    def __init__(self, max_size: int = 512) -> None:
        from collections import OrderedDict
        from threading import Lock

        self._max_size = max_size
        self._store: "OrderedDict[tuple[str, str, int, datetime], Decimal]" = OrderedDict()
        self._lock = Lock()

    def get_or_compute(
        self,
        symbol: str,
        indicator: str,
        period: int,
        candles: Sequence[Candle],
        compute: callable[[], Decimal],
    ) -> Decimal:
        key = (symbol, indicator, period, candles[-1].timestamp)
        with self._lock:
            if key in self._store:
                value = self._store.pop(key)
                self._store[key] = value
                return value
            value = compute()
            self._store[key] = value
            if len(self._store) > self._max_size:
                self._store.popitem(last=False)
            return value


__all__ = [
    "Candle",
    "CandleSeries",
    "IndicatorCache",
    "calculate_atr",
    "calculate_ema",
    "calculate_rsi",
    "calculate_volume_moving_average",
    "calculate_volume_ratio",
]
