#!/usr/bin/env python3
"""
통합 자동매매 엔진 - 완전 기능 버전
빗썸 API 2.0 JWT 인증 + 실제 주문 실행 + 실시간 모니터링
"""

import asyncio
import os
import sys
import signal
import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# 환경변수 로드
from src.utils.dotenv_simple import load_dotenv
env_file = PROJECT_ROOT / '.env'
load_dotenv(env_file)

# 프로젝트 모듈 import
from src.config import get_settings
from src.exchange.bithumb_client import BithumbClient
from src.core.strategy import StrategyEngine
from src.core.risk import RiskManager
from src.data.database import get_session
from src.utils.logger import setup_logging


class UnifiedTradingEngine:
    """통합 자동매매 엔진"""

    def __init__(self):
        # 설정 로드
        self.settings = get_settings()

        # 로깅 설정
        self.logger = setup_logging()

        # API 클라이언트 (정식 구조 사용)
        self.bithumb = BithumbClient()

        # 전략 엔진
        self.strategy_engine = StrategyEngine()

        # 리스크 매니저
        self.risk_manager = RiskManager()

        # 운영 상태
        self.running = False
        self.cycle_count = 0

        # 거래 설정
        self.target_symbols = ['BTC', 'ETH', 'XRP', 'ADA', 'DOT']
        self.min_order_amount = 5000  # 최소 주문 금액 (원)
        self.max_position_ratio = 0.20  # 종목당 최대 투자 비율 (20%)

        # 실제 주문 실행 여부 (운영 시 True로 변경)
        self.enable_real_orders = os.getenv('ENABLE_REAL_ORDERS', 'false').lower() == 'true'

        # 가격 히스토리 저장소
        self.price_history = {}

        self.logger.info("통합 자동매매 엔진 초기화 완료")

    def signal_handler(self, signum, frame):
        """시그널 핸들러 (Ctrl+C)"""
        self.logger.info(f"종료 시그널 수신: {signum}")
        self.running = False

    async def get_balance(self) -> Dict[str, Any]:
        """계좌 잔고 조회"""
        try:
            # 새로운 API 2.0 엔드포인트 사용
            balance_data = self.bithumb.get_accounts()

            if balance_data and balance_data.get('status') == '0000':
                return balance_data.get('data', {})
            else:
                self.logger.error(f"잔고 조회 실패: {balance_data}")
                return {}

        except Exception as e:
            self.logger.error(f"잔고 조회 중 오류: {e}")
            return {}

    async def get_ticker_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """시세 데이터 조회"""
        try:
            ticker_data = self.bithumb.get_ticker(symbol)

            if ticker_data and ticker_data.get('status') == '0000':
                return ticker_data.get('data')
            else:
                self.logger.warning(f"{symbol} 시세 조회 실패: {ticker_data}")
                return None

        except Exception as e:
            self.logger.error(f"{symbol} 시세 조회 중 오류: {e}")
            return None

    def update_price_history(self, symbol: str, price: float):
        """가격 히스토리 업데이트"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append({
            'price': price,
            'timestamp': datetime.now()
        })

        # 최근 100개 데이터만 보관
        if len(self.price_history[symbol]) > 100:
            self.price_history[symbol] = self.price_history[symbol][-100:]

    def calculate_technical_indicators(self, symbol: str) -> Dict[str, float]:
        """기술적 지표 계산"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 20:
            return {
                'ema_short': 0,
                'ema_long': 0,
                'rsi': 50,
                'signal': 'HOLD'
            }

        prices = [item['price'] for item in self.price_history[symbol]]

        # EMA 계산
        ema_short = self.calculate_ema(prices, 12)
        ema_long = self.calculate_ema(prices, 26)

        # RSI 계산
        rsi = self.calculate_rsi(prices, 14)

        # 신호 생성
        signal = 'HOLD'
        if ema_short > ema_long and rsi < 70:
            signal = 'BUY'
        elif ema_short < ema_long and rsi > 30:
            signal = 'SELL'

        return {
            'ema_short': ema_short,
            'ema_long': ema_long,
            'rsi': rsi,
            'signal': signal
        }

    def calculate_ema(self, prices: List[float], period: int) -> float:
        """지수 이동 평균 계산"""
        if len(prices) < period:
            return sum(prices) / len(prices)

        multiplier = 2 / (period + 1)
        ema = prices[0]

        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """RSI 계산"""
        if len(prices) < period + 1:
            return 50

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        if len(gains) < period:
            return 50

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    async def execute_order(self, symbol: str, side: str, amount: float, price: float) -> bool:
        """주문 실행"""
        try:
            if not self.enable_real_orders:
                self.logger.info(f"[모의] {symbol} {side} 주문: {amount:,.0f}원 @ {price:,.0f}원")
                return True

            # 실제 주문 실행
            if side == 'BUY':
                # 매수 주문
                quantity = amount / price
                result = self.bithumb.place_market_order(
                    side='buy',
                    order_currency=symbol,
                    units=quantity
                )
            else:
                # 매도 주문 (보유 수량 조회 필요)
                # 여기서는 간단히 처리
                quantity = amount / price
                result = self.bithumb.place_market_order(
                    side='sell',
                    order_currency=symbol,
                    units=quantity
                )

            if result and result.get('status') == '0000':
                self.logger.info(f"✅ {symbol} {side} 주문 성공: {result.get('order_id')}")
                return True
            else:
                self.logger.error(f"❌ {symbol} {side} 주문 실패: {result}")
                return False

        except Exception as e:
            self.logger.error(f"❌ {symbol} 주문 실행 중 오류: {e}")
            return False

    async def process_symbol(self, symbol: str):
        """종목별 처리"""
        try:
            # 시세 데이터 조회
            ticker_data = await self.get_ticker_data(symbol)
            if not ticker_data:
                return

            current_price = float(ticker_data.get('closing_price', 0))
            if current_price <= 0:
                return

            # 가격 히스토리 업데이트
            self.update_price_history(symbol, current_price)

            # 기술적 지표 계산
            indicators = self.calculate_technical_indicators(symbol)

            self.logger.info(
                f"📊 {symbol}: ₩{current_price:,.0f} | "
                f"EMA({indicators['ema_short']:.1f}/{indicators['ema_long']:.1f}) | "
                f"RSI({indicators['rsi']:.1f}) | "
                f"신호: {indicators['signal']}"
            )

            # 신호에 따른 주문 실행
            if indicators['signal'] in ['BUY', 'SELL']:
                balance_data = await self.get_balance()
                krw_balance = float(balance_data.get('total_krw', 0))

                if indicators['signal'] == 'BUY' and krw_balance > self.min_order_amount:
                    # 매수 주문
                    order_amount = min(krw_balance * self.max_position_ratio, krw_balance - 1000)
                    if order_amount >= self.min_order_amount:
                        await self.execute_order(symbol, 'BUY', order_amount, current_price)

                elif indicators['signal'] == 'SELL':
                    # 매도 주문 (보유 수량이 있는 경우)
                    symbol_balance = balance_data.get(f'total_{symbol.lower()}', 0)
                    if float(symbol_balance) > 0:
                        order_amount = float(symbol_balance) * current_price * 0.9  # 90% 매도
                        if order_amount >= self.min_order_amount:
                            await self.execute_order(symbol, 'SELL', order_amount, current_price)

        except Exception as e:
            self.logger.error(f"❌ {symbol} 처리 중 오류: {e}")

    async def run_cycle(self):
        """한 사이클 실행"""
        cycle_start = time.time()
        self.cycle_count += 1

        self.logger.info(f"\n🔄 매매 사이클 #{self.cycle_count} 시작 - {datetime.now().strftime('%H:%M:%S')}")

        try:
            # 잔고 정보 출력
            balance_data = await self.get_balance()
            krw_balance = float(balance_data.get('total_krw', 0))
            self.logger.info(f"💰 KRW 잔고: ₩{krw_balance:,.0f}")

            # 모든 대상 종목 처리
            for symbol in self.target_symbols:
                if not self.running:
                    break

                await self.process_symbol(symbol)
                await asyncio.sleep(1)  # API 호출 간격

        except Exception as e:
            self.logger.error(f"❌ 사이클 실행 중 오류: {e}")

        finally:
            cycle_time = time.time() - cycle_start
            self.logger.info(f"⏱️  사이클 완료 ({cycle_time:.1f}초)")

    async def start(self):
        """자동매매 엔진 시작"""
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        self.logger.info("🚀 통합 자동매매 엔진 시작!")
        self.logger.info(f"📈 거래 대상: {', '.join(self.target_symbols)}")
        self.logger.info(f"💰 최소 주문 금액: ₩{self.min_order_amount:,}")
        self.logger.info(f"📊 최대 포지션 비율: {self.max_position_ratio:.1%}")
        self.logger.info(f"⚡ 실제 주문: {'활성화' if self.enable_real_orders else '비활성화'}")
        self.logger.info("=" * 80)

        self.running = True

        try:
            while self.running:
                await self.run_cycle()

                if self.running:
                    self.logger.info("😴 30초 대기...")
                    for i in range(30):
                        if not self.running:
                            break
                        await asyncio.sleep(1)

        except KeyboardInterrupt:
            self.logger.info("🛑 사용자에 의해 중단됨")
        except Exception as e:
            self.logger.error(f"❌ 예상치 못한 오류: {e}")
        finally:
            self.running = False
            self.logger.info("🏁 통합 자동매매 엔진 종료")


async def main():
    """메인 함수"""
    try:
        engine = UnifiedTradingEngine()
        await engine.start()
        return 0
    except Exception as e:
        print(f"❌ 엔진 초기화 실패: {e}")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n프로그램이 중단되었습니다.")
        sys.exit(0)
    except Exception as e:
        print(f"치명적 오류: {e}")
        sys.exit(1)