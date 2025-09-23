"""빗썸 REST 및 WebSocket API 클라이언트."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, MutableMapping, Optional, Sequence, Tuple, Union

from urllib.parse import urlencode

import jwt
import requests
import websockets
from requests import Response, Session
from websockets import WebSocketClientProtocol

from ..config import get_settings
from ..utils.exceptions import ExchangeError, WebSocketError

JsonMapping = Mapping[str, Any]
MutableJsonMapping = MutableMapping[str, Any]
Headers = Mapping[str, str]
Timeout = Union[float, Tuple[float, float]]

DEFAULT_USER_AGENT = "bitt/0.1 (+https://github.com/user/bitt)"
DEFAULT_TIMEOUT: Timeout = 10
DEFAULT_WS_URL = "wss://pubwss.bithumb.com/pub/ws"
WS_DEFAULT_PING_INTERVAL = 20.0
WS_DEFAULT_PING_TIMEOUT = 10.0
WS_DEFAULT_RECV_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 0.5
RETRY_STATUS_CODES: Tuple[int, ...] = (429, 500, 502, 503, 504)
RATE_LIMIT_STATUSES = {"4290"}

BITHUMB_ERROR_MESSAGES: dict[str, str] = {
    "5100": "잘못된 요청입니다.",
    "5101": "필수 파라미터가 누락되었습니다.",
    "5102": "파라미터 형식이 올바르지 않습니다.",
    "5200": "계좌 잔액이 부족합니다.",
    "5300": "유효하지 않은 주문 요청입니다.",
    "5302": "주문 가격 또는 수량이 허용 범위를 벗어났습니다.",
    "5400": "API 접근 권한이 없습니다.",
    "5401": "허용되지 않은 IP 주소입니다.",
    "5600": "요청 처리 중 오류가 발생했습니다.",
    "5900": "인증 정보가 올바르지 않습니다.",
    "6000": "서비스 점검 중입니다.",
    "6100": "허용되지 않은 계정 접근입니다.",
    "6200": "API 호출 한도를 초과했습니다.",
    "6300": "내부 서버 오류가 발생했습니다.",
    "6900": "서비스 이용이 제한되었습니다.",
    "7000": "일시적으로 서비스가 중단되었습니다.",
}


def normalize_market_code(order_currency: str, payment_currency: Optional[str] = "KRW") -> str:
    """빗썸에서 사용하는 종목 코드를 정규화한다."""

    cleaned = order_currency.strip().upper().replace("-", "_")
    if cleaned == "ALL":
        return "ALL"
    if "_" in cleaned:
        return cleaned
    payment = payment_currency or "KRW"
    return f"{cleaned}_{payment.strip().upper().replace('-', '_')}"


class HttpMethod(str, Enum):
    """지원하는 HTTP 메서드."""

    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"


class BithumbEndpoint(str, Enum):
    """빗썸 REST API 2.0 엔드포인트."""

    # Public API (v1)
    TICKER = "/public/ticker/{market}"
    ORDERBOOK = "/public/orderbook/{market}"
    TRANSACTIONS = "/public/transaction_history/{market}"
    CANDLESTICK = "/public/candlestick/{market}/{interval}"

    # Private API (v1 - 새로운 API 2.0 엔드포인트)
    ACCOUNTS = "/v1/accounts"  # 전체 계좌 조회
    BALANCE = "/info/balance"  # 구버전 호환
    ACCOUNT = "/info/account"
    ORDERS = "/info/orders"
    ORDER_DETAIL = "/info/order_detail"
    USER_TRANSACTIONS = "/info/user_transactions"
    TRADE_PLACE = "/trade/place"
    TRADE_CANCEL = "/trade/cancel"


@dataclass(frozen=True)
class ClientCredentials:
    """빗썸 API 인증 정보를 담는 데이터 구조."""

    api_key: Optional[str]
    api_secret: Optional[str]


class BithumbClient:
    """빗썸 REST API 호출을 담당하는 기본 클라이언트."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        session: Optional[Session] = None,
        timeout: Timeout = DEFAULT_TIMEOUT,
        user_agent: str = DEFAULT_USER_AGENT,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        retry_statuses: Sequence[int] = RETRY_STATUS_CODES,
    ) -> None:
        settings = get_settings()
        bithumb_settings = settings.bithumb

        resolved_base_url = (base_url or bithumb_settings.rest_base_url).rstrip("/")
        self._base_url = resolved_base_url
        self._timeout: Timeout = timeout
        self._session: Session = session or requests.Session()
        self._owns_session = session is None
        self._default_headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": user_agent,
        }
        self._max_retries = max(0, max_retries)
        self._backoff_factor = max(0.0, backoff_factor)
        self._retry_statuses = tuple(set(int(code) for code in retry_statuses))
        self._logger = logging.getLogger(__name__)
        self._sleep = time.sleep

        resolved_api_key = api_key or (bithumb_settings.api_key.get_secret_value() if bithumb_settings.api_key else None)
        resolved_api_secret = api_secret or (
            bithumb_settings.api_secret.get_secret_value() if bithumb_settings.api_secret else None
        )
        self._credentials = ClientCredentials(resolved_api_key, resolved_api_secret)

    @property
    def base_url(self) -> str:
        """REST API 기본 URL."""

        return self._base_url

    @property
    def timeout(self) -> Timeout:
        """요청 기본 타임아웃."""

        return self._timeout

    @property
    def session(self) -> Session:
        """내부 HTTP 세션."""

        return self._session

    @property
    def credentials(self) -> ClientCredentials:
        """설정된 인증 정보."""

        return self._credentials

    def close(self) -> None:
        """세션을 종료한다."""

        if self._owns_session:
            self._session.close()

    def __enter__(self) -> "BithumbClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - 컨텍스트 관리자 편의 기능
        self.close()

    # ------------------------------------------------------------------
    # 내부 유틸리티
    # ------------------------------------------------------------------
    def _resolve_endpoint_path(
        self,
        endpoint: Union[BithumbEndpoint, str],
        path_params: Optional[Mapping[str, Any]],
    ) -> str:
        if isinstance(endpoint, BithumbEndpoint):
            path_template = endpoint.value
        else:
            path_template = str(endpoint)

        if not path_template.startswith("/"):
            path_template = f"/{path_template}"

        try:
            return path_template.format(**(path_params or {}))
        except KeyError as exc:  # pragma: no cover - 잘못된 포맷 지정 시만 실행
            missing_key = exc.args[0]
            raise ValueError(
                f"경로 변수 '{missing_key}'가 누락되었습니다: {path_template}"
            ) from exc

    def _build_url(self, endpoint: Union[BithumbEndpoint, str], path_params: Optional[Mapping[str, Any]]) -> str:
        path = self._resolve_endpoint_path(endpoint, path_params)
        return f"{self._base_url}{path}"

    def _merge_headers(self, extra_headers: Optional[Headers]) -> dict[str, str]:
        merged = dict(self._default_headers)
        if extra_headers:
            merged.update(extra_headers)
        return merged

    def _generate_nonce(self) -> str:
        return str(int(time.time() * 1000))

    def _create_signature(self, path: str, nonce: str, payload: MutableJsonMapping) -> str:
        if not self._credentials.api_secret:
            raise ExchangeError("API 시크릿이 설정되어 있지 않습니다.")
        query_string = f"{path}{chr(0)}{urlencode(payload)}{chr(0)}{nonce}"
        digest = hmac.new(
            self._credentials.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()
        return base64.b64encode(digest.encode("utf-8")).decode("utf-8")

    def _prepare_private_request(
        self,
        path: str,
        payload: Optional[Union[MutableJsonMapping, dict]],
    ) -> tuple[MutableJsonMapping, dict[str, str]]:
        """빗썸 API 2.0 JWT 인증 헤더를 생성합니다."""
        if not self._credentials.api_key or not self._credentials.api_secret:
            raise ExchangeError("빗썸 API 키/시크릿을 설정한 뒤 호출해야 합니다.")

        # JWT payload 구성
        jwt_payload = {
            'access_key': self._credentials.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }

        # 요청 파라미터가 있는 경우 해시 추가
        payload_to_send: MutableJsonMapping = dict(payload or {})
        if payload_to_send:
            # 쿼리 스트링 생성 (정렬된 순서로)
            query_string = urlencode(sorted(payload_to_send.items()))
            # SHA512 해시 생성
            query_hash = hashlib.sha512(query_string.encode('utf-8')).hexdigest()
            jwt_payload['query_hash'] = query_hash
            jwt_payload['query_hash_alg'] = 'SHA512'

        # JWT 토큰 생성 (HS256 알고리즘 사용)
        try:
            jwt_token = jwt.encode(jwt_payload, self._credentials.api_secret, algorithm='HS256')
        except Exception as e:
            raise ExchangeError(f"JWT 토큰 생성 실패: {e}")

        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        return payload_to_send, headers

    def _sleep_backoff(self, attempt: int) -> None:
        if self._backoff_factor <= 0:
            return
        delay = self._backoff_factor * (2 ** attempt)
        self._sleep(delay)

    def _is_retryable_status(self, status_code: int) -> bool:
        return status_code in self._retry_statuses

    def _is_rate_limit_payload(self, payload: Any) -> bool:
        if not isinstance(payload, Mapping):
            return False
        status = payload.get("status")
        return status in RATE_LIMIT_STATUSES

    def _raise_for_api_error(self, payload: Any) -> None:
        if not isinstance(payload, Mapping):
            return
        status = str(payload.get("status")) if payload.get("status") is not None else None
        if not status or status == "0000":
            return
        message = (
            payload.get("message")
            or payload.get("message_kor")
            or payload.get("errorMessage")
            or payload.get("resmsg")
        )
        mapped = BITHUMB_ERROR_MESSAGES.get(status)
        if mapped and message and mapped != message:
            detail = f"{mapped} ({message})"
        else:
            detail = message or mapped or "알 수 없는 오류가 발생했습니다."
        raise ExchangeError(f"빗썸 API 오류({status}): {detail}")

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------
    def request(
        self,
        method: Union[HttpMethod, str],
        endpoint: Union[BithumbEndpoint, str],
        *,
        params: Optional[JsonMapping] = None,
        data: Optional[MutableJsonMapping] = None,
        headers: Optional[Headers] = None,
        path_params: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        return_json: bool = True,
        private: bool = False,
    ) -> Any:
        method_value = method.value if isinstance(method, HttpMethod) else str(method).upper()
        path = self._resolve_endpoint_path(endpoint, path_params)
        url = f"{self._base_url}{path}"

        request_data = dict(data or {})
        request_params = dict(params or {}) if params else None
        merged_headers = self._merge_headers(headers)

        if private:
            # GET 요청은 params를, POST 요청은 data를 인증에 사용
            query_data = request_params if method_value == "GET" else request_data
            request_data, auth_headers = self._prepare_private_request(path, query_data)
            merged_headers.update(auth_headers)

        for attempt in range(self._max_retries + 1):
            try:
                response = self._session.request(
                    method=method_value,
                    url=url,
                    params=request_params,
                    data=request_data if request_data else None,
                    headers=merged_headers,
                    timeout=timeout or self._timeout,
                )
            except requests.RequestException as exc:
                if attempt >= self._max_retries:
                    raise ExchangeError(f"빗썸 API 호출 중 네트워크 오류가 발생했습니다: {exc}") from exc
                self._sleep_backoff(attempt)
                continue

            if self._is_retryable_status(response.status_code) and attempt < self._max_retries:
                self._sleep_backoff(attempt)
                continue

            result = self._handle_response(response, to_json=return_json)

            if return_json:
                if self._is_rate_limit_payload(result) and attempt < self._max_retries:
                    self._sleep_backoff(attempt)
                    continue
                self._raise_for_api_error(result)
            return result

        raise ExchangeError("재시도 한도를 초과했습니다.")

    def _handle_response(self, response: Response, *, to_json: bool) -> Any:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = response.status_code
            detail = response.text
            raise ExchangeError(f"빗썸 API 호출 실패: HTTP {status_code} - {detail}") from exc

        if to_json:
            try:
                return response.json()
            except ValueError as exc:
                raise ExchangeError("빗썸 API 응답 JSON 디코딩 실패") from exc
        return response

    def get(
        self,
        endpoint: Union[BithumbEndpoint, str],
        *,
        params: Optional[JsonMapping] = None,
        headers: Optional[Headers] = None,
        path_params: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        return_json: bool = True,
        private: bool = False,
    ) -> Any:
        return self.request(
            HttpMethod.GET,
            endpoint,
            params=params,
            headers=headers,
            path_params=path_params,
            timeout=timeout,
            return_json=return_json,
            private=private,
        )

    def post(
        self,
        endpoint: Union[BithumbEndpoint, str],
        *,
        data: Optional[MutableJsonMapping] = None,
        params: Optional[JsonMapping] = None,
        headers: Optional[Headers] = None,
        path_params: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        return_json: bool = True,
        private: bool = False,
    ) -> Any:
        return self.request(
            HttpMethod.POST,
            endpoint,
            params=params,
            data=data,
            headers=headers,
            path_params=path_params,
            timeout=timeout,
            return_json=return_json,
            private=private,
        )

    def delete(
        self,
        endpoint: Union[BithumbEndpoint, str],
        *,
        params: Optional[JsonMapping] = None,
        headers: Optional[Headers] = None,
        path_params: Optional[Mapping[str, Any]] = None,
        timeout: Optional[Timeout] = None,
        return_json: bool = True,
    ) -> Any:
        return self.request(
            HttpMethod.DELETE,
            endpoint,
            params=params,
            headers=headers,
            path_params=path_params,
            timeout=timeout,
            return_json=return_json,
        )

    # ------------------------------------------------------------------
    # 비즈니스 헬퍼
    # ------------------------------------------------------------------
    def get_ticker(self, order_currency: str = "ALL", *, payment_currency: str = "KRW") -> JsonMapping:
        market = normalize_market_code(order_currency, payment_currency if order_currency.upper() != "ALL" else None)
        return self.get(BithumbEndpoint.TICKER, path_params={"market": market})

    def get_orderbook(
        self,
        order_currency: str,
        *,
        payment_currency: str = "KRW",
        depth: Optional[int] = None,
    ) -> JsonMapping:
        market = normalize_market_code(order_currency, payment_currency)
        params = {"count": depth} if depth else None
        return self.get(BithumbEndpoint.ORDERBOOK, path_params={"market": market}, params=params)

    def get_recent_transactions(
        self,
        order_currency: str,
        *,
        payment_currency: str = "KRW",
        count: int = 20,
    ) -> JsonMapping:
        market = normalize_market_code(order_currency, payment_currency)
        params = {"count": max(1, min(count, 100))}
        return self.get(BithumbEndpoint.TRANSACTIONS, path_params={"market": market}, params=params)

    def get_candlestick(
        self,
        order_currency: str,
        *,
        payment_currency: str = "KRW",
        interval: str = "1m",
    ) -> JsonMapping:
        market = normalize_market_code(order_currency, payment_currency)
        return self.get(
            BithumbEndpoint.CANDLESTICK,
            path_params={"market": market, "interval": interval},
        )

    def get_balances(self, currency: str = "ALL") -> JsonMapping:
        """구버전 잔고 조회 API (호환성 유지)"""
        payload = {"currency": currency.upper()}
        return self.post(BithumbEndpoint.BALANCE, data=payload, private=True)

    def get_accounts(self) -> JsonMapping:
        """API 2.0 전체 계좌 조회 - JWT 인증 방식 사용"""
        return self.get(BithumbEndpoint.ACCOUNTS, private=True)

    def get_account_info(self, order_currency: str, payment_currency: str = "KRW") -> JsonMapping:
        payload = {
            "currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
        }
        return self.post(BithumbEndpoint.ACCOUNT, data=payload, private=True)

    def get_available_funds(self, payment_currency: str = "KRW") -> float:
        response = self.get_balances(payment_currency)
        data = response.get("data", {})
        key = f"available_{payment_currency.lower()}"
        available = data.get(key)
        if available is None:
            raise ExchangeError("주문 가능 금액 정보를 찾을 수 없습니다.")
        return float(available)

    def get_trading_fee(self, order_currency: str, payment_currency: str = "KRW") -> float:
        response = self.get_account_info(order_currency, payment_currency)
        fee = response.get("data", {}).get("trade_fee")
        if fee is None:
            raise ExchangeError("거래 수수료 정보를 찾을 수 없습니다.")
        return float(fee)

    def place_limit_order(
        self,
        *,
        side: str,
        order_currency: str,
        units: Union[str, float],
        price: Union[str, float],
        payment_currency: str = "KRW",
    ) -> JsonMapping:
        order_type = "bid" if side.lower() == "buy" else "ask"
        payload: MutableJsonMapping = {
            "type": order_type,
            "order_currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
            "units": str(units),
            "price": str(price),
        }
        return self.post(BithumbEndpoint.TRADE_PLACE, data=payload, private=True)

    def place_market_order(
        self,
        *,
        side: str,
        order_currency: str,
        units: Union[str, float],
        payment_currency: str = "KRW",
    ) -> JsonMapping:
        order_type = "bid" if side.lower() == "buy" else "ask"
        payload: MutableJsonMapping = {
            "type": order_type,
            "order_currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
            "units": str(units),
            "price": "0",
        }
        payload["ordertype"] = "market"
        return self.post(BithumbEndpoint.TRADE_PLACE, data=payload, private=True)

    def cancel_order(
        self,
        *,
        order_id: str,
        side: str,
        order_currency: str,
        payment_currency: str = "KRW",
    ) -> JsonMapping:
        payload: MutableJsonMapping = {
            "order_id": order_id,
            "type": "bid" if side.lower() == "buy" else "ask",
            "order_currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
        }
        return self.post(BithumbEndpoint.TRADE_CANCEL, data=payload, private=True)

    def get_open_orders(
        self,
        *,
        order_currency: str,
        payment_currency: str = "KRW",
        count: int = 100,
        after: Optional[int] = None,
    ) -> JsonMapping:
        payload: MutableJsonMapping = {
            "order_currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
            "count": max(1, min(count, 100)),
        }
        if after is not None:
            payload["after"] = after
        return self.post(BithumbEndpoint.ORDERS, data=payload, private=True)

    def get_order_detail(
        self,
        *,
        order_id: str,
        order_currency: str,
        payment_currency: str = "KRW",
    ) -> JsonMapping:
        payload: MutableJsonMapping = {
            "order_id": order_id,
            "order_currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
        }
        return self.post(BithumbEndpoint.ORDER_DETAIL, data=payload, private=True)

    def get_user_transactions(
        self,
        *,
        order_currency: str,
        payment_currency: str = "KRW",
        offset: int = 0,
        count: int = 20,
    ) -> JsonMapping:
        payload: MutableJsonMapping = {
            "order_currency": order_currency.upper(),
            "payment_currency": payment_currency.upper(),
            "offset": max(0, offset),
            "count": max(1, min(count, 100)),
        }
        return self.post(BithumbEndpoint.USER_TRANSACTIONS, data=payload, private=True)


class BithumbWebSocketClient:
    """빗썸 WebSocket 연결을 관리하는 비동기 클라이언트."""

    def __init__(
        self,
        *,
        url: str = DEFAULT_WS_URL,
        reconnect: bool = True,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        recv_timeout: float = WS_DEFAULT_RECV_TIMEOUT,
        ping_interval: float = WS_DEFAULT_PING_INTERVAL,
        ping_timeout: float = WS_DEFAULT_PING_TIMEOUT,
    ) -> None:
        self._url = url
        self._reconnect = reconnect
        self._max_retries = max(0, max_retries)
        self._backoff_factor = max(0.0, backoff_factor)
        self._recv_timeout = recv_timeout
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._ws: Optional[WebSocketClientProtocol] = None
        self._subscriptions: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger(__name__)
        self._sleep = asyncio.sleep

    async def __aenter__(self) -> "BithumbWebSocketClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - 컨텍스트 관리자 편의 기능
        await self.disconnect()

    async def connect(self) -> None:
        if self._ws and not self._ws.closed:
            return
        self._ws = await websockets.connect(
            self._url,
            ping_interval=None,
            ping_timeout=None,
        )
        await self._handle_handshake()
        await self._resubscribe()

    async def disconnect(self) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    async def subscribe_ticker(
        self,
        symbols: Iterable[str],
        *,
        tick_types: Optional[Sequence[str]] = None,
    ) -> None:
        payload = {
            "type": "ticker",
            "symbols": [normalize_market_code(symbol, None) for symbol in symbols],
            "tickTypes": [tick.upper() for tick in (tick_types or ["24H"])],
        }
        await self._register_subscription(payload)

    async def subscribe_transactions(self, symbols: Iterable[str]) -> None:
        payload = {
            "type": "transaction",
            "symbols": [normalize_market_code(symbol, None) for symbol in symbols],
        }
        await self._register_subscription(payload)

    async def subscribe_orderbook(
        self,
        symbols: Iterable[str],
        *,
        tick_types: Optional[Sequence[str]] = None,
    ) -> None:
        payload = {
            "type": "orderbookdepth",
            "symbols": [normalize_market_code(symbol, None) for symbol in symbols],
        }
        if tick_types:
            payload["tickTypes"] = [tick.upper() for tick in tick_types]
        await self._register_subscription(payload)

    async def listen(self):
        attempt = 0
        while True:
            try:
                if not self._ws or self._ws.closed:
                    if attempt > self._max_retries and not self._reconnect:
                        raise WebSocketError("WebSocket 연결이 종료되었습니다.")
                    await self.connect()
                    attempt = 0

                assert self._ws is not None
                message = await asyncio.wait_for(self._ws.recv(), timeout=self._recv_timeout)
                text = message.decode("utf-8") if isinstance(message, bytes) else message
                if not text:
                    continue
                if text.lower() == "pong":
                    continue

                payload = json.loads(text)
                if isinstance(payload, Mapping) and payload.get("type") == "ping":
                    await self._send_json({"type": "pong"})
                    continue
                if isinstance(payload, Mapping) and payload.get("status") and not payload.get("type"):
                    # 연결 또는 필터 등록 응답이므로 무시
                    continue
                yield payload
                attempt = 0
            except (asyncio.TimeoutError, websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as exc:
                if not self._reconnect or attempt >= self._max_retries:
                    raise WebSocketError("WebSocket 수신 중 오류가 발생했습니다.") from exc
                await self._handle_reconnect(attempt)
                attempt += 1
            except json.JSONDecodeError as exc:
                self._logger.debug("디코딩할 수 없는 메시지를 무시합니다: %s", exc)
                continue

    async def _register_subscription(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            if payload not in self._subscriptions:
                self._subscriptions.append(payload)
            if self._ws and not self._ws.closed:
                await self._send_json(payload)

    async def _send_json(self, payload: dict[str, Any]) -> None:
        if not self._ws or self._ws.closed:
            return
        await self._ws.send(json.dumps(payload))

    async def _handle_handshake(self) -> None:
        if not self._ws:
            return
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=self._recv_timeout)
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not text:
                return
            data = json.loads(text)
            if isinstance(data, Mapping) and data.get("type") == "ping":
                await self._send_json({"type": "pong"})
        except (asyncio.TimeoutError, json.JSONDecodeError):  # pragma: no cover - 드물게 발생
            return

    async def _resubscribe(self) -> None:
        async with self._lock:
            for payload in self._subscriptions:
                await self._send_json(payload)

    async def _handle_reconnect(self, attempt: int) -> None:
        await self.disconnect()
        delay = self._backoff_factor * (2 ** attempt) if self._backoff_factor > 0 else 0
        if delay:
            await self._sleep(delay)

    async def send_ping(self) -> None:
        if self._ws and not self._ws.closed:
            await self._ws.ping()


__all__ = [
    "BithumbClient",
    "BithumbEndpoint",
    "BithumbWebSocketClient",
    "ClientCredentials",
    "DEFAULT_TIMEOUT",
    "DEFAULT_USER_AGENT",
    "DEFAULT_WS_URL",
    "HttpMethod",
    "normalize_market_code",
]
