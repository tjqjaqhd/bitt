from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import pytest
import requests
import websockets

from src.exchange import BithumbClient, BithumbEndpoint, BithumbWebSocketClient, normalize_market_code
from src.utils.exceptions import ExchangeError, WebSocketError


@dataclass
class DummyResponse:
    status_code: int = 200
    json_payload: Any = None
    text: str = ""
    json_raises: bool = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)  # type: ignore[name-defined]

    def json(self) -> Any:
        if self.json_raises:
            raise ValueError("invalid json")
        return self.json_payload


class DummySession:
    def __init__(self, responses: List[DummyResponse]) -> None:
        self._responses = responses
        self.calls: List[Dict[str, Any]] = []

    def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Any = None,
    ) -> DummyResponse:
        if not self._responses:
            raise AssertionError("예상치 못한 추가 호출이 발생했습니다.")
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "data": data or {},
                "headers": headers or {},
                "timeout": timeout,
            }
        )
        return self._responses.pop(0)

    def close(self) -> None:  # pragma: no cover - 외부 세션에서는 호출되지 않음
        pass


def test_normalize_market_code_variants() -> None:
    assert normalize_market_code("btc") == "BTC_KRW"
    assert normalize_market_code("BTC_KRW") == "BTC_KRW"
    assert normalize_market_code("btc-krw") == "BTC_KRW"
    assert normalize_market_code("ALL") == "ALL"


def test_get_request_basic_flow() -> None:
    responses = [DummyResponse(json_payload={"status": "0000", "data": {"closing_price": "160830000"}})]
    session = DummySession(responses)
    client = BithumbClient(base_url="https://api.bithumb.com", session=session)

    payload = client.get(BithumbEndpoint.TICKER, path_params={"market": "BTC_KRW"})

    assert payload["data"]["closing_price"] == "160830000"
    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == "https://api.bithumb.com/public/ticker/BTC_KRW"
    assert call["headers"]["User-Agent"].startswith("bitt/")
    assert call["timeout"] == 10


def test_request_retries_on_http_status() -> None:
    responses = [
        DummyResponse(status_code=429, text="too many requests"),
        DummyResponse(json_payload={"status": "0000", "data": {}}),
    ]
    session = DummySession(responses)
    client = BithumbClient(base_url="https://api.bithumb.com", session=session)
    client._sleep = lambda _: None  # type: ignore[assignment]

    payload = client.get(BithumbEndpoint.TICKER, path_params={"market": "BTC_KRW"})

    assert payload["status"] == "0000"
    assert len(session.calls) == 2


def test_request_retries_on_rate_limit_payload() -> None:
    responses = [
        DummyResponse(json_payload={"status": "4290", "message": "rate limit"}),
        DummyResponse(json_payload={"status": "0000", "data": {"price": "160830000"}}),
    ]
    session = DummySession(responses)
    client = BithumbClient(base_url="https://api.bithumb.com", session=session)
    client._sleep = lambda _: None  # type: ignore[assignment]

    payload = client.get(BithumbEndpoint.TICKER, path_params={"market": "BTC_KRW"})

    assert payload["data"]["price"] == "160830000"
    assert len(session.calls) == 2


