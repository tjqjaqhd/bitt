"""백테스트 포트폴리오 관리."""

import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from .events import FillEvent
from ..core.order_types import OrderSide


@dataclass
class Position:
    """포지션 정보."""
    symbol: str
    quantity: Decimal = Decimal('0')
    average_price: Decimal = Decimal('0')
    realized_pnl: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    market_price: Decimal = Decimal('0')
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def market_value(self) -> Decimal:
        """현재 시장 가치."""
        return self.quantity * self.market_price

    @property
    def cost_basis(self) -> Decimal:
        """매입 원가."""
        return self.quantity * self.average_price

    @property
    def total_pnl(self) -> Decimal:
        """총 손익 (실현 + 미실현)."""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def is_long(self) -> bool:
        """롱 포지션 여부."""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """숏 포지션 여부."""
        return self.quantity < 0

    @property
    def is_flat(self) -> bool:
        """플랫 포지션 여부."""
        return self.quantity == 0

    def update_market_price(self, new_price: Decimal, timestamp: datetime):
        """시장가 업데이트."""
        self.market_price = new_price
        if not self.is_flat:
            self.unrealized_pnl = (new_price - self.average_price) * self.quantity
        self.last_updated = timestamp


@dataclass
class Trade:
    """거래 기록."""
    symbol: str
    side: OrderSide
    quantity: Decimal
    price: Decimal
    commission: Decimal
    timestamp: datetime
    fill_id: str

    @property
    def gross_amount(self) -> Decimal:
        """총 거래 금액."""
        return self.quantity * self.price

    @property
    def net_amount(self) -> Decimal:
        """순 거래 금액 (수수료 차감)."""
        if self.side == OrderSide.BUY:
            return self.gross_amount + self.commission
        else:
            return self.gross_amount - self.commission


