"""신호 생성 엔진과 관련 타입 정의."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Sequence

from src.data.models import SignalType
from src.utils.logger import get_logger

from .indicators import (
    Candle,
    IndicatorCache,
    calculate_atr,
    calculate_ema,
    calculate_rsi,
    calculate_volume_ratio,
)
from .parameters import StrategyParameters
from .risk import PortfolioState


@dataclass
class SignalDecision:
    """전략 신호 결과."""

    symbol: str
    signal_type: SignalType
    price: Decimal
    strength: Decimal
    rsi: Decimal | None
    atr: Decimal | None
    volume_ratio: Decimal | None
    reasons: list[str] = field(default_factory=list)
    timestamp: datetime | None = None


class SignalGenerator:
    """EMA/RSI/ATR 기반 매매 신호 생성기."""

    def __init__(self, indicator_cache: IndicatorCache | None = None) -> None:
        self._cache = indicator_cache or IndicatorCache()
        self._logger = get_logger(__name__)

    def _compute_ema(self, symbol: str, candles: Sequence[Candle], period: int) -> Decimal:
        return self._cache.get_or_compute(
            symbol,
            f"EMA_{period}",
            period,
            candles,
            lambda: calculate_ema(candles, period),
        )

    def _compute_previous_ema(self, symbol: str, candles: Sequence[Candle], period: int) -> Decimal | None:
        if len(candles) <= period:
            return None
        return calculate_ema(candles[:-1], period)

    def _compute_rsi(self, symbol: str, candles: Sequence[Candle], period: int) -> Decimal:
        return self._cache.get_or_compute(
            symbol,
            f"RSI_{period}",
            period,
            candles,
            lambda: calculate_rsi(candles, period),
        )

    def _compute_atr(self, symbol: str, candles: Sequence[Candle], period: int) -> Decimal:
        return self._cache.get_or_compute(
            symbol,
            f"ATR_{period}",
            period,
            candles,
            lambda: calculate_atr(candles, period),
        )

    def _compute_volume_ratio(self, symbol: str, candles: Sequence[Candle], period: int) -> Decimal:
        return self._cache.get_or_compute(
            symbol,
            f"VOLR_{period}",
            period,
            candles,
            lambda: calculate_volume_ratio(candles, period),
        )

    def _build_decision(
        self,
        *,
        symbol: str,
        signal_type: SignalType,
        price: Decimal,
        strength: Decimal,
        rsi: Decimal | None,
        atr: Decimal | None,
        volume_ratio: Decimal | None,
        reasons: list[str],
        timestamp: datetime,
    ) -> SignalDecision:
        with localcontext() as ctx:
            ctx.prec = 28
            clamped_strength = max(min(strength, Decimal("1")), Decimal("0"))
        decision = SignalDecision(
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            strength=clamped_strength,
            rsi=rsi,
            atr=atr,
            volume_ratio=volume_ratio,
            reasons=reasons,
            timestamp=timestamp,
        )
        return decision

    def _hold(self, symbol: str, price: Decimal, timestamp: datetime, *, rsi: Decimal | None, atr: Decimal | None, volume_ratio: Decimal | None) -> SignalDecision:
        return self._build_decision(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            price=price,
            strength=Decimal("0"),
            rsi=rsi,
            atr=atr,
            volume_ratio=volume_ratio,
            reasons=["조건 불충족"],
            timestamp=timestamp,
        )

    def generate(
        self,
        *,
        symbol: str,
        candles: Sequence[Candle],
        portfolio: PortfolioState,
        parameters: StrategyParameters,
    ) -> SignalDecision:
        if not candles:
            raise ValueError("캔들 데이터가 필요합니다.")
        price = candles[-1].close
        timestamp = candles[-1].timestamp
        try:
            ema_short = self._compute_ema(symbol, candles, parameters.short_ema_period)
            ema_long = self._compute_ema(symbol, candles, parameters.long_ema_period)
            prev_short = self._compute_previous_ema(symbol, candles, parameters.short_ema_period)
            prev_long = self._compute_previous_ema(symbol, candles, parameters.long_ema_period)
            rsi = self._compute_rsi(symbol, candles, parameters.rsi_period)
            atr = self._compute_atr(symbol, candles, parameters.atr_period)
            volume_ratio = self._compute_volume_ratio(symbol, candles, parameters.volume_ma_period)
        except ValueError as exc:
            self._logger.warning("지표 계산 실패", exc_info=exc)
            return self._hold(symbol, price, timestamp, rsi=None, atr=None, volume_ratio=None)

        position = portfolio.get(symbol)
        if position:
            return self._evaluate_sell(
                symbol=symbol,
                price=price,
                timestamp=timestamp,
                ema_short=ema_short,
                ema_long=ema_long,
                prev_short=prev_short,
                prev_long=prev_long,
                rsi=rsi,
                atr=atr,
                volume_ratio=volume_ratio,
                position_avg=position.avg_price,
                parameters=parameters,
                candles=candles,
            )
        return self._evaluate_buy(
            symbol=symbol,
            price=price,
            timestamp=timestamp,
            ema_short=ema_short,
            ema_long=ema_long,
            prev_short=prev_short,
            prev_long=prev_long,
            rsi=rsi,
            atr=atr,
            volume_ratio=volume_ratio,
            parameters=parameters,
        )

    def _evaluate_buy(
        self,
        *,
        symbol: str,
        price: Decimal,
        timestamp: datetime,
        ema_short: Decimal,
        ema_long: Decimal,
        prev_short: Decimal | None,
        prev_long: Decimal | None,
        rsi: Decimal,
        atr: Decimal,
        volume_ratio: Decimal,
        parameters: StrategyParameters,
    ) -> SignalDecision:
        reasons: list[str] = []
        golden_cross = (
            prev_short is not None
            and prev_long is not None
            and prev_short <= prev_long
            and ema_short > ema_long
        )
        if golden_cross:
            reasons.append("EMA 골든크로스")
        rsi_ok = parameters.rsi_buy_min <= rsi <= parameters.rsi_buy_max
        if rsi_ok:
            reasons.append("RSI 필터 통과")
        volume_ok = volume_ratio >= parameters.volume_ratio_threshold
        if volume_ok:
            reasons.append("거래량 증가 확인")
        if not (golden_cross and rsi_ok and volume_ok):
            return self._hold(symbol, price, timestamp, rsi=rsi, atr=atr, volume_ratio=volume_ratio)
        components: list[Decimal] = []
        with localcontext() as ctx:
            ctx.prec = 28
            components.append((ema_short - ema_long) / ema_long)
            span = parameters.rsi_buy_max - parameters.rsi_buy_min
            components.append((rsi - parameters.rsi_buy_min) / span)
            components.append(min(volume_ratio / parameters.volume_ratio_threshold, Decimal("2")))
            strength = sum(components) / Decimal(len(components))
        return self._build_decision(
            symbol=symbol,
            signal_type=SignalType.BUY,
            price=price,
            strength=strength,
            rsi=rsi,
            atr=atr,
            volume_ratio=volume_ratio,
            reasons=reasons,
            timestamp=timestamp,
        )

    def _evaluate_sell(
        self,
        *,
        symbol: str,
        price: Decimal,
        timestamp: datetime,
        ema_short: Decimal,
        ema_long: Decimal,
        prev_short: Decimal | None,
        prev_long: Decimal | None,
        rsi: Decimal,
        atr: Decimal,
        volume_ratio: Decimal,
        position_avg: Decimal,
        parameters: StrategyParameters,
        candles: Sequence[Candle],
    ) -> SignalDecision:
        reasons: list[str] = []
        death_cross = (
            prev_short is not None
            and prev_long is not None
            and prev_short >= prev_long
            and ema_short < ema_long
        )
        if death_cross:
            reasons.append("EMA 데드크로스")
        target_price = position_avg * (Decimal("1") + parameters.target_profit_pct)
        target_hit = price >= target_price
        if target_hit:
            reasons.append("목표 수익률 도달")
        stop_price = position_avg * (Decimal("1") - parameters.stop_loss_pct)
        stop_hit = price <= stop_price
        if stop_hit:
            reasons.append("손절 조건 충족")
        recent_high = max(candle.high for candle in candles[-parameters.atr_period :]) if candles else price
        trailing_trigger = price <= recent_high - atr * parameters.trailing_atr_multiplier
        if trailing_trigger:
            reasons.append("ATR 트레일링 스탑")
        rsi_confirm = rsi <= parameters.rsi_sell_threshold or rsi >= parameters.rsi_overbought
        if rsi_confirm:
            reasons.append("RSI 청산 시그널")
        triggered = [death_cross, target_hit, stop_hit, trailing_trigger, rsi_confirm]
        if not any(triggered):
            return self._hold(symbol, price, timestamp, rsi=rsi, atr=atr, volume_ratio=volume_ratio)
        with localcontext() as ctx:
            ctx.prec = 28
            strength = Decimal(sum(1 for flag in triggered if flag)) / Decimal(len(triggered))
        return self._build_decision(
            symbol=symbol,
            signal_type=SignalType.SELL,
            price=price,
            strength=strength,
            rsi=rsi,
            atr=atr,
            volume_ratio=volume_ratio,
            reasons=reasons,
            timestamp=timestamp,
        )


__all__ = ["SignalDecision", "SignalGenerator"]
