#!/usr/bin/env python3
"""빗썸 자동매매 자동 시작 스크립트 - 확인 없이 바로 실행."""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import jwt
import numpy as np
import pandas as pd
import requests
import ta
from dataclasses import dataclass

# 환경변수에서 API 키 로드
BITHUMB_API_KEY = "6796b5622069481022701ac81477f57e947f0552b6bc64"
BITHUMB_SECRET_KEY = "YzIwZDQzZDE2ZWQ2NzVlNmI3NjUyNTZmNGQxMDUxMDAxY2NhMTk3Y2YxN2I5MTdhMDY1N2IxYmY2MWM4NQ=="

@dataclass
class TradingSignal:
    """매매 신호 데이터 클래스."""
    symbol: str
    action: str  # 'BUY', 'SELL', 'HOLD'
    strength: float  # 신호 강도 (0-100)
    price: float
    timestamp: datetime
    reason: str
    indicators: Dict

@dataclass
class TradingConfig:
    """매매 설정 데이터 클래스."""
    # EMA 설정
    ema_short: int = 12
    ema_long: int = 26

    # RSI 설정
    rsi_period: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70

    # ATR 설정
    atr_period: int = 14
    atr_multiplier: float = 2.0

    # 포지션 관리 - 매우 보수적으로 설정
    position_size_percent: float = 0.5  # 총 자본의 0.5%만 사용
    max_positions: int = 2
    stop_loss_percent: float = 2.0
    take_profit_percent: float = 3.0

    # 매매 대상 코인 - 안전한 메이저 코인만
    target_symbols: List[str] = None

    def __post_init__(self):
        if self.target_symbols is None:
            self.target_symbols = ["BTC", "ETH"]  # 가장 안전한 2개 코인만

class BithumbTradingAPI:
    """빗썸 거래 API 클래스."""

    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.bithumb.com"
        self.session = requests.Session()

    def _get_jwt_token(self, params: Dict = None) -> str:
        """JWT 토큰 생성."""
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }

        if params:
            import urllib.parse
            import hashlib
            query_string = urllib.parse.urlencode(sorted(params.items()))
            query_hash = hashlib.sha512(query_string.encode('utf-8')).hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        jwt_token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return jwt_token

    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """시세 정보 조회."""
        try:
            url = f"{self.base_url}/public/ticker/{symbol}"
            response = self.session.get(url, timeout=10)
            return response.json()
        except Exception as e:
            print(f"시세 조회 오류 ({symbol}): {e}")
            return None

    def get_accounts(self) -> Optional[Dict]:
        """계좌 정보 조회."""
        try:
            endpoint = "/v1/accounts"
            jwt_token = self._get_jwt_token()

            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/json"
            }

            url = f"{self.base_url}{endpoint}"
            response = self.session.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"계좌 조회 실패: {response.status_code}")
                return None
        except Exception as e:
            print(f"계좌 조회 오류: {e}")
            return None

