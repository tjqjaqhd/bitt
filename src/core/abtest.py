"""A/B 테스트 지원 구조 (기본)"""

from typing import Any, Callable
from .parameters import StrategyParameters

class ABTestRunner:
    """A/B 테스트 실행기 (예정: Phase 5에서 본격 구현)"""
    def __init__(self, variants: dict[str, StrategyParameters]):
        self.variants = variants

    def run(self, test_fn: Callable[[StrategyParameters], Any]):
        """각 파라미터 조합에 대해 테스트 실행"""
        results = {}
        for name, params in self.variants.items():
            results[name] = test_fn(params)
        return results
