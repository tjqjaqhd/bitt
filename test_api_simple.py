#!/usr/bin/env python3
"""빗썸 API 연결 테스트 (간단 버전)."""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# 환경변수 로드
def load_env():
    env_file = ROOT_DIR / ".env"
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key not in os.environ:
                        os.environ[key] = value

load_env()

# 빗썸 API 키 확인
api_key = os.getenv("BITHUMB_API_KEY")
secret_key = os.getenv("BITHUMB_SECRET_KEY")

print("🔧 빗썸 API 연결 테스트 시작...")
print(f"📁 프로젝트 루트: {ROOT_DIR}")
print(f"🔑 API 키 존재 여부: {'✅' if api_key else '❌'}")
print(f"🔐 Secret 키 존재 여부: {'✅' if secret_key else '❌'}")

if not api_key or not secret_key:
    print("❌ API 키나 Secret 키가 설정되지 않았습니다.")
    print("💡 .env 파일에 BITHUMB_API_KEY와 BITHUMB_SECRET_KEY를 설정해주세요.")
    sys.exit(1)

# 간단한 API 요청 테스트
try:
    import requests
    import jwt
    import json
    import time

    print("\n📡 공개 API 테스트 중...")

    # 1. 공개 API - 현재가 정보
    url = "https://api.bithumb.com/public/ticker/BTC_KRW"
    response = requests.get(url, timeout=10)

    if response.status_code == 200:
        data = response.json()
        if data.get("status") == "0000":
            price = data["data"]["closing_price"]
            print(f"✅ BTC 현재가: {price}원")
        else:
            print(f"❌ API 응답 오류: {data}")
    else:
        print(f"❌ HTTP 오류: {response.status_code}")

    # 2. 계좌 정보 조회 (JWT 인증)
    print("\n🔒 인증 API 테스트 중...")

    # JWT 토큰 생성 (빗썸 API 2.0 방식)
    import uuid
    import hashlib
    from urllib.parse import urlencode

    endpoint = "/v1/accounts"

    # JWT payload 구성
    jwt_payload = {
        'access_key': api_key,
        'nonce': str(uuid.uuid4()),
        'timestamp': round(time.time() * 1000)
    }

    token = jwt.encode(jwt_payload, secret_key, algorithm="HS256")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    url = f"https://api.bithumb.com{endpoint}"
    response = requests.get(url, headers=headers, timeout=10)

    print(f"📊 응답 코드: {response.status_code}")
    print(f"📋 응답 헤더: {dict(response.headers)}")

    if response.status_code == 200:
        try:
            data = response.json()
            print(f"📄 응답 데이터 타입: {type(data)}")
            print(f"📝 응답 내용 (처음 500자): {str(data)[:500]}")

            # 계좌 정보 파싱
            if isinstance(data, list) and len(data) > 0:
                print(f"\n💰 계좌 정보 ({len(data)}개 자산):")
                for account in data:
                    if isinstance(account, dict):
                        currency = account.get("currency", "Unknown")
                        balance = account.get("balance", "0")
                        available = account.get("available", "0")
                        print(f"  - {currency}: 잔고 {balance}, 사용가능 {available}")
            else:
                print("❌ 예상과 다른 응답 형식입니다.")

        except json.JSONDecodeError:
            print(f"❌ JSON 파싱 실패: {response.text[:200]}")
    else:
        print(f"❌ 인증 API 오류: {response.status_code}")
        print(f"📝 응답 내용: {response.text[:200]}")

except ImportError as e:
    print(f"❌ 모듈 임포트 오류: {e}")
except Exception as e:
    print(f"❌ 테스트 실행 오류: {e}")

print("\n✅ API 연결 테스트 완료!")