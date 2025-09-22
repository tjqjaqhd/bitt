"""분석 API 라우터."""

from datetime import datetime, timedelta
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...backtest.performance import PerformanceAnalyzer
from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

class PerformanceMetrics(BaseModel):
    """성과 지표."""
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    total_trades: int
    profitable_trades: int
    losing_trades: int

class EquityPoint(BaseModel):
    """자산 곡선 포인트."""
    timestamp: datetime
    equity: float
    drawdown: float

@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics(
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)")
):
    """성과 지표 조회."""
    try:
        # 날짜 파싱
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # 실제로는 DB에서 거래 내역과 자산 곡선을 조회해야 함
        # 임시로 백테스트 결과 사용

        # 모의 자산 곡선 생성
        equity_curve = []
        initial_capital = 1000000
        days = (end_dt - start_dt).days

        for i in range(days):
            timestamp = start_dt + timedelta(days=i)
            # 간단한 성장 곡선 시뮬레이션
            growth_factor = 1 + (i * 0.001) + ((i % 7) - 3) * 0.002
            equity = initial_capital * growth_factor
            equity_curve.append((timestamp, equity))

        # 모의 거래 내역
        trades = [
            {
                'timestamp': start_dt + timedelta(days=5),
                'symbol': 'BTC_KRW',
                'side': 'buy',
                'quantity': 0.01,
                'price': 100000000,
                'commission': 2500
            },
            {
                'timestamp': start_dt + timedelta(days=15),
                'symbol': 'BTC_KRW',
                'side': 'sell',
                'quantity': 0.01,
                'price': 105000000,
                'commission': 2625
            }
        ]

        # 성과 분석
        analyzer = PerformanceAnalyzer(risk_free_rate=0.02)
        metrics = analyzer.analyze(equity_curve, trades, initial_capital)

        return PerformanceMetrics(
            total_return=round(metrics.total_return, 2),
            annualized_return=round(metrics.annualized_return, 2),
            max_drawdown=round(abs(metrics.max_drawdown), 2),
            sharpe_ratio=round(metrics.sharpe_ratio, 3),
            sortino_ratio=round(metrics.sortino_ratio, 3),
            calmar_ratio=round(metrics.calmar_ratio, 3),
            win_rate=round(metrics.win_rate, 1),
            profit_factor=round(metrics.profit_factor, 2),
            total_trades=len(trades),
            profitable_trades=sum(1 for t in trades if t['side'] == 'sell'),
            losing_trades=0
        )

    except Exception as e:
        logger.error(f"성과 지표 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/equity-curve", response_model=List[EquityPoint])
async def get_equity_curve(
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)")
):
    """자산 곡선 조회."""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # 실제로는 DB에서 일별 자산 데이터 조회
        equity_points = []
        initial_capital = 1000000
        peak_equity = initial_capital
        days = (end_dt - start_dt).days

        for i in range(days):
            timestamp = start_dt + timedelta(days=i)

            # 자산 시뮬레이션 (변동성 포함)
            growth_factor = 1 + (i * 0.001) + ((i % 7) - 3) * 0.002
            equity = initial_capital * growth_factor

            # 고점 갱신
            if equity > peak_equity:
                peak_equity = equity

            # 드로다운 계산
            drawdown = (equity - peak_equity) / peak_equity * 100 if peak_equity > 0 else 0

            equity_points.append(EquityPoint(
                timestamp=timestamp,
                equity=round(equity, 2),
                drawdown=round(drawdown, 2)
            ))

        return equity_points

    except Exception as e:
        logger.error(f"자산 곡선 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/monthly-returns")
async def get_monthly_returns(year: int = Query(..., description="연도")):
    """월별 수익률 조회."""
    try:
        # 실제로는 DB에서 월별 수익률 계산
        monthly_returns = []

        for month in range(1, 13):
            # 모의 월별 수익률 데이터
            returns = [
                2.5, -1.2, 4.8, 3.1, -0.8, 5.2,
                1.9, 3.7, -2.1, 4.5, 2.8, 1.6
            ]

            monthly_returns.append({
                "month": month,
                "return_percent": returns[month - 1],
                "cumulative_return": sum(returns[:month])
            })

        return {
            "year": year,
            "monthly_returns": monthly_returns,
            "total_return": sum(r["return_percent"] for r in monthly_returns)
        }

    except Exception as e:
        logger.error(f"월별 수익률 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trade-statistics")
async def get_trade_statistics():
    """거래 통계 조회."""
    try:
        # 실제로는 DB에서 거래 통계 계산
        return {
            "total_trades": 247,
            "profitable_trades": 168,
            "losing_trades": 79,
            "win_rate": 68.0,
            "average_win": 12500,
            "average_loss": -8750,
            "largest_win": 45000,
            "largest_loss": -25000,
            "profit_factor": 1.85,
            "avg_trade_duration": {
                "hours": 4,
                "minutes": 30
            },
            "best_performing_symbol": "BTC_KRW",
            "worst_performing_symbol": "ADA_KRW"
        }

    except Exception as e:
        logger.error(f"거래 통계 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/risk-metrics")
async def get_risk_metrics():
    """리스크 지표 조회."""
    try:
        # 실제로는 실시간 포트폴리오 데이터에서 계산
        return {
            "current_drawdown": -2.3,
            "max_daily_loss": -3.2,
            "var_95": -15000,  # 95% VaR
            "var_99": -25000,  # 99% VaR
            "portfolio_volatility": 12.5,
            "beta": 0.85,
            "correlation_with_btc": 0.72,
            "concentration_risk": {
                "top_position_percent": 15.2,
                "top_3_positions_percent": 38.7
            }
        }

    except Exception as e:
        logger.error(f"리스크 지표 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))