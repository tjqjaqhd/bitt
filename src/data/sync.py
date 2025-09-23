"""빗썸 종목 동기화 유틸리티."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Mapping, Optional

from sqlalchemy.orm import Session, sessionmaker

from ..exchange import BithumbClient, normalize_market_code
from ..utils.logger import get_logger
from .models import MarketWarningLevel
from .repositories import MarketRepository


RemoteMarketMap = Mapping[str, "RemoteMarket"]


@dataclass(frozen=True)
class RemoteMarket:
    """원격 API에서 조회한 종목 정보."""

    symbol: str
    korean_name: Optional[str]
    english_name: Optional[str]
    warning_level: MarketWarningLevel
    is_active: bool


@dataclass(frozen=True)
class SyncResult:
    """동기화 결과 요약."""

    new: int
    updated: int
    deactivated: int
    total: int


class MarketSynchronizer:
    """빗썸 공개 API를 이용해 시장 목록을 동기화한다."""

    def __init__(
        self,
        client: BithumbClient,
        session_factory: sessionmaker[Session] | Callable[[], Session],
        *,
        market_repository: Optional[MarketRepository] = None,
    ) -> None:
        self._client = client
        self._session_factory: Callable[[], Session]
        if isinstance(session_factory, sessionmaker):
            self._session_factory = session_factory
        else:
            self._session_factory = session_factory  # type: ignore[assignment]
        self._market_repo = market_repository or MarketRepository()
        self._logger = get_logger(__name__)

    def _fetch_ticker_snapshot(self) -> dict[str, dict[str, str]]:
        payload = self._client.get("/public/ticker/ALL_KRW")
        data = payload.get("data", {})
        return {key: value for key, value in data.items() if key.upper() != "DATE"}

    def _fetch_asset_status(self) -> dict[str, dict[str, int]]:
        payload = self._client.get("/public/assetsstatus/ALL_KRW")
        return payload.get("data", {})

    def _derive_warning_level(self, deposit_status: int | None, withdrawal_status: int | None) -> MarketWarningLevel:
        if deposit_status == 1 and withdrawal_status == 1:
            return MarketWarningLevel.NORMAL
        if deposit_status == 0 and withdrawal_status == 0:
            return MarketWarningLevel.SUSPENDED
        return MarketWarningLevel.PARTIAL_LIMIT

    def fetch_remote_markets(self) -> RemoteMarketMap:
        tickers = self._fetch_ticker_snapshot()
        status_payload = self._fetch_asset_status()

        markets: Dict[str, RemoteMarket] = {}
        for symbol, _ticker in tickers.items():
            normalized = normalize_market_code(symbol, "KRW")
            status_info = status_payload.get(symbol, {})
            deposit_status = status_info.get("deposit_status")
            withdrawal_status = status_info.get("withdrawal_status")
            warning = self._derive_warning_level(deposit_status, withdrawal_status)
            is_active = deposit_status == 1 and withdrawal_status == 1
            markets[normalized] = RemoteMarket(
                symbol=normalized,
                korean_name=symbol,
                english_name=symbol,
                warning_level=warning,
                is_active=is_active,
            )
        return markets

    def sync(self) -> SyncResult:
        remote_markets = self.fetch_remote_markets()
        total = len(remote_markets)
        new_count = 0
        updated_count = 0

        session: Session = self._session_factory()
        try:
            for market in remote_markets.values():
                existing = self._market_repo.get_by_symbol(session, market.symbol)
                if existing:
                    previous_state = (
                        existing.korean_name,
                        existing.english_name,
                        existing.warning_level,
                        existing.is_active,
                    )
                    self._market_repo.upsert(
                        session,
                        symbol=market.symbol,
                        korean_name=market.korean_name,
                        english_name=market.english_name,
                        warning_level=market.warning_level,
                        is_active=market.is_active,
                    )
                    if previous_state != (
                        market.korean_name,
                        market.english_name,
                        market.warning_level,
                        market.is_active,
                    ):
                        updated_count += 1
                else:
                    self._market_repo.upsert(
                        session,
                        symbol=market.symbol,
                        korean_name=market.korean_name,
                        english_name=market.english_name,
                        warning_level=market.warning_level,
                        is_active=market.is_active,
                    )
                    new_count += 1

            deactivated = self._market_repo.deactivate_missing(session, remote_markets.keys())
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        self._logger.info(
            "마켓 동기화 완료", extra={"new": new_count, "updated": updated_count, "deactivated": deactivated, "total": total}
        )
        return SyncResult(new=new_count, updated=updated_count, deactivated=deactivated, total=total)


__all__ = [
    "MarketSynchronizer",
    "RemoteMarket",
    "SyncResult",
]

