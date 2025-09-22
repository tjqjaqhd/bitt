"""전략 파라미터 정의와 저장소 구현."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session, sessionmaker

from src.data.repositories import ConfigRepository
from src.utils.logger import get_logger

PARAMETER_CONFIG_KEY = "strategy.parameters"


@dataclass
class StrategyParameters:
    """전략 전반에서 사용하는 하이퍼 파라미터 묶음."""

    short_ema_period: int = 20
    long_ema_period: int = 60
    rsi_period: int = 14
    rsi_buy_min: Decimal = Decimal("50")
    rsi_buy_max: Decimal = Decimal("70")
    rsi_sell_threshold: Decimal = Decimal("45")
    rsi_overbought: Decimal = Decimal("70")
    rsi_oversold: Decimal = Decimal("30")
    atr_period: int = 14
    atr_multiplier: Decimal = Decimal("2")
    trailing_atr_multiplier: Decimal = Decimal("2")
    stop_loss_pct: Decimal = Decimal("0.03")
    target_profit_pct: Decimal = Decimal("0.02")
    partial_take_profit_pct: Decimal = Decimal("0.01")
    volume_ma_period: int = 10
    volume_ratio_threshold: Decimal = Decimal("0.8")
    max_concurrent_positions: int = 5
    max_risk_per_trade: Decimal = Decimal("0.03")
    capital_allocation_per_position: Decimal = Decimal("0.04")
    kelly_win_rate: Decimal = Decimal("0.55")
    kelly_reward_risk: Decimal = Decimal("1.8")
    correlation_threshold: Decimal = Decimal("0.8")
    parameter_refresh_minutes: int = 10

    def validate(self) -> None:
        if self.short_ema_period <= 0 or self.long_ema_period <= 0:
            raise ValueError("EMA 기간은 양수여야 합니다.")
        if self.short_ema_period >= self.long_ema_period:
            raise ValueError("단기 EMA는 장기 EMA보다 작아야 합니다.")
        if self.rsi_period <= 1:
            raise ValueError("RSI 기간은 2 이상이어야 합니다.")
        if self.rsi_buy_min >= self.rsi_buy_max:
            raise ValueError("RSI 매수 범위가 올바르지 않습니다.")
        if not (Decimal("0") < self.max_risk_per_trade <= Decimal("0.1")):
            raise ValueError("거래당 최대 리스크 비율은 0 ~ 10% 사이여야 합니다.")
        if self.max_concurrent_positions <= 0:
            raise ValueError("동시 보유 포지션 수는 1개 이상이어야 합니다.")
        if not (Decimal("0") <= self.correlation_threshold <= Decimal("1")):
            raise ValueError("상관관계 임계값은 0~1 사이여야 합니다.")

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for field_name, field_value in self.__dict__.items():
            if isinstance(field_value, Decimal):
                result[field_name] = str(field_value)
            else:
                result[field_name] = field_value
        return result

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StrategyParameters":
        data: Dict[str, Any] = {}
        for field_name, value in payload.items():
            if field_name in {"rsi_buy_min", "rsi_buy_max", "rsi_sell_threshold", "rsi_overbought", "rsi_oversold",
                              "atr_multiplier", "trailing_atr_multiplier", "stop_loss_pct", "target_profit_pct",
                              "partial_take_profit_pct", "volume_ratio_threshold", "max_risk_per_trade",
                              "capital_allocation_per_position", "kelly_win_rate", "kelly_reward_risk", "correlation_threshold"}:
                data[field_name] = Decimal(str(value))
            else:
                data[field_name] = value
        instance = cls(**data)
        instance.validate()
        return instance


class StrategyParameterStore:
    """DB에 저장된 전략 파라미터를 캐시와 함께 관리한다."""

    def __init__(
        self,
        session_factory: sessionmaker,
        config_repository: ConfigRepository | None = None,
        *,
        timezone_: timezone = timezone.utc,
    ) -> None:
        self._session_factory = session_factory
        self._repository = config_repository or ConfigRepository()
        self._cache: StrategyParameters | None = None
        self._cache_expire_at: Optional[datetime] = None
        self._timezone = timezone_
        self._logger = get_logger(__name__)

    def _load_from_db(self, session: Session) -> StrategyParameters:
        record = self._repository.get(session, key=PARAMETER_CONFIG_KEY)
        if record is None:
            params = StrategyParameters()
            params.validate()
            payload = json.dumps(params.to_dict(), ensure_ascii=False)
            self._repository.set(session, PARAMETER_CONFIG_KEY, payload, "기본 전략 파라미터")
            session.commit()
            return params
        data = json.loads(record.value)
        params = StrategyParameters.from_dict(data)
        return params

    def get_parameters(self, *, force_refresh: bool = False) -> StrategyParameters:
        now = datetime.now(tz=self._timezone)
        if not force_refresh and self._cache and self._cache_expire_at and now < self._cache_expire_at:
            return self._cache
        with self._session_factory() as session:
            params = self._load_from_db(session)
        self._cache = params
        ttl = timedelta(minutes=self._cache.parameter_refresh_minutes)
        self._cache_expire_at = now + ttl
        self._logger.debug("전략 파라미터 로드", extra={"refresh": force_refresh, "expires_at": self._cache_expire_at})
        return params

    def update_parameters(self, session: Session, params: StrategyParameters) -> None:
        params.validate()
        payload = json.dumps(params.to_dict(), ensure_ascii=False)
        self._repository.set(session, PARAMETER_CONFIG_KEY, payload, "전략 파라미터 업데이트")
        session.commit()
        self._cache = params
        self._cache_expire_at = datetime.now(tz=self._timezone) + timedelta(minutes=params.parameter_refresh_minutes)


__all__ = ["StrategyParameterStore", "StrategyParameters", "PARAMETER_CONFIG_KEY"]