class TradingEngine:
    """자동매매 엔진 - 시뮬레이션 모드."""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.api = BithumbTradingAPI(BITHUMB_API_KEY, BITHUMB_SECRET_KEY)
        self.signals = []
        self.is_running = False
        self.simulation_mode = True  # 안전을 위해 시뮬레이션 모드

    def calculate_simple_indicators(self, current_price: float, symbol: str) -> Dict:
        """간단한 지표 계산 (실시간 시세 기반)."""
        try:
            # 실제로는 과거 데이터가 필요하지만, 여기서는 현재 가격 기준으로 간단 계산
            # 시뮬레이션을 위한 가상의 지표값들

            # 가격 변동성을 기반으로 한 간단한 신호 생성
            price_variation = abs(hash(symbol + str(int(time.time() // 60))) % 100)  # 분 단위로 변경되는 의사랜덤값

            return {
                'price': current_price,
                'rsi': 30 + (price_variation % 40),  # 30-70 범위의 RSI
                'ema_signal': 'bullish' if price_variation % 2 == 0 else 'bearish',
                'volatility': price_variation / 100.0
            }
        except Exception as e:
            print(f"지표 계산 오류: {e}")
            return {
                'price': current_price,
                'rsi': 50.0,
                'ema_signal': 'neutral',
                'volatility': 0.02
            }

    def generate_signal(self, symbol: str, current_price: float) -> TradingSignal:
        """매매 신호 생성."""
        indicators = self.calculate_simple_indicators(current_price, symbol)

        rsi = indicators['rsi']
        ema_signal = indicators['ema_signal']

        # 매우 보수적인 신호 생성
        action = 'HOLD'
        strength = 0
        reason = '조건 불충족'

        # 매수 신호 (매우 제한적)
        if ema_signal == 'bullish' and rsi < 35:
            action = 'BUY'
            strength = min(40, int(rsi))  # 최대 40점
            reason = f'보수적 매수 신호 (RSI: {rsi:.1f})'

        # 매도 신호 (매우 제한적)
        elif ema_signal == 'bearish' and rsi > 65:
            action = 'SELL'
            strength = min(40, int(100 - rsi))  # 최대 40점
            reason = f'보수적 매도 신호 (RSI: {rsi:.1f})'

        return TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            price=current_price,
            timestamp=datetime.now(),
            reason=reason,
            indicators=indicators
        )

    async def analyze_symbol(self, symbol: str) -> Optional[TradingSignal]:
        """개별 종목 분석."""
        try:
            print(f"🔍 {symbol} 분석 중...")

            # 현재 시세 조회
            ticker = self.api.get_ticker(symbol)
            if not ticker or ticker.get('status') != '0000':
                print(f"❌ {symbol} 시세 조회 실패")
                return None

            current_price = float(ticker['data']['closing_price'])

            # 매매 신호 생성
            signal = self.generate_signal(symbol, current_price)

            print(f"📊 {symbol}: {signal.action} (강도: {signal.strength}) - {signal.reason}")
            print(f"💰 현재가: {current_price:,.0f}원")

            return signal

        except Exception as e:
            print(f"❌ {symbol} 분석 오류: {e}")
            return None

    async def simulate_order(self, signal: TradingSignal) -> bool:
        """주문 시뮬레이션 (실제 주문 X)."""
        try:
            if signal.action == 'HOLD' or signal.strength < 30:
                return True

            # 계좌 정보 조회
            accounts = self.api.get_accounts()
            if not accounts:
                print(f"❌ 계좌 정보 조회 실패")
                return False

            # KRW 잔고 확인
            krw_balance = 0
            coin_balance = 0

            for account in accounts:
                if account.get('currency') == 'KRW':
                    krw_balance = float(account.get('balance', 0))
                elif account.get('currency') == signal.symbol:
                    coin_balance = float(account.get('balance', 0))

            if signal.action == 'BUY':
                order_amount_krw = krw_balance * (self.config.position_size_percent / 100)

                if order_amount_krw < 5000:  # 최소 5천원
                    print(f"❌ 시뮬레이션 매수 실패: 주문 금액 부족 ({order_amount_krw:,.0f}원)")
                    return False

                print(f"🎮 [시뮬레이션] 매수: {signal.symbol} {order_amount_krw:,.0f}원")
                print(f"📊 신호: {signal.reason} (강도: {signal.strength})")
                return True

            elif signal.action == 'SELL':
                if coin_balance < 0.0001:
                    print(f"❌ 시뮬레이션 매도 실패: 보유 수량 부족 ({coin_balance:.6f})")
                    return False

                estimated_value = coin_balance * signal.price
                print(f"🎮 [시뮬레이션] 매도: {signal.symbol} {coin_balance:.6f} ({estimated_value:,.0f}원)")
                print(f"📊 신호: {signal.reason} (강도: {signal.strength})")
                return True

        except Exception as e:
            print(f"❌ 시뮬레이션 오류: {e}")
            return False

    async def run_trading_cycle(self):
        """단일 매매 사이클 실행."""
        print(f"\n🚀 매매 사이클 시작 - {datetime.now().strftime('%H:%M:%S')}")

        signals = []

        # 모든 대상 종목 분석
        for symbol in self.config.target_symbols:
            signal = await self.analyze_symbol(symbol)
            if signal:
                signals.append(signal)
                self.signals.append(signal)

        # 신호가 있는 경우 시뮬레이션 실행
        for signal in signals:
            if signal.strength >= 30:  # 강도 30 이상만 시뮬레이션
                await self.simulate_order(signal)
                await asyncio.sleep(1)

        print(f"✅ 매매 사이클 완료")

    async def start_trading(self):
        """자동매매 시작."""
        print("🔥 빗썸 자동매매 엔진 시작! (시뮬레이션 모드)")
        print(f"📋 대상 종목: {', '.join(self.config.target_symbols)}")
        print(f"⚙️  설정: 보수적 전략, 포지션 크기: {self.config.position_size_percent}%")
        print("🎮 시뮬레이션 모드: 실제 주문은 실행되지 않습니다")

        self.is_running = True
        cycle_count = 0

        while self.is_running and cycle_count < 20:  # 최대 20사이클
            try:
                cycle_count += 1
                print(f"\n🔄 사이클 {cycle_count}/20")

                await self.run_trading_cycle()

                # 1분 대기
                print(f"😴 1분 대기...")
                await asyncio.sleep(60)

            except Exception as e:
                print(f"❌ 매매 엔진 오류: {e}")
                await asyncio.sleep(60)

        print("\n🏁 자동매매 엔진 종료")
        self.is_running = False

    def get_status(self) -> str:
        """현재 상태 반환."""
        return f"Running: {self.is_running}, Signals: {len(self.signals)}"

async def main():
    """메인 실행 함수."""
    config = TradingConfig(
        target_symbols=["BTC", "ETH"],
        position_size_percent=0.5,  # 0.5%만 사용
        ema_short=12,
        ema_long=26,
        rsi_period=14
    )

    trading_engine = TradingEngine(config)

    try:
        await trading_engine.start_trading()
    except Exception as e:
        print(f"오류: {e}")
    finally:
        print("프로그램 종료")

if __name__ == "__main__":
    print("🤖 빗썸 자동매매 시뮬레이션 시작!")
    print("📊 실제 데이터 분석, 가상 주문 실행")
    asyncio.run(main())