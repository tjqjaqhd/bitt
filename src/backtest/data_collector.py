"""백테스트용 과거 데이터 수집기."""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import pandas as pd
from dataclasses import dataclass

from ..exchange.bithumb_client import BithumbClient
from ..utils.exceptions import ExchangeError


@dataclass
class CandleData:
    """캔들 데이터."""
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    symbol: str

    def to_dict(self) -> dict:
        """딕셔너리로 변환."""
        return {
            'timestamp': self.timestamp,
            'open': float(self.open_price),
            'high': float(self.high_price),
            'low': float(self.low_price),
            'close': float(self.close_price),
            'volume': float(self.volume),
            'symbol': self.symbol
        }


class DataCollector:
    """백테스트용 데이터 수집기."""

    def __init__(self, bithumb_client: BithumbClient):
        """
        데이터 수집기 초기화.

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

        # Rate limit 관리
        self.request_delay = 0.2  # 초
        self.last_request_time = 0.0

    def _rate_limit(self):
        """Rate limit 관리."""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    def collect_candles(
        self,
        symbol: str,
        interval: str,
        start_date: datetime,
        end_date: datetime,
        limit: int = 200
    ) -> List[CandleData]:
        """
        캔들 데이터 수집.

        Args:
            symbol: 종목 코드 (예: "BTC_KRW")
            interval: 시간 간격 (1m, 5m, 15m, 30m, 1h, 4h, 1d)
            start_date: 시작 날짜
            end_date: 종료 날짜
            limit: 한 번에 가져올 최대 개수

        Returns:
            캔들 데이터 리스트
        """
        if interval not in self.supported_intervals:
            raise ValueError(f"지원하지 않는 간격: {interval}")

        self.logger.info(f"캔들 데이터 수집 시작: {symbol} {interval} {start_date} ~ {end_date}")

        all_candles = []
        current_end = end_date

        while current_end > start_date:
            try:
                self._rate_limit()

                # 빗썸 API 호출
                candles = self._fetch_candles_batch(symbol, interval, current_end, limit)

                if not candles:
                    break

                # 날짜 범위 필터링
                filtered_candles = [
                    candle for candle in candles
                    if start_date <= candle.timestamp <= end_date
                ]

                all_candles.extend(filtered_candles)

                # 다음 배치를 위한 시간 업데이트
                if candles:
                    current_end = min(candle.timestamp for candle in candles) - timedelta(minutes=1)

                self.logger.debug(f"수집된 캔들 수: {len(filtered_candles)}, 총 {len(all_candles)}개")

                # 시작 날짜에 도달했으면 중단
                if candles and min(candle.timestamp for candle in candles) <= start_date:
                    break

            except Exception as e:
                self.logger.error(f"캔들 데이터 수집 중 오류: {e}")
                time.sleep(1)  # 오류 발생 시 잠시 대기

        # 시간순 정렬
        all_candles.sort(key=lambda x: x.timestamp)

        self.logger.info(f"캔들 데이터 수집 완료: {len(all_candles)}개")
        return all_candles

    def _fetch_candles_batch(
        self,
        symbol: str,
        interval: str,
        end_time: datetime,
        limit: int
    ) -> List[CandleData]:
        """
        한 번의 API 호출로 캔들 데이터 가져오기.

        Args:
            symbol: 종목 코드
            interval: 시간 간격
            end_time: 종료 시간
            limit: 개수 제한

        Returns:
            캔들 데이터 리스트
        """
        try:
            # 빗썸 API는 캔들 데이터 제공하지 않으므로 mock 데이터 생성
            # 실제 구현에서는 다른 데이터 소스를 사용하거나 ticker 데이터를 활용
            return self._generate_mock_candles(symbol, interval, end_time, limit)

        except Exception as e:
            self.logger.error(f"캔들 데이터 배치 수집 실패: {e}")
            return []

    def _generate_mock_candles(
        self,
        symbol: str,
        interval: str,
        end_time: datetime,
        limit: int
    ) -> List[CandleData]:
        """
        Mock 캔들 데이터 생성 (실제 데이터 대신 사용).

        Args:
            symbol: 종목 코드
            interval: 시간 간격
            end_time: 종료 시간
            limit: 개수 제한

        Returns:
            Mock 캔들 데이터 리스트
        """
        candles = []
        interval_minutes = self.supported_intervals[interval]

        # 현재가 기준으로 시작
        try:
            ticker = self.client.get_ticker(symbol)
            if not ticker:
                return []

            base_price = Decimal(str(ticker.get('closing_price', 100000)))
        except:
            base_price = Decimal('100000')  # 기본값

        for i in range(limit):
            timestamp = end_time - timedelta(minutes=interval_minutes * i)

            # 가격 변동 시뮬레이션 (±2% 랜덤)
            import random
            change_rate = Decimal(str(random.uniform(-0.02, 0.02)))
            price = base_price * (Decimal('1') + change_rate)

            # OHLC 생성
            high_rate = Decimal(str(random.uniform(0, 0.01)))
            low_rate = Decimal(str(random.uniform(-0.01, 0)))

            open_price = price
            high_price = price * (Decimal('1') + high_rate)
            low_price = price * (Decimal('1') + low_rate)
            close_price = price

            volume = Decimal(str(random.uniform(1, 100)))

            candle = CandleData(
                timestamp=timestamp,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                symbol=symbol
            )
            candles.append(candle)

        return candles

    def collect_multiple_symbols(
        self,
        symbols: List[str],
        interval: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, List[CandleData]]:
        """
        여러 종목의 캔들 데이터 수집.

        Args:
            symbols: 종목 코드 리스트
            interval: 시간 간격
            start_date: 시작 날짜
            end_date: 종료 날짜

        Returns:
            종목별 캔들 데이터 딕셔너리
        """
        self.logger.info(f"다중 종목 데이터 수집 시작: {len(symbols)}개 종목")

        results = {}
        for i, symbol in enumerate(symbols):
            self.logger.info(f"수집 진행: {i+1}/{len(symbols)} - {symbol}")

            try:
                candles = self.collect_candles(symbol, interval, start_date, end_date)
                results[symbol] = candles

                # 종목 간 딜레이
                if i < len(symbols) - 1:
                    time.sleep(0.5)

            except Exception as e:
                self.logger.error(f"{symbol} 데이터 수집 실패: {e}")
                results[symbol] = []

        self.logger.info("다중 종목 데이터 수집 완료")
        return results

    def validate_data(self, candles: List[CandleData]) -> Tuple[bool, List[str]]:
        """
        데이터 검증.

        Args:
            candles: 캔들 데이터 리스트

        Returns:
            (검증 성공 여부, 오류 메시지 리스트)
        """
        errors = []

        if not candles:
            errors.append("데이터가 비어있습니다.")
            return False, errors

        # 시간 순서 확인
        for i in range(1, len(candles)):
            if candles[i].timestamp <= candles[i-1].timestamp:
                errors.append(f"시간 순서 오류: {i}번째 데이터")

        # 가격 데이터 확인
        for i, candle in enumerate(candles):
            if candle.high_price < candle.low_price:
                errors.append(f"고가 < 저가 오류: {i}번째 데이터")

            if not (candle.low_price <= candle.open_price <= candle.high_price):
                errors.append(f"시가 범위 오류: {i}번째 데이터")

            if not (candle.low_price <= candle.close_price <= candle.high_price):
                errors.append(f"종가 범위 오류: {i}번째 데이터")

            if candle.volume < 0:
                errors.append(f"거래량 음수 오류: {i}번째 데이터")

        # 결측치 확인
        missing_count = 0
        if len(candles) > 1:
            interval_minutes = (candles[1].timestamp - candles[0].timestamp).total_seconds() / 60
            expected_count = int((candles[-1].timestamp - candles[0].timestamp).total_seconds() / (interval_minutes * 60)) + 1
            missing_count = expected_count - len(candles)

        if missing_count > 0:
            errors.append(f"결측치 {missing_count}개 발견")

        is_valid = len(errors) == 0
        self.logger.info(f"데이터 검증 결과: {'성공' if is_valid else '실패'} ({len(errors)}개 오류)")

        return is_valid, errors

    def to_dataframe(self, candles: List[CandleData]) -> pd.DataFrame:
        """
        캔들 데이터를 pandas DataFrame으로 변환.

        Args:
            candles: 캔들 데이터 리스트

        Returns:
            pandas DataFrame
        """
        if not candles:
            return pd.DataFrame()

        data = [candle.to_dict() for candle in candles]
        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)

        return df

    def save_to_csv(self, candles: List[CandleData], filepath: str):
        """
        캔들 데이터를 CSV 파일로 저장.

        Args:
            candles: 캔들 데이터 리스트
            filepath: 저장할 파일 경로
        """
        df = self.to_dataframe(candles)
        df.to_csv(filepath)
        self.logger.info(f"데이터 저장 완료: {filepath} ({len(candles)}개 레코드)")

    def load_from_csv(self, filepath: str, symbol: str) -> List[CandleData]:
        """
        CSV 파일에서 캔들 데이터 로드.

        Args:
            filepath: CSV 파일 경로
            symbol: 종목 코드

        Returns:
            캔들 데이터 리스트
        """
        try:
            df = pd.read_csv(filepath, index_col='timestamp', parse_dates=True)

            candles = []
            for timestamp, row in df.iterrows():
                candle = CandleData(
                    timestamp=timestamp,
                    open_price=Decimal(str(row['open'])),
                    high_price=Decimal(str(row['high'])),
                    low_price=Decimal(str(row['low'])),
                    close_price=Decimal(str(row['close'])),
                    volume=Decimal(str(row['volume'])),
                    symbol=symbol
                )
                candles.append(candle)

            self.logger.info(f"데이터 로드 완료: {filepath} ({len(candles)}개 레코드)")
            return candles

        except Exception as e:
            self.logger.error(f"데이터 로드 실패: {filepath}, {e}")
            return []