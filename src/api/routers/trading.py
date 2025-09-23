"""거래 API 라우터."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# from ...exchange.client import BithumbClient  # 임시로 주석 처리
from ...utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

class OrderRequest(BaseModel):
    """주문 요청."""
    symbol: str
    side: str  # buy, sell
    order_type: str  # market, limit
    quantity: float
    price: Optional[float] = None

class OrderResponse(BaseModel):
    """주문 응답."""
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float]
    status: str
    timestamp: datetime

@router.post("/orders", response_model=OrderResponse)
async def create_order(order_request: OrderRequest):
    """주문 생성."""
    try:
        client = BithumbClient()

        # 주문 유효성 검증
        if order_request.side not in ['buy', 'sell']:
            raise HTTPException(status_code=400, detail="잘못된 주문 유형")

        if order_request.order_type not in ['market', 'limit']:
            raise HTTPException(status_code=400, detail="잘못된 주문 타입")

        if order_request.order_type == 'limit' and not order_request.price:
            raise HTTPException(status_code=400, detail="지정가 주문에는 가격이 필요합니다")

        # 빗썸 API 주문 실행 (실제 구현)
        if order_request.side == 'buy':
            if order_request.order_type == 'market':
                result = await client.market_buy(
                    symbol=order_request.symbol,
                    amount=order_request.quantity * order_request.price if order_request.price else 0
                )
            else:
                result = await client.limit_buy(
                    symbol=order_request.symbol,
                    quantity=order_request.quantity,
                    price=order_request.price
                )
        else:
            if order_request.order_type == 'market':
                result = await client.market_sell(
                    symbol=order_request.symbol,
                    quantity=order_request.quantity
                )
            else:
                result = await client.limit_sell(
                    symbol=order_request.symbol,
                    quantity=order_request.quantity,
                    price=order_request.price
                )

        # 주문 결과 처리
        order_id = result.get('order_id', 'unknown')

        return OrderResponse(
            order_id=order_id,
            symbol=order_request.symbol,
            side=order_request.side,
            order_type=order_request.order_type,
            quantity=order_request.quantity,
            price=order_request.price,
            status="pending",
            timestamp=datetime.now()
        )

    except Exception as e:
        logger.error(f"주문 생성 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/orders")
async def get_orders(symbol: Optional[str] = None, status: Optional[str] = None):
    """주문 내역 조회."""
    try:
        client = BithumbClient()

        # 빗썸 주문 내역 조회
        orders = await client.get_orders(symbol=symbol)

        # 상태별 필터링
        if status:
            orders = [order for order in orders if order.get('status') == status]

        return {"orders": orders}

    except Exception as e:
        logger.error(f"주문 내역 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    """주문 취소."""
    try:
        client = BithumbClient()

        # 빗썸 주문 취소
        result = await client.cancel_order(order_id)

        if result.get('status') == 'success':
            return {"message": "주문이 취소되었습니다", "order_id": order_id}
        else:
            raise HTTPException(status_code=400, detail="주문 취소 실패")

    except Exception as e:
        logger.error(f"주문 취소 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trades")
async def get_trade_history(
    symbol: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """거래 내역 조회."""
    try:
        # DB에서 거래 내역 조회 (실제 구현 필요)
        trades = [
            {
                "trade_id": "trade_001",
                "timestamp": "2025-09-22T13:30:00Z",
                "symbol": "BTC_KRW",
                "side": "buy",
                "quantity": 0.001,
                "price": 98500000,
                "amount": 98500,
                "fee": 246.25,
                "order_id": "order_001"
            },
            {
                "trade_id": "trade_002",
                "timestamp": "2025-09-22T12:45:00Z",
                "symbol": "ETH_KRW",
                "side": "sell",
                "quantity": 0.05,
                "price": 3200000,
                "amount": 160000,
                "fee": 400,
                "order_id": "order_002"
            }
        ]

        # 심볼별 필터링
        if symbol:
            trades = [trade for trade in trades if trade['symbol'] == symbol]

        # 페이징
        paginated_trades = trades[offset:offset + limit]

        return {
            "trades": paginated_trades,
            "total": len(trades),
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"거래 내역 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))