def test_private_request_signing() -> None:
    responses = [DummyResponse(json_payload={"status": "0000", "data": {}})]
    session = DummySession(responses)
    client = BithumbClient(
        base_url="https://api.bithumb.com",
        session=session,
        api_key="test-key",
        api_secret="test-secret",
    )
    client._sleep = lambda _: None  # type: ignore[assignment]
    client._generate_nonce = lambda: "1700000000000"  # type: ignore[assignment]

    client.post(BithumbEndpoint.BALANCE, data={"currency": "BTC"}, private=True)

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["headers"]["Api-Key"] == "test-key"
    assert call["headers"]["Api-Nonce"] == "1700000000000"

    payload = {"currency": "BTC", "endpoint": "/info/balance"}
    expected_query = "/info/balance" + chr(0) + urlencode(payload) + chr(0) + "1700000000000"
    expected_digest = hmac.new(
        b"test-secret",
        expected_query.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()
    expected_signature = base64.b64encode(expected_digest.encode("utf-8")).decode("utf-8")
    assert call["headers"]["Api-Sign"] == expected_signature
    assert call["data"]["endpoint"] == "/info/balance"


@pytest.mark.parametrize(
    "responses,method,expected",
    [
        (
            [
                DummyResponse(
                    json_payload={
                        "status": "0000",
                        "data": {
                            "closing_price": "160830000",
                            "opening_price": "161702000",
                            "min_price": "160336000",
                            "max_price": "162000000",
                            "units_traded_24H": "436.85469431",
                        },
                        "date": "1758520496561",
                    }
                ),
            ],
            "get_ticker",
            "closing_price",
        ),
    ],
)
def test_public_ticker_helper(responses, method, expected) -> None:
    session = DummySession(responses)
    client = BithumbClient(base_url="https://api.bithumb.com", session=session)
    result = getattr(client, method)("BTC")
    assert result["data"][expected] == "160830000"


def test_public_helpers_orderbook_transactions_candles() -> None:
    responses = [
        DummyResponse(
            json_payload={
                "status": "0000",
                "data": {
                    "timestamp": "1758520502075",
                    "bids": [
                        {"price": "160816000", "quantity": "0.0779"},
                        {"price": "160814000", "quantity": "0.0006"},
                    ],
                    "asks": [
                        {"price": "160830000", "quantity": "0.0431"},
                        {"price": "160831000", "quantity": "0.0861"},
                    ],
                },
            }
        ),
        DummyResponse(
            json_payload={
                "status": "0000",
                "data": [
                    {
                        "transaction_date": "2025-09-22 14:54:56",
                        "type": "ask",
                        "units_traded": "0.00171231",
                        "price": "160816000",
                        "total": "275366",
                    },
                    {
                        "transaction_date": "2025-09-22 14:54:57",
                        "type": "ask",
                        "units_traded": "0.02008196",
                        "price": "160816000",
                        "total": "3229500",
                    },
                ],
            }
        ),
        DummyResponse(
            json_payload={
                "status": "0000",
                "data": [
                    [1758340080000, "162178000", "162180000", "162213000", "162178000", "0.20632952"],
                    [1758340140000, "162209000", "162200000", "162209000", "162180000", "0.06366179"],
                ],
            }
        ),
    ]
    session = DummySession(responses)
    client = BithumbClient(base_url="https://api.bithumb.com", session=session)

    orderbook = client.get_orderbook("BTC")
    trades = client.get_recent_transactions("BTC", count=2)
    candles = client.get_candlestick("BTC", interval="1m")

    assert orderbook["data"]["bids"][0]["price"] == "160816000"
    assert trades["data"][0]["total"] == "275366"
    assert candles["data"][0][1] == "162178000"

    assert session.calls[0]["url"].endswith("/public/orderbook/BTC_KRW")
    assert session.calls[1]["params"]["count"] == 2
    assert session.calls[2]["url"].endswith("/public/candlestick/BTC_KRW/1m")


def test_private_balance_helpers() -> None:
    responses = [
        DummyResponse(
            json_payload={
                "status": "0000",
                "data": {
                    "available_krw": "125000.5000",
                },
            }
        ),
        DummyResponse(
            json_payload={
                "status": "0000",
                "data": {"trade_fee": "0.0025"},
            }
        ),
    ]
    session = DummySession(responses)
    client = BithumbClient(
        base_url="https://api.bithumb.com",
        session=session,
        api_key="key",
        api_secret="secret",
    )
    client._sleep = lambda _: None  # type: ignore[assignment]
    client._generate_nonce = lambda: "1700000000000"  # type: ignore[assignment]

    available = client.get_available_funds("KRW")
    fee = client.get_trading_fee("BTC")

    assert pytest.approx(available, rel=1e-9) == 125000.5
    assert pytest.approx(fee, rel=1e-9) == 0.0025


def test_request_raises_on_api_error() -> None:
    responses = [DummyResponse(json_payload={"status": "5300", "message": "invalid order"})]
    session = DummySession(responses)
    client = BithumbClient(base_url="https://api.bithumb.com", session=session)

    with pytest.raises(ExchangeError) as exc:
        client.get(BithumbEndpoint.TICKER, path_params={"market": "BTC_KRW"})
    assert "5300" in str(exc.value)


def test_websocket_client_handles_reconnect_and_ping() -> None:
    messages_to_emit = [
        {
            "type": "ticker",
            "content": {
                "symbol": "BTC_KRW",
                "closePrice": "160830000",
                "volume": "436.85469431",
            },
        },
        {
            "type": "transaction",
            "content": {
                "symbol": "BTC_KRW",
                "side": "ask",
                "contPrice": "160816000",
                "contQty": "0.00171231",
                "contAmt": "275366",
                "contDtm": "2025-09-22 14:54:56.123",
            },
        },
    ]
    subscriptions: List[Dict[str, Any]] = []
    pong_messages: List[Dict[str, Any]] = []

    async def scenario() -> None:
        connection_count = 0

        async def handler(websocket):
            nonlocal connection_count
            connection_count += 1
            await websocket.send(json.dumps({"status": "0000", "resmsg": "Connected Successfully"}))
            first_request = await websocket.recv()
            subscriptions.append(json.loads(first_request))
            await websocket.send(json.dumps({"status": "0000", "resmsg": "Filter Registered Successfully"}))
            await websocket.send(json.dumps({"type": "ping"}))
            pong_raw = await websocket.recv()
            pong_messages.append(json.loads(pong_raw))
            if connection_count == 1:
                await websocket.close()
                return
            for payload in messages_to_emit:
                await websocket.send(json.dumps(payload))
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)

        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            client = BithumbWebSocketClient(
                url=f"ws://127.0.0.1:{port}",
                backoff_factor=0.01,
                max_retries=3,
            )
            await client.subscribe_ticker(["BTC_KRW"])

            async def collect() -> List[Dict[str, Any]]:
                received: List[Dict[str, Any]] = []
                async for payload in client.listen():
                    received.append(payload)
                    if len(received) == len(messages_to_emit):
                        await client.disconnect()
                        break
                return received

            received_messages = await asyncio.wait_for(collect(), timeout=5)

            assert received_messages == messages_to_emit
            assert len(subscriptions) == 2
            assert subscriptions[0]["symbols"] == ["BTC_KRW"]
            assert subscriptions[1]["symbols"] == ["BTC_KRW"]
            assert pong_messages == [{"type": "pong"}, {"type": "pong"}]

    asyncio.run(scenario())


def test_websocket_client_raises_when_reconnect_disabled() -> None:
    async def scenario() -> None:
        async def handler(websocket):
            await websocket.send(json.dumps({"status": "0000", "resmsg": "Connected Successfully"}))
            await websocket.close()

        async with websockets.serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            client = BithumbWebSocketClient(
                url=f"ws://127.0.0.1:{port}",
                reconnect=False,
                max_retries=0,
            )
            await client.subscribe_ticker(["BTC_KRW"])

            async def consume():
                async for _ in client.listen():
                    pass

            with pytest.raises(WebSocketError):
                await asyncio.wait_for(consume(), timeout=2)

    asyncio.run(scenario())
