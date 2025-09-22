"""백테스트 엔진."""

import logging
from datetime import datetime
from decimal import Decimal
from queue import Queue, Empty
from typing import List, Dict, Optional, Callable, Any, Tuple
from uuid import uuid4

from .events import Event, EventType, MarketEvent, SignalEvent, OrderEvent, FillEvent
from .portfolio import Portfolio
from .data_collector import CandleData
from ..core.order_types import OrderSide, OrderType


class ExecutionHandler:
    """백테스트 주문 실행 처리기."""

    def __init__(self, events: Queue, commission_rate: Decimal = Decimal('0.0025')):
        """
        실행 처리기 초기화.

        Args:
            events: 이벤트 큐
            commission_rate: 수수료율
        """
        self.events = events
        self.commission_rate = commission_rate
        self.logger = logging.getLogger(self.__class__.__name__)

        # 슬리피지 설정
        self.slippage_rate = Decimal('0.001')  # 0.1%

    def execute_order(self, order_event: OrderEvent, current_price: Decimal):
        """
        주문 실행.

        Args:
            order_event: 주문 이벤트
            current_price: 현재가
        """
        # 슬리피지 적용
        if order_event.side == OrderSide.BUY:
            fill_price = current_price * (Decimal('1') + self.slippage_rate)
        else:
            fill_price = current_price * (Decimal('1') - self.slippage_rate)

        # 지정가 주문의 경우 가격 확인
        if order_event.order_type == OrderType.LIMIT:
            if order_event.price:
                if order_event.side == OrderSide.BUY and fill_price > order_event.price:
                    return  # 매수 지정가보다 높으면 체결 안됨
                elif order_event.side == OrderSide.SELL and fill_price < order_event.price:
                    return  # 매도 지정가보다 낮으면 체결 안됨
                fill_price = order_event.price

        # 수수료 계산
        commission = order_event.quantity * fill_price * self.commission_rate

        # 체결 이벤트 생성
        fill_event = FillEvent(
            timestamp=order_event.timestamp,
            symbol=order_event.symbol,
            side=order_event.side,
            quantity=order_event.quantity,
            fill_price=fill_price,
            commission=commission,
            order_id=order_event.order_id or f"order_{uuid4().hex[:8]}",
            fill_id=f"fill_{uuid4().hex[:8]}"
        )

        self.events.put(fill_event)
        self.logger.debug(f"주문 체결: {fill_event}")


