"""Bithumb API Response Structure Debug Script."""

import json
import sys
from src.config import get_settings
from src.exchange.bithumb_client import BithumbClient

# Windows console encoding fix
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def debug_api_response():
    """Analyze API response structure in detail."""
    settings = get_settings()

    if not settings.bithumb.api_key or not settings.bithumb.api_secret:
        print("API keys not configured.")
        return

    client = BithumbClient(
        api_key=settings.bithumb.api_key.get_secret_value(),
        api_secret=settings.bithumb.api_secret.get_secret_value()
    )

    print("=== API 2.0 Account Response Structure Analysis ===\n")

    try:
        accounts = client.get_accounts()
        print("Raw Response:")
        print(json.dumps(accounts, indent=2, ensure_ascii=False))

        print(f"\nResponse Type: {type(accounts)}")
        if isinstance(accounts, dict):
            print(f"Top-level Keys: {list(accounts.keys())}")

            if 'data' in accounts:
                data = accounts['data']
                print(f"Data Type: {type(data)}")
                print(f"Data Content: {data}")

            if 'status' in accounts:
                print(f"Status: {accounts['status']}")

            if 'message' in accounts:
                print(f"Message: {accounts['message']}")

    except Exception as e:
        print(f"Error: {e}")
        print("\n=== JWT Token Debugging ===")

        # JWT token generation process check
        import uuid
        import time
        import jwt

        jwt_payload = {
            'access_key': settings.bithumb.api_key.get_secret_value(),
            'nonce': str(uuid.uuid4()),
            'timestamp': round(time.time() * 1000)
        }

        print(f"JWT Payload: {jwt_payload}")

        try:
            jwt_token = jwt.encode(jwt_payload, settings.bithumb.api_secret.get_secret_value(), algorithm='HS256')
            print(f"JWT Token (first 50 chars): {jwt_token[:50]}...")
            print(f"Authorization Header: Bearer {jwt_token[:50]}...")
        except Exception as jwt_error:
            print(f"JWT Error: {jwt_error}")

if __name__ == "__main__":
    debug_api_response()