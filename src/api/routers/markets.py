"""종목 API 라우터."""

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# from ...exchange.client import BithumbClient  # 임시로 주석 처리
from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

class MarketInfo(BaseModel):
    """종목 정보."""
    symbol: str
    name: str
    current_price: float
    change_24h: float
    change_24h_percent: float
    volume_24h: float
    high_24h: float
    low_24h: float
    market_cap: Optional[float] = None

class CandleData(BaseModel):
    """캔들 데이터."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

@router.get("/list", response_model=List[MarketInfo])
async def get_market_list():
    """전체 종목 목록 조회."""
    try:
        client = BithumbClient()

        # 빗썸 전체 종목 조회
        tickers = await client.get_all_tickers()

        markets = []
        for symbol, ticker_data in tickers.items():
            if symbol == 'date':
                continue

            # 종목명 매핑 (실제로는 DB나 설정에서 관리)
            symbol_name_map = {
                'BTC': '비트코인',
                'ETH': '이더리움',
                'XRP': '리플',
                'ADA': '에이다',
                'DOT': '폴카닷'
            }

            current_price = float(ticker_data.get('closing_price', 0))
            prev_closing = float(ticker_data.get('prev_closing_price', current_price))
            change_24h = current_price - prev_closing
            change_24h_percent = (change_24h / prev_closing * 100) if prev_closing > 0 else 0

            markets.append(MarketInfo(
                symbol=f"{symbol}_KRW",
                name=symbol_name_map.get(symbol, symbol),
                current_price=current_price,
                change_24h=change_24h,
                change_24h_percent=round(change_24h_percent, 2),
                volume_24h=float(ticker_data.get('units_traded_24H', 0)),
                high_24h=float(ticker_data.get('max_price', 0)),
                low_24h=float(ticker_data.get('min_price', 0))
            ))

        # 거래량 순으로 정렬
        markets.sort(key=lambda x: x.volume_24h, reverse=True)

        return markets[:50]  # 상위 50개만

    except Exception as e:
        logger.error(f"종목 목록 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{symbol}")
async def get_market_detail(symbol: str):
    """종목 상세 정보 조회."""
    try:
        client = BithumbClient()

        # 심볼에서 _KRW 제거
        crypto_symbol = symbol.replace('_KRW', '')

        # 종목 상세 정보 조회
        ticker = await client.get_ticker(symbol)
        orderbook = await client.get_orderbook(symbol)

        if not ticker:
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

        current_price = float(ticker.get('closing_price', 0))
        prev_closing = float(ticker.get('prev_closing_price', current_price))

        return {
            "symbol": symbol,
            "name": crypto_symbol,
            "current_price": current_price,
            "prev_closing_price": prev_closing,
            "change_24h": current_price - prev_closing,
            "change_24h_percent": ((current_price - prev_closing) / prev_closing * 100) if prev_closing > 0 else 0,
            "volume_24h": float(ticker.get('units_traded_24H', 0)),
            "high_24h": float(ticker.get('max_price', 0)),
            "low_24h": float(ticker.get('min_price', 0)),
            "orderbook": {
                "bids": orderbook.get('bids', [])[:10] if orderbook else [],
                "asks": orderbook.get('asks', [])[:10] if orderbook else []
            },
            "last_updated": datetime.now()
        }

    except Exception as e:
        logger.error(f"종목 상세 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{symbol}/candles")
async def get_candle_data(
    symbol: str,
    interval: str = "1h",
    limit: int = 100
):
    """캔들 데이터 조회."""
    try:
        # 빗썸은 캔들 API가 제한적이므로 임시 데이터 생성
        # 실제로는 외부 데이터 소스나 수집된 데이터 사용

        client = BithumbClient()
        ticker = await client.get_ticker(symbol)

        if not ticker:
            raise HTTPException(status_code=404, detail="종목을 찾을 수 없습니다")

        current_price = float(ticker.get('closing_price', 0))
        candles = []

        # 간격 매핑
        interval_map = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "1h": 60,
            "4h": 240,
            "1d": 1440
        }

        minutes = interval_map.get(interval, 60)
        base_time = datetime.now() - timedelta(minutes=minutes * limit)

        # 임시 캔들 데이터 생성 (실제 가격 기반)
        for i in range(limit):
            timestamp = base_time + timedelta(minutes=minutes * i)

            # 가격 변동 시뮬레이션 (±1% 범위)
            price_variation = 1 + (i % 10 - 5) / 500  # ±1% 변동
            price = current_price * price_variation

            candles.append(CandleData(
                timestamp=timestamp,
                open=price * 0.999,
                high=price * 1.005,
                low=price * 0.995,
                close=price,
                volume=1000000 + (i * 50000)
            ))

        return {
            "symbol": symbol,
            "interval": interval,
            "candles": candles
        }

    except Exception as e:
        logger.error(f"캔들 데이터 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{symbol}/orderbook")
async def get_orderbook(symbol: str, depth: int = 20):
    """호가 정보 조회."""
    try:
        client = BithumbClient()

        orderbook = await client.get_orderbook(symbol)

        if not orderbook:
            raise HTTPException(status_code=404, detail="호가 정보를 찾을 수 없습니다")

        return {
            "symbol": symbol,
            "bids": orderbook.get('bids', [])[:depth],
            "asks": orderbook.get('asks', [])[:depth],
            "timestamp": datetime.now()
        }

    except Exception as e:
        logger.error(f"호가 정보 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))