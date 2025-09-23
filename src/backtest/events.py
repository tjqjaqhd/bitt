"""백테스트 이벤트 시스템 - 단순화 버전."""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any

from ..core.order_types import OrderSide, OrderType


class EventType(Enum):
    """이벤트 타입."""
    MARKET = "market"
    SIGNAL = "signal"
    ORDER = "order"
    FILL = "fill"


class Event(ABC):
    """이벤트 기본 클래스."""

    def __init__(self, timestamp: datetime, event_type: EventType):
        self.timestamp = timestamp
        self.event_type = event_type

    @abstractmethod
    def __str__(self) -> str:
        pass


class MarketEvent(Event):
    """마켓 이벤트 (새로운 시장 데이터)."""

    def __init__(
        self,
        timestamp: datetime,
        symbol: str,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        volume: Decimal
    ):
        super().__init__(timestamp, EventType.MARKET)
        self.symbol = symbol
        self.open_price = open_price
        self.high_price = high_price
        self.low_price = low_price
        self.close_price = close_price
        self.volume = volume

    def __str__(self) -> str:
        return f"MarketEvent({self.symbol} @ {self.timestamp}: {self.close_price})"


class SignalEvent(Event):
    """신호 이벤트 (매수/매도 신호)."""

    def __init__(
        self,
        timestamp: datetime,
        symbol: str,
        signal_type: OrderSide,
        strength: Decimal,
        strategy_id: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ):
        super().__init__(timestamp, EventType.SIGNAL)
        self.symbol = symbol
        self.signal_type = signal_type
        self.strength = strength
        self.strategy_id = strategy_id
        self.reason = reason
        self.metadata = metadata or {}

    def __str__(self) -> str:
        return f"SignalEvent({self.signal_type.value} {self.symbol} @ {self.timestamp}, strength: {self.strength})"


class OrderEvent(Event):
    """주문 이벤트."""

    def __init__(
        self,
        timestamp: datetime,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        order_id: Optional[str] = None,
        strategy_id: Optional[str] = None
    ):
        super().__init__(timestamp, EventType.ORDER)
        self.symbol = symbol
        self.order_type = order_type
        self.side = side
        self.quantity = quantity
        self.price = price
        self.order_id = order_id
        self.strategy_id = strategy_id

    def __str__(self) -> str:
        price_str = f" @ {self.price}" if self.price else ""
        return f"OrderEvent({self.side.value} {self.quantity} {self.symbol}{price_str})"


class FillEvent(Event):
    """체결 이벤트."""

    def __init__(
        self,
        timestamp: datetime,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        fill_price: Decimal,
        commission: Decimal,
        order_id: str,
        fill_id: str
    ):
        super().__init__(timestamp, EventType.FILL)
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.fill_price = fill_price
        self.commission = commission
        self.order_id = order_id
        self.fill_id = fill_id

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