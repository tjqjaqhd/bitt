"""비동기 백테스트 엔진."""

import asyncio
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import concurrent.futures
from multiprocessing import Pool, cpu_count

from .real_data_collector import RealDataCollector, CandleData
from .performance import PerformanceAnalyzer
from ..core.strategy import TradingStrategy
from ..core.signals import SignalGenerator
from ..core.risk import RiskManager
from ..core.parameters import StrategyParameters
from ..exchange.bithumb_unified_client import BithumbUnifiedClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class BacktestResult:
    """백테스트 결과."""
    symbol: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    trades: List[Dict[str, Any]]
    equity_curve: List[Dict[str, Any]]
    performance_metrics: Dict[str, float]
    execution_time: float


class AsyncBacktestEngine:
    """비동기 백테스트 엔진."""

    def __init__(
        self,
        bithumb_client: BithumbUnifiedClient,
        initial_capital: Decimal = Decimal('1000000')
    ):
        """
        비동기 백테스트 엔진 초기화.

        Args:
            bithumb_client: 빗썸 클라이언트
            initial_capital: 초기 자본
        """
        self.client = bithumb_client
        self.initial_capital = initial_capital

        # 컴포넌트들
        self.data_collector = RealDataCollector(bithumb_client)
        self.signal_generator = SignalGenerator()
        self.risk_manager = RiskManager()
        self.performance_analyzer = PerformanceAnalyzer()

        self.logger = logger

        # 병렬 처리 설정
        self.max_workers = min(cpu_count(), 8)

    async def run_single_backtest(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategy_params: StrategyParameters,
        interval: str = "1h"
    ) -> BacktestResult:
        """
        단일 종목 백테스트 실행.

        Args:
            symbol: 종목 코드
            start_date: 시작 날짜
            end_date: 종료 날짜
            strategy_params: 전략 파라미터
            interval: 시간 간격

        Returns:
            백테스트 결과
        """
        start_time = datetime.now()

        try:
            # 1. 데이터 수집
            self.logger.info(f"{symbol} 백테스트 시작: {start_date} ~ {end_date}")

            candle_data = await self.data_collector.collect_candles_from_trades(
                symbol, interval, start_date, end_date
            )

            if not candle_data:
                raise ValueError(f"{symbol}에 대한 데이터를 수집할 수 없습니다.")

            # 2. 데이터를 DataFrame으로 변환
            df = self._candles_to_dataframe(candle_data)

            # 3. 기술적 지표 계산 (비동기)
            df_with_indicators = await self._calculate_indicators_async(df, strategy_params)

            # 4. 시그널 생성
            signals = await self._generate_signals_async(df_with_indicators, strategy_params)

            # 5. 백테스트 실행
            trades, equity_curve = await self._execute_backtest_async(
                df_with_indicators, signals, strategy_params
            )

            # 6. 성과 분석
            performance_metrics = self.performance_analyzer.calculate_metrics(
                trades, equity_curve, float(self.initial_capital)
            )

            execution_time = (datetime.now() - start_time).total_seconds()

            result = BacktestResult(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                initial_capital=float(self.initial_capital),
                final_capital=equity_curve[-1]['equity'] if equity_curve else float(self.initial_capital),
                total_return=performance_metrics.get('total_return', 0),
                trades=trades,
                equity_curve=equity_curve,
                performance_metrics=performance_metrics,
                execution_time=execution_time
            )

            self.logger.info(
                f"{symbol} 백테스트 완료: "
                f"수익률 {result.total_return:.2f}%, "
                f"거래 수 {len(trades)}건, "
                f"실행 시간 {execution_time:.2f}초"
            )

            return result

        except Exception as e:
            self.logger.error(f"{symbol} 백테스트 실패: {e}")
            raise

    async def run_multi_symbol_backtest(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        strategy_params: StrategyParameters,
        interval: str = "1h"
    ) -> Dict[str, BacktestResult]:
        """
        다중 종목 백테스트 병렬 실행.

        Args:
            symbols: 종목 코드 리스트
            start_date: 시작 날짜
            end_date: 종료 날짜
            strategy_params: 전략 파라미터
            interval: 시간 간격

        Returns:
            종목별 백테스트 결과
        """
        self.logger.info(f"다중 종목 백테스트 시작: {len(symbols)}개 종목")

        # 비동기 태스크 생성
        tasks = []
        for symbol in symbols:
            task = self.run_single_backtest(
                symbol, start_date, end_date, strategy_params, interval
            )
            tasks.append(task)

        # 병렬 실행
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 정리
        backtest_results = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                self.logger.error(f"{symbol} 백테스트 실패: {result}")
                continue

            backtest_results[symbol] = result

        self.logger.info(f"다중 종목 백테스트 완료: {len(backtest_results)}개 성공")
        return backtest_results

    async def run_parameter_optimization(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        param_ranges: Dict[str, List[Any]],
        interval: str = "1h",
        max_combinations: int = 100
    ) -> Dict[str, Any]:
        """
        파라미터 최적화 실행.

        Args:
            symbol: 종목 코드
            start_date: 시작 날짜
            end_date: 종료 날짜
            param_ranges: 파라미터 범위 딕셔너리
            interval: 시간 간격
            max_combinations: 최대 조합 수

        Returns:
            최적화 결과
        """
        self.logger.info(f"{symbol} 파라미터 최적화 시작")

        # 파라미터 조합 생성
        param_combinations = self._generate_param_combinations(param_ranges, max_combinations)

        # 병렬 백테스트 실행
        optimization_tasks = []
        for params in param_combinations:
            strategy_params = StrategyParameters(**params)
            task = self.run_single_backtest(symbol, start_date, end_date, strategy_params, interval)
            optimization_tasks.append((params, task))

        # 배치별로 실행 (메모리 관리)
        batch_size = min(self.max_workers, 20)
        best_result = None
        best_params = None
        best_score = float('-inf')

        for i in range(0, len(optimization_tasks), batch_size):
            batch = optimization_tasks[i:i + batch_size]
            batch_tasks = [task for _, task in batch]

            results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # 결과 평가
            for (params, _), result in zip(batch, results):
                if isinstance(result, Exception):
                    continue

                # 샤프 비율을 최적화 기준으로 사용
                score = result.performance_metrics.get('sharpe_ratio', float('-inf'))

                if score > best_score:
                    best_score = score
                    best_result = result
                    best_params = params

        optimization_result = {
            'best_params': best_params,
            'best_result': best_result,
            'best_score': best_score,
            'total_combinations': len(param_combinations)
        }

        self.logger.info(
            f"{symbol} 파라미터 최적화 완료: "
            f"최고 샤프 비율 {best_score:.3f}"
        )

        return optimization_result

    def _candles_to_dataframe(self, candles: List[CandleData]) -> pd.DataFrame:
        """캔들 데이터를 DataFrame으로 변환."""
        data = []
        for candle in candles:
            data.append({
                'timestamp': candle.timestamp,
                'open': float(candle.open_price),
                'high': float(candle.high_price),
                'low': float(candle.low_price),
                'close': float(candle.close_price),
                'volume': float(candle.volume)
            })

        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)

        return df

    async def _calculate_indicators_async(
        self,
        df: pd.DataFrame,
        params: StrategyParameters
    ) -> pd.DataFrame:
        """비동기로 기술적 지표 계산."""
        loop = asyncio.get_event_loop()

        # CPU 집약적 계산을 별도 스레드에서 실행
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future = executor.submit(self._calculate_indicators, df, params)
            result = await loop.run_in_executor(None, lambda: future.result())

        return result

    def _calculate_indicators(self, df: pd.DataFrame, params: StrategyParameters) -> pd.DataFrame:
        """기술적 지표 계산 (CPU 집약적)."""
        df = df.copy()

        # EMA 계산
        df['ema_short'] = df['close'].ewm(span=params.ema_short_period).mean()
        df['ema_long'] = df['close'].ewm(span=params.ema_long_period).mean()

        # RSI 계산
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=params.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=params.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # ATR 계산
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(window=14).mean()

        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)

        return df

    async def _generate_signals_async(
        self,
        df: pd.DataFrame,
        params: StrategyParameters
    ) -> pd.DataFrame:
        """비동기로 시그널 생성."""
        loop = asyncio.get_event_loop()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._generate_signals, df, params)
            result = await loop.run_in_executor(None, lambda: future.result())

        return result

    def _generate_signals(self, df: pd.DataFrame, params: StrategyParameters) -> pd.DataFrame:
        """시그널 생성."""
        df = df.copy()

        # EMA 크로스오버 시그널
        df['ema_signal'] = 0
        df.loc[df['ema_short'] > df['ema_long'], 'ema_signal'] = 1
        df.loc[df['ema_short'] < df['ema_long'], 'ema_signal'] = -1

        # RSI 필터
        df['rsi_filter'] = 0
        df.loc[df['rsi'] < params.rsi_oversold, 'rsi_filter'] = 1  # 과매도
        df.loc[df['rsi'] > params.rsi_overbought, 'rsi_filter'] = -1  # 과매수

        # 최종 시그널 (EMA + RSI 조건)
        df['signal'] = 0
        df.loc[(df['ema_signal'] == 1) & (df['rsi_filter'] != -1), 'signal'] = 1  # 매수
        df.loc[(df['ema_signal'] == -1) & (df['rsi_filter'] != 1), 'signal'] = -1  # 매도

        return df

    async def _execute_backtest_async(
        self,
        df: pd.DataFrame,
        signals: pd.DataFrame,
        params: StrategyParameters
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """비동기로 백테스트 실행."""
        loop = asyncio.get_event_loop()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._execute_backtest, df, params)
            result = await loop.run_in_executor(None, lambda: future.result())

        return result

    def _execute_backtest(
        self,
        df: pd.DataFrame,
        params: StrategyParameters
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """백테스트 실행."""
        trades = []
        equity_curve = []

        cash = float(self.initial_capital)
        position = 0
        position_value = 0
        entry_price = 0

        for i, (timestamp, row) in enumerate(df.iterrows()):
            current_price = row['close']
            signal = row['signal']
            atr = row.get('atr', 0)

            # 포지션 가치 업데이트
            if position > 0:
                position_value = position * current_price

            total_equity = cash + position_value

            # 시그널 처리
            if signal == 1 and position == 0:  # 매수 진입
                position_size = (total_equity * params.position_size_percent / 100) / current_price
                position = position_size
                cash -= position_size * current_price
                entry_price = current_price

                trades.append({
                    'timestamp': timestamp,
                    'type': 'buy',
                    'price': current_price,
                    'quantity': position_size,
                    'value': position_size * current_price
                })

            elif signal == -1 and position > 0:  # 매도 청산
                cash += position * current_price

                pnl = (current_price - entry_price) * position
                trades.append({
                    'timestamp': timestamp,
                    'type': 'sell',
                    'price': current_price,
                    'quantity': position,
                    'value': position * current_price,
                    'pnl': pnl
                })

                position = 0
                position_value = 0

            # 손절 체크
            elif position > 0 and atr > 0:
                stop_loss_price = entry_price - (atr * params.stop_loss_atr_multiplier)
                if current_price <= stop_loss_price:
                    cash += position * current_price

                    pnl = (current_price - entry_price) * position
                    trades.append({
                        'timestamp': timestamp,
                        'type': 'stop_loss',
                        'price': current_price,
                        'quantity': position,
                        'value': position * current_price,
                        'pnl': pnl
                    })

                    position = 0
                    position_value = 0

            # 자산 곡선 기록
            total_equity = cash + position_value
            equity_curve.append({
                'timestamp': timestamp,
                'equity': total_equity,
                'cash': cash,
                'position_value': position_value
            })

        return trades, equity_curve

    def _generate_param_combinations(
        self,
        param_ranges: Dict[str, List[Any]],
        max_combinations: int
    ) -> List[Dict[str, Any]]:
        """파라미터 조합 생성."""
        import itertools

        # 모든 조합 생성
        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())

        all_combinations = list(itertools.product(*param_values))

        # 최대 조합 수 제한
        if len(all_combinations) > max_combinations:
            # 랜덤 샘플링
            import random
            all_combinations = random.sample(all_combinations, max_combinations)

        # 딕셔너리 형태로 변환
        combinations = []
        for combo in all_combinations:
            param_dict = dict(zip(param_names, combo))
            combinations.append(param_dict)

        return combinations