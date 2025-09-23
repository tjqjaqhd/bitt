#!/usr/bin/env python3
"""개선사항 테스트 스크립트."""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.exchange.bithumb_unified_client import BithumbUnifiedClient
from src.backtest.real_data_collector import RealDataCollector
from src.backtest.async_engine import AsyncBacktestEngine
from src.core.parameters import StrategyParameters
from src.api.routers.analysis_real import get_performance_metrics
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def test_unified_client():
    """통합 클라이언트 테스트."""
    print("\n🔄 1. 통합 클라이언트 테스트")
    print("=" * 50)

    client = BithumbUnifiedClient()

    try:
        await client.initialize()

        # REST API 테스트
        ticker = await client.get_ticker("BTC_KRW")
        print(f"✅ REST Ticker: {ticker.get('closing_price', 'N/A') if ticker else 'Failed'}")

        # WebSocket 상태 확인
        status = client.get_connection_status()
        print(f"✅ WebSocket 연결: {status['websocket_connected']}")

        # 캐시된 데이터 확인
        await asyncio.sleep(2)  # 잠시 대기
        cached_ticker = client.get_cached_ticker("BTC_KRW")
        print(f"✅ 캐시된 데이터: {'있음' if cached_ticker else '없음'}")

        return True

    except Exception as e:
        print(f"❌ 통합 클라이언트 테스트 실패: {e}")
        return False

    finally:
        await client.close()


async def test_real_data_collector():
    """실제 데이터 수집기 테스트."""
    print("\n📊 2. 실제 데이터 수집기 테스트")
    print("=" * 50)

    client = BithumbUnifiedClient()

    try:
        await client.initialize()
        collector = RealDataCollector(client)

        # 실제 데이터 수집 테스트
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)

        candles = await collector.collect_candles_from_trades(
            "BTC_KRW", "1h", start_time, end_time
        )

        print(f"✅ 수집된 캔들 데이터: {len(candles)}개")

        if candles:
            latest = candles[-1]
            print(f"✅ 최신 데이터: {latest.timestamp} - 종가 {latest.close_price}")

        # 실시간 데이터 수집 테스트
        realtime_candles = await collector.collect_realtime_candles(
            "BTC_KRW", "5m", 30
        )

        print(f"✅ 실시간 캔들: {len(realtime_candles)}개")

        return len(candles) > 0

    except Exception as e:
        print(f"❌ 실제 데이터 수집기 테스트 실패: {e}")
        return False

    finally:
        await client.close()


async def test_async_backtest_engine():
    """비동기 백테스트 엔진 테스트."""
    print("\n⚡ 3. 비동기 백테스트 엔진 테스트")
    print("=" * 50)

    client = BithumbUnifiedClient()

    try:
        await client.initialize()
        engine = AsyncBacktestEngine(client, Decimal('1000000'))

        # 전략 파라미터 설정
        params = StrategyParameters(
            ema_short_period=12,
            ema_long_period=26,
            rsi_period=14,
            rsi_oversold=30,
            rsi_overbought=70,
            position_size_percent=10,
            stop_loss_atr_multiplier=2.0
        )

        # 단일 백테스트
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        print("단일 종목 백테스트 실행 중...")
        result = await engine.run_single_backtest(
            "BTC_KRW", start_date, end_date, params, "1h"
        )

        print(f"✅ 백테스트 완료:")
        print(f"   - 종목: {result.symbol}")
        print(f"   - 총 수익률: {result.total_return:.2f}%")
        print(f"   - 거래 수: {len(result.trades)}건")
        print(f"   - 실행 시간: {result.execution_time:.2f}초")

        # 다중 종목 백테스트
        symbols = ["BTC_KRW", "ETH_KRW"]
        print(f"\n다중 종목 백테스트 실행 중... ({', '.join(symbols)})")

        multi_results = await engine.run_multi_symbol_backtest(
            symbols, start_date, end_date, params, "1h"
        )

        print(f"✅ 다중 백테스트 완료: {len(multi_results)}개 종목")
        for symbol, res in multi_results.items():
            print(f"   - {symbol}: {res.total_return:.2f}% ({len(res.trades)}건)")

        return True

    except Exception as e:
        print(f"❌ 비동기 백테스트 엔진 테스트 실패: {e}")
        return False

    finally:
        await client.close()


async def test_parameter_optimization():
    """파라미터 최적화 테스트."""
    print("\n🎯 4. 파라미터 최적화 테스트")
    print("=" * 50)

    client = BithumbUnifiedClient()

    try:
        await client.initialize()
        engine = AsyncBacktestEngine(client, Decimal('1000000'))

        # 최적화할 파라미터 범위
        param_ranges = {
            'ema_short_period': [8, 12, 16],
            'ema_long_period': [21, 26, 30],
            'rsi_period': [10, 14, 18],
            'position_size_percent': [5, 10, 15]
        }

        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)  # 짧은 기간으로 테스트

        print("파라미터 최적화 실행 중...")
        optimization_result = await engine.run_parameter_optimization(
            "BTC_KRW", start_date, end_date, param_ranges, "1h", max_combinations=20
        )

        print(f"✅ 최적화 완료:")
        print(f"   - 총 조합 수: {optimization_result['total_combinations']}")
        print(f"   - 최고 점수: {optimization_result['best_score']:.3f}")
        print(f"   - 최적 파라미터: {optimization_result['best_params']}")

        if optimization_result['best_result']:
            best = optimization_result['best_result']
            print(f"   - 최고 수익률: {best.total_return:.2f}%")

        return True

    except Exception as e:
        print(f"❌ 파라미터 최적화 테스트 실패: {e}")
        return False

    finally:
        await client.close()


