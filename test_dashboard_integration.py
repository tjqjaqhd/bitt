#!/usr/bin/env python3
"""대시보드 API 연동 테스트."""

import asyncio
import aiohttp
import json

API_BASE = 'http://localhost:8000/api'

async def test_dashboard_integration():
    """대시보드 API 연동 테스트."""
    async with aiohttp.ClientSession() as session:
        print("🧪 대시보드 API 연동 테스트 시작\n")

        # 1. 대시보드 요약 정보
        print("1️⃣ 대시보드 요약 정보 테스트")
        async with session.get(f"{API_BASE}/dashboard/summary") as response:
            data = await response.json()
            print(f"✅ 상태: {response.status}")
            print(f"   총 자산: ₩{data['total_balance_krw']:,}")
            print(f"   일일 손익: ₩{data['daily_pnl']:,}")
            print(f"   승률: {data['success_rate']}%")
            print(f"   활성 포지션: {data['active_positions']}개\n")

        # 2. 포지션 정보
        print("2️⃣ 포지션 정보 테스트")
        async with session.get(f"{API_BASE}/dashboard/positions") as response:
            positions = await response.json()
            print(f"✅ 상태: {response.status}")
            print(f"   포지션 수: {len(positions)}개")
            for pos in positions:
                pnl_color = "🟢" if pos['unrealized_pnl'] >= 0 else "🔴"
                print(f"   {pos['symbol']}: {pos['quantity']} (손익: {pnl_color}₩{pos['unrealized_pnl']:,})")
            print()

        # 3. 최근 거래
        print("3️⃣ 최근 거래 테스트")
        async with session.get(f"{API_BASE}/dashboard/recent-trades") as response:
            data = await response.json()
            print(f"✅ 상태: {response.status}")
            print(f"   거래 수: {len(data['trades'])}개")
            for trade in data['trades'][:2]:  # 최근 2개만 표시
                side_color = "🟢" if trade['side'] == 'buy' else "🔴"
                print(f"   {trade['symbol']}: {side_color}{trade['side'].upper()} {trade['quantity']} @ ₩{trade['price']:,}")
            print()

        # 4. 성과 지표
        print("4️⃣ 성과 지표 테스트")
        async with session.get(f"{API_BASE}/analysis/performance") as response:
            metrics = await response.json()
            print(f"✅ 상태: {response.status}")
            print(f"   총 수익률: {metrics['total_return']}%")
            print(f"   연환산 수익률: {metrics['annualized_return']}%")
            print(f"   최대 낙폭: {metrics['max_drawdown']}%")
            print(f"   샤프 비율: {metrics['sharpe_ratio']}")
            print(f"   총 거래 수: {metrics['total_trades']}건\n")

        # 5. 자산 곡선
        print("5️⃣ 자산 곡선 테스트")
        async with session.get(f"{API_BASE}/analysis/equity-curve") as response:
            data = await response.json()
            print(f"✅ 상태: {response.status}")
            print(f"   데이터 포인트: {len(data['equity_curve'])}개")

            # 최근 5일 자산 변화
            recent_points = data['equity_curve'][-5:]
            print("   최근 5일 자산 변화:")
            for point in recent_points:
                date = point['date'][:10]  # YYYY-MM-DD
                equity = point['equity']
                return_pct = point['return_pct']
                color = "🟢" if return_pct >= 0 else "🔴"
                print(f"     {date}: ₩{equity:,.0f} ({color}{return_pct:+.2f}%)")
            print()

        print("🎉 모든 API 연동 테스트 완료!")

if __name__ == "__main__":
    asyncio.run(test_dashboard_integration())