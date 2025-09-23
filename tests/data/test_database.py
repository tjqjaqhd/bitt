from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.data import (
    Base,
    Market,
    MarketRepository,
    MarketSynchronizer,
    MarketWarningLevel,
    SyncResult,
    backup_database,
    create_db_engine,
)


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_create_engine_resolves_sqlite_path(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "custom" / "app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

    engine = create_db_engine()

    resolved = Path(str(engine.url.database))
    assert resolved == db_path
    assert resolved.parent.exists()


def test_market_repository_upsert_and_deactivate() -> None:
    engine = create_db_engine(url="sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    repo = MarketRepository()

    with SessionLocal() as session:
        market = repo.upsert(
            session,
            symbol="BTC_KRW",
            korean_name="BTC",
            english_name="BTC",
            warning_level=MarketWarningLevel.NORMAL,
            is_active=True,
        )
        session.commit()
        assert market.id is not None

    with SessionLocal() as session:
        market = repo.get_by_symbol(session, "BTC_KRW")
        assert market is not None
        assert market.is_active is True
        repo.deactivate_missing(session, [])
        session.commit()

    with SessionLocal() as session:
        market = repo.get_by_symbol(session, "BTC_KRW")
        assert market is not None
        assert market.is_active is False


def test_market_synchronizer_syncs_remote_markets() -> None:
    engine = create_db_engine(url="sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    repo = MarketRepository()

    ticker_payload = json.loads(Path("tests/fixtures/bithumb_ticker_all_krw.json").read_text())
    status_payload = json.loads(Path("tests/fixtures/bithumb_assetsstatus_all_krw.json").read_text())

    class DummyClient:
        def __init__(self) -> None:
            self.calls: dict[str, int] = {}

        def get(self, endpoint: str, **_: object) -> dict:
            self.calls[endpoint] = self.calls.get(endpoint, 0) + 1
            if endpoint == "/public/ticker/ALL_KRW":
                return ticker_payload
            if endpoint == "/public/assetsstatus/ALL_KRW":
                return status_payload
            raise AssertionError(f"Unexpected endpoint: {endpoint}")

    dummy_client = DummyClient()
    synchronizer = MarketSynchronizer(dummy_client, SessionLocal, market_repository=repo)  # type: ignore[arg-type]

    with SessionLocal() as session:
        repo.upsert(
            session,
            symbol="FAKE_KRW",
            korean_name="FAKE",
            english_name="FAKE",
            warning_level=MarketWarningLevel.SUSPENDED,
            is_active=True,
        )
        session.commit()

    result = synchronizer.sync()
    assert isinstance(result, SyncResult)
    assert result.total == len(ticker_payload["data"]) - 1  # exclude "date"
    assert result.new > 0
    assert result.deactivated >= 1

    with SessionLocal() as session:
        btc = repo.get_by_symbol(session, "BTC_KRW")
        assert btc is not None
        assert btc.symbol == "BTC_KRW"
        assert btc.warning_level in {
            MarketWarningLevel.NORMAL,
            MarketWarningLevel.PARTIAL_LIMIT,
            MarketWarningLevel.SUSPENDED,
        }
        fake = repo.get_by_symbol(session, "FAKE_KRW")
        assert fake is not None
        assert fake.is_active is False


def test_backup_database_creates_and_prunes(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "app.db"
    db_path.write_text("dummy")

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    now = datetime(2024, 1, 1, tzinfo=timezone.utc)
    backup_path = backup_database(retention_days=1, now=now)
    assert backup_path.exists()

    old_backup = backup_path.parent / "app-20230101000000.db"
    old_backup.write_text("old")
    old_time = (now - timedelta(days=5)).timestamp()
    old_backup.touch()
    old_backup.chmod(0o644)
    # update mtime to old timestamp
    os.utime(old_backup, (old_time, old_time))

    backup_database(retention_days=1, now=now)
    assert not old_backup.exists()


def test_market_sync_job_interval() -> None:
    from src.jobs import MarketSyncJob

    class DummySynchronizer:
        def __init__(self) -> None:
            self.calls = 0

        def sync(self) -> SyncResult:
            self.calls += 1
            return SyncResult(new=0, updated=0, deactivated=0, total=0)

    synchronizer = DummySynchronizer()
    job = MarketSyncJob(synchronizer=synchronizer, interval_minutes=10)

    start = job.next_run_at
    assert job.due(start)
    result = job.run(start)
    assert synchronizer.calls == 1
    assert isinstance(result, SyncResult)

    later = start + timedelta(minutes=5)
    assert job.run_pending(later) is None
    finish = start + timedelta(minutes=10)
    job.run_pending(finish)
    assert synchronizer.calls == 2