def test_modular_structure():
    """모듈화된 구조 테스트."""
    print("\n🏗️ 5. 모듈화된 구조 테스트")
    print("=" * 50)

    try:
        # 개별 모듈 임포트 테스트
        from src.exchange.bithumb_rest_client import BithumbRestClient
        from src.exchange.bithumb_websocket_client import BithumbWebSocketClient
        from src.api.routers.analysis_real import PerformanceMetrics

        print("✅ REST 클라이언트 모듈: 임포트 성공")
        print("✅ WebSocket 클라이언트 모듈: 임포트 성공")
        print("✅ 실제 분석 API 모듈: 임포트 성공")

        # 모듈별 인스턴스 생성 테스트
        rest_client = BithumbRestClient()
        ws_client = BithumbWebSocketClient()

        print("✅ 모듈 인스턴스 생성: 성공")

        # 설정 정보 확인
        rest_status = hasattr(rest_client, 'session')
        ws_status = hasattr(ws_client, 'ws_url')

        print(f"✅ REST 클라이언트 설정: {'완료' if rest_status else '실패'}")
        print(f"✅ WebSocket 클라이언트 설정: {'완료' if ws_status else '실패'}")

        # 정리
        rest_client.close()

        return True

    except Exception as e:
        print(f"❌ 모듈화된 구조 테스트 실패: {e}")
        return False


async def run_performance_benchmark():
    """성능 벤치마크 테스트."""
    print("\n🚀 6. 성능 벤치마크 테스트")
    print("=" * 50)

    client = BithumbUnifiedClient()

    try:
        await client.initialize()

        # API 응답 시간 측정
        start_time = datetime.now()
        ticker = await client.get_ticker("BTC_KRW")
        api_time = (datetime.now() - start_time).total_seconds()

        print(f"✅ API 응답 시간: {api_time:.3f}초")

        # 데이터 처리 성능 측정
        collector = RealDataCollector(client)

        start_time = datetime.now()
        candles = await collector.collect_realtime_candles("BTC_KRW", "5m", 60)
        processing_time = (datetime.now() - start_time).total_seconds()

        print(f"✅ 데이터 처리 시간: {processing_time:.3f}초 ({len(candles)}개 캔들)")

        # 메모리 사용량 체크
        import psutil
        memory_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB

        print(f"✅ 메모리 사용량: {memory_usage:.1f} MB")

        return True

    except Exception as e:
        print(f"❌ 성능 벤치마크 테스트 실패: {e}")
        return False

    finally:
        await client.close()


async def main():
    """메인 테스트 실행."""
    print("🧪 빗썸 자동매매 시스템 개선사항 테스트")
    print("=" * 70)

    test_results = []

    # 1. 통합 클라이언트 테스트
    result1 = await test_unified_client()
    test_results.append(("통합 클라이언트", result1))

    # 2. 실제 데이터 수집기 테스트
    result2 = await test_real_data_collector()
    test_results.append(("실제 데이터 수집기", result2))

    # 3. 비동기 백테스트 엔진 테스트
    result3 = await test_async_backtest_engine()
    test_results.append(("비동기 백테스트 엔진", result3))

    # 4. 파라미터 최적화 테스트
    result4 = await test_parameter_optimization()
    test_results.append(("파라미터 최적화", result4))

    # 5. 모듈화된 구조 테스트
    result5 = test_modular_structure()
    test_results.append(("모듈화된 구조", result5))

    # 6. 성능 벤치마크 테스트
    result6 = await run_performance_benchmark()
    test_results.append(("성능 벤치마크", result6))

    # 결과 요약
    print("\n📋 테스트 결과 요약")
    print("=" * 70)

    success_count = 0
    for test_name, result in test_results:
        status = "✅ 성공" if result else "❌ 실패"
        print(f"{test_name:20} : {status}")
        if result:
            success_count += 1

    print(f"\n🎯 총 {len(test_results)}개 테스트 중 {success_count}개 성공")

    if success_count == len(test_results):
        print("🎉 모든 개선사항이 정상적으로 작동합니다!")
    else:
        print("⚠️ 일부 테스트가 실패했습니다. 로그를 확인하세요.")

    return success_count == len(test_results)


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n사용자에 의해 테스트가 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        print(f"\n예상치 못한 오류가 발생했습니다: {e}")
        sys.exit(1)