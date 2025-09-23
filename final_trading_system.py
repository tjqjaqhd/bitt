#!/usr/bin/env python3
"""
최종 완성형 자동매매 시스템
- 빗썸 API 2.0 JWT 인증
- 실제 주문 실행 가능
- 완전 독립 실행형
"""

import asyncio
import os
import sys
import signal
import time
import logging
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, List
from pathlib import Path

# 환경변수 로드
def load_env():
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

load_env()

import requests
import jwt
import uuid
import hashlib
import hmac
import base64
from urllib.parse import urlencode


class SimpleBithumbClient:
    """간단한 빗썸 API 클라이언트 (JWT 2.0)"""

    def __init__(self):
        self.api_key = os.getenv('BITHUMB_API_KEY')
        self.secret_key = os.getenv('BITHUMB_SECRET_KEY')
        self.base_url = "https://api.bithumb.com"

        if not self.api_key or not self.secret_key:
            raise ValueError("빗썸 API 키가 설정되지 않았습니다!")

        print(f"🔑 API Key: {self.api_key[:10]}...")

    def _create_jwt_token(self, params=None):
        """JWT 토큰 생성 (API 2.0 방식)"""
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }

        # 요청 파라미터가 있는 경우 해시 추가
        if params:
            query_string = urlencode(sorted(params.items()))
            query_hash = hashlib.sha512(query_string.encode('utf-8')).hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        return jwt.encode(payload, self.secret_key, algorithm='HS256')

    def _make_public_request(self, endpoint, params=None):
        """공개 API 요청"""
        try:
            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ 공개 API 요청 실패 ({endpoint}): {e}")
            return None

    def _make_private_request(self, endpoint, params=None):
        """인증된 API 요청"""
        try:
            jwt_token = self._create_jwt_token(params)
            headers = {
                'Authorization': f'Bearer {jwt_token}',
                'Content-Type': 'application/json'
            }

            url = f"{self.base_url}{endpoint}"
            response = requests.post(url, json=params or {}, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ 인증 API 요청 실패 ({endpoint}): {e}")
            return None

    def get_ticker(self, symbol):
        """시세 조회"""
        endpoint = f"/public/ticker/{symbol}_KRW"
        data = self._make_public_request(endpoint)
        if data and data.get('status') == '0000':
            return data.get('data')
        return None

    def get_balance(self):
        """잔고 조회 (API 2.0)"""
        endpoint = "/v1/accounts"
        data = self._make_private_request(endpoint)
        if data and data.get('status') == '0000':
            return data.get('data')
        return None

    def place_order(self, symbol, side, amount, price=None, order_type='market'):
        """주문 실행 (API 2.0)"""
        params = {
            'market': f'{symbol}_KRW',
            'side': side,  # 'bid' (매수) 또는 'ask' (매도)
            'volume': str(amount),
            'ord_type': order_type
        }

        if order_type == 'limit' and price:
            params['price'] = str(price)

        endpoint = "/v1/orders"
        return self._make_private_request(endpoint, params)


class TradingStrategy:
    """간단한 EMA + RSI 전략"""

    def __init__(self):
        self.price_history = {}

    def add_price(self, symbol, price):
        """가격 데이터 추가"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append({
            'price': float(price),
            'timestamp': datetime.now()
        })

        # 최근 100개만 유지
        if len(self.price_history[symbol]) > 100:
            self.price_history[symbol] = self.price_history[symbol][-100:]

    def calculate_ema(self, prices, period):
        """지수 이동 평균 계산"""
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0

        multiplier = 2 / (period + 1)
        ema = prices[0]

        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def calculate_rsi(self, prices, period=14):
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
        return 100 - (100 / (1 + rs))

    def generate_signal(self, symbol):
        """매매 신호 생성"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 20:
            return 'HOLD', 50, 0, 0

        prices = [item['price'] for item in self.price_history[symbol]]

        # EMA 계산
        ema_short = self.calculate_ema(prices, 12)
        ema_long = self.calculate_ema(prices, 26)

        # RSI 계산
        rsi = self.calculate_rsi(prices)

        # 신호 생성
        signal = 'HOLD'
        if ema_short > ema_long and rsi < 70:
            signal = 'BUY'
        elif ema_short < ema_long and rsi > 30:
            signal = 'SELL'

        return signal, rsi, ema_short, ema_long


class FinalTradingSystem:
    """최종 자동매매 시스템"""

    def __init__(self):
        # 로깅 설정
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(levelname)s | %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('trading_system.log', encoding='utf-8')
            ]
        )
        self.logger = logging.getLogger(__name__)

        # API 클라이언트
        self.client = SimpleBithumbClient()

        # 전략
        self.strategy = TradingStrategy()

        # 시스템 설정
        self.target_symbols = ['BTC', 'ETH', 'XRP', 'ADA', 'DOT']
        self.min_order_amount = 5000  # 최소 주문 금액
        self.max_position_ratio = 0.20  # 종목당 최대 투자 비율
        self.enable_real_orders = os.getenv('ENABLE_REAL_ORDERS', 'false').lower() == 'true'

        # 운영 상태
        self.running = False
        self.cycle_count = 0

        self.logger.info("🚀 최종 자동매매 시스템 초기화 완료")

    def signal_handler(self, signum, frame):
        """시그널 핸들러"""
        self.logger.info(f"🛑 종료 시그널 수신: {signum}")
        self.running = False

    async def get_account_info(self):
        """계좌 정보 조회"""
        try:
            balance_data = self.client.get_balance()
            if balance_data:
                krw_balance = float(balance_data.get('total_krw', 0))
                return {
                    'krw_balance': krw_balance,
                    'balances': balance_data
                }
            return {'krw_balance': 0, 'balances': {}}
        except Exception as e:
            self.logger.error(f"계좌 정보 조회 실패: {e}")
            return {'krw_balance': 0, 'balances': {}}

    async def process_symbol(self, symbol):
        """종목별 매매 처리"""
        try:
            # 시세 조회
            ticker_data = self.client.get_ticker(symbol)
            if not ticker_data:
                return

            current_price = float(ticker_data.get('closing_price', 0))
            if current_price <= 0:
                return

            # 가격 데이터 추가
            self.strategy.add_price(symbol, current_price)

            # 신호 생성
            signal, rsi, ema_short, ema_long = self.strategy.generate_signal(symbol)

            self.logger.info(
                f"📊 {symbol}: ₩{current_price:,.0f} | "
                f"EMA({ema_short:.1f}/{ema_long:.1f}) | "
                f"RSI({rsi:.1f}) | 신호: {signal}"
            )

            # 주문 실행
            if signal in ['BUY', 'SELL']:
                await self.execute_signal(symbol, signal, current_price)

        except Exception as e:
            self.logger.error(f"❌ {symbol} 처리 중 오류: {e}")

    async def execute_signal(self, symbol, signal, current_price):
        """신호에 따른 주문 실행"""
        try:
            account_info = await self.get_account_info()
            krw_balance = account_info['krw_balance']

            if signal == 'BUY' and krw_balance > self.min_order_amount:
                # 매수 주문
                order_amount = min(krw_balance * self.max_position_ratio, krw_balance - 1000)
                if order_amount >= self.min_order_amount:
                    quantity = order_amount / current_price

                    if self.enable_real_orders:
                        # 실제 주문 실행
                        result = self.client.place_order(symbol, 'bid', quantity)
                        if result and result.get('status') == '0000':
                            self.logger.info(f"✅ {symbol} 매수 주문 성공: {result.get('order_id')}")
                        else:
                            self.logger.error(f"❌ {symbol} 매수 주문 실패: {result}")
                    else:
                        self.logger.info(f"[모의] {symbol} 매수: {quantity:.8f} @ ₩{current_price:,.0f}")

            elif signal == 'SELL':
                # 매도 주문 (보유 수량 확인 필요)
                balances = account_info.get('balances', {})
                symbol_balance = balances.get(f'total_{symbol.lower()}', 0)

                if float(symbol_balance) > 0:
                    quantity = float(symbol_balance) * 0.9  # 90% 매도

                    if self.enable_real_orders:
                        # 실제 주문 실행
                        result = self.client.place_order(symbol, 'ask', quantity)
                        if result and result.get('status') == '0000':
                            self.logger.info(f"✅ {symbol} 매도 주문 성공: {result.get('order_id')}")
                        else:
                            self.logger.error(f"❌ {symbol} 매도 주문 실패: {result}")
                    else:
                        self.logger.info(f"[모의] {symbol} 매도: {quantity:.8f} @ ₩{current_price:,.0f}")

        except Exception as e:
            self.logger.error(f"❌ {symbol} 주문 실행 중 오류: {e}")

    async def run_cycle(self):
        """한 사이클 실행"""
        cycle_start = time.time()
        self.cycle_count += 1

        self.logger.info(f"\n🔄 매매 사이클 #{self.cycle_count} - {datetime.now().strftime('%H:%M:%S')}")

        try:
            # 계좌 정보 출력
            account_info = await self.get_account_info()
            krw_balance = account_info['krw_balance']
            self.logger.info(f"💰 KRW 잔고: ₩{krw_balance:,.0f}")

            # 모든 종목 처리
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
        """시스템 시작"""
        # 시그널 핸들러 등록
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        self.logger.info("🚀 최종 자동매매 시스템 시작!")
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
            self.logger.info("🏁 최종 자동매매 시스템 종료")


async def main():
    """메인 함수"""
    try:
        system = FinalTradingSystem()
        await system.start()
        return 0
    except Exception as e:
        print(f"❌ 시스템 초기화 실패: {e}")
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