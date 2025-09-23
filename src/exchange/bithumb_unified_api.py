#!/usr/bin/env python3
"""빗썸 통합 API 클라이언트 - API 2.0 JWT 방식."""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

import jwt
import requests


def load_dotenv(env_file_path: Path):
    """간단한 .env 파일 로더"""
    if env_file_path.exists():
        with open(env_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()


class BithumbUnifiedAPI:
    """빗썸 통합 API 클라이언트 - REST API 2.0 JWT 방식."""

    def __init__(self, api_key: str = None, secret_key: str = None, testnet: bool = False):
        """
        통합 API 클라이언트 초기화.

        Args:
            api_key: 빗썸 API 키 (없으면 환경변수에서 로드)
            secret_key: 빗썸 시크릿 키 (없으면 환경변수에서 로드)
            testnet: 테스트넷 사용 여부 (현재 미지원)
        """
        # 환경변수 로드
        if not api_key or not secret_key:
            env_file = Path(__file__).parent.parent.parent / '.env'
            load_dotenv(env_file)

        self.api_key = api_key or os.getenv('BITHUMB_API_KEY')
        self.secret_key = secret_key or os.getenv('BITHUMB_SECRET_KEY')
        self.testnet = testnet

        # API 기본 설정
        self.base_url = "https://api.bithumb.com"
        self.timeout = 30

        # 세션 설정
        self.session = requests.Session()

        # 요청 제한 관리
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 최소 요청 간격 (초)

        # 캐시 설정
        self._ticker_cache = {}
        self._ticker_cache_time = {}
        self._balance_cache = None
        self._balance_cache_time = None

        if not self.api_key or not self.secret_key:
            print("⚠️  빗썸 API 키가 설정되지 않았습니다. Public API만 사용 가능합니다.")

    def _wait_for_rate_limit(self):
        """API 요청 제한을 위한 대기."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            wait_time = self.min_request_interval - time_since_last
            time.sleep(wait_time)

        self.last_request_time = time.time()

    def _get_jwt_token(self, params: Dict = None) -> str:
        """빗썸 API 2.0 JWT 토큰 생성."""
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }

        # 파라미터가 있는 경우 query_hash 추가
        if params:
            query_string = urllib.parse.urlencode(sorted(params.items()))
            query_hash = hashlib.sha512(query_string.encode('utf-8')).hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        # JWT 토큰 생성 (HS256 알고리즘)
        jwt_token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return jwt_token

    def _make_public_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """공개 API 요청."""
        try:
            self._wait_for_rate_limit()

            url = f"{self.base_url}{endpoint}"
            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Public API 오류: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"❌ Public API 요청 실패: {e}")
            return None

    def _make_private_request(self, endpoint: str, params: Dict = None, method: str = "GET") -> Optional[Dict]:
        """인증이 필요한 Private API 요청."""
        try:
            if not self.api_key or not self.secret_key:
                raise ValueError("Private API 사용을 위해서는 API 키가 필요합니다.")

            self._wait_for_rate_limit()

            # JWT 토큰 생성
            jwt_token = self._get_jwt_token(params)

            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/json"
            }

            url = f"{self.base_url}{endpoint}"

            if method.upper() == "GET":
                response = self.session.get(url, headers=headers, timeout=self.timeout)
            else:
                headers["Content-Type"] = "application/json"
                response = self.session.post(url, json=params, headers=headers, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ Private API 오류: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"❌ Private API 요청 실패: {e}")
            return None

    # =========================
    # Public API 메서드들
    # =========================

    def get_ticker(self, symbol: str = "ALL") -> Optional[Dict]:
        """현재가 정보 조회 (Public API)."""
        try:
            endpoint = f"/public/ticker/{symbol}"
            response = self._make_public_request(endpoint)

            if response and response.get('status') == '0000':
                return response.get('data')
            return None

        except Exception as e:
            print(f"❌ Ticker 조회 실패: {e}")
            return None

    def get_orderbook(self, symbol: str, count: int = 20) -> Optional[Dict]:
        """호가 정보 조회 (Public API)."""
        try:
            endpoint = f"/public/orderbook/{symbol}"
            params = {"count": count}
            response = self._make_public_request(endpoint, params)

            if response and response.get('status') == '0000':
                return response.get('data')
            return None

        except Exception as e:
            print(f"❌ Orderbook 조회 실패: {e}")
            return None

    def get_recent_transactions(self, symbol: str, count: int = 20) -> Optional[List[Dict]]:
        """최근 체결 내역 조회 (Public API)."""
        try:
            endpoint = f"/public/transaction_history/{symbol}"
            params = {"count": count}
            response = self._make_public_request(endpoint, params)

            if response and response.get('status') == '0000':
                return response.get('data')
            return None

        except Exception as e:
            print(f"❌ Transaction 조회 실패: {e}")
            return None

    # =========================
    # Private API 메서드들
    # =========================

    def get_accounts(self) -> Optional[List[Dict]]:
        """전체 계좌 조회 (Private API) - 빗썸 API 2.0."""
        try:
            endpoint = "/v1/accounts"
            return self._make_private_request(endpoint, method="GET")

        except Exception as e:
            print(f"❌ 계좌 조회 실패: {e}")
            return None

    def get_balance(self, symbol: str = "ALL") -> Optional[Dict]:
        """잔고 조회 (계좌 정보를 파싱해서 반환)."""
        try:
            accounts = self.get_accounts()
            if not accounts:
                return None

            balance_info = {}
            total_krw_value = 0

            for account in accounts:
                currency = account.get('currency', '')
                balance = float(account.get('balance', 0))
                locked = float(account.get('locked', 0))

                if currency == 'KRW':
                    balance_info['krw_balance'] = balance
                    balance_info['krw_locked'] = locked
                    balance_info['total_krw'] = balance + locked
                    total_krw_value += balance + locked
                else:
                    # 다른 코인들
                    if balance > 0 or locked > 0:
                        balance_info[f'{currency.lower()}_balance'] = balance
                        balance_info[f'{currency.lower()}_locked'] = locked

                        # KRW로 환산하려면 시세 필요
                        ticker = self.get_ticker(currency)
                        if ticker:
                            price = float(ticker.get('closing_price', 0))
                            coin_value = (balance + locked) * price
                            total_krw_value += coin_value
                            balance_info[f'{currency.lower()}_value_krw'] = coin_value

            balance_info['total_balance_krw'] = total_krw_value

            if symbol == "ALL":
                return balance_info
            else:
                # 특정 심볼만 반환
                key = f'{symbol.lower()}_balance'
                return {
                    'balance': balance_info.get(key, 0),
                    'locked': balance_info.get(f'{symbol.lower()}_locked', 0)
                }

        except Exception as e:
            print(f"❌ 잔고 조회 실패: {e}")
            return None

    def place_order(self, symbol: str, side: str, order_type: str, quantity: Decimal,
                   price: Optional[Decimal] = None) -> Optional[Dict]:
        """주문 생성 (Private API)."""
        try:
            if side not in ['buy', 'sell']:
                raise ValueError("side는 'buy' 또는 'sell'이어야 합니다.")

            if order_type not in ['market', 'limit']:
                raise ValueError("order_type은 'market' 또는 'limit'이어야 합니다.")

            if order_type == 'limit' and price is None:
                raise ValueError("지정가 주문에는 가격이 필요합니다.")

            # 빗썸 API 2.0 주문 엔드포인트 (실제 문서 확인 필요)
            endpoint = "/v1/orders"

            # 매수/매도 타입 변환
            side_type = 'bid' if side == 'buy' else 'ask'

            params = {
                "market": f"{symbol}_KRW",
                "side": side_type,
                "volume": str(quantity),
                "ord_type": order_type
            }

            if order_type == 'limit' and price:
                params["price"] = str(price)

            return self._make_private_request(endpoint, params, method="POST")

        except Exception as e:
            print(f"❌ 주문 실행 실패: {e}")
            return None

    def cancel_order(self, order_id: str, symbol: str) -> Optional[Dict]:
        """주문 취소 (Private API)."""
        try:
            endpoint = f"/v1/order"
            params = {
                "uuid": order_id
            }

            return self._make_private_request(endpoint, params, method="DELETE")

        except Exception as e:
            print(f"❌ 주문 취소 실패: {e}")
            return None

    def get_orders(self, symbol: str = None, state: str = "wait") -> Optional[List[Dict]]:
        """주문 내역 조회 (Private API)."""
        try:
            endpoint = "/v1/orders"
            params = {"state": state}

            if symbol:
                params["market"] = f"{symbol}_KRW"

            return self._make_private_request(endpoint, params, method="GET")

        except Exception as e:
            print(f"❌ 주문 내역 조회 실패: {e}")
            return None

    # =========================
    # 캐시된 메서드들
    # =========================

    async def get_cached_ticker(self, symbol: str, cache_seconds: int = 30) -> Dict:
        """캐시된 시세 정보 반환."""
        now = datetime.now()

        if (symbol not in self._ticker_cache or
            symbol not in self._ticker_cache_time or
            now - self._ticker_cache_time[symbol] > timedelta(seconds=cache_seconds)):

            ticker_data = self.get_ticker(symbol)
            if ticker_data:
                self._ticker_cache[symbol] = ticker_data
                self._ticker_cache_time[symbol] = now
            else:
                # 실패 시 기본값
                self._ticker_cache[symbol] = {
                    'closing_price': '0',
                    'opening_price': '0',
                    'max_price': '0',
                    'min_price': '0'
                }
                self._ticker_cache_time[symbol] = now

        return self._ticker_cache[symbol]

    async def get_cached_balance(self, cache_minutes: int = 5) -> Dict:
        """캐시된 잔고 정보 반환."""
        now = datetime.now()

        if (self._balance_cache is None or
            self._balance_cache_time is None or
            now - self._balance_cache_time > timedelta(minutes=cache_minutes)):

            balance_data = self.get_balance("ALL")
            if balance_data:
                self._balance_cache = balance_data
                self._balance_cache_time = now
            else:
                self._balance_cache = {
                    'total_krw': 0,
                    'total_balance_krw': 0,
                    'error': 'Balance query failed'
                }
                self._balance_cache_time = now

        return self._balance_cache

    # =========================
    # 유틸리티 메서드들
    # =========================

    def get_connection_status(self) -> Dict[str, Any]:
        """연결 상태 확인."""
        try:
            # Public API 테스트
            btc_ticker = self.get_ticker("BTC")
            public_ok = btc_ticker is not None

            # Private API 테스트 (키가 있는 경우)
            private_ok = False
            if self.api_key and self.secret_key:
                accounts = self.get_accounts()
                private_ok = accounts is not None

            return {
                "public_api": "connected" if public_ok else "failed",
                "private_api": "connected" if private_ok else "not_configured" if not self.api_key else "failed",
                "api_key_configured": bool(self.api_key),
                "btc_price": float(btc_ticker.get('closing_price', 0)) if btc_ticker else 0
            }

        except Exception as e:
            return {
                "public_api": "error",
                "private_api": "error",
                "error": str(e)
            }

    def close(self):
        """리소스 정리."""
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 기존 클라이언트와의 호환성을 위한 별칭들
BithumbAPI = BithumbUnifiedAPI
BithumbClient = BithumbUnifiedAPI


# 사용 예시
async def example_usage():
    """사용 예시."""
    # API 키 없이 Public API만 사용
    client = BithumbUnifiedAPI()

    # 연결 상태 확인
    status = client.get_connection_status()
    print(f"연결 상태: {status}")

    # 시세 조회
    btc_ticker = client.get_ticker("BTC")
    print(f"BTC 시세: {btc_ticker}")

    # API 키가 있는 경우 Private API 사용
    if client.api_key:
        balance = client.get_balance("ALL")
        print(f"잔고: {balance}")

    client.close()


if __name__ == "__main__":
    asyncio.run(example_usage())