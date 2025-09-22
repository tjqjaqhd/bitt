#!/usr/bin/env python3
"""백테스트 시스템 테스트."""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal

# 프로젝트 루트를 sys.path에 추가
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_data_collector():
    """데이터 수집기 테스트."""
    print("🔧 데이터 수집기 테스트...")

    try:
        from src.backtest.data_collector import DataCollector, CandleData

        # Mock 클라이언트
        class MockClient:
            def get_ticker(self, symbol):
                return {'closing_price': '100000'}

        collector = DataCollector(MockClient())
        print("✅ 데이터 수집기 생성 완료")

        # 테스트 데이터 수집
        start_date = datetime.now() - timedelta(days=7)
        end_date = datetime.now()

        candles = collector.collect_candles("BTC_KRW", "1h", start_date, end_date, limit=50)
        print(f"✅ 캔들 데이터 수집: {len(candles)}개")

        # 데이터 검증
        is_valid, errors = collector.validate_data(candles)
        print(f"✅ 데이터 검증: {'성공' if is_valid else '실패'}")
        if errors:
            print(f"   오류: {errors[:3]}...")  # 처음 3개만 표시

        # DataFrame 변환
        df = collector.to_dataframe(candles)
        print(f"✅ DataFrame 변환: {len(df)}행")

        return True

    except Exception as e:
        print(f"❌ 데이터 수집기 테스트 실패: {e}")
        return False

