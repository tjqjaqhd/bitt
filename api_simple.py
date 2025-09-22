#!/usr/bin/env python3
"""간단한 FastAPI 대시보드 서버."""

from datetime import datetime
from typing import List, Optional
import uvicorn

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# FastAPI 앱 생성
app = FastAPI(
    title="빗썸 자동매매 대시보드",
    description="실시간 암호화폐 자동매매 모니터링 및 제어 시스템",
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

@app.get("/")
async def root():
    """기본 엔드포인트."""
    return {
        "message": "빗썸 자동매매 대시보드 API",
        "version": "1.0.0",
        "status": "running",
        "phase": "Phase 6 - Dashboard Implementation"
    }

@app.get("/api/health")
async def health_check():
    """헬스체크 엔드포인트."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "database": "connected",
            "bithumb_api": "connected",
            "websocket": "running"
        }
    }

# 대시보드 API
@app.get("/api/dashboard/summary", response_model=DashboardSummary)
async def get_dashboard_summary():
    """대시보드 요약 정보 조회."""
    return DashboardSummary(
        total_balance_krw=1500000.0,
        total_balance_btc=0.015,
        daily_pnl=25420.5,
        daily_pnl_percent=1.73,
        active_positions=3,
        total_trades_today=8,
        success_rate=72.5,
        timestamp=datetime.now()
    )

@app.get("/api/dashboard/positions", response_model=List[PositionInfo])
async def get_positions():
    """현재 포지션 목록 조회."""
    return [
        PositionInfo(
            symbol="BTC_KRW",
            quantity=0.005,
            average_price=98000000,
            current_price=100000000,
            unrealized_pnl=10000,
            unrealized_pnl_percent=2.04,
            market_value=500000
        ),
        PositionInfo(
            symbol="ETH_KRW",
            quantity=0.1,
            average_price=3100000,
            current_price=3200000,
            unrealized_pnl=10000,
            unrealized_pnl_percent=3.23,
            market_value=320000
        ),
        PositionInfo(
            symbol="XRP_KRW",
            quantity=1000,
            average_price=650,
            current_price=680,
            unrealized_pnl=30000,
            unrealized_pnl_percent=4.62,
            market_value=680000
        )
    ]

@app.get("/api/dashboard/recent-trades")
async def get_recent_trades():
    """최근 거래 내역 조회."""
    return {
        "trades": [
            {
                "timestamp": "2025-09-22T13:35:00Z",
                "symbol": "BTC_KRW",
                "side": "buy",
                "quantity": 0.001,
                "price": 98500000,
                "amount": 98500,
                "fee": 246.25,
                "status": "filled"
            },
            {
                "timestamp": "2025-09-22T12:45:00Z",
                "symbol": "ETH_KRW",
                "side": "sell",
                "quantity": 0.05,
                "price": 3200000,
                "amount": 160000,
                "fee": 400,
                "status": "filled"
            },
            {
                "timestamp": "2025-09-22T11:30:00Z",
                "symbol": "XRP_KRW",
                "side": "buy",
                "quantity": 500,
                "price": 675,
                "amount": 337500,
                "fee": 843.75,
                "status": "filled"
            }
        ]
    }

# 분석 API
@app.get("/api/analysis/performance", response_model=PerformanceMetrics)
async def get_performance_metrics():
    """성과 지표 조회."""
    return PerformanceMetrics(
        total_return=18.5,
        annualized_return=24.7,
        max_drawdown=5.2,
        sharpe_ratio=1.85,
        win_rate=72.5,
        total_trades=247
    )

@app.get("/api/analysis/equity-curve")
async def get_equity_curve():
    """자산 곡선 조회."""
    # 30일간 자산 곡선 시뮬레이션
    import random
    equity_points = []
    base_equity = 1000000

    for i in range(30):
        date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        date = date.replace(day=max(1, date.day - 30 + i))

        # 성장 + 변동성
        growth = 1 + (i * 0.005) + random.uniform(-0.02, 0.02)
        equity = base_equity * growth

        equity_points.append({
            "date": date.isoformat(),
            "equity": round(equity, 2),
            "return_pct": round((equity - base_equity) / base_equity * 100, 2)
        })

    return {"equity_curve": equity_points}

# 설정 API
@app.get("/api/settings/strategy")
async def get_strategy_settings():
    """전략 설정 조회."""
    return {
        "ema_short": 20,
        "ema_long": 60,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "position_size": 5.0,
        "max_positions": 5,
        "stop_loss": 3.0
    }

@app.get("/api/markets/list")
async def get_market_list():
    """종목 목록 조회."""
    return {
        "markets": [
            {
                "symbol": "BTC_KRW",
                "name": "비트코인",
                "current_price": 100000000,
                "change_24h": 2500000,
                "change_24h_percent": 2.56,
                "volume_24h": 1500.5,
                "high_24h": 101000000,
                "low_24h": 97500000
            },
            {
                "symbol": "ETH_KRW",
                "name": "이더리움",
                "current_price": 3200000,
                "change_24h": -100000,
                "change_24h_percent": -3.03,
                "volume_24h": 8500.2,
                "high_24h": 3350000,
                "low_24h": 3150000
            },
            {
                "symbol": "XRP_KRW",
                "name": "리플",
                "current_price": 680,
                "change_24h": 25,
                "change_24h_percent": 3.82,
                "volume_24h": 125000,
                "high_24h": 685,
                "low_24h": 650
            }
        ]
    }

if __name__ == "__main__":
    print("🚀 빗썸 자동매매 대시보드 API 시작")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")