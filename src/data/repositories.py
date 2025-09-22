"""데이터 접근 계층 구현."""

from __future__ import annotations

import json
from typing import Any, Generic, Iterable, Mapping, Optional, Sequence, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import (
    Config,
    DailyPnL,
    Market,
    MarketWarningLevel,
    OrderHistory,
    Position,
    PositionStatus,
    SignalType,
    StrategySignal,
    Trade,
)

from .database import Base

ModelT = TypeVar("ModelT", bound=Base)


class CRUDRepository(Generic[ModelT]):
    """일반적인 CRUD 동작을 제공하는 기본 저장소."""

    def __init__(self, model: type[ModelT]) -> None:
        self._model = model

    @property
    def model(self) -> type[ModelT]:
        return self._model

    def create(self, session: Session, **data: Any) -> ModelT:
        instance = self._model(**data)
        session.add(instance)
        return instance

    def get(self, session: Session, **filters: Any) -> Optional[ModelT]:
        statement = select(self._model)
        for column, value in filters.items():
            statement = statement.filter(getattr(self._model, column) == value)
        return session.execute(statement.limit(1)).scalars().first()

    def list(
        self,
        session: Session,
        *,
        filters: Optional[Mapping[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Sequence[ModelT]:
        statement = select(self._model)
        if filters:
            for column, value in filters.items():
                statement = statement.filter(getattr(self._model, column) == value)
        if limit:
            statement = statement.limit(limit)
        return session.execute(statement).scalars().all()

    def update(self, session: Session, filters: Mapping[str, Any], values: Mapping[str, Any]) -> int:
        statement = update(self._model)
        for column, value in filters.items():
            statement = statement.where(getattr(self._model, column) == value)
        result = session.execute(statement.values(**values))
        return result.rowcount or 0

    def delete(self, session: Session, **filters: Any) -> int:
        statement = delete(self._model)
        for column, value in filters.items():
            statement = statement.where(getattr(self._model, column) == value)
        result = session.execute(statement)
        return result.rowcount or 0


class MarketRepository(CRUDRepository[Market]):
    """거래 지원 종목을 관리하는 저장소."""

    def __init__(self) -> None:
        super().__init__(Market)

    def get_by_symbol(self, session: Session, symbol: str) -> Optional[Market]:
        return self.get(session, symbol=symbol)

    def upsert(
        self,
        session: Session,
        *,
        symbol: str,
        korean_name: Optional[str],
        english_name: Optional[str],
        warning_level: MarketWarningLevel,
        is_active: bool,
    ) -> Market:
        existing = self.get_by_symbol(session, symbol)
        if existing:
            existing.korean_name = korean_name
            existing.english_name = english_name
            existing.warning_level = warning_level
            existing.is_active = is_active
            return existing
        return self.create(
            session,
            symbol=symbol,
            korean_name=korean_name,
            english_name=english_name,
            warning_level=warning_level,
            is_active=is_active,
        )

    def deactivate_missing(self, session: Session, valid_symbols: Iterable[str]) -> int:
        symbols = list(valid_symbols)
        statement = update(Market)
        if symbols:
            statement = statement.where(~Market.symbol.in_(symbols))
        result = session.execute(statement.values(is_active=False))
        return result.rowcount or 0


class TradeRepository(CRUDRepository[Trade]):
    def __init__(self) -> None:
        super().__init__(Trade)


class PositionRepository(CRUDRepository[Position]):
    def __init__(self) -> None:
        super().__init__(Position)

    def close_position(self, session: Session, symbol: str) -> int:
        statement = (
            update(Position)
            .where(Position.symbol == symbol)
            .values(status=PositionStatus.CLOSED)
        )
        result = session.execute(statement)
        return result.rowcount or 0


class DailyPnLRepository(CRUDRepository[DailyPnL]):
    def __init__(self) -> None:
        super().__init__(DailyPnL)


class ConfigRepository(CRUDRepository[Config]):
    def __init__(self) -> None:
        super().__init__(Config)

    def set(self, session: Session, key: str, value: str, description: Optional[str] = None) -> Config:
        existing = self.get(session, key=key)
        if existing:
            existing.value = value
            existing.description = description
            return existing
        return self.create(session, key=key, value=value, description=description)


class OrderHistoryRepository(CRUDRepository[OrderHistory]):
    def __init__(self) -> None:
        super().__init__(OrderHistory)


class StrategySignalRepository(CRUDRepository[StrategySignal]):
    """전략 신호 이력을 관리한다."""

    def __init__(self) -> None:
        super().__init__(StrategySignal)

    def record(
        self,
        session: Session,
        *,
        symbol: str,
        signal_type: SignalType,
        price: Any,
        strength: Any,
        rsi: Any | None,
        atr: Any | None,
        volume_ratio: Any | None,
        risk_amount: Any | None,
        context: Mapping[str, Any] | None = None,
    ) -> StrategySignal:
        payload = json.dumps(context, ensure_ascii=False) if context else None
        return self.create(
            session,
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            strength=strength,
            rsi=rsi,
            atr=atr,
            volume_ratio=volume_ratio,
            risk_amount=risk_amount,
            context=payload,
        )


__all__ = [
    "ConfigRepository",
    "DailyPnLRepository",
    "MarketRepository",
    "OrderHistoryRepository",
    "PositionRepository",
    "StrategySignalRepository",
    "TradeRepository",
]