def test_backtest_engine():
    """백테스트 엔진 테스트."""
    print("\n🚀 백테스트 엔진 테스트...")

    try:
        from src.backtest.engine import BacktestEngine
        from src.backtest.events import SignalEvent
        from src.backtest.data_collector import CandleData
        from src.core.order_types import OrderSide

        # 백테스트 엔진 생성
        engine = BacktestEngine(
            initial_capital=Decimal('1000000'),  # 100만원
            commission_rate=Decimal('0.0025')
        )
        print("✅ 백테스트 엔진 생성 완료")

        # 테스트 데이터 생성
        candles = []
        base_time = datetime.now() - timedelta(days=10)

        for i in range(100):  # 100개 캔들
            timestamp = base_time + timedelta(hours=i)
            price = Decimal('100000') * (Decimal('1') + Decimal(str((i % 20 - 10) / 1000)))  # ±1% 변동

            candle = CandleData(
                timestamp=timestamp,
                open_price=price,
                high_price=price * Decimal('1.005'),
                low_price=price * Decimal('0.995'),
                close_price=price,
                volume=Decimal('10'),
                symbol="BTC_KRW"
            )
            candles.append(candle)

        engine.add_data("BTC_KRW", candles)
        print("✅ 테스트 데이터 추가 완료")

        # 간단한 전략 콜백
        def simple_strategy(current_data):
            """간단한 매수-보유 전략."""
            if 'BTC_KRW' in current_data:
                candle = current_data['BTC_KRW']

                # 매 10번째 캔들마다 매수 신호
                if candle.timestamp.hour % 10 == 0:
                    engine.submit_signal(
                        symbol="BTC_KRW",
                        signal_type=OrderSide.BUY,
                        strength=Decimal('0.8'),
                        strategy_id="simple_strategy",
                        reason="매수 신호"
                    )

        engine.add_strategy_callback(simple_strategy)
        print("✅ 전략 콜백 추가 완료")

        # 백테스트 실행
        start_date = candles[0].timestamp
        end_date = candles[-1].timestamp

        engine.run(start_date, end_date)
        print("✅ 백테스트 실행 완료")

        # 결과 확인
        summary = engine.get_summary()
        print(f"✅ 결과 요약:")
        print(f"   초기 자본: {summary['initial_capital']:,.0f}원")
        print(f"   최종 자산: {summary['final_equity']:,.0f}원")
        print(f"   총 수익률: {summary['total_return']:.2f}%")
        print(f"   총 거래: {summary['total_trades']}회")
        print(f"   생성 신호: {summary['signals_generated']}개")

        return True

    except Exception as e:
        print(f"❌ 백테스트 엔진 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_performance_analysis():
    """성과 분석 테스트."""
    print("\n📊 성과 분석 테스트...")

    try:
        from src.backtest.performance import PerformanceAnalyzer

        # 모의 자산 곡선 생성
        equity_curve = []
        base_time = datetime.now() - timedelta(days=30)
        initial_capital = 1000000

        for i in range(30):
            timestamp = base_time + timedelta(days=i)
            # 간단한 성장 곡선 (일부 변동 포함)
            growth_factor = 1 + (i * 0.01) + (i % 5 - 2) * 0.005
            equity = initial_capital * growth_factor
            equity_curve.append((timestamp, equity))

        # 모의 거래 내역
        trades = [
            {
                'timestamp': base_time + timedelta(days=5),
                'symbol': 'BTC_KRW',
                'side': 'buy',
                'quantity': 0.01,
                'price': 100000,
                'commission': 25
            },
            {
                'timestamp': base_time + timedelta(days=15),
                'symbol': 'BTC_KRW',
                'side': 'sell',
                'quantity': 0.01,
                'price': 105000,
                'commission': 26.25
            }
        ]

        analyzer = PerformanceAnalyzer(risk_free_rate=0.02)
        metrics = analyzer.analyze(equity_curve, trades, initial_capital)

        print("✅ 성과 분석 완료")
        print(f"   총 수익률: {metrics.total_return:.2f}%")
        print(f"   연환산 수익률: {metrics.annualized_return:.2f}%")
        print(f"   최대 낙폭: {metrics.max_drawdown:.2f}%")
        print(f"   샤프 비율: {metrics.sharpe_ratio:.3f}")
        print(f"   승률: {metrics.win_rate:.1f}%")

        # 요약 리포트 생성
        report = analyzer.generate_summary_report(metrics)
        print("\n📋 성과 리포트 생성 완료")

        return True

    except Exception as e:
        print(f"❌ 성과 분석 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_portfolio():
    """포트폴리오 테스트."""
    print("\n💼 포트폴리오 테스트...")

    try:
        from src.backtest.portfolio import Portfolio
        from src.backtest.events import FillEvent
        from src.core.order_types import OrderSide

        # 포트폴리오 생성
        portfolio = Portfolio(Decimal('1000000'))
        print("✅ 포트폴리오 생성 완료")

        # 모의 체결 이벤트
        fill1 = FillEvent(
            timestamp=datetime.now(),
            symbol="BTC_KRW",
            side=OrderSide.BUY,
            quantity=Decimal('0.01'),
            fill_price=Decimal('100000'),
            commission=Decimal('25'),
            order_id="order_1",
            fill_id="fill_1"
        )

        fill2 = FillEvent(
            timestamp=datetime.now() + timedelta(hours=1),
            symbol="BTC_KRW",
            side=OrderSide.SELL,
            quantity=Decimal('0.005'),
            fill_price=Decimal('105000'),
            commission=Decimal('13.125'),
            order_id="order_2",
            fill_id="fill_2"
        )

        # 체결 처리
        portfolio.update_fill(fill1)
        portfolio.update_fill(fill2)
        print("✅ 체결 처리 완료")

        # 시장 데이터 업데이트
        portfolio.update_market_data("BTC_KRW", Decimal('110000'), datetime.now())
        print("✅ 시장 데이터 업데이트 완료")

        # 포트폴리오 요약
        summary = portfolio.get_portfolio_summary()
        print(f"✅ 포트폴리오 요약:")
        print(f"   총 자산: {summary['total_equity']:,.0f}원")
        print(f"   현금: {summary['cash']:,.0f}원")
        print(f"   실현 손익: {summary['realized_pnl']:,.0f}원")
        print(f"   미실현 손익: {summary['unrealized_pnl']:,.0f}원")
        print(f"   총 거래: {summary['total_trades']}회")

        # 포지션 확인
        position = portfolio.get_position("BTC_KRW")
        if position:
            print(f"✅ BTC 포지션: {position.quantity} @ {position.average_price}")

        return True

    except Exception as e:
        print(f"❌ 포트폴리오 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🧪 Phase 5 백테스트 시스템 테스트")
    print("=" * 55)

    tests = [
        ("데이터 수집기", test_data_collector),
        ("포트폴리오", test_portfolio),
        ("백테스트 엔진", test_backtest_engine),
        ("성과 분석", test_performance_analysis)
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 테스트 중 예외 발생: {e}")
            results.append((test_name, False))

    print("\n" + "=" * 55)
    print("📋 테스트 결과 요약")
    print("=" * 55)

    success_count = 0
    for test_name, success in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{test_name:20} : {status}")
        if success:
            success_count += 1

    print(f"\n총 {len(results)}개 테스트 중 {success_count}개 성공")

    if success_count == len(results):
        print("🎉 모든 백테스트 시스템 테스트 통과!")
    else:
        print("⚠️ 일부 테스트 실패. 구현을 확인해주세요.")

    print("\n💡 백테스트 시스템의 핵심 기능이 구현되었습니다.")
    print("📈 이제 실제 전략으로 백테스트를 실행할 수 있습니다!")