"""빗썸 WebSocket 전용 클라이언트."""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from ..utils.exceptions import ExchangeError
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BithumbWebSocketClient:
    """빗썸 WebSocket 전용 클라이언트."""

    def __init__(self, testnet: bool = False):
        """
        WebSocket 클라이언트 초기화.

        Args:
            testnet: 테스트넷 사용 여부
        """
        self.testnet = testnet
        self.ws_url = "wss://pubwss.bithumb.com/pub/ws" if not testnet else "wss://pubwss.bithumb.com/pub/ws"

        self.websocket = None
        self.is_connected = False
        self.reconnect_interval = 5  # 재연결 간격 (초)
        self.max_reconnect_attempts = 10
        self.reconnect_count = 0

        # 구독 관리
        self.subscriptions = set()
        self.callbacks = {}

        # 메시지 관리
        self.last_ping_time = 0
        self.ping_interval = 30  # 핑 간격 (초)

        self.logger = logger
        self._running = False

    async def connect(self) -> bool:
        """WebSocket 연결."""
        try:
            self.logger.info(f"빗썸 WebSocket 연결 시도: {self.ws_url}")

            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )

            self.is_connected = True
            self.reconnect_count = 0
            self._running = True

            self.logger.info("빗썸 WebSocket 연결 성공")

            # 백그라운드에서 메시지 수신 시작
            asyncio.create_task(self._message_handler())
            asyncio.create_task(self._ping_sender())

            return True

        except Exception as e:
            self.logger.error(f"WebSocket 연결 실패: {e}")
            self.is_connected = False
            return False

    async def disconnect(self):
        """WebSocket 연결 해제."""
        self._running = False
        self.is_connected = False

        if self.websocket:
            try:
                await self.websocket.close()
                self.logger.info("WebSocket 연결 해제")
            except Exception as e:
                self.logger.error(f"WebSocket 연결 해제 실패: {e}")

        self.websocket = None

    async def _reconnect(self):
        """WebSocket 재연결."""
        if self.reconnect_count >= self.max_reconnect_attempts:
            self.logger.error("최대 재연결 시도 횟수 초과")
            return False

        self.reconnect_count += 1
        self.logger.info(f"WebSocket 재연결 시도 ({self.reconnect_count}/{self.max_reconnect_attempts})")

        await asyncio.sleep(self.reconnect_interval)

        if await self.connect():
            # 기존 구독 복원
            await self._restore_subscriptions()
            return True

        return False

    async def _restore_subscriptions(self):
        """기존 구독 복원."""
        for subscription in self.subscriptions.copy():
            try:
                await self._send_message(subscription)
                self.logger.info(f"구독 복원: {subscription}")
            except Exception as e:
                self.logger.error(f"구독 복원 실패: {e}")

    async def _send_message(self, message: Dict[str, Any]):
        """WebSocket 메시지 전송."""
        if not self.is_connected or not self.websocket:
            raise ExchangeError("WebSocket이 연결되지 않았습니다.")

        try:
            await self.websocket.send(json.dumps(message))
        except ConnectionClosed:
            self.logger.warning("WebSocket 연결이 끊어졌습니다. 재연결 시도...")
            self.is_connected = False
            await self._reconnect()
        except Exception as e:
            self.logger.error(f"메시지 전송 실패: {e}")
            raise ExchangeError(f"메시지 전송 실패: {e}")

    async def _message_handler(self):
        """WebSocket 메시지 수신 처리."""
        while self._running and self.websocket:
            try:
                message = await self.websocket.recv()
                await self._process_message(message)

            except ConnectionClosed:
                self.logger.warning("WebSocket 연결이 끊어졌습니다.")
                self.is_connected = False
                if self._running:
                    await self._reconnect()
                break

            except WebSocketException as e:
                self.logger.error(f"WebSocket 오류: {e}")
                self.is_connected = False
                if self._running:
                    await self._reconnect()
                break

            except Exception as e:
                self.logger.error(f"메시지 처리 오류: {e}")

    async def _process_message(self, message: str):
        """수신된 메시지 처리."""
        try:
            data = json.loads(message)

            # 메시지 타입별 처리
            if 'type' in data:
                message_type = data['type']

                # ticker 데이터
                if message_type == 'ticker':
                    await self._handle_ticker(data)

                # orderbook 데이터
                elif message_type == 'orderbook':
                    await self._handle_orderbook(data)

                # transaction 데이터
                elif message_type == 'transaction':
                    await self._handle_transaction(data)

                # 기타 메시지
                else:
                    self.logger.debug(f"알 수 없는 메시지 타입: {message_type}")

        except json.JSONDecodeError:
            self.logger.error(f"JSON 파싱 실패: {message}")
        except Exception as e:
            self.logger.error(f"메시지 처리 실패: {e}")

    async def _handle_ticker(self, data: Dict[str, Any]):
        """Ticker 데이터 처리."""
        callback = self.callbacks.get('ticker')
        if callback:
            try:
                await callback(data)
            except Exception as e:
                self.logger.error(f"Ticker 콜백 실행 실패: {e}")

    async def _handle_orderbook(self, data: Dict[str, Any]):
        """Orderbook 데이터 처리."""
        callback = self.callbacks.get('orderbook')
        if callback:
            try:
                await callback(data)
            except Exception as e:
                self.logger.error(f"Orderbook 콜백 실행 실패: {e}")

    async def _handle_transaction(self, data: Dict[str, Any]):
        """Transaction 데이터 처리."""
        callback = self.callbacks.get('transaction')
        if callback:
            try:
                await callback(data)
            except Exception as e:
                self.logger.error(f"Transaction 콜백 실행 실패: {e}")

    async def _ping_sender(self):
        """주기적으로 핑 전송."""
        while self._running and self.is_connected:
            try:
                current_time = time.time()

                if current_time - self.last_ping_time >= self.ping_interval:
                    if self.websocket:
                        await self.websocket.ping()
                        self.last_ping_time = current_time

                await asyncio.sleep(5)

            except Exception as e:
                self.logger.error(f"핑 전송 실패: {e}")

    async def subscribe_ticker(self, symbols: List[str], callback: Callable = None):
        """Ticker 구독."""
        try:
            message = {
                "type": "ticker",
                "symbols": symbols
            }

            await self._send_message(message)
            self.subscriptions.add(json.dumps(message, sort_keys=True))

            if callback:
                self.callbacks['ticker'] = callback

            self.logger.info(f"Ticker 구독 완료: {symbols}")

        except Exception as e:
            self.logger.error(f"Ticker 구독 실패: {e}")
            raise ExchangeError(f"Ticker 구독 실패: {e}")

    async def subscribe_orderbook(self, symbols: List[str], callback: Callable = None):
        """Orderbook 구독."""
        try:
            message = {
                "type": "orderbook",
                "symbols": symbols
            }

            await self._send_message(message)
            self.subscriptions.add(json.dumps(message, sort_keys=True))

            if callback:
                self.callbacks['orderbook'] = callback

            self.logger.info(f"Orderbook 구독 완료: {symbols}")

        except Exception as e:
            self.logger.error(f"Orderbook 구독 실패: {e}")
            raise ExchangeError(f"Orderbook 구독 실패: {e}")

    async def subscribe_transaction(self, symbols: List[str], callback: Callable = None):
        """Transaction 구독."""
        try:
            message = {
                "type": "transaction",
                "symbols": symbols
            }

            await self._send_message(message)
            self.subscriptions.add(json.dumps(message, sort_keys=True))

            if callback:
                self.callbacks['transaction'] = callback

            self.logger.info(f"Transaction 구독 완료: {symbols}")

        except Exception as e:
            self.logger.error(f"Transaction 구독 실패: {e}")
            raise ExchangeError(f"Transaction 구독 실패: {e}")

    async def unsubscribe(self, message_type: str, symbols: List[str]):
        """구독 해제."""
        try:
            message = {
                "type": message_type,
                "symbols": symbols,
                "unsubscribe": True
            }

            await self._send_message(message)

            # 구독 목록에서 제거
            subscription_key = json.dumps({
                "type": message_type,
                "symbols": symbols
            }, sort_keys=True)

            self.subscriptions.discard(subscription_key)

            self.logger.info(f"{message_type} 구독 해제 완료: {symbols}")

        except Exception as e:
            self.logger.error(f"구독 해제 실패: {e}")
            raise ExchangeError(f"구독 해제 실패: {e}")

    def get_connection_status(self) -> Dict[str, Any]:
        """연결 상태 조회."""
        return {
            "is_connected": self.is_connected,
            "reconnect_count": self.reconnect_count,
            "subscriptions": len(self.subscriptions),
            "callbacks": list(self.callbacks.keys())
        }

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()