class BacktestEngine:
    """백테스트 엔진."""

    def __init__(
        self,
        initial_capital: Decimal,
        commission_rate: Decimal = Decimal('0.0025'),
        slippage_rate: Decimal = Decimal('0.001')
    ):
        """
        백테스트 엔진 초기화.

        Args:
            initial_capital: 초기 자본
            commission_rate: 수수료율
            slippage_rate: 슬리피지율
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        self.logger = logging.getLogger(self.__class__.__name__)

        # 컴포넌트 초기화
        self.events = Queue()
        self.portfolio = Portfolio(initial_capital, commission_rate)
        self.execution_handler = ExecutionHandler(self.events, commission_rate)

        # 데이터 저장
        self.market_data: Dict[str, List[CandleData]] = {}
        self.current_data: Dict[str, CandleData] = {}

        # 전략 및 콜백
        self.strategy_callbacks: List[Callable] = []
        self.event_callbacks: Dict[EventType, List[Callable]] = {
            EventType.MARKET: [],
            EventType.SIGNAL: [],
            EventType.ORDER: [],
            EventType.FILL: []
        }

        # 백테스트 상태
        self.current_time: Optional[datetime] = None
        self.is_running = False

        # 성과 추적
        self.signals_generated = 0
        self.orders_executed = 0
        self.fills_completed = 0

    def add_data(self, symbol: str, candles: List[CandleData]):
        """
        백테스트 데이터 추가.

        Args:
            symbol: 종목 코드
            candles: 캔들 데이터 리스트
        """
        self.market_data[symbol] = sorted(candles, key=lambda x: x.timestamp)
        self.logger.info(f"데이터 추가: {symbol} ({len(candles)}개 캔들)")

    def add_strategy_callback(self, callback: Callable[[Dict[str, CandleData]], None]):
        """
        전략 콜백 추가.

        Args:
            callback: 전략 함수 (현재 시장 데이터를 받아 신호 생성)
        """
        self.strategy_callbacks.append(callback)

    def add_event_callback(self, event_type: EventType, callback: Callable[[Event], None]):
        """
        이벤트 콜백 추가.

        Args:
            event_type: 이벤트 타입
            callback: 콜백 함수
        """
        if event_type in self.event_callbacks:
            self.event_callbacks[event_type].append(callback)

    def generate_market_events(self, timestamp: datetime) -> List[MarketEvent]:
        """
        시장 이벤트 생성.

        Args:
            timestamp: 현재 시점

        Returns:
            시장 이벤트 리스트
        """
        market_events = []

        for symbol, candles in self.market_data.items():
            # 현재 시점의 캔들 데이터 찾기
            current_candle = None
            for candle in candles:
                if candle.timestamp == timestamp:
                    current_candle = candle
                    break

            if current_candle:
                self.current_data[symbol] = current_candle

                market_event = MarketEvent(
                    timestamp=timestamp,
                    symbol=symbol,
                    open_price=current_candle.open_price,
                    high_price=current_candle.high_price,
                    low_price=current_candle.low_price,
                    close_price=current_candle.close_price,
                    volume=current_candle.volume
                )
                market_events.append(market_event)

        return market_events

    def run_strategy_callbacks(self):
        """전략 콜백 실행."""
        if not self.current_data:
            return

        for callback in self.strategy_callbacks:
            try:
                callback(self.current_data.copy())
            except Exception as e:
                self.logger.error(f"전략 콜백 실행 오류: {e}")

    def process_events(self):
        """이벤트 처리."""
        while not self.events.empty():
            try:
                event = self.events.get(False)
            except Empty:
                break

            # 이벤트 타입별 처리
            if event.event_type == EventType.MARKET:
                self._handle_market_event(event)
            elif event.event_type == EventType.SIGNAL:
                self._handle_signal_event(event)
            elif event.event_type == EventType.ORDER:
                self._handle_order_event(event)
            elif event.event_type == EventType.FILL:
                self._handle_fill_event(event)

            # 콜백 실행
            for callback in self.event_callbacks[event.event_type]:
                try:
                    callback(event)
                except Exception as e:
                    self.logger.error(f"이벤트 콜백 실행 오류: {e}")

    def _handle_market_event(self, event: MarketEvent):
        """마켓 이벤트 처리."""
        # 포트폴리오 시장가 업데이트
        self.portfolio.update_market_data(
            event.symbol,
            event.close_price,
            event.timestamp
        )

    def _handle_signal_event(self, event: SignalEvent):
        """신호 이벤트 처리."""
        self.signals_generated += 1
        self.logger.debug(f"신호 처리: {event}")

        # 신호를 주문으로 변환 (간단한 구현)
        # 실제 구현에서는 더 복잡한 로직 사용
        if event.symbol in self.current_data:
            current_price = self.current_data[event.symbol].close_price

            # 포지션 사이즈 계산 (간단한 예시)
            if event.signal_type == OrderSide.BUY:
                buying_power = self.portfolio.calculate_buying_power(event.symbol, current_price)
                quantity = min(buying_power, current_price)  # 1주 또는 가용 자금 내에서
            else:
                position = self.portfolio.get_position(event.symbol)
                if position and position.quantity > 0:
                    quantity = position.quantity
                else:
                    return  # 매도할 포지션이 없음

            if quantity > 0:
                order_event = OrderEvent(
                    timestamp=event.timestamp,
                    symbol=event.symbol,
                    order_type=OrderType.MARKET,
                    side=event.signal_type,
                    quantity=quantity,
                    strategy_id=event.strategy_id
                )
                self.events.put(order_event)

    def _handle_order_event(self, event: OrderEvent):
        """주문 이벤트 처리."""
        self.orders_executed += 1
        self.logger.debug(f"주문 처리: {event}")

        # 현재가 확인
        if event.symbol in self.current_data:
            current_price = self.current_data[event.symbol].close_price
            self.execution_handler.execute_order(event, current_price)

    def _handle_fill_event(self, event: FillEvent):
        """체결 이벤트 처리."""
        self.fills_completed += 1
        self.logger.debug(f"체결 처리: {event}")

        # 포트폴리오 업데이트
        self.portfolio.update_fill(event)

    def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: Decimal,
        price: Optional[Decimal] = None,
        strategy_id: Optional[str] = None
    ):
        """
        주문 제출.

        Args:
            symbol: 종목 코드
            side: 매수/매도
            order_type: 주문 유형
            quantity: 수량
            price: 가격 (지정가의 경우)
            strategy_id: 전략 ID
        """
        if not self.current_time:
            return

        order_event = OrderEvent(
            timestamp=self.current_time,
            symbol=symbol,
            order_type=order_type,
            side=side,
            quantity=quantity,
            price=price,
            strategy_id=strategy_id
        )
        self.events.put(order_event)

    def submit_signal(
        self,
        symbol: str,
        signal_type: OrderSide,
        strength: Decimal,
        strategy_id: str,
        reason: str = ""
    ):
        """
        신호 제출.

        Args:
            symbol: 종목 코드
            signal_type: 신호 유형 (매수/매도)
            strength: 신호 강도
            strategy_id: 전략 ID
            reason: 신호 이유
        """
        if not self.current_time:
            return

        signal_event = SignalEvent(
            timestamp=self.current_time,
            symbol=symbol,
            signal_type=signal_type,
            strength=strength,
            strategy_id=strategy_id,
            reason=reason
        )
        self.events.put(signal_event)

    def run(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        """
        백테스트 실행.

        Args:
            start_date: 시작 날짜
            end_date: 종료 날짜
        """
        if not self.market_data:
            raise ValueError("시장 데이터가 없습니다.")

        # 전체 시간 범위 계산
        all_timestamps = set()
        for candles in self.market_data.values():
            for candle in candles:
                if start_date and candle.timestamp < start_date:
                    continue
                if end_date and candle.timestamp > end_date:
                    continue
                all_timestamps.add(candle.timestamp)

        timestamps = sorted(all_timestamps)

        if not timestamps:
            raise ValueError("지정된 기간에 데이터가 없습니다.")

        self.logger.info(f"백테스트 시작: {timestamps[0]} ~ {timestamps[-1]} ({len(timestamps)}개 시점)")
        self.is_running = True

        try:
            for timestamp in timestamps:
                self.current_time = timestamp

                # 1. 시장 이벤트 생성
                market_events = self.generate_market_events(timestamp)
                for event in market_events:
                    self.events.put(event)

                # 2. 이벤트 처리
                self.process_events()

                # 3. 전략 실행
                self.run_strategy_callbacks()

                # 4. 다시 이벤트 처리 (전략에서 생성된 신호/주문)
                self.process_events()

                # 5. 포트폴리오 업데이트
                self.portfolio.update_equity_curve(timestamp)

        except Exception as e:
            self.logger.error(f"백테스트 실행 중 오류: {e}")
            raise
        finally:
            self.is_running = False

        self.logger.info("백테스트 완료")
        self._log_summary()

    def _log_summary(self):
        """백테스트 결과 요약 로그."""
        summary = self.get_summary()
        self.logger.info("=== 백테스트 결과 요약 ===")
        self.logger.info(f"초기 자본: {summary['initial_capital']:,.2f}원")
        self.logger.info(f"최종 자산: {summary['final_equity']:,.2f}원")
        self.logger.info(f"총 수익률: {summary['total_return']:.2f}%")
        self.logger.info(f"총 거래 수: {summary['total_trades']}회")
        self.logger.info(f"생성된 신호: {summary['signals_generated']}개")
        self.logger.info(f"실행된 주문: {summary['orders_executed']}개")
        self.logger.info(f"완료된 체결: {summary['fills_completed']}개")

    def get_summary(self) -> Dict[str, Any]:
        """백테스트 결과 요약."""
        portfolio_summary = self.portfolio.get_portfolio_summary()
        trade_stats = self.portfolio.get_trade_statistics()

        return {
            'initial_capital': float(self.initial_capital),
            'final_equity': portfolio_summary['total_equity'],
            'total_return': portfolio_summary['total_return_pct'],
            'max_drawdown': float(self.portfolio.get_max_drawdown()),
            'total_trades': portfolio_summary['total_trades'],
            'total_commission': portfolio_summary['total_commission'],
            'signals_generated': self.signals_generated,
            'orders_executed': self.orders_executed,
            'fills_completed': self.fills_completed,
            'win_rate': trade_stats.get('win_rate_pct', 0),
            'profitable_trades': trade_stats.get('profitable_trades', 0),
            'losing_trades': trade_stats.get('losing_trades', 0)
        }

    def get_equity_curve(self) -> List[Tuple[datetime, float]]:
        """자산 곡선 반환."""
        return [(ts, float(equity)) for ts, equity in self.portfolio.equity_curve]

    def get_drawdown_curve(self) -> List[Tuple[datetime, float]]:
        """드로다운 곡선 반환."""
        return [(ts, float(dd)) for ts, dd in self.portfolio.drawdown_curve]

    def get_trades(self) -> List[Dict]:
        """거래 내역 반환."""
        trades = []
        for trade in self.portfolio.trades:
            trades.append({
                'timestamp': trade.timestamp,
                'symbol': trade.symbol,
                'side': trade.side.value,
                'quantity': float(trade.quantity),
                'price': float(trade.price),
                'commission': float(trade.commission),
                'gross_amount': float(trade.gross_amount),
                'net_amount': float(trade.net_amount)
            })
        return trades