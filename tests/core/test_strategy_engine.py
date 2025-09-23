from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from src.core import (
    PortfolioPosition,
    PortfolioState,
    SignalGenerator,
    StrategyContext,
    StrategyEngine,
    StrategyParameterStore,
    StrategyParameters,
)
from src.data import Base, StrategySignalRepository
from src.data.database import create_db_engine


@pytest.fixture()
def memory_session_factory():
    engine = create_db_engine(url="sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def slice_candles(candles, count: int):
    return candles[:count]


def test_parameter_store_roundtrip(memory_session_factory) -> None:
    session_factory = memory_session_factory
    store = StrategyParameterStore(session_factory)
    params = store.get_parameters(force_refresh=True)
    assert params.short_ema_period == 20
    params.volume_ratio_threshold = Decimal("0.9")
    params.validate()
    with session_factory() as session:
        store.update_parameters(session, params)
    updated = store.get_parameters(force_refresh=True)
    assert updated.volume_ratio_threshold == Decimal("0.9")


def test_signal_generator_buy_signal(btc_krw_candles) -> None:
    generator = SignalGenerator()
    params = StrategyParameters()
    subset = slice_candles(btc_krw_candles, 147)
    decision = generator.generate(
        symbol="BTC_KRW",
        candles=subset,
        portfolio=PortfolioState(),
        parameters=params,
    )
    assert decision.signal_type.value == "BUY"
    assert decision.strength > Decimal("0")
    assert "EMA 골든크로스" in decision.reasons


def test_signal_generator_sell_signal(btc_krw_candles) -> None:
    generator = SignalGenerator()
    params = StrategyParameters()
    subset = slice_candles(btc_krw_candles, 143)
    position = PortfolioPosition(
        symbol="BTC_KRW",
        quantity=Decimal("0.005"),
        avg_price=subset[-2].close,
        entry_time=subset[-2].timestamp,
    )
    portfolio = PortfolioState([position])
    decision = generator.generate(
        symbol="BTC_KRW",
        candles=subset,
        portfolio=portfolio,
        parameters=params,
    )
    assert decision.signal_type.value == "SELL"
    assert any(reason.startswith("EMA") for reason in decision.reasons)


def test_strategy_engine_records_signal(memory_session_factory, btc_krw_candles) -> None:
    session_factory = memory_session_factory
    engine = StrategyEngine(session_factory)
    subset = slice_candles(btc_krw_candles, 147)
    context = StrategyContext(
        symbol="BTC_KRW",
        candles=subset,
        equity=Decimal("1000000000"),
        portfolio=PortfolioState(),
        as_of=subset[-1].timestamp,
    )
    result = engine.evaluate(context)
    assert result.signal.signal_type.value == "BUY"
    assert result.risk.quantity > Decimal("0")
    assert result.risk.partial_take_profit is not None

    with session_factory() as session:
        repo = StrategySignalRepository()
        records = repo.list(session)
        assert len(records) == 1
        record = records[0]
        assert record.signal_type.value == "BUY"
        assert record.symbol == "BTC_KRW"
