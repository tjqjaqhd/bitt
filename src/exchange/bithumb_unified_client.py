"""통합된 빗썸 클라이언트 (REST + WebSocket)."""

import asyncio
from decimal import Decimal
from typing import Dict, List, Optional, Any, Callable

from .bithumb_rest_client import BithumbRestClient
from .bithumb_websocket_client import BithumbWebSocketClient
from ..utils.exceptions import ExchangeError
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BithumbUnifiedClient:
    """REST와 WebSocket을 통합한 빗썸 클라이언트."""

    def __init__(self, api_key: str = "", secret_key: str = "", testnet: bool = False):
        """
        통합 클라이언트 초기화.

        Args:
            api_key: API 키
            secret_key: 시크릿 키
            testnet: 테스트넷 사용 여부
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet

        # REST 클라이언트
        self.rest_client = BithumbRestClient(api_key, secret_key, testnet)

        # WebSocket 클라이언트
        self.ws_client = BithumbWebSocketClient(testnet)

        # 실시간 데이터 캐시
        self.ticker_cache = {}
        self.orderbook_cache = {}
        self.transaction_cache = {}

        self.logger = logger

    async def initialize(self):
        """클라이언트 초기화."""
        try:
            # WebSocket 연결 (선택적)
            await self.ws_client.connect()

            # 실시간 데이터 콜백 설정
            await self.ws_client.subscribe_ticker(
                ["BTC_KRW", "ETH_KRW", "XRP_KRW"],
                self._ticker_callback
            )

            self.logger.info("통합 클라이언트 초기화 완료")

        except Exception as e:
            self.logger.warning(f"WebSocket 초기화 실패 (REST만 사용): {e}")

    async def close(self):
        """클라이언트 종료."""
        if self.ws_client:
            await self.ws_client.disconnect()

        if self.rest_client:
            self.rest_client.close()

        self.logger.info("통합 클라이언트 종료 완료")

    # 콜백 함수들
    async def _ticker_callback(self, data: Dict[str, Any]):
        """Ticker 데이터 캐시 업데이트."""
        symbol = data.get('symbol')
        if symbol:
            self.ticker_cache[symbol] = data

    async def _orderbook_callback(self, data: Dict[str, Any]):
        """Orderbook 데이터 캐시 업데이트."""
        symbol = data.get('symbol')
        if symbol:
            self.orderbook_cache[symbol] = data

    async def _transaction_callback(self, data: Dict[str, Any]):
        """Transaction 데이터 캐시 업데이트."""
        symbol = data.get('symbol')
        if symbol:
            if symbol not in self.transaction_cache:
                self.transaction_cache[symbol] = []
            self.transaction_cache[symbol].append(data)

            # 최근 100개만 유지
            self.transaction_cache[symbol] = self.transaction_cache[symbol][-100:]

    # Public API 메서드들 (REST 기반)
    async def get_ticker(self, symbol: str = "ALL") -> Optional[Dict[str, Any]]:
        """현재가 정보 조회 (캐시 우선, REST 폴백)."""
        # WebSocket 캐시에서 우선 조회
        if symbol != "ALL" and symbol in self.ticker_cache:
            return self.ticker_cache[symbol]

        # REST API로 폴백
        return await self.rest_client.get_ticker(symbol)

    async def get_orderbook(self, symbol: str, count: int = 20) -> Optional[Dict[str, Any]]:
        """호가 정보 조회."""
        return await self.rest_client.get_orderbook(symbol, count)

    async def get_recent_transactions(self, symbol: str, count: int = 20) -> Optional[List[Dict[str, Any]]]:
        """최근 체결 내역 조회 (캐시 우선, REST 폴백)."""
        # WebSocket 캐시에서 우선 조회
        if symbol in self.transaction_cache:
            cached_data = self.transaction_cache[symbol][-count:]
            if cached_data:
                return cached_data

        # REST API로 폴백
        return await self.rest_client.get_recent_transactions(symbol, count)

    async def get_assets_status(self, symbol: str = "ALL") -> Optional[Dict[str, Any]]:
        """입출금 현황 조회."""
        return await self.rest_client.get_assets_status(symbol)

    # Private API 메서드들 (REST 전용)
    async def get_balance(self, symbol: str = "ALL") -> Optional[Dict[str, Any]]:
        """잔고 조회."""
        return await self.rest_client.get_balance(symbol)

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Optional[Dict[str, Any]]:
        """주문 생성."""
        return await self.rest_client.place_order(symbol, side, order_type, quantity, price)

    async def cancel_order(self, order_id: str, symbol: str, side: str) -> Optional[Dict[str, Any]]:
        """주문 취소."""
        return await self.rest_client.cancel_order(order_id, symbol, side)

    async def get_orders(self, symbol: str, order_id: str = None) -> Optional[Dict[str, Any]]:
        """주문 조회."""
        return await self.rest_client.get_orders(symbol, order_id)

    async def get_order_detail(self, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """주문 상세 조회."""
        return await self.rest_client.get_order_detail(order_id, symbol)

    async def get_user_transactions(
        self,
        symbol: str,
        search_gb: int = 0,
        offset: int = 0,
        count: int = 20
    ) -> Optional[List[Dict[str, Any]]]:
        """거래 내역 조회."""
        return await self.rest_client.get_user_transactions(symbol, search_gb, offset, count)

    # WebSocket 관련 메서드들
    async def subscribe_ticker(self, symbols: List[str], callback: Callable = None):
        """Ticker 실시간 구독."""
        if self.ws_client.is_connected:
            await self.ws_client.subscribe_ticker(symbols, callback or self._ticker_callback)
        else:
            self.logger.warning("WebSocket이 연결되지 않아 ticker 구독을 건너뜁니다.")

    async def subscribe_orderbook(self, symbols: List[str], callback: Callable = None):
        """Orderbook 실시간 구독."""
        if self.ws_client.is_connected:
            await self.ws_client.subscribe_orderbook(symbols, callback or self._orderbook_callback)
        else:
            self.logger.warning("WebSocket이 연결되지 않아 orderbook 구독을 건너뜁니다.")

    async def subscribe_transaction(self, symbols: List[str], callback: Callable = None):
        """Transaction 실시간 구독."""
        if self.ws_client.is_connected:
            await self.ws_client.subscribe_transaction(symbols, callback or self._transaction_callback)
        else:
            self.logger.warning("WebSocket이 연결되지 않아 transaction 구독을 건너뜁니다.")

    # 유틸리티 메서드들
    def get_cached_ticker(self, symbol: str) -> Optional[Dict[str, Any]]:
        """캐시된 ticker 데이터 조회."""
        return self.ticker_cache.get(symbol)

    def get_cached_transactions(self, symbol: str, count: int = 10) -> List[Dict[str, Any]]:
        """캐시된 transaction 데이터 조회."""
        cached = self.transaction_cache.get(symbol, [])
        return cached[-count:] if cached else []

    def get_connection_status(self) -> Dict[str, Any]:
        """연결 상태 조회."""
        return {
            "rest_available": True,
            "websocket_connected": self.ws_client.is_connected if self.ws_client else False,
            "cached_tickers": len(self.ticker_cache),
            "cached_transactions": sum(len(v) for v in self.transaction_cache.values()),
            **self.ws_client.get_connection_status() if self.ws_client else {}
        }

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# 기존 BithumbClient와의 호환성을 위한 별칭
BithumbClient = BithumbUnifiedClient


# 사용 예시
async def example_usage():
    """사용 예시."""
    client = BithumbUnifiedClient(api_key="your_api_key", secret_key="your_secret")

    try:
        # 클라이언트 초기화
        await client.initialize()

        # 현재가 조회 (캐시 우선)
        ticker = await client.get_ticker("BTC_KRW")
        print(f"BTC 현재가: {ticker}")

        # 최근 거래 내역 조회
        transactions = await client.get_recent_transactions("BTC_KRW", 10)
        print(f"최근 거래 {len(transactions)}건")

        # 잔고 조회
        balance = await client.get_balance("ALL")
        print(f"잔고: {balance}")

        # 실시간 데이터 구독
        await client.subscribe_ticker(["BTC_KRW", "ETH_KRW"])

        # 일정 시간 대기 (실시간 데이터 수신)
        await asyncio.sleep(10)

        # 연결 상태 확인
        status = client.get_connection_status()
        print(f"연결 상태: {status}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(example_usage())