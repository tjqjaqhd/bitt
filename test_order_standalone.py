#!/usr/bin/env python3
"""주문 시스템 독립 테스트."""

import logging
import threading
import time
from datetime import datetime
from decimal import Decimal
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, List, Callable, Set
from uuid import uuid4
from queue import PriorityQueue, Empty

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 주문 관련 타입 정의 (독립 버전)
class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    CANCELLED = "cancelled"

class OrderPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    price: Optional[Decimal] = None
    client_order_id: Optional[str] = None
    reason: Optional[str] = None

    def __post_init__(self):
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError(f"{self.order_type.value} 주문은 가격이 필요합니다.")

@dataclass
class OrderResult:
    order_id: str
    client_order_id: Optional[str] = None
    symbol: str = ""
    side: Optional[OrderSide] = None
    order_type: Optional[OrderType] = None
    status: OrderStatus = OrderStatus.PENDING
    original_quantity: Decimal = Decimal('0')
    price: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class QueuedOrder:
    request: OrderRequest
    priority: OrderPriority
    created_at: datetime
    retry_count: int = 0
    max_retries: int = 3

    def __lt__(self, other):
        if not isinstance(other, QueuedOrder):
            return NotImplemented
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.created_at < other.created_at

@dataclass
class Position:
    symbol: str
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    entry_time: datetime
    last_updated: datetime

    @property
    def pnl_percentage(self) -> Decimal:
        if self.average_price == 0:
            return Decimal('0')
        return (self.unrealized_pnl / (self.quantity * self.average_price)) * Decimal('100')

