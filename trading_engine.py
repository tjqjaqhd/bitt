#!/usr/bin/env python3
"""빗썸 자동매매 엔진 - EMA + RSI + ATR 전략 실시간 실행."""

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
    ema_short: int = 20
    ema_long: int = 60

    # RSI 설정
    rsi_period: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70

    # ATR 설정
    atr_period: int = 14
    atr_multiplier: float = 2.0

    # 포지션 관리
    position_size_percent: float = 3.0  # 총 자본의 3%
    max_positions: int = 5
    stop_loss_percent: float = 3.0
    take_profit_percent: float = 5.0

    # 매매 대상 코인
    target_symbols: List[str] = None

    def __post_init__(self):
        if self.target_symbols is None:
            self.target_symbols = ["BTC", "ETH", "XRP", "ADA", "DOT"]

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
                print(f"계좌 조회 실패: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"계좌 조회 오류: {e}")
            return None

    def place_order(self, symbol: str, side: str, amount: float, price: float = None) -> Optional[Dict]:
        """주문 실행 (실제 주문 - 주의!)."""
        try:
            endpoint = "/v1/orders"
            params = {
                "market": f"{symbol}-KRW",
                "side": side.lower(),  # 'bid' or 'ask'
                "volume": str(amount),
                "ord_type": "limit" if price else "market"
            }

            if price:
                params["price"] = str(price)

            jwt_token = self._get_jwt_token(params)

            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            url = f"{self.base_url}{endpoint}"

            print(f"🚨 실제 주문 실행: {symbol} {side} {amount} @ {price}")
            print(f"⚠️  주의: 실제 돈이 사용됩니다!")

            # 안전을 위해 주문 실행 전 확인
            if amount * (price or 0) > 50000:  # 5만원 이상 주문은 차단
                print(f"❌ 안전 장치: 5만원 이상 주문은 차단됩니다")
                return {"error": "Amount too large for safety"}

            response = self.session.post(url, data=params, headers=headers, timeout=10)

            if response.status_code == 201:
                print(f"✅ 주문 성공: {response.json()}")
                return response.json()
            else:
                print(f"❌ 주문 실패: {response.status_code} - {response.text}")
                return {"error": f"HTTP {response.status_code}", "message": response.text}

        except Exception as e:
            print(f"주문 실행 오류: {e}")
            return {"error": "Exception", "message": str(e)}

class TradingEngine:
    """자동매매 엔진."""

    def __init__(self, config: TradingConfig):
        self.config = config
        self.api = BithumbTradingAPI(BITHUMB_API_KEY, BITHUMB_SECRET_KEY)
        self.price_data = {}  # 가격 데이터 캐시
        self.positions = {}   # 현재 포지션
        self.signals = []     # 매매 신호 기록
        self.is_running = False

    async def get_ohlcv_data(self, symbol: str, count: int = 100) -> Optional[pd.DataFrame]:
        """OHLCV 데이터 조회 (공개 API 사용)."""
        try:
            # 빗썸은 캔들 데이터 API가 제한적이므로 실시간 시세를 활용
            ticker = self.api.get_ticker(symbol)
            if not ticker or ticker.get('status') != '0000':
                return None

            data = ticker['data']

            # 단일 시점 데이터를 DataFrame으로 변환 (간단한 예시)
            df = pd.DataFrame({
                'timestamp': [datetime.now()],
                'open': [float(data['opening_price'])],
                'high': [float(data['max_price'])],
                'low': [float(data['min_price'])],
                'close': [float(data['closing_price'])],
                'volume': [float(data['units_traded'])]
            })

            # 실제로는 과거 데이터가 필요하지만, 여기서는 현재 가격 기준으로 시뮬레이션
            # 과거 데이터를 위해서는 외부 데이터 소스나 자체 수집 시스템이 필요

            return df

        except Exception as e:
            print(f"OHLCV 데이터 조회 오류 ({symbol}): {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """기술적 지표 계산."""
        try:
            if len(df) < max(self.config.ema_long, self.config.rsi_period, self.config.atr_period):
                # 데이터가 부족한 경우 기본값 반환
                return {
                    'ema_short': df['close'].iloc[-1],
                    'ema_long': df['close'].iloc[-1],
                    'rsi': 50.0,
                    'atr': df['close'].iloc[-1] * 0.02,  # 2% 가정
                    'price': df['close'].iloc[-1]
                }

            # EMA 계산
            ema_short = ta.trend.EMAIndicator(df['close'], window=self.config.ema_short).ema_indicator()
            ema_long = ta.trend.EMAIndicator(df['close'], window=self.config.ema_long).ema_indicator()

            # RSI 계산
            rsi = ta.momentum.RSIIndicator(df['close'], window=self.config.rsi_period).rsi()

            # ATR 계산
            atr = ta.volatility.AverageTrueRange(
                df['high'], df['low'], df['close'], window=self.config.atr_period
            ).average_true_range()

            return {
                'ema_short': ema_short.iloc[-1] if not ema_short.empty else df['close'].iloc[-1],
                'ema_long': ema_long.iloc[-1] if not ema_long.empty else df['close'].iloc[-1],
                'rsi': rsi.iloc[-1] if not rsi.empty else 50.0,
                'atr': atr.iloc[-1] if not atr.empty else df['close'].iloc[-1] * 0.02,
                'price': df['close'].iloc[-1]
            }

        except Exception as e:
            print(f"지표 계산 오류: {e}")
            return {
                'ema_short': df['close'].iloc[-1],
                'ema_long': df['close'].iloc[-1],
                'rsi': 50.0,
                'atr': df['close'].iloc[-1] * 0.02,
                'price': df['close'].iloc[-1]
            }

    def generate_signal(self, symbol: str, indicators: Dict) -> TradingSignal:
        """매매 신호 생성."""
        ema_short = indicators['ema_short']
        ema_long = indicators['ema_long']
        rsi = indicators['rsi']
        price = indicators['price']

        # 신호 강도 계산
        strength = 0
        action = 'HOLD'
        reason = '조건 불충족'

        # EMA 크로스오버 확인
        ema_bullish = ema_short > ema_long
        ema_bearish = ema_short < ema_long

        # RSI 조건 확인
        rsi_oversold = rsi < self.config.rsi_oversold
        rsi_overbought = rsi > self.config.rsi_overbought
        rsi_neutral = self.config.rsi_oversold <= rsi <= self.config.rsi_overbought

        # 매수 신호
        if ema_bullish and rsi_oversold:
            action = 'BUY'
            strength = 90
            reason = f'EMA 골든크로스 + RSI 과매도 ({rsi:.1f})'
        elif ema_bullish and rsi_neutral:
            action = 'BUY'
            strength = 60
            reason = f'EMA 골든크로스 + RSI 중립 ({rsi:.1f})'
        elif rsi_oversold:
            action = 'BUY'
            strength = 40
            reason = f'RSI 과매도 ({rsi:.1f})'

        # 매도 신호
        elif ema_bearish and rsi_overbought:
            action = 'SELL'
            strength = 90
            reason = f'EMA 데드크로스 + RSI 과매수 ({rsi:.1f})'
        elif ema_bearish and rsi_neutral:
            action = 'SELL'
            strength = 60
            reason = f'EMA 데드크로스 + RSI 중립 ({rsi:.1f})'
        elif rsi_overbought:
            action = 'SELL'
            strength = 40
            reason = f'RSI 과매수 ({rsi:.1f})'

        return TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            price=price,
            timestamp=datetime.now(),
            reason=reason,
            indicators=indicators
        )

    async def execute_signal(self, signal: TradingSignal) -> bool:
        """매매 신호 실행."""
        try:
            if signal.action == 'HOLD':
                return True

            # 계좌 정보 조회
            accounts = self.api.get_accounts()
            if not accounts:
                print(f"❌ 계좌 정보 조회 실패")
                return False

            # KRW 잔고 확인
            krw_balance = 0
            for account in accounts:
                if account.get('currency') == 'KRW':
                    krw_balance = float(account.get('balance', 0))
                    break

            if signal.action == 'BUY':
                # 매수 주문 금액 계산
                order_amount_krw = krw_balance * (self.config.position_size_percent / 100)
                order_amount_coin = order_amount_krw / signal.price

                if order_amount_krw < 10000:  # 최소 주문 금액 1만원
                    print(f"❌ 매수 실패: 주문 금액 부족 ({order_amount_krw:,.0f}원)")
                    return False

                print(f"🛒 매수 주문: {signal.symbol} {order_amount_coin:.6f} @ {signal.price:,.0f}원")
                print(f"📊 신호: {signal.reason} (강도: {signal.strength})")

                # 실제 주문 실행 (주의!)
                result = self.api.place_order(signal.symbol, 'bid', order_amount_coin, signal.price)

                if result and not result.get('error'):
                    print(f"✅ 매수 주문 성공")
                    return True
                else:
                    print(f"❌ 매수 주문 실패: {result}")
                    return False

            elif signal.action == 'SELL':
                # 보유 수량 확인
                coin_balance = 0
                for account in accounts:
                    if account.get('currency') == signal.symbol:
                        coin_balance = float(account.get('balance', 0))
                        break

                if coin_balance < 0.0001:  # 최소 매도 수량
                    print(f"❌ 매도 실패: 보유 수량 부족 ({coin_balance:.6f})")
                    return False

                print(f"🛍️ 매도 주문: {signal.symbol} {coin_balance:.6f} @ {signal.price:,.0f}원")
                print(f"📊 신호: {signal.reason} (강도: {signal.strength})")

                # 실제 주문 실행 (주의!)
                result = self.api.place_order(signal.symbol, 'ask', coin_balance, signal.price)

                if result and not result.get('error'):
                    print(f"✅ 매도 주문 성공")
                    return True
                else:
                    print(f"❌ 매도 주문 실패: {result}")
                    return False

        except Exception as e:
            print(f"❌ 신호 실행 오류: {e}")
            return False

    async def analyze_symbol(self, symbol: str) -> Optional[TradingSignal]:
        """개별 종목 분석."""
        try:
            print(f"🔍 {symbol} 분석 중...")

            # OHLCV 데이터 조회
            df = await self.get_ohlcv_data(symbol)
            if df is None or df.empty:
                print(f"❌ {symbol} 데이터 조회 실패")
                return None

            # 기술적 지표 계산
            indicators = self.calculate_indicators(df)

            # 매매 신호 생성
            signal = self.generate_signal(symbol, indicators)

            print(f"📊 {symbol}: {signal.action} (강도: {signal.strength}) - {signal.reason}")

            return signal

        except Exception as e:
            print(f"❌ {symbol} 분석 오류: {e}")
            return None

    async def run_trading_cycle(self):
        """단일 매매 사이클 실행."""
        print(f"\n🚀 매매 사이클 시작 - {datetime.now().strftime('%H:%M:%S')}")

        signals = []

        # 모든 대상 종목 분석
        for symbol in self.config.target_symbols:
            signal = await self.analyze_symbol(symbol)
            if signal:
                signals.append(signal)
                self.signals.append(signal)  # 기록 저장

        # 강도 높은 신호부터 실행
        buy_signals = [s for s in signals if s.action == 'BUY']
        sell_signals = [s for s in signals if s.action == 'SELL']

        buy_signals.sort(key=lambda x: x.strength, reverse=True)
        sell_signals.sort(key=lambda x: x.strength, reverse=True)

        # 매도 신호 먼저 실행
        for signal in sell_signals:
            if signal.strength >= 60:  # 강도 60 이상만 실행
                await self.execute_signal(signal)
                await asyncio.sleep(1)  # API 호출 간격

        # 매수 신호 실행
        for signal in buy_signals:
            if signal.strength >= 60:  # 강도 60 이상만 실행
                await self.execute_signal(signal)
                await asyncio.sleep(1)  # API 호출 간격

        print(f"✅ 매매 사이클 완료")

    async def start_trading(self):
        """자동매매 시작."""
        print("🔥 빗썸 자동매매 엔진 시작!")
        print(f"📋 대상 종목: {', '.join(self.config.target_symbols)}")
        print(f"⚙️  설정: EMA({self.config.ema_short},{self.config.ema_long}), RSI({self.config.rsi_period})")
        print(f"💰 포지션 크기: {self.config.position_size_percent}%")
        print("⚠️  주의: 실제 거래가 실행됩니다!")

        self.is_running = True

        while self.is_running:
            try:
                await self.run_trading_cycle()

                # 30초 대기 (실제 운영 시에는 더 긴 간격 권장)
                print(f"😴 30초 대기...")
                await asyncio.sleep(30)

            except KeyboardInterrupt:
                print("\n🛑 사용자에 의한 중단")
                self.is_running = False
                break
            except Exception as e:
                print(f"❌ 매매 엔진 오류: {e}")
                await asyncio.sleep(60)  # 오류 시 1분 대기

    def stop_trading(self):
        """자동매매 중단."""
        self.is_running = False
        print("🛑 자동매매 중단 요청")

    def get_status(self) -> Dict:
        """현재 상태 반환."""
        recent_signals = self.signals[-10:] if len(self.signals) > 10 else self.signals

        return {
            "is_running": self.is_running,
            "total_signals": len(self.signals),
            "recent_signals": [
                {
                    "symbol": s.symbol,
                    "action": s.action,
                    "strength": s.strength,
                    "price": s.price,
                    "timestamp": s.timestamp.isoformat(),
                    "reason": s.reason
                }
                for s in recent_signals
            ],
            "config": {
                "target_symbols": self.config.target_symbols,
                "ema_short": self.config.ema_short,
                "ema_long": self.config.ema_long,
                "rsi_period": self.config.rsi_period,
                "position_size_percent": self.config.position_size_percent
            }
        }

# 글로벌 매매 엔진 인스턴스
trading_engine = None

async def main():
    """메인 실행 함수."""
    global trading_engine

    config = TradingConfig(
        target_symbols=["BTC", "ETH", "XRP"],  # 안전을 위해 3개 종목만
        position_size_percent=1.0,  # 안전을 위해 1%로 낮춤
        ema_short=20,
        ema_long=60,
        rsi_period=14
    )

    trading_engine = TradingEngine(config)

    try:
        await trading_engine.start_trading()
    except KeyboardInterrupt:
        print("\n프로그램 종료")
    finally:
        if trading_engine:
            trading_engine.stop_trading()

if __name__ == "__main__":
    print("⚠️  경고: 실제 자동매매 시스템입니다!")
    print("💰 실제 돈이 사용되므로 신중하게 실행하세요!")

    confirm = input("계속하시겠습니까? (yes/no): ")
    if confirm.lower() == 'yes':
        asyncio.run(main())
    else:
        print("실행 취소됨")