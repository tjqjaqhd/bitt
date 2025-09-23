#!/usr/bin/env python3
"""개선된 자동매매 엔진 - 실제 주문 실행 포함."""

import asyncio
import os
import sys
import signal
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 간단한 dotenv 로더
from pathlib import Path

def load_dotenv(env_file_path: Path):
    """간단한 .env 파일 로더"""
    if env_file_path.exists():
        with open(env_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# .env 파일 로드
env_file = Path(__file__).parent / '.env'
load_dotenv(env_file)

import requests
import jwt
import json
import base64
import hashlib
import hmac
from urllib.parse import urlencode


class BithumbRealAPIClient:
    """빗썸 실제 API 클라이언트 (JWT 인증)"""

    def __init__(self):
        self.api_key = os.getenv('BITHUMB_API_KEY')
        self.secret_key = os.getenv('BITHUMB_SECRET_KEY')
        self.base_url = "https://api.bithumb.com"

        if not self.api_key or not self.secret_key:
            raise ValueError("API 키가 설정되지 않았습니다!")

        print(f"🔑 API Key: {self.api_key[:10]}...")

    def _get_jwt_token(self, params=None):
        """JWT 토큰 생성"""
        import uuid
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }
        jwt_token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return jwt_token

    def _make_authenticated_request(self, endpoint, params=None):
        """인증된 API 요청"""
        if params is None:
            params = {}

        jwt_token = self._get_jwt_token(params)
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Content-Type': 'application/json'
        }

        url = f"{self.base_url}{endpoint}"

        try:
            response = requests.post(url, json=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ API 요청 실패: {e}")
            return None

    def get_ticker(self, symbol):
        """시세 조회 (공개 API)"""
        try:
            url = f"{self.base_url}/public/ticker/{symbol}_KRW"
            response = requests.get(url, timeout=10)
            data = response.json()

            if data.get('status') == '0000':
                return data.get('data')
            return None
        except Exception as e:
            print(f"❌ 시세 조회 실패: {e}")
            return None

    def get_balance(self):
        """잔고 조회 (구버전 API 사용)"""
        try:
            # 구버전 API 엔드포인트 사용
            url = f"{self.base_url}/info/balance"

            # 구버전 HMAC 서명 방식
            import uuid
            nonce = str(int(time.time() * 1000))
            params = {
                "order_currency": "ALL",
                "payment_currency": "KRW",
                "endpoint": "/info/balance",
                "nonce": nonce
            }

            # 파라미터 정렬 및 인코딩
            query_string = urlencode(sorted(params.items()))

            # HMAC-SHA512 서명 생성 후 Base64 인코딩
            signature_bytes = hmac.new(
                self.secret_key.encode(),
                query_string.encode(),
                hashlib.sha512
            ).digest()
            signature = base64.b64encode(signature_bytes).decode()

            headers = {
                'Api-Key': self.api_key,
                'Api-Sign': signature,
                'Api-Nonce': nonce,
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(url, data=params, headers=headers, timeout=10)
            data = response.json()

            if data.get('status') == '0000':
                return data.get('data')
            else:
                print(f"❌ 잔고 조회 API 오류: {data}")
                return None

        except Exception as e:
            print(f"❌ 잔고 조회 실패: {e}")
            return None

    def place_order(self, symbol, side, quantity, price=None, order_type='market'):
        """주문 실행"""
        params = {
            'market': f'{symbol}_KRW',
            'side': side,  # 'bid' (매수) 또는 'ask' (매도)
            'volume': str(quantity),
            'ord_type': order_type
        }

        if order_type == 'limit' and price:
            params['price'] = str(price)

        return self._make_authenticated_request('/v1/orders', params)


class TradingStrategy:
    """간단한 EMA + RSI 전략"""

    def __init__(self):
        self.price_history = {}
        self.signals_history = {}

    def calculate_ema(self, prices, period):
        """지수 이동 평균 계산"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = prices[0]

        for price in prices[1:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))

        return ema

    def calculate_rsi(self, prices, period=14):
        """RSI 계산"""
        if len(prices) < period + 1:
            return 50  # 중립값

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

    def get_signal(self, symbol, current_price):
        """매매 신호 생성"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []

        self.price_history[symbol].append(current_price)

        # 최근 50개 가격만 유지
        if len(self.price_history[symbol]) > 50:
            self.price_history[symbol] = self.price_history[symbol][-50:]

        prices = self.price_history[symbol]

        if len(prices) < 20:
            return 'HOLD', 50  # 데이터 부족

        # EMA 계산
        ema_short = self.calculate_ema(prices, 12)
        ema_long = self.calculate_ema(prices, 26)

        # RSI 계산
        rsi = self.calculate_rsi(prices)

        # 신호 생성
        signal = 'HOLD'

        if ema_short and ema_long:
            if ema_short > ema_long and rsi < 70:  # 상승 추세 + 과매수 아님
                if rsi < 30:  # 과매도 영역
                    signal = 'BUY'
                elif rsi > 50:  # 중립 이상
                    signal = 'BUY'
            elif ema_short < ema_long and rsi > 30:  # 하락 추세 + 과매도 아님
                if rsi > 70:  # 과매수 영역
                    signal = 'SELL'
                elif rsi < 50:  # 중립 이하
                    signal = 'SELL'

        return signal, rsi


class AutoTradingEngine:
    """자동매매 엔진"""

    def __init__(self):
        self.client = BithumbRealAPIClient()
        self.strategy = TradingStrategy()
        self.running = False
        self.positions = {}  # 보유 포지션
        self.min_order_amount = 10000  # 최소 주문 금액 (10,000원)
        self.max_position_ratio = 0.05  # 최대 포지션 비율 (5%)

        # 거래 대상 코인들
        self.target_symbols = ['BTC', 'ETH', 'XRP', 'DOGE', 'WLD']

        # 시그널 처리를 위한 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """종료 시그널 처리"""
        print(f"\n🛑 종료 신호 수신 ({signum})")
        self.running = False

    def get_krw_balance(self):
        """KRW 잔고 조회"""
        balance_data = self.client.get_balance()
        if balance_data:
            # 빗썸 구버전 API 응답 형식에 맞춰 파싱
            if isinstance(balance_data, dict):
                krw_info = balance_data.get('total_krw')
                if krw_info:
                    return float(krw_info)

                # 다른 형식도 시도
                available_krw = balance_data.get('available_krw')
                if available_krw:
                    return float(available_krw)
        return 0

    def get_coin_balance(self, symbol):
        """특정 코인 잔고 조회"""
        balance_data = self.client.get_balance()
        if balance_data and isinstance(balance_data, dict):
            # 코인별 잔고 확인
            coin_key = f'available_{symbol.lower()}'
            coin_balance = balance_data.get(coin_key)
            if coin_balance:
                return float(coin_balance)

            # 대문자로도 확인
            coin_key_upper = f'available_{symbol.upper()}'
            coin_balance_upper = balance_data.get(coin_key_upper)
            if coin_balance_upper:
                return float(coin_balance_upper)
        return 0

    def calculate_order_amount(self, signal, current_price, symbol):
        """주문 금액 계산"""
        krw_balance = self.get_krw_balance()

        if signal == 'BUY':
            # 매수: 보유 KRW의 일정 비율
            max_amount = krw_balance * self.max_position_ratio
            order_amount = min(max_amount, 30000)  # 최대 3만원
            return max(order_amount, self.min_order_amount) if order_amount >= self.min_order_amount else 0

        elif signal == 'SELL':
            # 매도: 보유 코인의 50%
            coin_balance = self.get_coin_balance(symbol)
            if coin_balance > 0:
                sell_amount = coin_balance * 0.5
                # 최소 거래 단위 확인 (임시로 0.001 설정)
                min_unit = 0.001
                return sell_amount if sell_amount >= min_unit else 0

        return 0

    def execute_order(self, symbol, signal, current_price, rsi):
        """실제 주문 실행"""
        try:
            if signal == 'BUY':
                order_amount = self.calculate_order_amount(signal, current_price, symbol)
                if order_amount >= self.min_order_amount:
                    quantity = order_amount / current_price

                    print(f"💰 매수 주문 실행: {symbol}")
                    print(f"   - 금액: {order_amount:,.0f}원")
                    print(f"   - 수량: {quantity:.6f}")
                    print(f"   - 가격: {current_price:,.0f}원")

                    # 실제 주문 (주석 해제하여 활성화)
                    # result = self.client.place_order(symbol, 'bid', quantity, order_type='market')
                    # if result:
                    #     print(f"✅ 매수 주문 성공: {result}")
                    # else:
                    #     print(f"❌ 매수 주문 실패")

                    print("⚠️  실제 주문은 안전을 위해 비활성화됨")
                else:
                    print(f"💸 매수 불가: 주문 금액 부족 ({order_amount:,.0f}원 < {self.min_order_amount:,.0f}원)")

            elif signal == 'SELL':
                quantity = self.calculate_order_amount(signal, current_price, symbol)
                if quantity > 0:
                    print(f"💸 매도 주문 실행: {symbol}")
                    print(f"   - 수량: {quantity:.6f}")
                    print(f"   - 가격: {current_price:,.0f}원")
                    print(f"   - 예상 금액: {quantity * current_price:,.0f}원")

                    # 실제 주문 (주석 해제하여 활성화)
                    # result = self.client.place_order(symbol, 'ask', quantity, order_type='market')
                    # if result:
                    #     print(f"✅ 매도 주문 성공: {result}")
                    # else:
                    #     print(f"❌ 매도 주문 실패")

                    print("⚠️  실제 주문은 안전을 위해 비활성화됨")
                else:
                    print(f"💸 매도 불가: 보유 수량 부족")

        except Exception as e:
            print(f"❌ 주문 실행 중 오류: {e}")

    def process_symbol(self, symbol):
        """개별 종목 처리"""
        try:
            # 1. 시세 조회
            ticker_data = self.client.get_ticker(symbol)
            if not ticker_data:
                print(f"❌ {symbol} 시세 조회 실패")
                return

            current_price = float(ticker_data.get('closing_price', 0))
            if current_price <= 0:
                print(f"❌ {symbol} 유효하지 않은 가격: {current_price}")
                return

            # 2. 매매 신호 생성
            signal, rsi = self.strategy.get_signal(symbol, current_price)

            # 3. 결과 출력
            print(f"📊 {symbol}: {current_price:>12,.0f}원 | RSI: {rsi:>5.1f} | 신호: {signal}")

            # 4. 실제 주문 실행 (매수/매도 신호인 경우)
            if signal in ['BUY', 'SELL']:
                self.execute_order(symbol, signal, current_price, rsi)

        except Exception as e:
            print(f"❌ {symbol} 처리 중 오류: {e}")

    async def run_cycle(self):
        """한 사이클 실행"""
        cycle_start = time.time()
        print(f"\n🔄 매매 사이클 시작 - {datetime.now().strftime('%H:%M:%S')}")

        try:
            # 모든 대상 종목 처리
            for symbol in self.target_symbols:
                if not self.running:
                    break

                self.process_symbol(symbol)
                await asyncio.sleep(1)  # API 호출 간격

            # 잔고 정보 출력
            krw_balance = self.get_krw_balance()
            print(f"💰 KRW 잔고: {krw_balance:,.0f}원")

        except Exception as e:
            print(f"❌ 사이클 실행 중 오류: {e}")

        finally:
            cycle_time = time.time() - cycle_start
            print(f"⏱️  사이클 완료 ({cycle_time:.1f}초)")

    async def start(self):
        """자동매매 엔진 시작"""
        print("🚀 자동매매 엔진 시작!")
        print(f"📈 거래 대상: {', '.join(self.target_symbols)}")
        print(f"💰 최소 주문 금액: {self.min_order_amount:,}원")
        print(f"📊 최대 포지션 비율: {self.max_position_ratio:.1%}")
        print("⚠️  실제 주문은 현재 비활성화 상태입니다.")
        print("=" * 60)

        self.running = True
        cycle_count = 0

        try:
            while self.running:
                cycle_count += 1
                print(f"\n📋 사이클 #{cycle_count}")

                await self.run_cycle()

                if self.running:
                    print(f"😴 30초 대기...")
                    for i in range(30):
                        if not self.running:
                            break
                        await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\n🛑 사용자에 의해 중단됨")
        except Exception as e:
            print(f"\n❌ 예상치 못한 오류: {e}")
        finally:
            self.running = False
            print("\n🏁 자동매매 엔진 종료")


async def main():
    """메인 함수"""
    try:
        engine = AutoTradingEngine()
        await engine.start()
    except Exception as e:
        print(f"❌ 엔진 초기화 실패: {e}")
        return 1

    return 0


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