"""빗썸 REST API 전용 클라이언트."""

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..utils.exceptions import ExchangeError, APIRateLimitError
from ..utils.logger import get_logger

logger = get_logger(__name__)


class BithumbRestClient:
    """빗썸 REST API 전용 클라이언트."""

    def __init__(self, api_key: str = "", secret_key: str = "", testnet: bool = False):
        """
        REST 클라이언트 초기화.

        Args:
            api_key: API 키
            secret_key: 시크릿 키
            testnet: 테스트넷 사용 여부
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.testnet = testnet

        # API 기본 설정
        self.base_url = "https://api.bithumb.com" if not testnet else "https://api.bithumb.com"
        self.timeout = 30
        self.logger = logger

        # 세션 설정 (연결 풀링 및 재시도)
        self.session = requests.Session()

        # 재시도 전략 설정
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # 요청 제한 관리
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 최소 요청 간격 (초)

    def _wait_for_rate_limit(self):
        """API 요청 제한을 위한 대기."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last
            time.sleep(wait_time)

        self.last_request_time = time.time()

    def _generate_signature(self, endpoint: str, params: Dict[str, Any]) -> tuple[str, str]:
        """
        API 요청 서명 생성.

        Args:
            endpoint: API 엔드포인트
            params: 요청 파라미터

        Returns:
            (signature, nonce) 튜플
        """
        # nonce 추가
        params['endpoint'] = endpoint
        nonce = str(int(time.time() * 1000))
        params['nonce'] = nonce

        # 파라미터 정렬 및 인코딩
        query_string = urlencode(sorted(params.items()))

        # HMAC-SHA512 서명 생성
        signature_bytes = hmac.new(
            self.secret_key.encode(),
            query_string.encode(),
            hashlib.sha512
        ).digest()

        # Base64 인코딩
        signature = base64.b64encode(signature_bytes).decode()

        return signature, nonce

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        require_auth: bool = False
    ) -> Dict[str, Any]:
        """
        API 요청 실행.

        Args:
            method: HTTP 메서드
            endpoint: API 엔드포인트
            params: 요청 파라미터
            require_auth: 인증 필요 여부

        Returns:
            API 응답 데이터

        Raises:
            ExchangeError: API 오류 시
            APIRateLimitError: 요청 제한 초과 시
        """
        if params is None:
            params = {}

        # 요청 제한 대기
        self._wait_for_rate_limit()

        url = f"{self.base_url}{endpoint}"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }

        # 인증이 필요한 경우 서명 추가
        if require_auth:
            if not self.api_key or not self.secret_key:
                raise ExchangeError("API 키와 시크릿 키가 필요합니다.")

            signature, nonce = self._generate_signature(endpoint, params.copy())
            headers['Api-Key'] = self.api_key
            headers['Api-Sign'] = signature
            headers['Api-Nonce'] = nonce

        try:
            if method.upper() == 'GET':
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
            else:
                response = self.session.post(
                    url,
                    data=params,
                    headers=headers,
                    timeout=self.timeout
                )

            # 응답 상태 확인
            if response.status_code == 429:
                raise APIRateLimitError("API 요청 제한 초과")

            response.raise_for_status()

            # JSON 응답 파싱
            data = response.json()

            # 빗썸 API 오류 확인
            status = data.get('status')
            if status != '0000':
                error_message = data.get('message', '알 수 없는 오류')
                raise ExchangeError(f"빗썸 API 오류 ({status}): {error_message}")

            return data

        except requests.exceptions.Timeout:
            raise ExchangeError("API 요청 시간 초과")
        except requests.exceptions.ConnectionError:
            raise ExchangeError("API 서버 연결 실패")
        except requests.exceptions.HTTPError as e:
            raise ExchangeError(f"HTTP 오류: {e}")
        except json.JSONDecodeError:
            raise ExchangeError("API 응답 파싱 실패")
        except Exception as e:
            self.logger.error(f"API 요청 실패: {e}")
            raise ExchangeError(f"API 요청 중 오류 발생: {e}")

    # Public API 메서드들
    async def get_ticker(self, symbol: str = "ALL") -> Optional[Dict[str, Any]]:
        """현재가 정보 조회."""
        try:
            endpoint = "/public/ticker"
            params = {"order_currency": symbol} if symbol != "ALL" else {}

            response = self._make_request("GET", endpoint, params)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"Ticker 조회 실패 ({symbol}): {e}")
            return None

    async def get_orderbook(self, symbol: str, count: int = 20) -> Optional[Dict[str, Any]]:
        """호가 정보 조회."""
        try:
            endpoint = "/public/orderbook"
            params = {
                "order_currency": symbol,
                "count": count
            }

            response = self._make_request("GET", endpoint, params)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"Orderbook 조회 실패 ({symbol}): {e}")
            return None

    async def get_recent_transactions(self, symbol: str, count: int = 20) -> Optional[List[Dict[str, Any]]]:
        """최근 체결 내역 조회."""
        try:
            endpoint = "/public/transaction_history"
            params = {
                "order_currency": symbol,
                "count": count
            }

            response = self._make_request("GET", endpoint, params)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"체결 내역 조회 실패 ({symbol}): {e}")
            return None

    async def get_assets_status(self, symbol: str = "ALL") -> Optional[Dict[str, Any]]:
        """입출금 현황 조회."""
        try:
            endpoint = "/public/assetsstatus"
            params = {"order_currency": symbol} if symbol != "ALL" else {}

            response = self._make_request("GET", endpoint, params)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"자산 현황 조회 실패 ({symbol}): {e}")
            return None

    # Private API 메서드들
    async def get_balance(self, symbol: str = "ALL") -> Optional[Dict[str, Any]]:
        """잔고 조회."""
        try:
            endpoint = "/info/balance"
            params = {"order_currency": symbol, "payment_currency": "KRW"}

            response = self._make_request("POST", endpoint, params, require_auth=True)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"잔고 조회 실패 ({symbol}): {e}")
            return None

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> Optional[Dict[str, Any]]:
        """주문 생성."""
        try:
            if side not in ['buy', 'sell']:
                raise ValueError("side는 'buy' 또는 'sell'이어야 합니다.")

            if order_type not in ['market', 'limit']:
                raise ValueError("order_type은 'market' 또는 'limit'이어야 합니다.")

            if order_type == 'limit' and price is None:
                raise ValueError("지정가 주문에는 가격이 필요합니다.")

            endpoint = "/trade/place"
            # 'buy' -> 'bid', 'sell' -> 'ask' 변환
            trade_type = 'bid' if side == 'buy' else 'ask'

            params = {
                "order_currency": symbol,
                "payment_currency": "KRW",
                "units": str(quantity),
                "type": trade_type
            }

            if order_type == 'limit' and price:
                params["price"] = str(price)
            else:
                # 시장가 주문
                params["ordertype"] = "market"

            response = self._make_request("POST", endpoint, params, require_auth=True)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"주문 실패 ({symbol} {side} {quantity}): {e}")
            return None

    async def cancel_order(self, order_id: str, symbol: str, side: str) -> Optional[Dict[str, Any]]:
        """주문 취소."""
        try:
            endpoint = "/trade/cancel"
            params = {
                "order_id": order_id,
                "order_currency": symbol,
                "payment_currency": "KRW",
                "type": side
            }

            response = self._make_request("POST", endpoint, params, require_auth=True)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"주문 취소 실패 ({order_id}): {e}")
            return None

    async def get_orders(self, symbol: str, order_id: str = None) -> Optional[Dict[str, Any]]:
        """주문 조회."""
        try:
            endpoint = "/info/orders"
            params = {
                "order_currency": symbol,
                "payment_currency": "KRW"
            }

            if order_id:
                params["order_id"] = order_id

            response = self._make_request("POST", endpoint, params, require_auth=True)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"주문 조회 실패 ({symbol}): {e}")
            return None

    async def get_order_detail(self, order_id: str, symbol: str) -> Optional[Dict[str, Any]]:
        """주문 상세 조회."""
        try:
            endpoint = "/info/order_detail"
            params = {
                "order_id": order_id,
                "order_currency": symbol,
                "payment_currency": "KRW"
            }

            response = self._make_request("POST", endpoint, params, require_auth=True)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"주문 상세 조회 실패 ({order_id}): {e}")
            return None

    async def get_user_transactions(
        self,
        symbol: str,
        search_gb: int = 0,
        offset: int = 0,
        count: int = 20
    ) -> Optional[List[Dict[str, Any]]]:
        """거래 내역 조회."""
        try:
            endpoint = "/info/user_transactions"
            params = {
                "order_currency": symbol,
                "payment_currency": "KRW",
                "searchGb": search_gb,
                "offset": offset,
                "count": count
            }

            response = self._make_request("POST", endpoint, params, require_auth=True)
            return response.get('data')

        except Exception as e:
            self.logger.error(f"거래 내역 조회 실패 ({symbol}): {e}")
            return None

    def close(self):
        """클라이언트 종료."""
        if self.session:
            self.session.close()
            self.logger.info("REST 클라이언트 세션 종료")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()