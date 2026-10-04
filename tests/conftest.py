from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import SecretStr

from app.engine import Engine
from app.models.signal import Signal
from app.utils.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_path=tmp_path / "paper.sqlite3",
        log_path=tmp_path / "orders.jsonl",
        kill_switch_path=tmp_path / "STOP_TRADING",
        webhook_secret=SecretStr("w" * 32),
        admin_token=SecretStr("a" * 32),
        paper_fee_rate=Decimal(0),
        paper_slippage_bps=Decimal(0),
    )


@pytest.fixture
def engine(settings):
    return Engine(settings)


def make_signal(signal_id="entry-1", action="LONG", **overrides):
    data = {
        "signal_id": signal_id,
        "timestamp": datetime.now(UTC),
        "symbol": "BTCUSDT",
        "action": action,
        "strategy": "EXTERNAL-V1",
        "timeframe": "4H",
        "price": "100000",
    }
    if action in ("LONG", "SHORT"):
        data["stop_loss"] = "98000" if action == "LONG" else "102000"
    data.update(overrides)
    return Signal.model_validate(data)


def execute(engine, signal):
    engine.store.enqueue(signal, engine.settings.queue_limit)
    while engine.process_one():
        pass
    return engine.store.signal_status(signal.signal_id)
