#!/usr/bin/env python3
"""자동매매 엔진 디버그 버전."""

import asyncio
import time
import uuid
from datetime import datetime
import jwt
import requests

# API 키
BITHUMB_API_KEY = "6796b5622069481022701ac81477f57e947f0552b6bc64"
BITHUMB_SECRET_KEY = "YzIwZDQzZDE2ZWQ2NzVlNmI3NjUyNTZmNGQxMDUxMDAxY2NhMTk3Y2YxN2I5MTdhMDY1N2IxYmY2MWM4NQ=="

class BithumbAPI:
    def __init__(self):
        self.api_key = BITHUMB_API_KEY
        self.secret_key = BITHUMB_SECRET_KEY
        self.base_url = "https://api.bithumb.com"

    def _get_jwt_token(self, params=None):
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }

        if params:
            import urllib.parse
            import hashlib
            query_string = urllib.parse.urlencode(sorted(params.items()))
            query_hash = hashlib.sha512(query_string.encode('utf-8')).hexdigest()
            payload['query_hash'] = query_hash
            payload['query_hash_alg'] = 'SHA512'

        jwt_token = jwt.encode(payload, self.secret_key, algorithm='HS256')
        return jwt_token

    def get_ticker(self, symbol):
        print(f"📊 {symbol} 시세 조회 중...")
        try:
            url = f"{self.base_url}/public/ticker/{symbol}"
            response = requests.get(url, timeout=5)
            data = response.json()
            print(f"✅ {symbol} 시세 조회 완료: {data.get('data', {}).get('closing_price', 'N/A')}원")
            return data
        except Exception as e:
            print(f"❌ {symbol} 시세 조회 실패: {e}")
            return None

    def get_accounts(self):
        print("💰 계좌 정보 조회 중...")
        try:
            endpoint = "/v1/accounts"
            jwt_token = self._get_jwt_token()

            headers = {
                "Authorization": f"Bearer {jwt_token}",
                "Accept": "application/json"
            }

            url = f"{self.base_url}{endpoint}"
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                print(f"✅ 계좌 조회 완료: {len(data)} 개 항목")
                return data
            else:
                print(f"❌ 계좌 조회 실패: HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ 계좌 조회 오류: {e}")
            return None

async def debug_test():
    print("🔍 자동매매 엔진 디버그 테스트 시작!")

    api = BithumbAPI()

    # 1. 시세 조회 테스트
    print("\n1️⃣ 시세 조회 테스트")
    for symbol in ["BTC", "ETH", "XRP"]:
        ticker = api.get_ticker(symbol)
        await asyncio.sleep(1)

    # 2. 계좌 조회 테스트
    print("\n2️⃣ 계좌 조회 테스트")
    accounts = api.get_accounts()

    # 3. 간단한 매매 사이클 시뮬레이션
    print("\n3️⃣ 매매 사이클 시뮬레이션")
    for i in range(3):
        print(f"🔄 사이클 {i+1}/3 - {datetime.now().strftime('%H:%M:%S')}")

        # BTC 시세 조회
        btc_ticker = api.get_ticker("BTC")
        if btc_ticker and btc_ticker.get('status') == '0000':
            price = float(btc_ticker['data']['closing_price'])
            print(f"📈 BTC 현재가: {price:,.0f}원")

            # 가상 신호 생성
            rsi = 30 + (i * 20)  # 30, 50, 70
            signal = "매수" if rsi < 40 else "매도" if rsi > 60 else "대기"
            print(f"🔔 매매 신호: {signal} (RSI: {rsi})")

        print(f"😴 30초 대기...")
        await asyncio.sleep(30)

    print("✅ 디버그 테스트 완료!")

if __name__ == "__main__":
    print("🚨 빗썸 자동매매 디버그 테스트!")
    asyncio.run(debug_test())