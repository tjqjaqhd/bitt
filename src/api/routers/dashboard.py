"""대시보드 API 라우터."""

from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

# from ...exchange.client import BithumbClient  # 임시로 주석 처리
from ...data.database import get_db_session
from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

class DashboardSummary(BaseModel):
    """대시보드 요약 정보."""
    total_balance_krw: float
    total_balance_btc: float
    daily_pnl: float
    daily_pnl_percent: float
    active_positions: int
    total_trades_today: int
    success_rate: float
    timestamp: datetime

class PositionInfo(BaseModel):
    """포지션 정보."""
    symbol: str
    quantity: float
    average_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    market_value: float

@router.get("/summary", response_model=DashboardSummary)
async def get_dashboard_summary():
    """대시보드 요약 정보 조회."""
    try:
        # 임시 Mock 데이터 (실제로는 빗썸 API 연동)
        # client = BithumbClient()
        # balance = await client.get_balance()

        # Mock 데이터
        total_balance_krw = 1500000.0  # 150만원
        total_balance_btc = 0.015  # 0.015 BTC

        # 일일 손익은 임시로 계산 (실제로는 DB에서 조회)
        daily_pnl = 15420.5  # 실제 계산 필요
        daily_pnl_percent = (daily_pnl / total_balance_krw * 100) if total_balance_krw > 0 else 0

        return DashboardSummary(
            total_balance_krw=total_balance_krw,
            total_balance_btc=round(total_balance_btc, 8),
            daily_pnl=daily_pnl,
            daily_pnl_percent=round(daily_pnl_percent, 2),
            active_positions=3,  # DB에서 조회
            total_trades_today=12,  # DB에서 조회
            success_rate=68.5,  # DB에서 계산
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"대시보드 요약 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/positions", response_model=List[PositionInfo])
async def get_positions():
    """현재 포지션 목록 조회."""
    try:
        # Mock 포지션 데이터
        positions = [
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

        return positions

    except Exception as e:
        logger.error(f"포지션 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recent-trades")
async def get_recent_trades(limit: int = 10):
    """최근 거래 내역 조회."""
    try:
        # DB에서 최근 거래 내역 조회 (임시 데이터)
        recent_trades = [
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
            }
        ]

        return {"trades": recent_trades[:limit]}

    except Exception as e:
        logger.error(f"최근 거래 내역 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/performance")
async def get_performance_metrics():
    """성과 지표 조회."""
    try:
        # 실제로는 백테스트 결과나 실거래 성과에서 계산
        return {
            "total_return": 15.7,
            "total_return_amount": 157000,
            "daily_return": 1.2,
            "weekly_return": 5.8,
            "monthly_return": 12.3,
            "max_drawdown": -3.2,
            "win_rate": 68.5,
            "profit_factor": 1.85,
            "sharpe_ratio": 1.42,
            "total_trades": 147,
            "profitable_trades": 101,
            "losing_trades": 46
        }

    except Exception as e:
        logger.error(f"성과 지표 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))