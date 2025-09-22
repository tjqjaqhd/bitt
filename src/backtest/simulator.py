"""백테스트 시뮬레이션 모드 인터페이스 (기본 구조)"""

from typing import Any
from src.core.strategy import StrategyEngine, StrategyContext

class BacktestSimulator:
    """시뮬레이션 모드 지원용 백테스트 엔진 (예정: Phase 5에서 본격 구현)"""
    def __init__(self, engine: StrategyEngine):
        self.engine = engine

    def run(self, data: Any):
        """시뮬레이션 실행 (예시)"""
        # TODO: Phase 5에서 실제 구현
        results = []
        for context in data:
            result = self.engine.evaluate(context)
            results.append(result)
        return results
