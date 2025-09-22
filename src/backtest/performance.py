"""백테스트 성과 분석."""

import math
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

import pandas as pd


@dataclass
class PerformanceMetrics:
    """성과 지표."""
    # 수익률 지표
    total_return: float
    annualized_return: float
    daily_return_mean: float
    daily_return_std: float

    # 리스크 지표
    max_drawdown: float
    volatility: float
    downside_deviation: float
    var_95: float  # Value at Risk (95%)
    var_99: float  # Value at Risk (99%)

    # 효율성 지표
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    information_ratio: float

    # 거래 통계
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    avg_trade_duration: float  # 평균 보유 기간 (일)

    # 기타
    max_consecutive_wins: int
    max_consecutive_losses: int
    recovery_factor: float  # 총 수익 / 최대 낙폭


class PerformanceAnalyzer:
    """성과 분석기."""

    def __init__(self, risk_free_rate: float = 0.02):
        """
        성과 분석기 초기화.

        Args:
            risk_free_rate: 무위험 수익률 (연율, 기본 2%)
        """
        self.risk_free_rate = risk_free_rate
        self.logger = logging.getLogger(self.__class__.__name__)

    def analyze(
        self,
        equity_curve: List[Tuple[datetime, float]],
        trades: List[Dict],
        initial_capital: float
    ) -> PerformanceMetrics:
        """
        성과 분석 실행.

        Args:
            equity_curve: 자산 곡선 [(timestamp, equity), ...]
            trades: 거래 내역 리스트
            initial_capital: 초기 자본

        Returns:
            성과 지표
        """
        if not equity_curve:
            raise ValueError("자산 곡선 데이터가 없습니다.")

        self.logger.info("성과 분석 시작")

        # 데이터 준비
        df = self._prepare_dataframe(equity_curve, initial_capital)

        # 수익률 지표 계산
        total_return = self._calculate_total_return(df)
        annualized_return = self._calculate_annualized_return(df)
        daily_return_mean = df['daily_return'].mean()
        daily_return_std = df['daily_return'].std()

        # 리스크 지표 계산
        max_drawdown = self._calculate_max_drawdown(df)
        volatility = self._calculate_volatility(df)
        downside_deviation = self._calculate_downside_deviation(df)
        var_95, var_99 = self._calculate_var(df)

        # 효율성 지표 계산
        sharpe_ratio = self._calculate_sharpe_ratio(df)
        sortino_ratio = self._calculate_sortino_ratio(df)
        calmar_ratio = self._calculate_calmar_ratio(annualized_return, max_drawdown)
        information_ratio = self._calculate_information_ratio(df)

        # 거래 통계 계산
        trade_stats = self._calculate_trade_statistics(trades)

        # 기타 지표
        consecutive_stats = self._calculate_consecutive_stats(df)
        recovery_factor = total_return / abs(max_drawdown) if max_drawdown != 0 else 0

        metrics = PerformanceMetrics(
            # 수익률 지표
            total_return=total_return,
            annualized_return=annualized_return,
            daily_return_mean=daily_return_mean,
            daily_return_std=daily_return_std,

            # 리스크 지표
            max_drawdown=max_drawdown,
            volatility=volatility,
            downside_deviation=downside_deviation,
            var_95=var_95,
            var_99=var_99,

            # 효율성 지표
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            information_ratio=information_ratio,

            # 거래 통계
            total_trades=trade_stats['total_trades'],
            winning_trades=trade_stats['winning_trades'],
            losing_trades=trade_stats['losing_trades'],
            win_rate=trade_stats['win_rate'],
            avg_win=trade_stats['avg_win'],
            avg_loss=trade_stats['avg_loss'],
            profit_factor=trade_stats['profit_factor'],
            avg_trade_duration=trade_stats['avg_trade_duration'],

            # 기타
            max_consecutive_wins=consecutive_stats['max_wins'],
            max_consecutive_losses=consecutive_stats['max_losses'],
            recovery_factor=recovery_factor
        )

        self.logger.info("성과 분석 완료")
        return metrics

    def _prepare_dataframe(self, equity_curve: List[Tuple[datetime, float]], initial_capital: float) -> pd.DataFrame:
        """데이터프레임 준비."""
        df = pd.DataFrame(equity_curve, columns=['timestamp', 'equity'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)

        # 수익률 계산
        df['return_pct'] = df['equity'].pct_change()
        df['daily_return'] = df['return_pct']

        # 누적 수익률
        df['cumulative_return'] = (df['equity'] / initial_capital - 1) * 100

        # 드로다운 계산
        df['running_max'] = df['equity'].expanding().max()
        df['drawdown'] = (df['equity'] - df['running_max']) / df['running_max'] * 100

        return df

    def _calculate_total_return(self, df: pd.DataFrame) -> float:
        """총 수익률 계산."""
        if len(df) < 2:
            return 0.0

        initial_equity = df['equity'].iloc[0]
        final_equity = df['equity'].iloc[-1]

        return (final_equity - initial_equity) / initial_equity * 100

    def _calculate_annualized_return(self, df: pd.DataFrame) -> float:
        """연환산 수익률 계산."""
        if len(df) < 2:
            return 0.0

        # 기간 계산
        start_date = df.index[0]
        end_date = df.index[-1]
        days = (end_date - start_date).days

        if days == 0:
            return 0.0

        years = days / 365.25

        initial_equity = df['equity'].iloc[0]
        final_equity = df['equity'].iloc[-1]

        if initial_equity <= 0:
            return 0.0

        annualized_return = (pow(final_equity / initial_equity, 1 / years) - 1) * 100
        return annualized_return

    def _calculate_max_drawdown(self, df: pd.DataFrame) -> float:
        """최대 낙폭 계산."""
        if 'drawdown' not in df.columns:
            return 0.0
        return df['drawdown'].min()

    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """변동성 계산 (연환산)."""
        if len(df) < 2:
            return 0.0

        daily_vol = df['daily_return'].std()
        annualized_vol = daily_vol * math.sqrt(252) * 100  # 252 trading days
        return annualized_vol

    def _calculate_downside_deviation(self, df: pd.DataFrame) -> float:
        """하방 편차 계산."""
        if len(df) < 2:
            return 0.0

        negative_returns = df['daily_return'][df['daily_return'] < 0]
        if len(negative_returns) == 0:
            return 0.0

        downside_dev = negative_returns.std() * math.sqrt(252) * 100
        return downside_dev

    def _calculate_var(self, df: pd.DataFrame) -> Tuple[float, float]:
        """VaR 계산."""
        if len(df) < 2:
            return 0.0, 0.0

        returns = df['daily_return'].dropna()
        var_95 = returns.quantile(0.05) * 100
        var_99 = returns.quantile(0.01) * 100

        return var_95, var_99

    def _calculate_sharpe_ratio(self, df: pd.DataFrame) -> float:
        """샤프 비율 계산."""
        if len(df) < 2:
            return 0.0

        excess_returns = df['daily_return'] - (self.risk_free_rate / 252)

        if excess_returns.std() == 0:
            return 0.0

        sharpe = excess_returns.mean() / excess_returns.std() * math.sqrt(252)
        return sharpe

    def _calculate_sortino_ratio(self, df: pd.DataFrame) -> float:
        """소르티노 비율 계산."""
        if len(df) < 2:
            return 0.0

        excess_returns = df['daily_return'] - (self.risk_free_rate / 252)
        negative_returns = excess_returns[excess_returns < 0]

        if len(negative_returns) == 0 or negative_returns.std() == 0:
            return 0.0

        sortino = excess_returns.mean() / negative_returns.std() * math.sqrt(252)
        return sortino

    def _calculate_calmar_ratio(self, annualized_return: float, max_drawdown: float) -> float:
        """칼마 비율 계산."""
        if max_drawdown == 0:
            return 0.0
        return annualized_return / abs(max_drawdown)

    def _calculate_information_ratio(self, df: pd.DataFrame) -> float:
        """정보 비율 계산 (벤치마크 대비)."""
        # 벤치마크가 없으므로 0으로 가정
        if len(df) < 2:
            return 0.0

        active_returns = df['daily_return']  # 벤치마크 대비 초과 수익

        if active_returns.std() == 0:
            return 0.0

        info_ratio = active_returns.mean() / active_returns.std() * math.sqrt(252)
        return info_ratio

    def _calculate_trade_statistics(self, trades: List[Dict]) -> Dict:
        """거래 통계 계산."""
        if not trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'avg_trade_duration': 0.0
            }

        # 거래쌍 생성 (매수-매도)
        trade_pairs = self._create_trade_pairs(trades)

        if not trade_pairs:
            return {
                'total_trades': len(trades),
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'profit_factor': 0.0,
                'avg_trade_duration': 0.0
            }

        winning_trades = [tp for tp in trade_pairs if tp['pnl'] > 0]
        losing_trades = [tp for tp in trade_pairs if tp['pnl'] < 0]

        total_pairs = len(trade_pairs)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)

        win_rate = (win_count / total_pairs * 100) if total_pairs > 0 else 0.0

        avg_win = sum(tp['pnl'] for tp in winning_trades) / win_count if win_count > 0 else 0.0
        avg_loss = sum(tp['pnl'] for tp in losing_trades) / loss_count if loss_count > 0 else 0.0

        gross_profit = sum(tp['pnl'] for tp in winning_trades)
        gross_loss = abs(sum(tp['pnl'] for tp in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # 평균 거래 기간
        durations = [tp['duration_days'] for tp in trade_pairs]
        avg_duration = sum(durations) / len(durations) if durations else 0.0

        return {
            'total_trades': total_pairs,
            'winning_trades': win_count,
            'losing_trades': loss_count,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'avg_trade_duration': avg_duration
        }

    def _create_trade_pairs(self, trades: List[Dict]) -> List[Dict]:
        """거래쌍 생성 (매수-매도)."""
        pairs = []
        positions = {}  # symbol -> [buy_trades]

        for trade in sorted(trades, key=lambda x: x['timestamp']):
            symbol = trade['symbol']
            side = trade['side']

            if symbol not in positions:
                positions[symbol] = []

            if side == 'buy':
                positions[symbol].append(trade)
            elif side == 'sell' and positions[symbol]:
                # FIFO로 매칭
                buy_trade = positions[symbol].pop(0)

                quantity = min(trade['quantity'], buy_trade['quantity'])
                buy_cost = quantity * buy_trade['price'] + buy_trade['commission']
                sell_proceeds = quantity * trade['price'] - trade['commission']
                pnl = sell_proceeds - buy_cost

                duration = (trade['timestamp'] - buy_trade['timestamp']).days

                pairs.append({
                    'symbol': symbol,
                    'buy_price': buy_trade['price'],
                    'sell_price': trade['price'],
                    'quantity': quantity,
                    'pnl': pnl,
                    'duration_days': duration,
                    'buy_time': buy_trade['timestamp'],
                    'sell_time': trade['timestamp']
                })

                # 부분 체결 처리
                if buy_trade['quantity'] > quantity:
                    buy_trade['quantity'] -= quantity
                    positions[symbol].insert(0, buy_trade)

        return pairs

    def _calculate_consecutive_stats(self, df: pd.DataFrame) -> Dict:
        """연속 승패 통계."""
        if len(df) < 2:
            return {'max_wins': 0, 'max_losses': 0}

        returns = df['daily_return'].dropna()

        max_wins = 0
        max_losses = 0
        current_wins = 0
        current_losses = 0

        for ret in returns:
            if ret > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif ret < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)
            else:
                current_wins = 0
                current_losses = 0

        return {'max_wins': max_wins, 'max_losses': max_losses}

    def compare_to_benchmark(
        self,
        strategy_curve: List[Tuple[datetime, float]],
        benchmark_curve: List[Tuple[datetime, float]]
    ) -> Dict:
        """벤치마크 대비 성과 비교."""
        if not strategy_curve or not benchmark_curve:
            return {}

        # DataFrame 생성
        strategy_df = pd.DataFrame(strategy_curve, columns=['timestamp', 'strategy'])
        benchmark_df = pd.DataFrame(benchmark_curve, columns=['timestamp', 'benchmark'])

        # 타임스탬프 기준 병합
        strategy_df['timestamp'] = pd.to_datetime(strategy_df['timestamp'])
        benchmark_df['timestamp'] = pd.to_datetime(benchmark_df['timestamp'])

        merged_df = pd.merge(strategy_df, benchmark_df, on='timestamp', how='inner')

        if len(merged_df) < 2:
            return {}

        # 수익률 계산
        merged_df['strategy_return'] = merged_df['strategy'].pct_change()
        merged_df['benchmark_return'] = merged_df['benchmark'].pct_change()
        merged_df['excess_return'] = merged_df['strategy_return'] - merged_df['benchmark_return']

        # 누적 수익률
        strategy_total = (merged_df['strategy'].iloc[-1] / merged_df['strategy'].iloc[0] - 1) * 100
        benchmark_total = (merged_df['benchmark'].iloc[-1] / merged_df['benchmark'].iloc[0] - 1) * 100

        # 베타 계산
        covariance = merged_df['strategy_return'].cov(merged_df['benchmark_return'])
        benchmark_variance = merged_df['benchmark_return'].var()
        beta = covariance / benchmark_variance if benchmark_variance != 0 else 0

        # 알파 계산 (CAPM)
        strategy_mean = merged_df['strategy_return'].mean() * 252
        benchmark_mean = merged_df['benchmark_return'].mean() * 252
        alpha = strategy_mean - (self.risk_free_rate + beta * (benchmark_mean - self.risk_free_rate))

        # 트래킹 에러
        tracking_error = merged_df['excess_return'].std() * math.sqrt(252) * 100

        return {
            'strategy_total_return': strategy_total,
            'benchmark_total_return': benchmark_total,
            'excess_return': strategy_total - benchmark_total,
            'alpha': alpha * 100,
            'beta': beta,
            'tracking_error': tracking_error,
            'information_ratio': (merged_df['excess_return'].mean() / merged_df['excess_return'].std() * math.sqrt(252)) if merged_df['excess_return'].std() != 0 else 0
        }

    def generate_summary_report(self, metrics: PerformanceMetrics) -> str:
        """성과 요약 리포트 생성."""
        report = "=" * 50 + "\n"
        report += "백테스트 성과 분석 리포트\n"
        report += "=" * 50 + "\n\n"

        # 수익률 지표
        report += "📈 수익률 지표\n"
        report += "-" * 20 + "\n"
        report += f"총 수익률: {metrics.total_return:.2f}%\n"
        report += f"연환산 수익률: {metrics.annualized_return:.2f}%\n"
        report += f"일평균 수익률: {metrics.daily_return_mean:.4f}%\n"
        report += f"일수익률 표준편차: {metrics.daily_return_std:.4f}%\n\n"

        # 리스크 지표
        report += "⚠️ 리스크 지표\n"
        report += "-" * 20 + "\n"
        report += f"최대 낙폭: {metrics.max_drawdown:.2f}%\n"
        report += f"변동성 (연환산): {metrics.volatility:.2f}%\n"
        report += f"하방 편차: {metrics.downside_deviation:.2f}%\n"
        report += f"VaR (95%): {metrics.var_95:.2f}%\n"
        report += f"VaR (99%): {metrics.var_99:.2f}%\n\n"

        # 효율성 지표
        report += "⚡ 효율성 지표\n"
        report += "-" * 20 + "\n"
        report += f"샤프 비율: {metrics.sharpe_ratio:.3f}\n"
        report += f"소르티노 비율: {metrics.sortino_ratio:.3f}\n"
        report += f"칼마 비율: {metrics.calmar_ratio:.3f}\n"
        report += f"정보 비율: {metrics.information_ratio:.3f}\n\n"

        # 거래 통계
        report += "📊 거래 통계\n"
        report += "-" * 20 + "\n"
        report += f"총 거래 수: {metrics.total_trades}회\n"
        report += f"수익 거래: {metrics.winning_trades}회\n"
        report += f"손실 거래: {metrics.losing_trades}회\n"
        report += f"승률: {metrics.win_rate:.1f}%\n"
        report += f"평균 수익: {metrics.avg_win:.2f}원\n"
        report += f"평균 손실: {metrics.avg_loss:.2f}원\n"
        report += f"Profit Factor: {metrics.profit_factor:.2f}\n"
        report += f"평균 보유 기간: {metrics.avg_trade_duration:.1f}일\n\n"

        # 기타
        report += "🔄 기타 지표\n"
        report += "-" * 20 + "\n"
        report += f"최대 연속 승: {metrics.max_consecutive_wins}회\n"
        report += f"최대 연속 패: {metrics.max_consecutive_losses}회\n"
        report += f"회복 팩터: {metrics.recovery_factor:.2f}\n"

        return report