# 사용 예시를 위한 콜백 함수들
async def ticker_callback(data: Dict[str, Any]):
    """Ticker 데이터 처리 콜백."""
    symbol = data.get('symbol', 'UNKNOWN')
    price = data.get('closePrice', 0)
    logger.info(f"Ticker - {symbol}: {price}")


async def orderbook_callback(data: Dict[str, Any]):
    """Orderbook 데이터 처리 콜백."""
    symbol = data.get('symbol', 'UNKNOWN')
    bids = data.get('bids', [])
    asks = data.get('asks', [])
    logger.info(f"Orderbook - {symbol}: {len(bids)} bids, {len(asks)} asks")


async def transaction_callback(data: Dict[str, Any]):
    """Transaction 데이터 처리 콜백."""
    symbol = data.get('symbol', 'UNKNOWN')
    price = data.get('price', 0)
    volume = data.get('volume', 0)
    logger.info(f"Transaction - {symbol}: {price} x {volume}")


# 통합 WebSocket 관리자
class BithumbWebSocketManager:
    """빗썸 WebSocket 관리자."""

    def __init__(self):
        self.client = None
        self.is_running = False

    async def start(self, symbols: List[str]):
        """WebSocket 관리자 시작."""
        try:
            self.client = BithumbWebSocketClient()
            await self.client.connect()

            # 주요 데이터 구독
            await self.client.subscribe_ticker(symbols, ticker_callback)
            await self.client.subscribe_transaction(symbols, transaction_callback)

            self.is_running = True
            logger.info("WebSocket 관리자 시작 완료")

        except Exception as e:
            logger.error(f"WebSocket 관리자 시작 실패: {e}")
            raise

    async def stop(self):
        """WebSocket 관리자 중지."""
        self.is_running = False

        if self.client:
            await self.client.disconnect()

        logger.info("WebSocket 관리자 중지 완료")

    def get_status(self) -> Dict[str, Any]:
        """관리자 상태 조회."""
        if self.client:
            return {
                "manager_running": self.is_running,
                **self.client.get_connection_status()
            }
        return {"manager_running": False}