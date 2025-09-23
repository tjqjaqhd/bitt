"""주문 실행 및 관리 시스템."""

import logging
import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from queue import PriorityQueue, Empty
from typing import Dict, List, Optional, Callable, Set
from uuid import uuid4

from .order_types import (
    OrderRequest, OrderResult, OrderStatus, OrderType, OrderSide,
    QueuedOrder, OrderPriority, Fill, Position, TimeInForce
)


class OrderError(Exception):
    """주문 관련 예외."""
    pass


class OrderManager:
    """주문 실행 및 관리 매니저."""

    def __init__(self, bithumb_client, max_concurrent_orders: int = 5):
        """
        주문 매니저 초기화.

        Args:
            bithumb_client: 빗썸 클라이언트 인스턴스
            max_concurrent_orders: 최대 동시 처리 주문 수
        """
        self.client = bithumb_client
        self.max_concurrent_orders = max_concurrent_orders

        # 로거 설정
        self.logger = logging.getLogger(self.__class__.__name__)

        # 주문 큐 및 관리
        self._order_queue = PriorityQueue()
        self._pending_orders: Dict[str, OrderResult] = {}  # order_id -> OrderResult
        self._active_orders: Set[str] = set()  # 현재 처리 중인 주문 ID들
        self._order_history: Dict[str, OrderResult] = {}  # 주문 이력

        # 포지션 관리
        self._positions: Dict[str, Position] = {}  # symbol -> Position

        # 콜백 함수들
        self._fill_callbacks: List[Callable[[Fill], None]] = []
        self._order_update_callbacks: List[Callable[[OrderResult], None]] = []
        self._position_update_callbacks: List[Callable[[Position], None]] = []

        # 스레드 관리
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        self._order_monitor_thread: Optional[threading.Thread] = None

        # 설정
        self.order_timeout = 300  # 5분 (초)
        self.position_sync_interval = 60  # 1분 (초)

    def start(self):
        """주문 매니저 시작."""
        if self._running:
            return

        self._running = True
        self.logger.info("주문 매니저 시작")

        # 워커 스레드 시작
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

        # 주문 모니터링 스레드 시작
        self._order_monitor_thread = threading.Thread(target=self._monitor_orders, daemon=True)
        self._order_monitor_thread.start()

        # 포지션 동기화
        self._sync_positions()

    def stop(self):
        """주문 매니저 정지."""
        if not self._running:
            return

        self.logger.info("주문 매니저 정지 중...")
        self._running = False

        # 스레드 종료 대기
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        if self._order_monitor_thread:
            self._order_monitor_thread.join(timeout=5)

        self.logger.info("주문 매니저 정지 완료")

    def submit_order(self, request: OrderRequest, priority: OrderPriority = OrderPriority.NORMAL) -> str:
        """
        주문을 큐에 추가.

        Args:
            request: 주문 요청
            priority: 우선순위

        Returns:
            클라이언트 주문 ID
        """
        if not request.client_order_id:
            request.client_order_id = f"order_{uuid4().hex[:8]}"

        queued_order = QueuedOrder(
            request=request,
            priority=priority,
            created_at=datetime.now()
        )

        self._order_queue.put(queued_order)
        self.logger.info(f"주문 큐에 추가: {request.client_order_id} ({request.symbol} {request.side.value} {request.quantity})")

        return request.client_order_id

    def cancel_order(self, order_id: str) -> bool:
        """
        주문 취소.

        Args:
            order_id: 취소할 주문 ID (거래소 주문 ID 또는 클라이언트 주문 ID)

        Returns:
            취소 성공 여부
        """
        try:
            # 거래소 주문 ID인지 확인
            if order_id in self._pending_orders:
                exchange_order_id = order_id
            else:
                # 클라이언트 주문 ID로 거래소 주문 ID 찾기
                exchange_order_id = None
                for oid, order in self._pending_orders.items():
                    if order.client_order_id == order_id:
                        exchange_order_id = oid
                        break

                if not exchange_order_id:
                    self.logger.warning(f"취소할 주문을 찾을 수 없음: {order_id}")
                    return False

            # 빗썸 API를 통해 주문 취소
            result = self.client.cancel_order(exchange_order_id)

            if result:
                self.logger.info(f"주문 취소 성공: {order_id}")
                # 주문 상태 업데이트
                if exchange_order_id in self._pending_orders:
                    self._pending_orders[exchange_order_id].status = OrderStatus.CANCELLED
                    self._pending_orders[exchange_order_id].updated_at = datetime.now()
                return True
            else:
                self.logger.error(f"주문 취소 실패: {order_id}")
                return False

        except Exception as e:
            self.logger.error(f"주문 취소 중 오류: {order_id}, {e}")
            return False

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        """주문 상태 조회."""
        # 활성 주문에서 먼저 찾기
        if order_id in self._pending_orders:
            return self._pending_orders[order_id]

        # 주문 이력에서 찾기
        if order_id in self._order_history:
            return self._order_history[order_id]

        # 클라이언트 주문 ID로 찾기
        for order in list(self._pending_orders.values()) + list(self._order_history.values()):
            if order.client_order_id == order_id:
                return order

        return None

    def get_pending_orders(self) -> List[OrderResult]:
        """대기 중인 주문 목록 조회."""
        return list(self._pending_orders.values())

    def get_position(self, symbol: str) -> Optional[Position]:
        """포지션 조회."""
        return self._positions.get(symbol)

    def get_all_positions(self) -> Dict[str, Position]:
        """모든 포지션 조회."""
        return self._positions.copy()

    def add_fill_callback(self, callback: Callable[[Fill], None]):
        """체결 콜백 함수 추가."""
        self._fill_callbacks.append(callback)

    def add_order_update_callback(self, callback: Callable[[OrderResult], None]):
        """주문 업데이트 콜백 함수 추가."""
        self._order_update_callbacks.append(callback)

    def add_position_update_callback(self, callback: Callable[[Position], None]):
        """포지션 업데이트 콜백 함수 추가."""
        self._position_update_callbacks.append(callback)

    def _worker_loop(self):
        """주문 처리 워커 루프."""
        self.logger.info("주문 워커 루프 시작")

        while self._running:
            try:
                # 동시 처리 제한 확인
                if len(self._active_orders) >= self.max_concurrent_orders:
                    time.sleep(0.1)
                    continue

                # 큐에서 주문 가져오기
                try:
                    queued_order = self._order_queue.get(timeout=1)
                except Empty:
                    continue

                # 주문 처리
                self._process_order(queued_order)

            except Exception as e:
                self.logger.error(f"주문 워커 루프 오류: {e}")
                time.sleep(1)

        self.logger.info("주문 워커 루프 종료")

    def _process_order(self, queued_order: QueuedOrder):
        """개별 주문 처리."""
        request = queued_order.request

        try:
            self.logger.info(f"주문 처리 시작: {request.client_order_id}")

            # 주문 전 검증
            if not self._validate_order(request):
                self.logger.error(f"주문 검증 실패: {request.client_order_id}")
                return

            # 주문 실행
            result = self._execute_order(request)

            if result and result.status != OrderStatus.REJECTED:
                self._active_orders.add(result.order_id)
                self._pending_orders[result.order_id] = result
                self.logger.info(f"주문 실행 성공: {result.order_id}")

                # 콜백 호출
                self._notify_order_update(result)
            else:
                self.logger.error(f"주문 실행 실패: {request.client_order_id}")

        except Exception as e:
            self.logger.error(f"주문 처리 중 오류: {request.client_order_id}, {e}")

            # 재시도 로직
            if queued_order.retry_count < queued_order.max_retries:
                queued_order.retry_count += 1
                self.logger.info(f"주문 재시도: {request.client_order_id} ({queued_order.retry_count}/{queued_order.max_retries})")
                time.sleep(2 ** queued_order.retry_count)  # 지수 백오프
                self._order_queue.put(queued_order)

    def _validate_order(self, request: OrderRequest) -> bool:
        """주문 전 검증."""
        try:
            # 기본 검증
            if request.quantity <= 0:
                self.logger.error(f"잘못된 주문 수량: {request.quantity}")
                return False

            if request.order_type == OrderType.LIMIT and (not request.price or request.price <= 0):
                self.logger.error(f"지정가 주문에 잘못된 가격: {request.price}")
                return False

            # 잔고 확인 (매수 주문)
            if request.side == OrderSide.BUY:
                if not self._check_buying_power(request):
                    self.logger.error(f"매수 가능 금액 부족: {request.symbol}")
                    return False

            # 보유 수량 확인 (매도 주문)
            elif request.side == OrderSide.SELL:
                if not self._check_sell_quantity(request):
                    self.logger.error(f"매도 가능 수량 부족: {request.symbol}")
                    return False

            return True

        except Exception as e:
            self.logger.error(f"주문 검증 중 오류: {e}")
            return False

    def _check_buying_power(self, request: OrderRequest) -> bool:
        """매수 가능 금액 확인."""
        try:
            # 계좌 잔고 조회
            accounts = self.client.get_accounts()
            krw_account = next((acc for acc in accounts if acc.get('currency') == 'KRW'), None)

            if not krw_account:
                return False

            available_krw = Decimal(krw_account.get('balance', '0'))

            # 필요 금액 계산
            if request.order_type == OrderType.MARKET:
                # 시장가의 경우 현재가로 추정
                ticker = self.client.get_ticker(request.symbol)
                if not ticker:
                    return False
                estimated_price = Decimal(str(ticker.get('closing_price', 0)))
            else:
                estimated_price = request.price

            required_amount = request.quantity * estimated_price
            # 수수료 고려 (0.25%)
            required_amount *= Decimal('1.0025')

            return available_krw >= required_amount

        except Exception as e:
            self.logger.error(f"매수 가능 금액 확인 중 오류: {e}")
            return False

    def _check_sell_quantity(self, request: OrderRequest) -> bool:
        """매도 가능 수량 확인."""
        try:
            # 계좌 잔고 조회
            accounts = self.client.get_accounts()
            currency = request.symbol.split('_')[0]  # BTC_KRW -> BTC

            account = next((acc for acc in accounts if acc.get('currency') == currency), None)
            if not account:
                return False

            available_quantity = Decimal(account.get('balance', '0'))
            return available_quantity >= request.quantity

        except Exception as e:
            self.logger.error(f"매도 가능 수량 확인 중 오류: {e}")
            return False

    def _execute_order(self, request: OrderRequest) -> Optional[OrderResult]:
        """주문 실행."""
        try:
            # 주문 타입별 실행
            if request.order_type == OrderType.MARKET:
                return self._execute_market_order(request)
            elif request.order_type == OrderType.LIMIT:
                return self._execute_limit_order(request)
            else:
                self.logger.error(f"지원하지 않는 주문 타입: {request.order_type}")
                return None

        except Exception as e:
            self.logger.error(f"주문 실행 중 오류: {e}")
            return None

    def _execute_market_order(self, request: OrderRequest) -> Optional[OrderResult]:
        """시장가 주문 실행."""
        try:
            self.logger.info(f"시장가 주문 실행: {request.symbol} {request.side.value} {request.quantity}")

            # 임시로 주문 결과 생성 (실제 API 연동 전까지)
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

        except Exception as e:
            self.logger.error(f"시장가 주문 실행 실패: {e}")
            return None

    def _execute_limit_order(self, request: OrderRequest) -> Optional[OrderResult]:
        """지정가 주문 실행."""
        try:
            self.logger.info(f"지정가 주문 실행: {request.symbol} {request.side.value} {request.quantity} @ {request.price}")

            # 임시로 주문 결과 생성 (실제 API 연동 전까지)
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

        except Exception as e:
            self.logger.error(f"지정가 주문 실행 실패: {e}")
            return None

    def _monitor_orders(self):
        """주문 상태 모니터링."""
        self.logger.info("주문 모니터링 시작")

        while self._running:
            try:
                # 포지션 동기화 (주기적)
                if int(time.time()) % self.position_sync_interval == 0:
                    self._sync_positions()

                time.sleep(5)  # 5초마다 확인

            except Exception as e:
                self.logger.error(f"주문 모니터링 중 오류: {e}")
                time.sleep(5)

        self.logger.info("주문 모니터링 종료")

    def _sync_positions(self):
        """계좌와 포지션 동기화."""
        try:
            accounts = self.client.get_accounts()
            if not accounts:
                return

            current_time = datetime.now()

            for account in accounts:
                currency = account.get('currency')
                balance = Decimal(account.get('balance', '0'))

                if currency == 'KRW' or balance <= 0:
                    continue

                symbol = f"{currency}_KRW"

                # 현재가 조회
                ticker = self.client.get_ticker(symbol)
                if not ticker:
                    continue

                current_price = Decimal(str(ticker.get('closing_price', 0)))

                # 포지션 업데이트 또는 생성
                if symbol in self._positions:
                    position = self._positions[symbol]
                    position.quantity = balance
                    position.market_price = current_price
                    position.unrealized_pnl = (current_price - position.average_price) * balance
                    position.last_updated = current_time
                else:
                    # 새 포지션 (평균 단가는 현재가로 추정)
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

    def _notify_fill(self, fill: Fill):
        """체결 콜백 호출."""
        for callback in self._fill_callbacks:
            try:
                callback(fill)
            except Exception as e:
                self.logger.error(f"체결 콜백 호출 중 오류: {e}")

    def _notify_order_update(self, order: OrderResult):
        """주문 업데이트 콜백 호출."""
        for callback in self._order_update_callbacks:
            try:
                callback(order)
            except Exception as e:
                self.logger.error(f"주문 업데이트 콜백 호출 중 오류: {e}")

    def _notify_position_update(self, position: Position):
        """포지션 업데이트 콜백 호출."""
        for callback in self._position_update_callbacks:
            try:
                callback(position)
            except Exception as e:
                self.logger.error(f"포지션 업데이트 콜백 호출 중 오류: {e}")

    def __enter__(self):
        """컨텍스트 매니저 진입."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료."""
        self.stop()