from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.core.indicators import Candle

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture(scope="module")
def btc_krw_candles() -> list[Candle]:
    payload = json.loads(Path("tests/fixtures/bithumb_candles_btc_krw_1h.json").read_text())
    symbol = "BTC_KRW"
    return [Candle.from_raw(symbol, row) for row in payload["data"]]