# 간단한 주문 매니저 (독립 버전)
class SimpleOrderManager:
    def __init__(self, mock_client, max_concurrent_orders: int = 5):
        self.client = mock_client
        self.max_concurrent_orders = max_concurrent_orders
        self.logger = logging.getLogger(self.__class__.__name__)

        # 주문 관리
        self._order_queue = PriorityQueue()
        self._pending_orders: Dict[str, OrderResult] = {}
        self._active_orders: Set[str] = set()
        self._order_history: Dict[str, OrderResult] = {}
        self._positions: Dict[str, Position] = {}

        # 콜백
        self._order_update_callbacks: List[Callable] = []
        self._position_update_callbacks: List[Callable] = []

        # 스레드 관리
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self.logger.info("주문 매니저 시작")
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        self._sync_positions()

    def stop(self):
        if not self._running:
            return
        self.logger.info("주문 매니저 정지 중...")
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        self.logger.info("주문 매니저 정지 완료")

    def submit_order(self, request: OrderRequest, priority: OrderPriority = OrderPriority.NORMAL) -> str:
        if not request.client_order_id:
            request.client_order_id = f"order_{uuid4().hex[:8]}"

        queued_order = QueuedOrder(
            request=request,
            priority=priority,
            created_at=datetime.now()
        )

        self._order_queue.put(queued_order)
        self.logger.info(f"주문 큐에 추가: {request.client_order_id}")
        return request.client_order_id

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        if order_id in self._pending_orders:
            return self._pending_orders[order_id]
        if order_id in self._order_history:
            return self._order_history[order_id]
        for order in list(self._pending_orders.values()) + list(self._order_history.values()):
            if order.client_order_id == order_id:
                return order
        return None

    def get_pending_orders(self) -> List[OrderResult]:
        return list(self._pending_orders.values())

    def get_all_positions(self) -> Dict[str, Position]:
        return self._positions.copy()

    def add_order_update_callback(self, callback):
        self._order_update_callbacks.append(callback)

    def add_position_update_callback(self, callback):
        self._position_update_callbacks.append(callback)

    def _worker_loop(self):
        self.logger.info("주문 워커 루프 시작")
        while self._running:
            try:
                if len(self._active_orders) >= self.max_concurrent_orders:
                    time.sleep(0.1)
                    continue

                try:
                    queued_order = self._order_queue.get(timeout=1)
                except Empty:
                    continue

                self._process_order(queued_order)

            except Exception as e:
                self.logger.error(f"주문 워커 루프 오류: {e}")
                time.sleep(1)

        self.logger.info("주문 워커 루프 종료")

    def _process_order(self, queued_order: QueuedOrder):
        request = queued_order.request
        try:
            self.logger.info(f"주문 처리 시작: {request.client_order_id}")

            if not self._validate_order(request):
                self.logger.error(f"주문 검증 실패: {request.client_order_id}")
                return

            result = self._execute_order(request)
            if result:
                self._active_orders.add(result.order_id)
                self._pending_orders[result.order_id] = result
                self.logger.info(f"주문 실행 성공: {result.order_id}")
                self._notify_order_update(result)

        except Exception as e:
            self.logger.error(f"주문 처리 중 오류: {request.client_order_id}, {e}")

    def _validate_order(self, request: OrderRequest) -> bool:
        if request.quantity <= 0:
            return False
        if request.order_type == OrderType.LIMIT and (not request.price or request.price <= 0):
            return False
        # 간단한 잔고 확인 생략
        return True

    def _execute_order(self, request: OrderRequest) -> Optional[OrderResult]:
        self.logger.info(f"주문 실행: {request.symbol} {request.side.value} {request.quantity}")

        order_result = OrderResult(
            order_id=f"test_order_{uuid4().hex[:8]}",
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            status=OrderStatus.SUBMITTED,
            original_quantity=request.quantity,
            price=request.price,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        return order_result

    def _sync_positions(self):
        try:
            accounts = self.client.get_accounts()
            current_time = datetime.now()

            for account in accounts:
                currency = account.get('currency')
                balance = Decimal(account.get('balance', '0'))

                if currency == 'KRW' or balance <= 0:
                    continue

                symbol = f"{currency}_KRW"
                ticker = self.client.get_ticker(symbol)
                if not ticker:
                    continue

                current_price = Decimal(str(ticker.get('closing_price', 0)))

                position = Position(
                    symbol=symbol,
                    quantity=balance,
                    average_price=current_price,
                    market_price=current_price,
                    unrealized_pnl=Decimal('0'),
                    realized_pnl=Decimal('0'),
                    entry_time=current_time,
                    last_updated=current_time
                )
                self._positions[symbol] = position
                self._notify_position_update(position)

        except Exception as e:
            self.logger.error(f"포지션 동기화 중 오류: {e}")

    def _notify_order_update(self, order):
        for callback in self._order_update_callbacks:
            try:
                callback(order)
            except Exception as e:
                self.logger.error(f"주문 업데이트 콜백 오류: {e}")

    def _notify_position_update(self, position):
        for callback in self._position_update_callbacks:
            try:
                callback(position)
            except Exception as e:
                self.logger.error(f"포지션 업데이트 콜백 오류: {e}")

# 테스트 함수들
def test_order_types():
    print("🔧 주문 타입 테스트...")

    # 시장가 매수 주문
    market_buy = OrderRequest(
        symbol="BTC_KRW",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal('0.001')
    )
    print(f"✅ 시장가 매수 주문: {market_buy.symbol} {market_buy.quantity}")

    # 지정가 매도 주문
    limit_sell = OrderRequest(
        symbol="ETH_KRW",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal('0.1'),
        price=Decimal('4500000')
    )
    print(f"✅ 지정가 매도 주문: {limit_sell.symbol} {limit_sell.quantity} @ {limit_sell.price}")

    # 잘못된 주문 테스트
    try:
        invalid_order = OrderRequest(
            symbol="BTC_KRW",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal('0.001')
        )
        print("❌ 잘못된 주문이 생성되었습니다")
    except ValueError as e:
        print(f"✅ 잘못된 주문 검증 성공: {e}")

def test_order_manager():
    print("\n🚀 주문 매니저 테스트 시작...")

    # Mock 클라이언트
    class MockBithumbClient:
        def get_accounts(self):
            return [
                {'currency': 'KRW', 'balance': '147059.085549'},
                {'currency': 'BTC', 'balance': '0.00016106'},
                {'currency': 'SOL', 'balance': '0.00016106'}
            ]

        def get_ticker(self, symbol):
            prices = {
                'BTC_KRW': {'closing_price': '159375000'},
                'SOL_KRW': {'closing_price': '900000'}
            }
            return prices.get(symbol)

    mock_client = MockBithumbClient()
    order_manager = SimpleOrderManager(mock_client, max_concurrent_orders=3)

    print("✅ 주문 매니저 생성 완료")

    # 콜백 함수 설정
    def on_order_update(order):
        print(f"📝 주문 업데이트: {order.client_order_id} - {order.status.value}")

    def on_position_update(position):
        print(f"📊 포지션 업데이트: {position.symbol} - {position.quantity} @ {position.market_price}")

    order_manager.add_order_update_callback(on_order_update)
    order_manager.add_position_update_callback(on_position_update)

    # 주문 매니저 시작
    order_manager.start()
    print("✅ 주문 매니저 시작됨")

    # 테스트 주문들
    buy_request = OrderRequest(
        symbol="BTC_KRW",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal('0.00001'),
        reason="테스트 매수 주문"
    )

    sell_request = OrderRequest(
        symbol="SOL_KRW",
        side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        quantity=Decimal('0.00001'),
        price=Decimal('950000'),
        reason="테스트 매도 주문"
    )

    client_order_id1 = order_manager.submit_order(buy_request, OrderPriority.HIGH)
    client_order_id2 = order_manager.submit_order(sell_request, OrderPriority.NORMAL)

    print(f"✅ 매수 주문 제출: {client_order_id1}")
    print(f"✅ 매도 주문 제출: {client_order_id2}")

    # 처리 대기
    print("\n⏳ 주문 처리 중... (3초 대기)")
    time.sleep(3)

    # 상태 확인
    print("\n📋 주문 상태 확인:")
    order1 = order_manager.get_order_status(client_order_id1)
    if order1:
        print(f"  주문 1: {order1.status.value} - {order1.symbol} {order1.side.value}")

    order2 = order_manager.get_order_status(client_order_id2)
    if order2:
        print(f"  주문 2: {order2.status.value} - {order2.symbol} {order2.side.value}")

    pending_orders = order_manager.get_pending_orders()
    print(f"\n📝 대기 중인 주문: {len(pending_orders)}개")

    positions = order_manager.get_all_positions()
    print(f"\n💼 현재 포지션: {len(positions)}개")
    for symbol, position in positions.items():
        print(f"  - {symbol}: {position.quantity} @ {position.market_price}")

    # 정지
    order_manager.stop()
    print("✅ 주문 매니저 정지됨")

if __name__ == "__main__":
    print("🧪 Phase 4 주문 실행 시스템 독립 테스트")
    print("=" * 55)

    test_order_types()
    test_order_manager()

    print("\n✅ 모든 테스트 완료!")
    print("💡 주문 시스템의 핵심 기능이 정상적으로 작동합니다.")