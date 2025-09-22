"""WebSocket 실시간 통신."""

import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any

from fastapi import WebSocket, WebSocketDisconnect
from fastapi.applications import FastAPI

# from ..exchange.client import BithumbClient  # 임시로 주석 처리
from ..utils.logger import get_logger

logger = get_logger(__name__)

class ConnectionManager:
    """WebSocket 연결 관리자."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # self.client = BithumbClient()  # 임시로 주석 처리

    async def connect(self, websocket: WebSocket):
        """클라이언트 연결."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket 클라이언트 연결: {len(self.active_connections)}명")

    def disconnect(self, websocket: WebSocket):
        """클라이언트 연결 해제."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket 클라이언트 연결 해제: {len(self.active_connections)}명")

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        """개별 메시지 전송."""
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as e:
            logger.error(f"개별 메시지 전송 실패: {e}")

    async def broadcast(self, message: Dict[str, Any]):
        """모든 연결된 클라이언트에 브로드캐스트."""
        if not self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"브로드캐스트 실패: {e}")
                disconnected.append(connection)

        # 연결이 끊어진 클라이언트 제거
        for connection in disconnected:
            self.disconnect(connection)

    async def start_price_stream(self):
        """실시간 가격 스트림 시작."""
        logger.info("실시간 가격 스트림 시작")

        symbols = ["BTC_KRW", "ETH_KRW", "XRP_KRW", "ADA_KRW"]

        while True:
            try:
                if not self.active_connections:
                    await asyncio.sleep(5)
                    continue

                # 주요 종목 가격 조회
                price_data = {}
                for symbol in symbols:
                    ticker = await self.client.get_ticker(symbol)
                    if ticker:
                        price_data[symbol] = {
                            "symbol": symbol,
                            "price": float(ticker.get('closing_price', 0)),
                            "change_24h": float(ticker.get('fluctate_24H', 0)),
                            "change_rate_24h": float(ticker.get('fluctate_rate_24H', 0)),
                            "volume_24h": float(ticker.get('units_traded_24H', 0)),
                            "timestamp": datetime.now().isoformat()
                        }

                if price_data:
                    await self.broadcast({
                        "type": "price_update",
                        "data": price_data
                    })

                await asyncio.sleep(2)  # 2초마다 업데이트

            except Exception as e:
                logger.error(f"가격 스트림 오류: {e}")
                await asyncio.sleep(5)

    async def start_portfolio_stream(self):
        """실시간 포트폴리오 스트림 시작."""
        logger.info("실시간 포트폴리오 스트림 시작")

        while True:
            try:
                if not self.active_connections:
                    await asyncio.sleep(10)
                    continue

                # 포트폴리오 정보 조회
                balance = await self.client.get_balance()
                if balance:
                    total_krw = float(balance.get('KRW', {}).get('available', 0))

                    portfolio_data = {
                        "total_balance_krw": total_krw,
                        "positions": [],
                        "timestamp": datetime.now().isoformat()
                    }

                    # 보유 코인 정보
                    for symbol, info in balance.items():
                        if symbol in ['KRW', 'date']:
                            continue

                        available = float(info.get('available', 0))
                        in_use = float(info.get('in_use', 0))
                        total_quantity = available + in_use

                        if total_quantity > 0:
                            # 현재가 조회
                            ticker = await self.client.get_ticker(f'{symbol}_KRW')
                            current_price = float(ticker.get('closing_price', 0)) if ticker else 0

                            portfolio_data["positions"].append({
                                "symbol": f"{symbol}_KRW",
                                "quantity": total_quantity,
                                "current_price": current_price,
                                "market_value": total_quantity * current_price
                            })

                    await self.broadcast({
                        "type": "portfolio_update",
                        "data": portfolio_data
                    })

                await asyncio.sleep(10)  # 10초마다 업데이트

            except Exception as e:
                logger.error(f"포트폴리오 스트림 오류: {e}")
                await asyncio.sleep(10)

    async def send_trade_notification(self, trade_data: Dict[str, Any]):
        """거래 알림 전송."""
        await self.broadcast({
            "type": "trade_notification",
            "data": {
                **trade_data,
                "timestamp": datetime.now().isoformat()
            }
        })

# 전역 연결 관리자
manager = ConnectionManager()

class WebSocketManager:
    """WebSocket 앱 관리자."""

    def __init__(self):
        self.app = FastAPI()
        self.manager = manager
        self._setup_routes()
        self._start_background_tasks()

    def _setup_routes(self):
        """WebSocket 라우트 설정."""

        @self.app.websocket("/")
        async def websocket_endpoint(websocket: WebSocket):
            await self.manager.connect(websocket)
            try:
                while True:
                    # 클라이언트로부터 메시지 수신 대기
                    data = await websocket.receive_text()
                    message = json.loads(data)

                    # 메시지 타입별 처리
                    if message.get("type") == "ping":
                        await self.manager.send_personal_message(
                            {"type": "pong", "timestamp": datetime.now().isoformat()},
                            websocket
                        )
                    elif message.get("type") == "subscribe":
                        # 구독 요청 처리
                        await self.manager.send_personal_message(
                            {"type": "subscribed", "channels": message.get("channels", [])},
                            websocket
                        )

            except WebSocketDisconnect:
                self.manager.disconnect(websocket)

    def _start_background_tasks(self):
        """백그라운드 태스크 시작."""
        import threading

        def start_price_stream():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.manager.start_price_stream())

        def start_portfolio_stream():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.manager.start_portfolio_stream())

        # 별도 스레드에서 실행
        threading.Thread(target=start_price_stream, daemon=True).start()
        threading.Thread(target=start_portfolio_stream, daemon=True).start()

# 전역 WebSocket 매니저
websocket_manager = WebSocketManager()