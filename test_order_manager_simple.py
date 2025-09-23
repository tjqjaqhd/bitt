#!/usr/bin/env python3
"""주문 매니저 간단 테스트."""

import sys
import time
import logging
from pathlib import Path
from decimal import Decimal

# 프로젝트 루트를 sys.path에 추가
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_order_types():
    """주문 타입 간단 테스트."""
    print("🔧 주문 타입 테스트...")

    try:
        from src.core.order_types import OrderRequest, OrderType, OrderSide, OrderPriority

        print("✅ 주문 타입 모듈 임포트 성공")

        # 시장가 매수 주문
        market_buy = OrderRequest(
            symbol="BTC_KRW",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal('0.001')
        )
        print(f"✅ 시장가 매수 주문 생성: {market_buy.symbol} {market_buy.quantity}")

        # 지정가 매도 주문
        limit_sell = OrderRequest(
            symbol="ETH_KRW",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal('0.1'),
            price=Decimal('4500000')
        )
        print(f"✅ 지정가 매도 주문 생성: {limit_sell.symbol} {limit_sell.quantity} @ {limit_sell.price}")

        # 잘못된 주문 (지정가 주문에 가격 없음)
        try:
            invalid_order = OrderRequest(
                symbol="BTC_KRW",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=Decimal('0.001')
                # price 누락
            )
            print("❌ 잘못된 주문이 생성되었습니다 (예상하지 못한 결과)")
        except ValueError as e:
            print(f"✅ 잘못된 주문 검증 성공: {e}")

    except Exception as e:
        print(f"❌ 주문 타입 테스트 오류: {e}")
        import traceback
        traceback.print_exc()

def test_order_manager():
    """주문 매니저 간단 테스트."""
    print("\n🚀 주문 매니저 테스트 시작...")

    try:
        # 간단한 Mock 클라이언트 생성
        class MockBithumbClient:
            def get_accounts(self):
                return [
                    {'currency': 'KRW', 'balance': '147059.085549'},
                    {'currency': 'BTC', 'balance': '0.00016106'},
                    {'currency': 'SOL', 'balance': '0.00016106'}
                ]

            def get_ticker(self, symbol):
                # 모의 시세 데이터
                prices = {
                    'BTC_KRW': {'closing_price': '159375000'},
                    'SOL_KRW': {'closing_price': '900000'}
                }
                return prices.get(symbol)

            def cancel_order(self, order_id):
                return True

        # 주문 매니저 모듈 임포트
        from src.core.order_types import OrderRequest, OrderType, OrderSide, OrderPriority
        from src.core.order_manager import OrderManager

        print("✅ 주문 매니저 모듈 임포트 성공")

        # 모의 클라이언트로 주문 매니저 생성
        mock_client = MockBithumbClient()
        order_manager = OrderManager(mock_client, max_concurrent_orders=3)

        print("✅ 주문 매니저 생성 완료")

        # 콜백 함수 설정
        def on_order_update(order):
            print(f"📝 주문 업데이트: {order.client_order_id} - {order.status.value}")

        def on_position_update(position):
            print(f"📊 포지션 업데이트: {position.symbol} - {position.quantity} @ {position.market_price}")

        order_manager.add_order_update_callback(on_order_update)
        order_manager.add_position_update_callback(on_position_update)

        # 주문 매니저 시작
        order_manager.start()
        print("✅ 주문 매니저 시작됨")

        # 테스트 주문 1: BTC 시장가 매수
        buy_request = OrderRequest(
            symbol="BTC_KRW",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal('0.00001'),  # 매우 작은 수량
            reason="테스트 매수 주문"
        )

        client_order_id1 = order_manager.submit_order(buy_request, OrderPriority.HIGH)
        print(f"✅ 매수 주문 제출: {client_order_id1}")

        # 테스트 주문 2: SOL 지정가 매도
        sell_request = OrderRequest(
            symbol="SOL_KRW",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=Decimal('0.00001'),  # 보유량보다 적은 수량
            price=Decimal('950000'),
            reason="테스트 매도 주문"
        )

        client_order_id2 = order_manager.submit_order(sell_request, OrderPriority.NORMAL)
        print(f"✅ 매도 주문 제출: {client_order_id2}")

        # 잠시 대기하여 주문 처리 관찰
        print("\n⏳ 주문 처리 중... (3초 대기)")
        time.sleep(3)

        # 주문 상태 확인
        print("\n📋 주문 상태 확인:")
        order1 = order_manager.get_order_status(client_order_id1)
        if order1:
            print(f"  주문 1: {order1.status.value} - {order1.symbol} {order1.side.value}")

        order2 = order_manager.get_order_status(client_order_id2)
        if order2:
            print(f"  주문 2: {order2.status.value} - {order2.symbol} {order2.side.value}")

        # 대기 중인 주문 목록
        pending_orders = order_manager.get_pending_orders()
        print(f"\n📝 대기 중인 주문: {len(pending_orders)}개")
        for order in pending_orders:
            print(f"  - {order.client_order_id}: {order.symbol} {order.side.value} {order.status.value}")

        # 포지션 확인
        positions = order_manager.get_all_positions()
        print(f"\n💼 현재 포지션: {len(positions)}개")
        for symbol, position in positions.items():
            pnl_pct = position.pnl_percentage
            print(f"  - {symbol}: {position.quantity} @ {position.market_price} (손익: {pnl_pct:.2f}%)")

        print("\n⏳ 추가 처리 대기... (2초)")
        time.sleep(2)

        # 주문 매니저 정지
        order_manager.stop()
        print("✅ 주문 매니저 정지됨")

    except Exception as e:
        print(f"❌ 테스트 실행 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🧪 Phase 4 주문 실행 시스템 간단 테스트")
    print("=" * 55)

    # 주문 타입 테스트
    test_order_types()

    # 주문 매니저 테스트
    test_order_manager()

    print("\n✅ 모든 테스트 완료!")
    print("💡 실제 거래소 연동 시에는 매우 작은 금액으로 테스트하세요.")