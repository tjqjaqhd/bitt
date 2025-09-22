"""시장 동기화 스케줄러."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..utils.logger import get_logger
from ..data.sync import MarketSynchronizer, SyncResult


@dataclass
class MarketSyncJob:
    """주기적으로 종목을 동기화하는 스케줄러."""

    synchronizer: MarketSynchronizer
    interval_minutes: int = 10
    _next_run_at: Optional[datetime] = None
    _last_result: Optional[SyncResult] = None

    def __post_init__(self) -> None:
        self._logger = get_logger(__name__)

    @property
    def next_run_at(self) -> datetime:
        if self._next_run_at is None:
            self._next_run_at = datetime.now(timezone.utc)
        return self._next_run_at

    @property
    def last_result(self) -> Optional[SyncResult]:
        return self._last_result

    def due(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return now >= self.next_run_at

    def run(self, now: Optional[datetime] = None) -> SyncResult:
        now = now or datetime.now(timezone.utc)
        result = self.synchronizer.sync()
        self._last_result = result
        self._next_run_at = now + timedelta(minutes=self.interval_minutes)
        self._logger.info(
            "시장 동기화 작업 실행", extra={"result": result.__dict__, "next_run_at": self._next_run_at.isoformat()}
        )
        return result

    def run_pending(self, now: Optional[datetime] = None) -> Optional[SyncResult]:
        if self.due(now):
            return self.run(now)
        return None


__all__ = ["MarketSyncJob"]

