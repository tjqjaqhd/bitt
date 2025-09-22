"""거래 API 라우터 - 단순 버전."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
        # 주문 유효성 검증
        if order_request.side not in ['buy', 'sell']:
            raise HTTPException(status_code=400, detail="잘못된 주문 유형")

        if order_request.order_type not in ['market', 'limit']:
            raise HTTPException(status_code=400, detail="잘못된 주문 타입")

        if order_request.order_type == 'limit' and not order_request.price:
            raise HTTPException(status_code=400, detail="지정가 주문에는 가격이 필요합니다")

        # Mock 주문 ID 생성
        import uuid
        order_id = f"order_{uuid.uuid4().hex[:8]}"

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
        # Mock 주문 내역
        orders = [
            {
                "order_id": "order_12345",
                "symbol": "BTC_KRW",
                "side": "buy",
                "order_type": "limit",
                "quantity": 0.001,
                "price": 98000000,
                "status": "filled",
                "timestamp": "2025-09-22T13:30:00Z"
            },
            {
                "order_id": "order_12346",
                "symbol": "ETH_KRW",
                "side": "sell",
                "order_type": "market",
                "quantity": 0.05,
                "price": None,
                "status": "pending",
                "timestamp": "2025-09-22T13:45:00Z"
            }
        ]

        # 필터링
        if symbol:
            orders = [order for order in orders if order['symbol'] == symbol]
        if status:
            orders = [order for order in orders if order['status'] == status]

        return {"orders": orders}

    except Exception as e:
        logger.error(f"주문 내역 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=str(e))