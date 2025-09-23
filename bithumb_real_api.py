#!/usr/bin/env python3
"""빗썸 실거래 API 직접 연동 서버 (순환 임포트 해결)."""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import jwt
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 환경변수에서 API 키 로드
BITHUMB_API_KEY = "6796b5622069481022701ac81477f57e947f0552b6bc64"
BITHUMB_SECRET_KEY = "YzIwZDQzZDE2ZWQ2NzVlNmI3NjUyNTZmNGQxMDUxMDAxY2NhMTk3Y2YxN2I5MTdhMDY1N2IxYmY2MWM4NQ=="

# FastAPI 앱 생성
app = FastAPI(
    title="빗썸 실거래 데이터 대시보드",
    description="빗썸 실제 API 직접 연동 - 순수 실거래 데이터",
    version="1.0.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic 모델들
class DashboardSummary(BaseModel):
    total_balance_krw: float
    total_balance_btc: float
    daily_pnl: float
    daily_pnl_percent: float
    active_positions: int
    total_trades_today: int
    success_rate: float
    timestamp: datetime

class PositionInfo(BaseModel):
    symbol: str
    quantity: float
    average_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    market_value: float

class PerformanceMetrics(BaseModel):
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    win_rate: float
    total_trades: int

# 빗썸 API 클래스
class SimpleBithumbAPI:
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = "https://api.bithumb.com"

    def _get_jwt_token(self, params: Dict = None) -> str:
        """빗썸 API 2.0 JWT 토큰 생성."""
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }

        # 파라미터가 있는 경우 query_hash 추가
        if params:
            query_string = urllib.parse.urlencode(sorted(params.items()))
            query_hash = hashlib.sha512(query_string.encode('utf-8')).hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        # JWT 토큰 생성 (HS256 알고리즘)
        jwt_token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return jwt_token

    def get_ticker(self, symbol: str = "ALL") -> Optional[Dict]:
        """시세 정보 조회 (Public API)."""
        try:
            url = f"{self.base_url}/public/ticker/{symbol}"
            response = requests.get(url, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Ticker API 오류: {e}")
            return None

    def get_accounts(self) -> Optional[Dict]:
        """전체 계좌 조회 (Private API) - API v1 JWT 방식."""
        try:
            endpoint = "/v1/accounts"

            # JWT 토큰 생성 (파라미터 없음)
            jwt_token = self._get_jwt_token()

            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/json"
            }

            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, headers=headers, timeout=10)

            print(f"🔍 Accounts API 요청: {url}")
            print(f"📋 Headers: {headers}")
            print(f"📊 Response: {response.status_code} - {response.text[:500]}")

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ API 오류: {response.status_code} - {response.text}")
                return {"error": f"HTTP {response.status_code}", "message": response.text}

        except Exception as e:
            print(f"❌ Accounts API 오류: {e}")
            return {"error": "Exception", "message": str(e)}

    def get_user_transactions(self, currency: str = "BTC", count: int = 20) -> Optional[Dict]:
        """거래 내역 조회 (Private API)."""
        try:
            endpoint = "/info/user_transactions"
            params = {
                "currency": currency,
                "count": count
            }

            # JWT 토큰 생성
            jwt_token = self._get_jwt_token(params)

            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            url = f"{self.base_url}{endpoint}"
            response = requests.post(url, data=params, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Transactions API 오류: {e}")
            return None

    def get_orders(self, currency: str = "BTC", count: int = 20) -> Optional[Dict]:
        """주문 내역 조회 (Private API)."""
        try:
            endpoint = "/info/orders"
            params = {
                "currency": currency,
                "count": count
            }

            # JWT 토큰 생성
            jwt_token = self._get_jwt_token(params)

            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            url = f"{self.base_url}{endpoint}"
            response = requests.post(url, data=params, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            print(f"Orders API 오류: {e}")
            return None

# 빗썸 API 클라이언트 초기화
bithumb_api = SimpleBithumbAPI(BITHUMB_API_KEY, BITHUMB_SECRET_KEY)

# 캐시 변수들
_balance_cache = None
_balance_cache_time = None
_ticker_cache = {}
_ticker_cache_time = {}

async def get_cached_balance() -> Dict:
    """캐시된 잔고 정보 반환 (5분 캐시)."""
    global _balance_cache, _balance_cache_time

    now = datetime.now()
    if (_balance_cache is None or
        _balance_cache_time is None or
        now - _balance_cache_time > timedelta(minutes=5)):

        print("💰 실제 빗썸 계좌 잔고 조회 중...")
        accounts_data = bithumb_api.get_accounts()

        if accounts_data and isinstance(accounts_data, list):
            # 빗썸 v1 API는 리스트를 반환
            balance_info = {}
            total_krw_value = 0

            for account in accounts_data:
                currency = account.get('currency', '')
                balance = float(account.get('balance', 0))
                locked = float(account.get('locked', 0))

                if currency == 'KRW':
                    balance_info['krw_balance'] = balance
                    balance_info['krw_locked'] = locked
                    balance_info['total_krw'] = balance + locked
                    total_krw_value += balance + locked
                else:
                    # 다른 코인들은 KRW로 환산
                    if balance > 0 or locked > 0:
                        # 현재 시세로 KRW 환산 (시세 조회 필요)
                        ticker = await get_cached_ticker(currency)
                        price = float(ticker.get('closing_price', 0))
                        coin_value = (balance + locked) * price
                        total_krw_value += coin_value

                        balance_info[f'{currency.lower()}_balance'] = balance
                        balance_info[f'{currency.lower()}_locked'] = locked
                        balance_info[f'{currency.lower()}_value_krw'] = coin_value

            balance_info['total_balance_krw'] = total_krw_value
            _balance_cache = balance_info
            _balance_cache_time = now
            print(f"✅ 잔고 업데이트 완료: 총 {total_krw_value:,.0f}원")

        elif accounts_data and accounts_data.get('error'):
            print(f"❌ 계좌 조회 API 오류: {accounts_data.get('message', 'Unknown error')}")
            _balance_cache = {
                'total_krw': 0,
                'total_balance_krw': 0,
                'error': accounts_data.get('message', 'API Error')
            }
            _balance_cache_time = now
        else:
            print(f"❌ 계좌 조회 실패: 예상치 못한 응답 형식")
            _balance_cache = {
                'total_krw': 0,
                'total_balance_krw': 0,
                'error': 'Unexpected response format'
            }
            _balance_cache_time = now

    return _balance_cache

async def get_cached_ticker(symbol: str) -> Dict:
    """캐시된 시세 정보 반환 (30초 캐시)."""
    global _ticker_cache, _ticker_cache_time

    now = datetime.now()
    if (symbol not in _ticker_cache or
        symbol not in _ticker_cache_time or
        now - _ticker_cache_time[symbol] > timedelta(seconds=30)):

        ticker_data = bithumb_api.get_ticker(symbol)
        if ticker_data and ticker_data.get('status') == '0000':
            _ticker_cache[symbol] = ticker_data['data']
            _ticker_cache_time[symbol] = now
        else:
            # 실패 시 기본값
            _ticker_cache[symbol] = {
                'closing_price': '0',
                'opening_price': '0',
                'max_price': '0',
                'min_price': '0',
                'prev_closing_price': '0'
            }
            _ticker_cache_time[symbol] = now

    return _ticker_cache[symbol]

@app.get("/")
async def root():
    """기본 엔드포인트."""
    return {
        "message": "빗썸 실거래 데이터 대시보드 API",
        "version": "1.0.0",
        "status": "running",
        "data_source": "🔥 REAL BITHUMB API (실거래 데이터)",
        "api_key_status": "활성화됨" if BITHUMB_API_KEY else "비활성화됨"
    }

@app.get("/api/health")
async def health_check():
    """헬스체크 - 실제 빗썸 API 연결 확인."""
    try:
        # Public API 테스트
        btc_ticker = bithumb_api.get_ticker("BTC")
        public_api_status = "connected" if btc_ticker and btc_ticker.get('status') == '0000' else "error"

        # Private API 테스트 (계좌 조회)
        accounts_test = bithumb_api.get_accounts()
        private_api_status = "connected" if accounts_test and isinstance(accounts_test, list) else "error"

        return {
            "status": "healthy" if public_api_status == "connected" else "degraded",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "bithumb_public_api": public_api_status,
                "bithumb_private_api": private_api_status,
                "database": "simulated",
                "websocket": "simulated"
            },
            "api_test_results": {
                "btc_price": float(btc_ticker['data']['closing_price']) if btc_ticker and btc_ticker.get('status') == '0000' else 0,
                "balance_check": "OK" if private_api_status == "connected" else "FAIL"
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "services": {
                "bithumb_public_api": "error",
                "bithumb_private_api": "error",
                "database": "error",
                "websocket": "error"
            }
        }

@app.get("/api/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary():
    """실제 빗썸 계좌 기반 대시보드 요약."""
    try:
        # 실제 잔고 조회
        balance_data = await get_cached_balance()

        # KRW 잔고
        total_krw = float(balance_data.get('total_krw', 0))
        available_krw = float(balance_data.get('available_krw', 0))

        # BTC 시세로 BTC 환산 계산
        btc_ticker = await get_cached_ticker("BTC")
        btc_price = float(btc_ticker.get('closing_price', 100000000))
        total_balance_btc = total_krw / btc_price if btc_price > 0 else 0

        # 코인 포지션 계산
        active_positions = 0
        total_crypto_value = 0

        # 잔고에서 코인별 수량 확인
        for key, value in balance_data.items():
            if key.endswith('_krw') or key in ['available_krw', 'in_use_krw', 'total_krw']:
                continue

            if isinstance(value, dict):
                total_amount = float(value.get('total', 0))
                if total_amount > 0:
                    active_positions += 1
                    # 해당 코인의 현재 시세 조회
                    coin_ticker = await get_cached_ticker(key.upper())
                    coin_price = float(coin_ticker.get('closing_price', 0))
                    total_crypto_value += total_amount * coin_price

        total_balance_krw = total_krw + total_crypto_value

        # TODO: 실제 일일 손익 계산 (과거 데이터 필요)
        daily_pnl = 0
        daily_pnl_percent = 0

        return DashboardSummary(
            total_balance_krw=total_balance_krw,
            total_balance_btc=total_balance_btc,
            daily_pnl=daily_pnl,
            daily_pnl_percent=daily_pnl_percent,
            active_positions=active_positions,
            total_trades_today=0,  # TODO: 거래 내역 API 연동 필요
            success_rate=0,  # TODO: 거래 성공률 계산 필요
            timestamp=datetime.now()
        )

    except Exception as e:
        print(f"대시보드 요약 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=f"대시보드 데이터 조회 실패: {str(e)}")

@app.get("/api/dashboard/positions", response_model=List[PositionInfo])
async def get_positions():
    """실제 빗썸 계좌의 코인 포지션."""
    try:
        balance_data = await get_cached_balance()
        positions = []

        for symbol, amounts in balance_data.items():
            if symbol.endswith('_krw') or symbol in ['available_krw', 'in_use_krw', 'total_krw']:
                continue

            if isinstance(amounts, dict):
                total_amount = float(amounts.get('total', 0))
                if total_amount > 0:
                    # 현재 시세 조회
                    ticker = await get_cached_ticker(symbol.upper())
                    current_price = float(ticker.get('closing_price', 0))
                    market_value = total_amount * current_price

                    positions.append(PositionInfo(
                        symbol=f"{symbol.upper()}_KRW",
                        quantity=total_amount,
                        average_price=current_price,  # TODO: 실제 평균 매수가 계산
                        current_price=current_price,
                        unrealized_pnl=0,  # TODO: 실제 손익 계산
                        unrealized_pnl_percent=0,  # TODO: 실제 수익률 계산
                        market_value=market_value
                    ))

        return positions

    except Exception as e:
        print(f"포지션 조회 오류: {e}")
        raise HTTPException(status_code=500, detail=f"포지션 조회 실패: {str(e)}")

@app.get("/api/dashboard/recent-trades")
async def get_recent_trades():
    """실제 빗썸 거래 내역 조회."""
    try:
        # BTC 거래 내역 조회
        btc_transactions = bithumb_api.get_user_transactions("BTC", 10)
        trades_list = []

        if btc_transactions and btc_transactions.get('status') == '0000':
            for tx in btc_transactions.get('data', []):
                trades_list.append({
                    "timestamp": tx.get('transfer_date', ''),
                    "symbol": "BTC_KRW",
                    "side": tx.get('type', ''),  # buy/sell
                    "quantity": float(tx.get('units', 0)),
                    "price": float(tx.get('price', 0)),
                    "amount": float(tx.get('total', 0)),
                    "fee": float(tx.get('fee', 0)),
                    "status": "completed"
                })

        # ETH 거래 내역도 추가 조회
        eth_transactions = bithumb_api.get_user_transactions("ETH", 5)
        if eth_transactions and eth_transactions.get('status') == '0000':
            for tx in eth_transactions.get('data', []):
                trades_list.append({
                    "timestamp": tx.get('transfer_date', ''),
                    "symbol": "ETH_KRW",
                    "side": tx.get('type', ''),
                    "quantity": float(tx.get('units', 0)),
                    "price": float(tx.get('price', 0)),
                    "amount": float(tx.get('total', 0)),
                    "fee": float(tx.get('fee', 0)),
                    "status": "completed"
                })

        # 시간순 정렬
        trades_list.sort(key=lambda x: x['timestamp'], reverse=True)

        return {
            "trades": trades_list[:20],  # 최근 20개만
            "message": "실제 빗썸 거래 내역",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        print(f"거래 내역 조회 오류: {e}")
        return {
            "trades": [],
            "message": f"거래 내역 조회 실패: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/analysis/performance", response_model=PerformanceMetrics)
async def get_performance_metrics():
    """성과 지표 (향후 구현)."""
    return PerformanceMetrics(
        total_return=0.0,
        annualized_return=0.0,
        max_drawdown=0.0,
        sharpe_ratio=0.0,
        win_rate=0.0,
        total_trades=0
    )

@app.get("/api/analysis/equity-curve")
async def get_equity_curve():
    """자산 곡선 (현재 잔고 기준)."""
    try:
        balance_data = await get_cached_balance()
        total_krw = float(balance_data.get('total_krw', 0))

        return {
            "equity_curve": [{
                "date": datetime.now().isoformat(),
                "equity": total_krw,
                "return_rate": 0.0
            }],
            "message": "실제 계좌 잔고 기반",
            "current_balance": total_krw
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/markets/symbols")
async def get_market_symbols():
    """빗썸 전체 마켓 목록."""
    try:
        all_tickers = bithumb_api.get_ticker("ALL")
        if all_tickers and all_tickers.get('status') == '0000':
            symbols = [f"{symbol}_KRW" for symbol in all_tickers['data'].keys() if symbol != 'date']
            return {
                "symbols": symbols,
                "count": len(symbols),
                "timestamp": datetime.now().isoformat(),
                "source": "실제 빗썸 API"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/realtime/ticker/{symbol}")
async def get_realtime_ticker(symbol: str):
    """실시간 시세."""
    try:
        clean_symbol = symbol.replace("_KRW", "").upper()
        ticker_data = await get_cached_ticker(clean_symbol)

        return {
            "symbol": f"{clean_symbol}_KRW",
            "current_price": float(ticker_data.get('closing_price', 0)),
            "opening_price": float(ticker_data.get('opening_price', 0)),
            "high_price": float(ticker_data.get('max_price', 0)),
            "low_price": float(ticker_data.get('min_price', 0)),
            "prev_closing_price": float(ticker_data.get('prev_closing_price', 0)),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 자동매매 엔진 관련 엔드포인트
@app.get("/api/trading/status")
async def get_trading_status():
    """자동매매 엔진 상태 조회."""
    try:
        import subprocess

        # 실제 자동매매 프로세스 실행 여부 확인
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        is_running = 'real_trading_start.py' in result.stdout

        if is_running:
            return {
                "trading_engine_status": "running",  # 실제 실행 중
                "message": "5개 코인 (BTC, ETH, XRP, DOGE, WLD) 자동매매 엔진 실행 중",
                "command": "python3 real_trading_start.py",
                "coins": ["BTC", "ETH", "XRP", "DOGE", "WLD"],
                "safety_features": {
                    "max_position_size": "1%",
                    "max_order_amount": "30,000 KRW",
                    "target_symbols": ["BTC", "ETH", "XRP", "DOGE", "WLD"],
                    "strategy": "EMA 크로스오버 + RSI 필터",
                    "signal_threshold": "15점 이상"
                },
                "current_time": datetime.now().isoformat()
            }
        else:
            return {
                "trading_engine_status": "stopped",
                "message": "자동매매 엔진이 실행되지 않음",
                "command": "python3 real_trading_start.py",
                "safety_features": {
                    "max_position_size": "1%",
                    "max_order_amount": "30,000 KRW",
                    "target_symbols": ["BTC", "ETH", "XRP", "DOGE", "WLD"],
                    "strategy": "EMA 크로스오버 + RSI 필터"
                },
                "current_time": datetime.now().isoformat()
            }
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/trading/signals")
async def get_trading_signals():
    """매매 신호 분석 (실시간)."""
    try:
        # 각 대상 종목의 현재 지표 분석
        symbols = ["BTC", "ETH", "XRP"]
        signals = []

        for symbol in symbols:
            ticker = await get_cached_ticker(symbol)
            if ticker:
                current_price = float(ticker.get('closing_price', 0))

                # 간단한 분석 (실제로는 trading_engine의 분석 로직 사용)
                signals.append({
                    "symbol": f"{symbol}_KRW",
                    "current_price": current_price,
                    "analysis": "조건 분석 중",
                    "action": "HOLD",
                    "strength": 0,
                    "timestamp": datetime.now().isoformat()
                })

        return {
            "signals": signals,
            "message": "실시간 매매 신호 분석",
            "note": "자동매매 엔진이 실행 중일 때 더 정확한 신호 제공",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/api/trading/performance")
async def get_trading_performance():
    """매매 성과 분석."""
    try:
        # 실제 거래 내역 기반 성과 계산 (향후 구현)
        return {
            "daily_trades": 0,
            "successful_trades": 0,
            "total_profit_loss": 0,
            "win_rate": 0,
            "message": "매매 성과는 거래 내역이 누적되면 계산됩니다",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    print("🔥 빗썸 실거래 API 직접 연동 서버 시작")
    print("📊 100% 실제 빗썸 데이터 사용")
    print("🤖 자동매매 엔진 모니터링 API 포함")
    print("⚠️  주의: 실제 계좌 데이터를 조회합니다")
    print(f"🔑 API Key: {BITHUMB_API_KEY[:10]}...")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        reload=False
    )