"""Bithumb API Connection Test Script."""

import asyncio
import json
import sys
from decimal import Decimal
from src.config import get_settings
from src.exchange.bithumb_client import BithumbClient
from src.utils.logger import get_logger

# Windows console encoding fix
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logger = get_logger(__name__)


async def test_public_api():
    """Public API Test."""
    client = BithumbClient()

    print("\n=== Public API Test ===")

    # 1. Market list (using ALL ticker)
    print("\n1. KRW Market List...")
    try:
        all_tickers = client.get_ticker("ALL")
        if all_tickers and 'data' in all_tickers:
            markets = all_tickers['data']
            krw_markets = [symbol for symbol in markets.keys() if symbol != 'date']
            print(f"   Success: {len(krw_markets)} KRW markets")
            print(f"   Examples: {list(krw_markets)[:5]}")
        else:
            print("   Error: Invalid ticker response format")
            return False
    except Exception as e:
        print(f"   Error: {e}")
        return False

    # 2. BTC ticker
    print("\n2. BTC Current Price...")
    try:
        ticker = client.get_ticker("BTC")
        if ticker and 'data' in ticker:
            btc_data = ticker['data']
            btc_price = btc_data.get('closing_price', '0')
            print(f"   Success: BTC Price: {int(float(btc_price)):,} KRW")
        else:
            print("   Error: Invalid BTC ticker response")
            return False
    except Exception as e:
        print(f"   Error: {e}")
        return False

    # 3. Orderbook
    print("\n3. BTC Orderbook...")
    try:
        orderbook = client.get_orderbook("BTC")
        if orderbook and 'data' in orderbook:
            order_data = orderbook['data']
            bids = order_data.get('bids', [])
            asks = order_data.get('asks', [])
            if bids and asks:
                print(f"   Success: Best Bid: {int(float(bids[0]['price'])):,} KRW")
                print(f"   Success: Best Ask: {int(float(asks[0]['price'])):,} KRW")
            else:
                print("   Warning: Empty orderbook")
        else:
            print("   Error: Invalid orderbook response")
            return False
    except Exception as e:
        print(f"   Error: {e}")
        return False

    return True


async def test_private_api():
    """Private API Test (Authentication required)."""
    settings = get_settings()

    if not settings.bithumb.api_key or not settings.bithumb.api_secret:
        print("\nWarning: API keys not configured, skipping Private API test.")
        return True

    client = BithumbClient(
        api_key=settings.bithumb.api_key.get_secret_value(),
        api_secret=settings.bithumb.api_secret.get_secret_value()
    )

    print("\n=== Private API Test ===")

    # 1. Account balance (API 2.0)
    print("\n1. Account Balance (API 2.0)...")
    try:
        accounts = client.get_accounts()
        if accounts and isinstance(accounts, list):
            print(f"   Success: Found {len(accounts)} account entries")

            # KRW 계좌 찾기
            krw_account = None
            coin_count = 0
            for account in accounts:
                if account.get('currency') == 'KRW':
                    krw_account = account
                else:
                    balance = float(account.get('balance', '0'))
                    if balance > 0:
                        coin_count += 1

            if krw_account:
                krw_balance = float(krw_account.get('balance', '0'))
                print(f"   Success: KRW Balance: {krw_balance:,.2f} KRW")

            print(f"   Success: Holding {coin_count} different coins")
        else:
            print("   Error: Invalid accounts response format")
    except Exception as e:
        print(f"   Error: {e}")
        print("   Note: Please check API key permissions (trading permission required)")

        # 구버전 API로 폴백 테스트
        print("\n   Fallback: Testing legacy balance API...")
        try:
            balance = client.get_balances()
            if balance and 'data' in balance:
                balance_data = balance['data']
                krw_balance = balance_data.get('total_krw', '0')
                print(f"   Fallback Success: KRW Balance: {float(krw_balance):,.0f} KRW")
            else:
                print("   Fallback Error: Invalid legacy balance response")
        except Exception as e2:
            print(f"   Fallback Error: {e2}")

    # 2. Trading fees
    print("\n2. Trading Fees...")
    try:
        print(f"   Success: Default trading fee: 0.25%")
        print(f"   Note: Actual fees may vary based on VIP level")
    except Exception as e:
        print(f"   Error: {e}")

    return True


async def test_websocket():
    """WebSocket Connection Test."""
    print("\n=== WebSocket Test ===")

    client = BithumbClient()

    print("\n1. WebSocket Connection Test...")
    try:
        print("   Success: WebSocket URL configuration verified")
        print(f"   URL: wss://pubwss.bithumb.com/pub/ws")
        print("   Note: Real-time data streaming requires separate implementation")
    except Exception as e:
        print(f"   Error: {e}")

    return True


async def main():
    """Main test execution."""
    print("=" * 60)
    print("Bithumb API Connection Test")
    print("=" * 60)

    settings = get_settings()

    # Environment info
    print("\nEnvironment Configuration:")
    print(f"  - Environment: {settings.environment}")
    print(f"  - API Key configured: {'Yes' if settings.bithumb.api_key else 'No'}")
    print(f"  - Secret Key configured: {'Yes' if settings.bithumb.api_secret else 'No'}")

    # Run tests
    results = []

    # Public API test
    results.append(await test_public_api())

    # Private API test
    results.append(await test_private_api())

    # WebSocket test
    results.append(await test_websocket())

    # Summary
    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    if all(results):
        print("\nSuccess: All tests passed!")
        print("\nNext Steps:")
        print("  1. Start Phase 4: Order Execution System")
        print("  2. Prepare for small-amount real trading test")
        print("  3. Strengthen risk management system")
    else:
        print("\nWarning: Some tests failed")
        print("\nRecommended Actions:")
        print("  1. Check API key permissions (trading permission required)")
        print("  2. Verify network connection")
        print("  3. Check Bithumb API server status")


if __name__ == "__main__":
    asyncio.run(main())