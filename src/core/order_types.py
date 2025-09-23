"""주문 관련 타입 및 열거형 정의."""

from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


class OrderType(Enum):
    """주문 유형."""
    MARKET = "market"           # 시장가
    LIMIT = "limit"            # 지정가
    STOP = "stop"              # 스탑 주문
    STOP_LIMIT = "stop_limit"  # 스탑 지정가
    TRAILING_STOP = "trailing_stop"  # 트레일링 스탑


class OrderSide(Enum):
    """주문 방향."""
    BUY = "buy"     # 매수
    SELL = "sell"   # 매도


class OrderStatus(Enum):
    """주문 상태."""
    PENDING = "pending"           # 대기중
    SUBMITTED = "submitted"       # 제출됨
    PARTIALLY_FILLED = "partially_filled"  # 부분체결
    FILLED = "filled"            # 완전체결
    CANCELLED = "cancelled"      # 취소됨
    REJECTED = "rejected"        # 거부됨
    EXPIRED = "expired"          # 만료됨
    FAILED = "failed"            # 실패


class TimeInForce(Enum):
    """주문 유효기간."""
    GTC = "gtc"  # Good Till Cancelled (취소까지 유효)
    IOC = "ioc"  # Immediate Or Cancel (즉시체결 또는 취소)
    FOK = "fok"  # Fill Or Kill (전량체결 또는 취소)
    DAY = "day"  # Day (당일 유효)


@dataclass
class OrderRequest:
    """주문 요청 데이터."""
    symbol: str                    # 종목 코드 (예: "BTC_KRW")
    side: OrderSide               # 매수/매도
    order_type: OrderType         # 주문 유형
    quantity: Decimal             # 주문 수량
    price: Optional[Decimal] = None          # 주문 가격 (시장가의 경우 None)
    stop_price: Optional[Decimal] = None     # 스탑 가격
    time_in_force: TimeInForce = TimeInForce.GTC
    client_order_id: Optional[str] = None    # 클라이언트 주문 ID

    # 메타데이터
    strategy_id: Optional[str] = None        # 전략 ID
    signal_id: Optional[str] = None          # 신호 ID
    reason: Optional[str] = None             # 주문 사유

    def __post_init__(self):
        """초기화 후 검증."""
        if self.order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT] and self.price is None:
            raise ValueError(f"{self.order_type.value} 주문은 가격이 필요합니다.")

        if self.order_type in [OrderType.STOP, OrderType.STOP_LIMIT, OrderType.TRAILING_STOP] and self.stop_price is None:
            raise ValueError(f"{self.order_type.value} 주문은 스탑 가격이 필요합니다.")


@dataclass
class OrderResult:
    """주문 실행 결과."""
    order_id: str                 # 거래소 주문 ID
    client_order_id: Optional[str] = None  # 클라이언트 주문 ID
    symbol: str = ""              # 종목 코드
    side: Optional[OrderSide] = None       # 매수/매도
    order_type: Optional[OrderType] = None # 주문 유형
    status: OrderStatus = OrderStatus.PENDING

    # 수량 정보
    original_quantity: Decimal = Decimal('0')     # 원래 주문 수량
    executed_quantity: Decimal = Decimal('0')     # 체결된 수량
    remaining_quantity: Decimal = Decimal('0')    # 잔여 수량

    # 가격 정보
    price: Optional[Decimal] = None               # 주문 가격
    average_price: Optional[Decimal] = None       # 평균 체결가

    # 수수료 및 비용
    commission: Decimal = Decimal('0')            # 수수료
    commission_asset: str = "KRW"                 # 수수료 자산

    # 시간 정보
    created_at: Optional[datetime] = None         # 생성 시간
    updated_at: Optional[datetime] = None         # 업데이트 시간

    # 오류 정보
    error_code: Optional[str] = None              # 오류 코드
    error_message: Optional[str] = None           # 오류 메시지

    # 원시 응답
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class Fill:
    """체결 정보."""
    fill_id: str                  # 체결 ID
    order_id: str                 # 주문 ID
    symbol: str                   # 종목 코드
    side: OrderSide              # 매수/매도
    quantity: Decimal            # 체결 수량
    price: Decimal               # 체결 가격
    commission: Decimal          # 수수료
    commission_asset: str        # 수수료 자산
    timestamp: datetime          # 체결 시간
    is_maker: bool = False       # 메이커 여부


@dataclass
class Position:
    """포지션 정보."""
    symbol: str                   # 종목 코드
    quantity: Decimal            # 보유 수량
    average_price: Decimal       # 평균 단가
    market_price: Decimal        # 현재 시장가
    unrealized_pnl: Decimal      # 미실현 손익
    realized_pnl: Decimal        # 실현 손익
    entry_time: datetime         # 진입 시간
    last_updated: datetime       # 마지막 업데이트 시간

    @property
    def market_value(self) -> Decimal:
        """현재 시장 가치."""
        return self.quantity * self.market_price

    @property
    def cost_basis(self) -> Decimal:
        """매입 원가."""
        return self.quantity * self.average_price

    @property
    def pnl_percentage(self) -> Decimal:
        """손익률 (%)."""
        if self.cost_basis == 0:
            return Decimal('0')
        return (self.unrealized_pnl / self.cost_basis) * Decimal('100')


class OrderPriority(Enum):
    """주문 우선순위."""
    LOW = 1      # 낮음
    NORMAL = 2   # 보통
    HIGH = 3     # 높음
    URGENT = 4   # 긴급


@dataclass
class QueuedOrder:
    """큐에 대기 중인 주문."""
    request: OrderRequest         # 주문 요청
    priority: OrderPriority       # 우선순위
    created_at: datetime         # 생성 시간
    retry_count: int = 0         # 재시도 횟수
    max_retries: int = 3         # 최대 재시도 횟수

    def __lt__(self, other):
        """우선순위 비교 (높은 우선순위가 먼저)."""
        if not isinstance(other, QueuedOrder):
            return NotImplemented

        # 우선순위가 높을수록 먼저 처리
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value

        # 같은 우선순위면 먼저 생성된 것부터
        return self.created_at < other.created_at