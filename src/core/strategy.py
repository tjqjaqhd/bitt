"""전략 실행 엔진 구현."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence

from sqlalchemy.orm import sessionmaker

from src.data.models import SignalType
from src.data.repositories import ConfigRepository, StrategySignalRepository
from src.utils.logger import get_logger

from .indicators import Candle
from .parameters import StrategyParameterStore, StrategyParameters
from .risk import PortfolioState, RiskAssessment, RiskManager
from .signals import SignalDecision, SignalGenerator


@dataclass
class StrategyContext:
    """전략 평가에 필요한 입력."""

    symbol: str
    candles: Sequence[Candle]
    equity: Decimal
    portfolio: PortfolioState
    as_of: datetime


@dataclass
class StrategyResult:
    """전략 평가 결과."""

    signal: SignalDecision
    risk: RiskAssessment


class PerformanceTracker:
    """신호 실행 현황을 요약한다."""

    def __init__(self) -> None:
        self.total_signals = 0
        self.buy_signals = 0
        self.sell_signals = 0
        self.cumulative_strength = Decimal("0")
        self.last_signal: Optional[SignalDecision] = None
        self.last_updated: Optional[datetime] = None

    def record(self, decision: SignalDecision, assessment: RiskAssessment) -> None:  # noqa: ARG002 - 미래 확장 대비
        if decision.signal_type != SignalType.HOLD:
            self.total_signals += 1
            if decision.signal_type == SignalType.BUY:
                self.buy_signals += 1
            elif decision.signal_type == SignalType.SELL:
                self.sell_signals += 1
            self.cumulative_strength += decision.strength
            self.last_updated = decision.timestamp
        self.last_signal = decision

    def summary(self) -> dict[str, object]:
        average_strength = (
            (self.cumulative_strength / Decimal(self.total_signals))
            if self.total_signals
            else Decimal("0")
        )
        return {
            "total": self.total_signals,
            "buy": self.buy_signals,
            "sell": self.sell_signals,
            "avg_strength": average_strength,
            "last_signal": self.last_signal.signal_type.value if self.last_signal else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }

    def reset(self) -> None:
        self.__init__()


class StrategyEngine:
    """파라미터-리스크-신호를 연계해 실행하는 전략 엔진."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        parameter_store: StrategyParameterStore | None = None,
        risk_manager: RiskManager | None = None,
        signal_generator: SignalGenerator | None = None,
        signal_repository: StrategySignalRepository | None = None,
        config_repository: ConfigRepository | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._parameter_store = parameter_store or StrategyParameterStore(
            session_factory,
            config_repository=config_repository,
        )
        initial_params = self._parameter_store.get_parameters()
        self._risk_manager = risk_manager or RiskManager(initial_params)
        self._signal_generator = signal_generator or SignalGenerator()
        self._signal_repository = signal_repository or StrategySignalRepository()
        self._performance_tracker = PerformanceTracker()
        self._logger = get_logger(__name__)

    def evaluate(self, context: StrategyContext) -> StrategyResult:
        params = self._parameter_store.get_parameters()
        self._risk_manager.update_parameters(params)
        decision = self._signal_generator.generate(
            symbol=context.symbol,
            candles=context.candles,
            portfolio=context.portfolio,
            parameters=params,
        )
        assessment = self._risk_manager.assess(
            symbol=context.symbol,
            signal_type=decision.signal_type,
            equity=context.equity,
            price=decision.price,
            atr=decision.atr,
            portfolio=context.portfolio,
        )
        if decision.signal_type != SignalType.HOLD:
            self._persist_signal(decision, assessment, params)
        self._performance_tracker.record(decision, assessment)
        self._logger.debug(
            "전략 평가 완료",
            extra={
                "symbol": context.symbol,
                "signal": decision.signal_type.value,
                "strength": str(decision.strength),
            },
        )
        return StrategyResult(signal=decision, risk=assessment)

    def performance(self) -> dict[str, object]:
        return self._performance_tracker.summary()

    def reset_performance(self) -> None:
        self._performance_tracker.reset()

    def _persist_signal(
        self,
        decision: SignalDecision,
        assessment: RiskAssessment,
        params: StrategyParameters,
    ) -> None:
        context_payload = {
            "reasons": decision.reasons,
            "strength": str(decision.strength),
            "risk_amount": str(assessment.risk_amount),
            "partial_take_profit": str(assessment.partial_take_profit)
            if assessment.partial_take_profit is not None
            else None,
            "parameters": params.to_dict(),
        }
        with self._session_factory() as session:
            self._signal_repository.record(
                session,
                symbol=decision.symbol,
                signal_type=decision.signal_type,
                price=decision.price,
                strength=decision.strength,
                rsi=decision.rsi,
                atr=decision.atr,
                volume_ratio=decision.volume_ratio,
                risk_amount=assessment.risk_amount,
                context=context_payload,
            )
            session.commit()


__all__ = [
    "PerformanceTracker",
    "StrategyContext",
    "StrategyEngine",
    "StrategyResult",
]
