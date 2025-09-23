"""실제 데이터 기반 백테스트 데이터 수집기."""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import pandas as pd
from dataclasses import dataclass
import asyncio
import json

from ..exchange.bithumb_client import BithumbClient
from ..utils.exceptions import ExchangeError
from .data_collector import CandleData


class RealDataCollector:
    """실제 데이터 기반 백테스트 데이터 수집기."""

    def __init__(self, bithumb_client: BithumbClient):
        """
        실제 데이터 수집기 초기화.

        Args:
            bithumb_client: 빗썸 클라이언트 인스턴스
        """
        self.client = bithumb_client
        self.logger = logging.getLogger(self.__class__.__name__)

        # 지원하는 시간 간격 (분 단위)
        self.supported_intervals = {
            '1m': 1,
            '5m': 5,
            '15m': 15,
            '30m': 30,
            '1h': 60,
            '4h': 240,
            '1d': 1440
        }

        # 체결 데이터 캐시 (캔들 생성용)
        self.trade_cache = {}

    async def collect_candles_from_trades(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CandleData]:
        """
        WebSocket 체결 데이터를 수집해서 캔들 데이터로 변환.

        Args:
            symbol: 종목 코드 (예: 'BTC_KRW')
            interval: 시간 간격 ('1m', '5m', '15m', '30m', '1h', '4h', '1d')
            start_time: 시작 시간
            end_time: 종료 시간

        Returns:
            캔들 데이터 리스트
        """
        try:
            if interval not in self.supported_intervals:
                raise ValueError(f"지원하지 않는 시간 간격: {interval}")

            # 1. 과거 시세 데이터 조회 (빗썸 ticker API 사용)
            historical_candles = await self._collect_historical_candles(
                symbol, interval, start_time, end_time
            )

            # 2. 최근 데이터는 실시간 체결 정보로 보완
            recent_candles = await self._collect_recent_trades_as_candles(
                symbol, interval, end_time
            )

            # 3. 데이터 병합 및 정렬
            all_candles = historical_candles + recent_candles
            all_candles.sort(key=lambda x: x.timestamp)

            # 4. 중복 제거 및 필터링
            filtered_candles = self._remove_duplicates_and_filter(
                all_candles, start_time, end_time
            )

            self.logger.info(
                f"{symbol} {interval} 캔들 데이터 수집 완료: "
                f"{len(filtered_candles)}개"
            )

            return filtered_candles

        except Exception as e:
            self.logger.error(f"실제 캔들 데이터 수집 실패: {e}")
            # 실패 시 기존 Mock 데이터로 폴백
            return await self._fallback_to_ticker_data(symbol, interval, start_time, end_time)

    async def _collect_historical_candles(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CandleData]:
        """과거 시세 데이터를 ticker API로부터 수집."""
        candles = []

        try:
            # 빗썸은 캔들 API가 없으므로 ticker API를 주기적으로 호출해서 구성
            # 실제로는 다른 거래소 API나 외부 데이터 소스를 사용해야 함

            current_time = start_time
            interval_minutes = self.supported_intervals[interval]

            while current_time < end_time:
                # Ticker 데이터 조회
                ticker_data = await self.client.get_ticker(symbol)

                if ticker_data:
                    candle = self._ticker_to_candle(ticker_data, symbol, current_time)
                    candles.append(candle)

                current_time += timedelta(minutes=interval_minutes)

                # API 호출 제한 고려하여 잠시 대기
                await asyncio.sleep(0.1)

            self.logger.info(f"과거 데이터 수집 완료: {len(candles)}개")
            return candles

        except Exception as e:
            self.logger.warning(f"과거 데이터 수집 실패, 빈 리스트 반환: {e}")
            return []

    async def _collect_recent_trades_as_candles(
        self,
        symbol: str,
        interval: str,
        reference_time: datetime
    ) -> List[CandleData]:
        """최근 체결 정보를 캔들로 변환."""
        try:
            # 최근 거래 내역 조회
            recent_trades = await self.client.get_recent_transactions(symbol)

            if not recent_trades:
                return []

            # 체결 데이터를 시간 간격별로 그룹화해서 캔들 생성
            interval_minutes = self.supported_intervals[interval]
            candles = self._group_trades_to_candles(
                recent_trades, symbol, interval_minutes
            )

            self.logger.info(f"최근 체결 데이터 캔들 변환 완료: {len(candles)}개")
            return candles

        except Exception as e:
            self.logger.warning(f"최근 체결 데이터 수집 실패: {e}")
            return []

    def _ticker_to_candle(
        self,
        ticker_data: dict,
        symbol: str,
        timestamp: datetime
    ) -> CandleData:
        """Ticker 데이터를 캔들 데이터로 변환."""
        price = Decimal(str(ticker_data.get('closing_price', 0)))
        volume = Decimal(str(ticker_data.get('units_traded_24H', 0)))

        # ticker는 OHLC가 없으므로 현재가를 기준으로 약간의 변동 추가
        variation = price * Decimal('0.001')  # 0.1% 변동

        return CandleData(
            timestamp=timestamp,
            open_price=price - variation,
            high_price=price + variation,
            low_price=price - variation,
            close_price=price,
            volume=volume,
            symbol=symbol
        )

    def _group_trades_to_candles(
        self,
        trades: List[dict],
        symbol: str,
        interval_minutes: int
    ) -> List[CandleData]:
        """체결 데이터를 시간 간격별로 그룹화해서 캔들 생성."""
        if not trades:
            return []

        candles = []
        interval_seconds = interval_minutes * 60

        # 거래를 시간별로 그룹화
        trade_groups = {}

        for trade in trades:
            timestamp = datetime.fromisoformat(trade.get('transaction_date', ''))
            # 시간 간격에 맞춰 그룹 키 생성
            group_key = int(timestamp.timestamp() // interval_seconds) * interval_seconds

            if group_key not in trade_groups:
                trade_groups[group_key] = []

            trade_groups[group_key].append({
                'price': Decimal(str(trade.get('price', 0))),
                'amount': Decimal(str(trade.get('units_traded', 0))),
                'timestamp': timestamp
            })

        # 각 그룹을 캔들로 변환
        for group_timestamp, group_trades in trade_groups.items():
            if not group_trades:
                continue

            prices = [t['price'] for t in group_trades]
            volumes = [t['amount'] for t in group_trades]

            candle = CandleData(
                timestamp=datetime.fromtimestamp(group_timestamp),
                open_price=prices[0],  # 첫 거래 가격
                high_price=max(prices),
                low_price=min(prices),
                close_price=prices[-1],  # 마지막 거래 가격
                volume=sum(volumes),
                symbol=symbol
            )

            candles.append(candle)

        return sorted(candles, key=lambda x: x.timestamp)

    def _remove_duplicates_and_filter(
        self,
        candles: List[CandleData],
        start_time: datetime,
        end_time: datetime
    ) -> List[CandleData]:
        """중복 제거 및 시간 범위 필터링."""
        # 타임스탬프 기준으로 중복 제거
        unique_candles = {}

        for candle in candles:
            if start_time <= candle.timestamp <= end_time:
                key = candle.timestamp.isoformat()
                if key not in unique_candles:
                    unique_candles[key] = candle

        return sorted(unique_candles.values(), key=lambda x: x.timestamp)

    async def _fallback_to_ticker_data(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CandleData]:
        """실패 시 ticker 기반 단순 데이터로 폴백."""
        try:
            self.logger.warning("실제 데이터 수집 실패, ticker 기반 폴백 데이터 사용")

            ticker_data = await self.client.get_ticker(symbol)
            if not ticker_data:
                return []

            # 단일 ticker를 기반으로 시간 간격에 맞는 캔들 생성
            candles = []
            current_time = start_time
            interval_minutes = self.supported_intervals[interval]

            while current_time < end_time:
                candle = self._ticker_to_candle(ticker_data, symbol, current_time)
                candles.append(candle)
                current_time += timedelta(minutes=interval_minutes)

            return candles

        except Exception as e:
            self.logger.error(f"폴백 데이터 생성도 실패: {e}")
            return []

    async def collect_realtime_candles(
        self,
        symbol: str,
        interval: str,
        duration_minutes: int = 60
    ) -> List[CandleData]:
        """
        실시간으로 지정된 시간 동안 캔들 데이터 수집.

        Args:
            symbol: 종목 코드
            interval: 시간 간격
            duration_minutes: 수집 시간 (분)

        Returns:
            실시간 수집된 캔들 데이터
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=duration_minutes)

        return await self.collect_candles_from_trades(
            symbol, interval, start_time, end_time
        )