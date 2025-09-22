"""시간 관련 헬퍼 함수 모음."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

_DEFAULT_TIMEZONE = "Asia/Seoul"


def utc_now() -> datetime:
    """UTC 기준 현재 시간을 반환한다."""
    return datetime.now(timezone.utc)


def now_in_timezone(tz_name: str = _DEFAULT_TIMEZONE) -> datetime:
    """지정된 시간대의 현재 시간을 반환한다."""
    return utc_now().astimezone(ZoneInfo(tz_name))


def ensure_timezone(dt: datetime, tz_name: str = _DEFAULT_TIMEZONE) -> datetime:
    """시간대 정보가 없으면 지정된 시간대를 부여하고, 있으면 해당 시간대로 변환한다."""
    zone = ZoneInfo(tz_name)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=zone)
    return dt.astimezone(zone)


def to_timestamp(dt: datetime) -> float:
    """datetime 객체를 POSIX 타임스탬프로 변환한다."""
    aware_dt = dt if dt.tzinfo is not None else ensure_timezone(dt)
    return aware_dt.timestamp()


def parse_isoformat(value: str, tz_name: Optional[str] = None) -> datetime:
    """ISO8601 문자열을 datetime으로 변환한다."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        target_tz = tz_name or _DEFAULT_TIMEZONE
        dt = dt.replace(tzinfo=ZoneInfo(target_tz))
    if tz_name:
        dt = dt.astimezone(ZoneInfo(tz_name))
    return dt


__all__ = [
    "ensure_timezone",
    "now_in_timezone",
    "parse_isoformat",
    "to_timestamp",
    "utc_now",
]
