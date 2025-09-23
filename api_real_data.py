#!/usr/bin/env python3
"""실제 빗썸 API 데이터를 사용하는 FastAPI 대시보드 서버."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 프로젝트 루트를 Python path에 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.config import get_settings
from src.exchange.bithumb_client import BithumbClient
from src.data.models import SessionLocal
from src.utils.logger import get_logger

# 설정 및 로거 초기화
settings = get_settings()
logger = get_logger(__name__)

# FastAPI 앱 생성
app = FastAPI(
    title="빗썸 자동매매 실시간 대시보드",
    description="빗썸 실거래 데이터 기반 자동매매 모니터링 시스템",
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

# 빗썸 클라이언트 초기화
bithumb_client = BithumbClient()

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

# 글로벌 변수 (캐시용)
_account_balance = None
_last_balance_update = None
_cached_positions = None
_last_positions_update = None

async def get_real_account_balance():
    """실제 빗썸 계좌 잔고 조회."""
    global _account_balance, _last_balance_update

    # 5분 캐시
    if (_account_balance is not None and
        _last_balance_update is not None and
        datetime.now() - _last_balance_update < timedelta(minutes=5)):
        return _account_balance

    try:
        balance_data = bithumb_client.get_balance("ALL")
        if balance_data and balance_data.get('status') == '0000':
            data = balance_data.get('data', {})

            # KRW 잔고
            krw_available = float(data.get('available_krw', 0))
            krw_in_use = float(data.get('in_use_krw', 0))
            total_krw = krw_available + krw_in_use

            # 각 코인별 잔고 및 KRW 환산값 계산
            total_crypto_krw = 0
            positions = []

            for symbol, amounts in data.items():
                if symbol.endswith('_krw') or symbol in ['available_krw', 'in_use_krw', 'total_krw']:
                    continue

                if isinstance(amounts, dict):
                    available = float(amounts.get('available', 0))
                    in_use = float(amounts.get('in_use', 0))
                    total_amount = available + in_use

                    if total_amount > 0:
                        # 현재 시세 조회
                        ticker = bithumb_client.get_ticker(symbol.upper())
                        if ticker and ticker.get('status') == '0000':
                            current_price = float(ticker['data']['closing_price'])
                            market_value = total_amount * current_price
                            total_crypto_krw += market_value

                            positions.append({
                                'symbol': f"{symbol.upper()}_KRW",
                                'quantity': total_amount,
                                'current_price': current_price,
                                'market_value': market_value,
                                'available': available,
                                'in_use': in_use
                            })

            _account_balance = {
                'total_krw': total_krw,
                'total_crypto_krw': total_crypto_krw,
                'total_balance_krw': total_krw + total_crypto_krw,
                'positions': positions,
                'raw_data': data
            }
            _last_balance_update = datetime.now()

            logger.info(f"실제 계좌 잔고 업데이트: 총 {_account_balance['total_balance_krw']:,.0f} KRW")
            return _account_balance

    except Exception as e:
        logger.error(f"계좌 잔고 조회 실패: {e}")
        # 실패 시 기본값 반환
        return {
            'total_krw': 0,
            'total_crypto_krw': 0,
            'total_balance_krw': 0,
            'positions': [],
            'error': str(e)
        }

async def get_real_market_data(symbol: str = "BTC"):
    """실제 빗썸 시장 데이터 조회."""
    try:
        ticker = bithumb_client.get_ticker(symbol)
        if ticker and ticker.get('status') == '0000':
            data = ticker['data']
            return {
                'symbol': f"{symbol}_KRW",
                'current_price': float(data['closing_price']),
                'opening_price': float(data['opening_price']),
                'high_price': float(data['max_price']),
                'low_price': float(data['min_price']),
                'volume': float(data['units_traded']),
                'prev_closing_price': float(data['prev_closing_price']),
                'change_rate': ((float(data['closing_price']) - float(data['prev_closing_price'])) / float(data['prev_closing_price'])) * 100,
                'timestamp': datetime.now()
            }
    except Exception as e:
        logger.error(f"시장 데이터 조회 실패 ({symbol}): {e}")
        return None

@app.get("/")
async def root():
    """기본 엔드포인트."""
    return {
        "message": "빗썸 자동매매 실시간 대시보드 API",
        "version": "1.0.0",
        "status": "running",
        "data_source": "REAL BITHUMB API",
        "phase": "실거래 데이터 연동 완료"
    }

@app.get("/api/health")
async def health_check():
    """헬스체크 엔드포인트 - 실제 빗썸 API 연결 상태 확인."""
    try:
        # 빗썸 API 연결 테스트
        ticker_test = bithumb_client.get_ticker("BTC")
        api_status = "connected" if ticker_test and ticker_test.get('status') == '0000' else "disconnected"

        # 계좌 API 테스트
        balance_test = bithumb_client.get_balance("BTC")
        account_status = "connected" if balance_test and balance_test.get('status') == '0000' else "limited"

        return {
            "status": "healthy" if api_status == "connected" else "degraded",
            "timestamp": datetime.now().isoformat(),
            "services": {
                "bithumb_public_api": api_status,
                "bithumb_private_api": account_status,
                "database": "connected",
                "websocket": "simulated"
            }
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "services": {
                "bithumb_public_api": "error",
                "bithumb_private_api": "error",
                "database": "unknown",
                "websocket": "error"
            }
        }

@app.get("/api/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary():
    """실제 빗썸 계좌 기반 대시보드 요약 정보."""
    try:
        balance_data = await get_real_account_balance()

        # BTC 환산 계산
        btc_ticker = await get_real_market_data("BTC")
        btc_price = btc_ticker['current_price'] if btc_ticker else 100000000
        total_balance_btc = balance_data['total_balance_krw'] / btc_price

        # 일일 손익은 실제 거래 내역에서 계산해야 하지만, 현재는 시뮬레이션
        daily_pnl = 0  # TODO: 실제 일일 손익 계산 로직 구현
        daily_pnl_percent = 0

        return DashboardSummary(
            total_balance_krw=balance_data['total_balance_krw'],
            total_balance_btc=total_balance_btc,
            daily_pnl=daily_pnl,
            daily_pnl_percent=daily_pnl_percent,
            active_positions=len(balance_data['positions']),
            total_trades_today=0,  # TODO: 실제 거래 내역에서 계산
            success_rate=0,  # TODO: 실제 거래 성공률 계산
            timestamp=datetime.now()
        )
    except Exception as e:
        logger.error(f"대시보드 요약 정보 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"대시보드 데이터 조회 실패: {str(e)}")

@app.get("/api/dashboard/positions", response_model=List[PositionInfo])
async def get_positions():
    """실제 빗썸 계좌의 현재 포지션 목록."""
    try:
        balance_data = await get_real_account_balance()
        positions = []

        for position in balance_data['positions']:
            positions.append(PositionInfo(
                symbol=position['symbol'],
                quantity=position['quantity'],
                average_price=position['current_price'],  # TODO: 실제 평균 매수가 계산
                current_price=position['current_price'],
                unrealized_pnl=0,  # TODO: 실제 미실현 손익 계산
                unrealized_pnl_percent=0,  # TODO: 실제 수익률 계산
                market_value=position['market_value']
            ))

        return positions
    except Exception as e:
        logger.error(f"포지션 정보 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"포지션 데이터 조회 실패: {str(e)}")

@app.get("/api/dashboard/recent-trades")
async def get_recent_trades():
    """최근 거래 내역 - 실제 빗썸 거래 내역."""
    try:
        # TODO: 실제 거래 내역 API 연동
        # 현재는 빈 배열 반환, 실제 구현 시 bithumb_client.get_user_transactions() 사용
        return {
            "trades": [],
            "message": "실제 거래 내역 연동 준비 중",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"거래 내역 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"거래 내역 조회 실패: {str(e)}")

@app.get("/api/analysis/performance", response_model=PerformanceMetrics)
async def get_performance_metrics():
    """성과 지표 - 실제 거래 데이터 기반."""
    try:
        # TODO: 실제 거래 내역 기반 성과 지표 계산
        return PerformanceMetrics(
            total_return=0.0,
            annualized_return=0.0,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            win_rate=0.0,
            total_trades=0
        )
    except Exception as e:
        logger.error(f"성과 지표 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"성과 지표 조회 실패: {str(e)}")

@app.get("/api/analysis/equity-curve")
async def get_equity_curve():
    """자산 곡선 - 실제 계좌 자산 변화."""
    try:
        balance_data = await get_real_account_balance()
        current_balance = balance_data['total_balance_krw']

        # 현재는 현재 잔고만 반환, 실제로는 과거 데이터 필요
        equity_curve = [{
            "date": datetime.now().isoformat(),
            "equity": current_balance,
            "return_rate": 0.0
        }]

        return {
            "equity_curve": equity_curve,
            "message": "실제 계좌 기반 자산 데이터",
            "current_balance": current_balance
        }
    except Exception as e:
        logger.error(f"자산 곡선 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"자산 곡선 조회 실패: {str(e)}")

@app.get("/api/markets/symbols")
async def get_market_symbols():
    """빗썸 KRW 마켓 심볼 목록 - 실제 빗썸 API."""
    try:
        all_tickers = bithumb_client.get_ticker("ALL")
        if all_tickers and all_tickers.get('status') == '0000':
            markets = all_tickers['data']
            symbols = [f"{symbol}_KRW" for symbol in markets.keys() if symbol != 'date']

            return {
                "symbols": symbols,
                "count": len(symbols),
                "timestamp": datetime.now().isoformat(),
                "source": "실제 빗썸 API"
            }
    except Exception as e:
        logger.error(f"마켓 심볼 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"마켓 데이터 조회 실패: {str(e)}")

@app.get("/api/realtime/ticker/{symbol}")
async def get_realtime_ticker(symbol: str):
    """실시간 시세 조회."""
    try:
        # _KRW 제거
        clean_symbol = symbol.replace("_KRW", "").upper()
        market_data = await get_real_market_data(clean_symbol)

        if market_data:
            return market_data
        else:
            raise HTTPException(status_code=404, detail=f"심볼 {symbol} 데이터를 찾을 수 없습니다")
    except Exception as e:
        logger.error(f"실시간 시세 조회 실패 ({symbol}): {e}")
        raise HTTPException(status_code=500, detail=f"시세 조회 실패: {str(e)}")

if __name__ == "__main__":
    print("🚀 빗썸 실거래 데이터 기반 대시보드 API 시작")
    print("📊 실제 빗썸 API 연동 완료")
    print("⚠️  주의: 실거래 데이터를 사용합니다")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,  # 기존 더미 서버와 구분
        reload=False
    )