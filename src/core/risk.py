"""리스크 및 포트폴리오 관리 로직."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Iterable, Optional

from src.data.models import SignalType
from src.utils.logger import get_logger

from .parameters import StrategyParameters


@dataclass(frozen=True)
class PortfolioPosition:
    """전략 관점에서 필요한 포지션 스냅샷."""

    symbol: str
    quantity: Decimal
    avg_price: Decimal
    entry_time: datetime

    def notional_value(self) -> Decimal:
        return self.quantity * self.avg_price


class PortfolioState:
    """현재 포지션 목록과 포트폴리오 한도를 추적한다."""

    def __init__(self, positions: Iterable[PortfolioPosition] | None = None) -> None:
        self._positions: dict[str, PortfolioPosition] = {}
        if positions:
            for position in positions:
                self._positions[position.symbol] = position

    def get(self, symbol: str) -> Optional[PortfolioPosition]:
        return self._positions.get(symbol)

    def total_open_positions(self) -> int:
        return len(self._positions)

    def all_positions(self) -> Iterable[PortfolioPosition]:  # pragma: no cover - 단순 위임
        return self._positions.values()


@dataclass
class RiskAssessment:
    """신호 실행 시 사용할 리스크 지표."""

    quantity: Decimal
    notional: Decimal
    risk_amount: Decimal
    stop_loss: Optional[Decimal]
    take_profit: Optional[Decimal]
    trailing_stop: Optional[Decimal]
    partial_take_profit: Optional[Decimal]


class RiskManager:
    """전략 파라미터 기반 리스크 관리를 담당한다."""

    def __init__(self, parameters: StrategyParameters) -> None:
        self._parameters = parameters
        self._logger = get_logger(__name__)

    @property
    def parameters(self) -> StrategyParameters:
        return self._parameters

    def update_parameters(self, parameters: StrategyParameters) -> None:
        parameters.validate()
        self._parameters = parameters

    def can_open_new_position(self, portfolio: PortfolioState) -> bool:
        return portfolio.total_open_positions() < self._parameters.max_concurrent_positions

    def calculate_position_size(
        self,
        *,
        equity: Decimal,
        price: Decimal,
        atr: Optional[Decimal],
    ) -> Decimal:
        params = self._parameters
        with localcontext() as ctx:
            ctx.prec = 28
            win_rate = params.kelly_win_rate
            reward_risk = params.kelly_reward_risk
            kelly_fraction = win_rate - (Decimal("1") - win_rate) / reward_risk
            kelly_fraction = max(kelly_fraction, Decimal("0"))
            kelly_amount = equity * kelly_fraction
            risk_cap = equity * params.max_risk_per_trade
            capital_cap = equity * params.capital_allocation_per_position
            allocation = min(capital_cap, risk_cap, kelly_amount if kelly_amount > 0 else capital_cap)
            if allocation <= 0:
                return Decimal("0")
            atr_component = (atr or Decimal("0")) * params.atr_multiplier
            stop_loss_value = price * params.stop_loss_pct
            unit_risk = max(stop_loss_value, atr_component)
            if unit_risk == 0:
                return Decimal("0")
            quantity = allocation / unit_risk
            return quantity

    def correlation_score(self, portfolio: PortfolioState) -> Decimal:
        if portfolio.total_open_positions() == 0:
            return Decimal("0")
        with localcontext() as ctx:
            ctx.prec = 28
            return Decimal(portfolio.total_open_positions()) / Decimal(self._parameters.max_concurrent_positions)

    def determine_stop_levels(
        self,
        *,
        price: Decimal,
        atr: Optional[Decimal],
        position: Optional[PortfolioPosition] = None,
    ) -> tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        params = self._parameters
        with localcontext() as ctx:
            ctx.prec = 28
            anchor = position.avg_price if position else price
            atr_component = (atr or Decimal("0")) * params.atr_multiplier
            trailing_component = (atr or Decimal("0")) * params.trailing_atr_multiplier
            stop_loss = anchor - max(anchor * params.stop_loss_pct, atr_component)
            take_profit = anchor + anchor * params.target_profit_pct
            partial_take_profit = anchor + anchor * params.partial_take_profit_pct
            trailing_stop = price - trailing_component if trailing_component > 0 else None
        return stop_loss, take_profit, trailing_stop, partial_take_profit

    def assess(
        self,
        *,
        symbol: str,
        signal_type: SignalType,
        equity: Decimal,
        price: Decimal,
        atr: Optional[Decimal],
        portfolio: PortfolioState,
    ) -> RiskAssessment:
        params = self._parameters
        if signal_type == SignalType.BUY:
            if not self.can_open_new_position(portfolio):
                self._logger.info("최대 보유 종목 수 초과로 진입 불가", extra={"limit": params.max_concurrent_positions})
                return RiskAssessment(
                    quantity=Decimal("0"),
                    notional=Decimal("0"),
                    risk_amount=Decimal("0"),
                    stop_loss=None,
                    take_profit=None,
                    trailing_stop=None,
                    partial_take_profit=None,
                )
            crowding = self.correlation_score(portfolio)
            if crowding >= params.correlation_threshold:
                self._logger.info(
                    "상관관계 한도 초과로 진입 보류",
                    extra={"score": str(crowding), "threshold": str(params.correlation_threshold)},
                )
                return RiskAssessment(
                    quantity=Decimal("0"),
                    notional=Decimal("0"),
                    risk_amount=Decimal("0"),
                    stop_loss=None,
                    take_profit=None,
                    trailing_stop=None,
                    partial_take_profit=None,
                )
            quantity = self.calculate_position_size(equity=equity, price=price, atr=atr)
            stop_loss, take_profit, trailing_stop, partial_take_profit = self.determine_stop_levels(price=price, atr=atr)
            risk_amount = quantity * price * params.stop_loss_pct
            return RiskAssessment(
                quantity=quantity,
                notional=quantity * price,
                risk_amount=risk_amount,
                stop_loss=stop_loss,
                take_profit=take_profit,
                trailing_stop=trailing_stop,
                partial_take_profit=partial_take_profit,
            )
        position = portfolio.get(symbol)
        if position is None:
            self._logger.warning("청산 신호지만 보유 포지션이 없습니다.", extra={"symbol": symbol})
            return RiskAssessment(
                quantity=Decimal("0"),
                notional=Decimal("0"),
                risk_amount=Decimal("0"),
                stop_loss=None,
                take_profit=None,
                trailing_stop=None,
                partial_take_profit=None,
            )
        stop_loss, take_profit, trailing_stop, partial_take_profit = self.determine_stop_levels(
            price=price,
            atr=atr,
            position=position,
        )
        with localcontext() as ctx:
            ctx.prec = 28
            risk_amount = position.quantity * max(position.avg_price - (stop_loss or position.avg_price), Decimal("0"))
        return RiskAssessment(
            quantity=position.quantity,
            notional=position.quantity * price,
            risk_amount=risk_amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop=trailing_stop,
            partial_take_profit=partial_take_profit,
        )


__all__ = [
    "PortfolioPosition",
    "PortfolioState",
    "RiskAssessment",
    "RiskManager",
]
