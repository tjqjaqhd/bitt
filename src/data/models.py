"""데이터베이스 ORM 모델 정의."""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .database import Base


class MarketWarningLevel(str, Enum):
    """빗썸 투자 경고 수준."""

    NORMAL = "NORMAL"
    PARTIAL_LIMIT = "PARTIAL_LIMIT"
    SUSPENDED = "SUSPENDED"


class OrderSide(str, Enum):
    """주문 방향."""

    BUY = "BUY"
    SELL = "SELL"


class PositionStatus(str, Enum):
    """포지션 상태."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class OrderType(str, Enum):
    """주문 유형."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    TRAILING_STOP = "TRAILING_STOP"


class OrderStatus(str, Enum):
    """주문 진행 상태."""

    PENDING = "PENDING"
    PLACED = "PLACED"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"


class SignalType(str, Enum):
    """전략 신호 유형."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class TimestampMixin:
    """생성/수정 시각 공통 컬럼."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Market(TimestampMixin, Base):
    """거래 지원 종목 정보."""

    __tablename__ = "markets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    korean_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    english_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    warning_level: Mapped[MarketWarningLevel] = mapped_column(
        SAEnum(MarketWarningLevel, native_enum=False, length=32),
        default=MarketWarningLevel.NORMAL,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Trade(TimestampMixin, Base):
    """체결 내역."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    side: Mapped[OrderSide] = mapped_column(SAEnum(OrderSide, native_enum=False, length=8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_trades_symbol_time", "symbol", "executed_at"),
    )


class Position(TimestampMixin, Base):
    """보유 포지션."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[PositionStatus] = mapped_column(
        SAEnum(PositionStatus, native_enum=False, length=16),
        default=PositionStatus.OPEN,
        nullable=False,
    )


class DailyPnL(TimestampMixin, Base):
    """일별 손익."""

    __tablename__ = "pnl_daily"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    total_equity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False, default=Decimal("0"))
    return_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))


class Config(TimestampMixin, Base):
    """전략 및 시스템 설정."""

    __tablename__ = "configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OrderHistory(TimestampMixin, Base):
    """주문 이력."""

    __tablename__ = "order_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    order_type: Mapped[OrderType] = mapped_column(SAEnum(OrderType, native_enum=False, length=20), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(SAEnum(OrderStatus, native_enum=False, length=20), nullable=False)


class StrategySignal(TimestampMixin, Base):
    """전략 신호 이력."""

    __tablename__ = "strategy_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    signal_type: Mapped[SignalType] = mapped_column(
        SAEnum(SignalType, native_enum=False, length=8), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    strength: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    rsi: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    atr: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    volume_ratio: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    risk_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_strategy_signals_symbol_created_at", "symbol", "created_at"),
    )


__all__ = [
    "Config",
    "DailyPnL",
    "Market",
    "MarketWarningLevel",
    "OrderHistory",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "Position",
    "PositionStatus",
    "SignalType",
    "StrategySignal",
    "Trade",
]

