"""실제 DB 데이터 기반 분석 API 라우터."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...data.database import get_db
from ...data.models import Trade, Position, DailyPnL
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
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float

class EquityPoint(BaseModel):
    """자산 곡선 포인트."""
    timestamp: datetime
    equity: float
    drawdown: float
    daily_return: float

class TradeAnalysis(BaseModel):
    """거래 분석."""
    symbol: str
    total_trades: int
    win_rate: float
    avg_return: float
    total_pnl: float

@router.get("/performance", response_model=PerformanceMetrics)
async def get_performance_metrics(
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    symbol: Optional[str] = Query(None, description="특정 종목 필터링"),
    db: Session = Depends(get_db)
):
    """실제 DB 기반 성과 지표 조회."""
    try:
        # 날짜 파싱
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # DB에서 거래 내역 조회
        query = db.query(Trade).filter(
            Trade.executed_at >= start_dt,
            Trade.executed_at <= end_dt
        )

        if symbol:
            query = query.filter(Trade.symbol == symbol)

        trades = query.all()

        if not trades:
            raise HTTPException(status_code=404, detail="해당 기간에 거래 내역이 없습니다.")

        # 성과 분석 실행
        analyzer = PerformanceAnalyzer()

        # 거래 데이터를 분석 가능한 형태로 변환
        trade_data = []
        for trade in trades:
            trade_data.append({
                'timestamp': trade.executed_at,
                'symbol': trade.symbol,
                'side': trade.side,
                'quantity': float(trade.quantity),
                'price': float(trade.price),
                'fee': float(trade.fee or 0),
                'pnl': float(trade.realized_pnl or 0)
            })

        # 일별 PnL 데이터 조회
        daily_pnl_query = db.query(DailyPnL).filter(
            DailyPnL.date >= start_dt.date(),
            DailyPnL.date <= end_dt.date()
        )
        daily_pnl_records = daily_pnl_query.all()

        # 성과 지표 계산
        metrics = analyzer.calculate_comprehensive_metrics(
            trades=trade_data,
            daily_pnl=[{
                'date': record.date,
                'pnl': float(record.realized_pnl),
                'equity': float(record.total_equity)
            } for record in daily_pnl_records]
        )

        return PerformanceMetrics(**metrics)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 날짜 형식: {e}")
    except Exception as e:
        logger.error(f"성과 지표 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="성과 지표 조회 중 오류 발생")

@router.get("/equity-curve", response_model=List[EquityPoint])
async def get_equity_curve(
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """실제 DB 기반 자산 곡선 조회."""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # DB에서 일별 PnL 데이터 조회
        daily_records = db.query(DailyPnL).filter(
            DailyPnL.date >= start_dt.date(),
            DailyPnL.date <= end_dt.date()
        ).order_by(DailyPnL.date).all()

        if not daily_records:
            raise HTTPException(status_code=404, detail="해당 기간에 자산 데이터가 없습니다.")

        # 자산 곡선 계산
        equity_curve = []
        max_equity = 0

        for record in daily_records:
            equity = float(record.total_equity)
            max_equity = max(max_equity, equity)

            # 드로우다운 계산
            drawdown = (equity - max_equity) / max_equity * 100 if max_equity > 0 else 0

            # 일일 수익률 계산
            daily_return = float(record.realized_pnl) / equity * 100 if equity > 0 else 0

            equity_curve.append(EquityPoint(
                timestamp=datetime.combine(record.date, datetime.min.time()),
                equity=equity,
                drawdown=drawdown,
                daily_return=daily_return
            ))

        return equity_curve

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 날짜 형식: {e}")
    except Exception as e:
        logger.error(f"자산 곡선 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="자산 곡선 조회 중 오류 발생")

@router.get("/trades-analysis", response_model=List[TradeAnalysis])
async def get_trades_analysis(
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """종목별 거래 분석."""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # 종목별 거래 통계 계산
        trades = db.query(Trade).filter(
            Trade.executed_at >= start_dt,
            Trade.executed_at <= end_dt
        ).all()

        if not trades:
            return []

        # 종목별로 그룹화
        symbol_stats = {}

        for trade in trades:
            symbol = trade.symbol
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {
                    'trades': [],
                    'total_pnl': 0
                }

            symbol_stats[symbol]['trades'].append(trade)
            symbol_stats[symbol]['total_pnl'] += float(trade.realized_pnl or 0)

        # 분석 결과 생성
        analysis_results = []

        for symbol, stats in symbol_stats.items():
            trades_list = stats['trades']
            total_trades = len(trades_list)

            # 수익 거래 계산
            profitable_trades = sum(1 for t in trades_list if (t.realized_pnl or 0) > 0)
            win_rate = profitable_trades / total_trades * 100 if total_trades > 0 else 0

            # 평균 수익률 계산
            avg_return = stats['total_pnl'] / total_trades if total_trades > 0 else 0

            analysis_results.append(TradeAnalysis(
                symbol=symbol,
                total_trades=total_trades,
                win_rate=win_rate,
                avg_return=avg_return,
                total_pnl=stats['total_pnl']
            ))

        # 총 거래 수 기준으로 정렬
        analysis_results.sort(key=lambda x: x.total_trades, reverse=True)

        return analysis_results

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"잘못된 날짜 형식: {e}")
    except Exception as e:
        logger.error(f"거래 분석 실패: {e}")
        raise HTTPException(status_code=500, detail="거래 분석 중 오류 발생")

@router.get("/current-positions")
async def get_current_positions(db: Session = Depends(get_db)):
    """현재 보유 포지션 조회."""
    try:
        # 현재 활성 포지션 조회
        positions = db.query(Position).filter(
            Position.is_active == True,
            Position.quantity > 0
        ).all()

        result = []
        for pos in positions:
            # 현재가 조회 (실시간 API 호출 필요)
            # 여기서는 저장된 마지막 가격 사용
            unrealized_pnl = float(pos.quantity) * (float(pos.current_price or 0) - float(pos.average_price))

            result.append({
                'symbol': pos.symbol,
                'quantity': float(pos.quantity),
                'average_price': float(pos.average_price),
                'current_price': float(pos.current_price or 0),
                'market_value': float(pos.quantity) * float(pos.current_price or 0),
                'unrealized_pnl': unrealized_pnl,
                'unrealized_pnl_percent': unrealized_pnl / (float(pos.quantity) * float(pos.average_price)) * 100,
                'opened_at': pos.opened_at
            })

        return {"positions": result}

    except Exception as e:
        logger.error(f"포지션 조회 실패: {e}")
        raise HTTPException(status_code=500, detail="포지션 조회 중 오류 발생")

@router.get("/risk-metrics")
async def get_risk_metrics(
    start_date: str = Query(..., description="시작 날짜 (YYYY-MM-DD)"),
    end_date: str = Query(..., description="종료 날짜 (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """위험 지표 조회."""
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        # 일별 수익률 데이터 조회
        daily_records = db.query(DailyPnL).filter(
            DailyPnL.date >= start_dt.date(),
            DailyPnL.date <= end_dt.date()
        ).order_by(DailyPnL.date).all()

        if not daily_records:
            raise HTTPException(status_code=404, detail="위험 지표 계산을 위한 데이터가 없습니다.")

        # 위험 지표 계산
        daily_returns = [float(record.realized_pnl) / float(record.total_equity) * 100
                        for record in daily_records if record.total_equity > 0]

        if not daily_returns:
            return {"error": "유효한 수익률 데이터가 없습니다."}

        import numpy as np

        volatility = float(np.std(daily_returns)) * (252 ** 0.5)  # 연환산 변동성
        downside_returns = [r for r in daily_returns if r < 0]
        downside_volatility = float(np.std(downside_returns)) * (252 ** 0.5) if downside_returns else 0

        # VaR 계산 (95% 신뢰도)
        var_95 = float(np.percentile(daily_returns, 5)) if daily_returns else 0

        return {
            "volatility": volatility,
            "downside_volatility": downside_volatility,
            "var_95": var_95,
            "skewness": float(np.skew(daily_returns)) if len(daily_returns) > 2 else 0,
            "kurtosis": float(np.kurtosis(daily_returns)) if len(daily_returns) > 3 else 0,
            "max_consecutive_losses": _calculate_max_consecutive_losses(daily_returns)
        }

    except Exception as e:
        logger.error(f"위험 지표 계산 실패: {e}")
        raise HTTPException(status_code=500, detail="위험 지표 계산 중 오류 발생")

def _calculate_max_consecutive_losses(returns: List[float]) -> int:
    """최대 연속 손실 일수 계산."""
    max_consecutive = 0
    current_consecutive = 0

    for ret in returns:
        if ret < 0:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0

    return max_consecutive