class Portfolio:
    """백테스트 포트폴리오."""

    def __init__(self, initial_capital: Decimal, commission_rate: Decimal = Decimal('0.0025')):
        """
        포트폴리오 초기화.

        Args:
            initial_capital: 초기 자본
            commission_rate: 수수료율 (기본 0.25%)
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.logger = logging.getLogger(self.__class__.__name__)

        # 포지션 관리
        self.positions: Dict[str, Position] = {}
        self.cash = initial_capital

        # 거래 기록
        self.trades: List[Trade] = []
        self.fills: List[FillEvent] = []

        # 성과 추적
        self.equity_curve: List[Tuple[datetime, Decimal]] = []
        self.drawdown_curve: List[Tuple[datetime, Decimal]] = []

        # 통계
        self.total_commission = Decimal('0')
        self.total_slippage = Decimal('0')

    def update_fill(self, fill_event: FillEvent):
        """
        체결 이벤트 처리.

        Args:
            fill_event: 체결 이벤트
        """
        symbol = fill_event.symbol
        side = fill_event.side
        quantity = fill_event.quantity
        price = fill_event.fill_price
        commission = fill_event.commission

        self.logger.debug(f"체결 처리: {side.value} {quantity} {symbol} @ {price}")

        # 포지션 업데이트
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)

        position = self.positions[symbol]
        self._update_position(position, side, quantity, price, commission)

        # 현금 업데이트
        if side == OrderSide.BUY:
            self.cash -= (quantity * price + commission)
        else:
            self.cash += (quantity * price - commission)

        # 거래 기록
        trade = Trade(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            commission=commission,
            timestamp=fill_event.timestamp,
            fill_id=fill_event.fill_id
        )
        self.trades.append(trade)
        self.fills.append(fill_event)

        # 통계 업데이트
        self.total_commission += commission

        self.logger.info(f"포지션 업데이트: {symbol} {position.quantity} @ {position.average_price}")

    def _update_position(
        self,
        position: Position,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal,
        commission: Decimal
    ):
        """포지션 업데이트."""
        if side == OrderSide.BUY:
            if position.quantity >= 0:
                # 롱 추가 또는 신규 롱
                total_cost = position.quantity * position.average_price + quantity * price
                position.quantity += quantity
                position.average_price = total_cost / position.quantity if position.quantity > 0 else Decimal('0')
            else:
                # 숏 커버
                if quantity >= abs(position.quantity):
                    # 완전 청산 + 롱 전환
                    cover_quantity = abs(position.quantity)
                    realized_pnl = (position.average_price - price) * cover_quantity - commission
                    position.realized_pnl += realized_pnl

                    remaining_quantity = quantity - cover_quantity
                    if remaining_quantity > 0:
                        position.quantity = remaining_quantity
                        position.average_price = price
                    else:
                        position.quantity = Decimal('0')
                        position.average_price = Decimal('0')
                else:
                    # 부분 청산
                    realized_pnl = (position.average_price - price) * quantity - commission
                    position.realized_pnl += realized_pnl
                    position.quantity += quantity  # quantity는 양수, position.quantity는 음수

        else:  # SELL
            if position.quantity <= 0:
                # 숏 추가 또는 신규 숏
                total_cost = abs(position.quantity) * position.average_price + quantity * price
                position.quantity -= quantity
                position.average_price = total_cost / abs(position.quantity) if position.quantity != 0 else Decimal('0')
            else:
                # 롱 청산
                if quantity >= position.quantity:
                    # 완전 청산 + 숏 전환
                    sell_quantity = position.quantity
                    realized_pnl = (price - position.average_price) * sell_quantity - commission
                    position.realized_pnl += realized_pnl

                    remaining_quantity = quantity - sell_quantity
                    if remaining_quantity > 0:
                        position.quantity = -remaining_quantity
                        position.average_price = price
                    else:
                        position.quantity = Decimal('0')
                        position.average_price = Decimal('0')
                else:
                    # 부분 청산
                    realized_pnl = (price - position.average_price) * quantity - commission
                    position.realized_pnl += realized_pnl
                    position.quantity -= quantity

    def update_market_data(self, symbol: str, price: Decimal, timestamp: datetime):
        """
        시장 데이터 업데이트.

        Args:
            symbol: 종목 코드
            price: 현재가
            timestamp: 시점
        """
        if symbol in self.positions:
            self.positions[symbol].update_market_price(price, timestamp)

    def calculate_total_equity(self) -> Decimal:
        """총 자산 계산."""
        total_equity = self.cash

        for position in self.positions.values():
            if not position.is_flat:
                total_equity += position.market_value

        return total_equity

    def update_equity_curve(self, timestamp: datetime):
        """자산 곡선 업데이트."""
        total_equity = self.calculate_total_equity()
        self.equity_curve.append((timestamp, total_equity))

        # 드로다운 계산
        if self.equity_curve:
            peak = max(eq[1] for eq in self.equity_curve)
            drawdown = (total_equity - peak) / peak * Decimal('100')
            self.drawdown_curve.append((timestamp, drawdown))

    def get_portfolio_summary(self) -> Dict:
        """포트폴리오 요약 정보."""
        total_equity = self.calculate_total_equity()
        total_return = (total_equity - self.initial_capital) / self.initial_capital * Decimal('100')

        # 활성 포지션
        active_positions = {
            symbol: position for symbol, position in self.positions.items()
            if not position.is_flat
        }

        # 총 손익
        total_realized_pnl = sum(pos.realized_pnl for pos in self.positions.values())
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in self.positions.values())

        return {
            'initial_capital': float(self.initial_capital),
            'total_equity': float(total_equity),
            'cash': float(self.cash),
            'total_return_pct': float(total_return),
            'realized_pnl': float(total_realized_pnl),
            'unrealized_pnl': float(total_unrealized_pnl),
            'total_commission': float(self.total_commission),
            'active_positions': len(active_positions),
            'total_trades': len(self.trades)
        }

    def get_position(self, symbol: str) -> Optional[Position]:
        """포지션 조회."""
        return self.positions.get(symbol)

    def get_all_positions(self) -> Dict[str, Position]:
        """모든 포지션 조회."""
        return self.positions.copy()

    def calculate_buying_power(self, symbol: str, price: Decimal) -> Decimal:
        """매수 가능 수량 계산."""
        available_cash = self.cash
        commission = price * self.commission_rate
        max_quantity = available_cash / (price + commission)
        return max_quantity

    def can_sell(self, symbol: str, quantity: Decimal) -> bool:
        """매도 가능 여부 확인."""
        if symbol not in self.positions:
            return False

        position = self.positions[symbol]
        return position.quantity >= quantity

    def get_daily_returns(self) -> List[Tuple[datetime, Decimal]]:
        """일별 수익률 계산."""
        if len(self.equity_curve) < 2:
            return []

        daily_returns = []
        for i in range(1, len(self.equity_curve)):
            prev_equity = self.equity_curve[i-1][1]
            curr_equity = self.equity_curve[i][1]
            timestamp = self.equity_curve[i][0]

            if prev_equity > 0:
                daily_return = (curr_equity - prev_equity) / prev_equity * Decimal('100')
                daily_returns.append((timestamp, daily_return))

        return daily_returns

    def get_max_drawdown(self) -> Decimal:
        """최대 낙폭 계산."""
        if not self.drawdown_curve:
            return Decimal('0')

        return min(dd[1] for dd in self.drawdown_curve)

    def get_trade_statistics(self) -> Dict:
        """거래 통계."""
        if not self.trades:
            return {}

        # 수익/손실 거래 분리
        profitable_trades = []
        losing_trades = []

        for trade in self.trades:
            # 간단한 구현: 매도 거래에서만 손익 계산
            if trade.side == OrderSide.SELL:
                symbol = trade.symbol
                if symbol in self.positions:
                    position = self.positions[symbol]
                    if position.realized_pnl > 0:
                        profitable_trades.append(trade)
                    else:
                        losing_trades.append(trade)

        total_trades = len(self.trades)
        win_rate = len(profitable_trades) / total_trades * 100 if total_trades > 0 else 0

        return {
            'total_trades': total_trades,
            'profitable_trades': len(profitable_trades),
            'losing_trades': len(losing_trades),
            'win_rate_pct': win_rate,
            'total_commission': float(self.total_commission)
        }