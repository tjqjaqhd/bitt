"""백테스트 이벤트 시스템."""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from ..core.order_types import OrderSide, OrderType


class EventType(Enum):
    """이벤트 타입."""
    MARKET = "market"
    SIGNAL = "signal"
    ORDER = "order"
    FILL = "fill"


@dataclass
class Event(ABC):
    """이벤트 기본 클래스."""
    timestamp: datetime
    event_type: Optional[EventType] = field(default=None)

    @abstractmethod
    def __str__(self) -> str:
        pass


@dataclass
class MarketEvent(Event):
    """마켓 이벤트 (새로운 시장 데이터)."""
    symbol: str = field()
    open_price: Decimal = field()
    high_price: Decimal = field()
    low_price: Decimal = field()
    close_price: Decimal = field()
    volume: Decimal = field()

    def __post_init__(self):
        self.event_type = EventType.MARKET

    def __str__(self) -> str:
        return f"MarketEvent({self.symbol} @ {self.timestamp}: {self.close_price})"


@dataclass
class SignalEvent(Event):
    """신호 이벤트 (매수/매도 신호)."""
    symbol: str = field()
    signal_type: OrderSide = field()
    strength: Decimal = field()  # 신호 강도 (0.0 ~ 1.0)
    strategy_id: str = field()
    reason: str = field()
    metadata: Optional[Dict[str, Any]] = field(default=None)

    def __post_init__(self):
        self.event_type = EventType.SIGNAL

    def __str__(self) -> str:
        return f"SignalEvent({self.signal_type.value} {self.symbol} @ {self.timestamp}, strength: {self.strength})"


@dataclass
class OrderEvent(Event):
    """주문 이벤트."""
    symbol: str = field()
    order_type: OrderType = field()
    side: OrderSide = field()
    quantity: Decimal = field()
    price: Optional[Decimal] = field(default=None)
    order_id: Optional[str] = field(default=None)
    strategy_id: Optional[str] = field(default=None)

    def __post_init__(self):
        self.event_type = EventType.ORDER

    def __str__(self) -> str:
        price_str = f" @ {self.price}" if self.price else ""
        return f"OrderEvent({self.side.value} {self.quantity} {self.symbol}{price_str})"


@dataclass
class FillEvent(Event):
    """체결 이벤트."""
    symbol: str = field()
    side: OrderSide = field()
    quantity: Decimal = field()
    fill_price: Decimal = field()
    commission: Decimal = field()
    order_id: str = field()
    fill_id: str = field()

    def __post_init__(self):
        self.event_type = EventType.FILL

    def __str__(self) -> str:
        return f"FillEvent({self.side.value} {self.quantity} {self.symbol} @ {self.fill_price})"

    @property
    def fill_cost(self) -> Decimal:
        """체결 비용 (수수료 포함)."""
        cost = self.quantity * self.fill_price
        if self.side == OrderSide.BUY:
            return cost + self.commission
        else:
            return cost - self.commission