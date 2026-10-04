import time
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.engine import Engine, validate_scope
from app.models.signal import Signal
from app.utils.config import Settings, check_runtime


def v6_settings(tmp_path):
    return Settings(
        strategy_profile="V6_SOL_LONG",
        symbol="SOLUSDT",
        timeframe="5m",
        reward_risk_ratio="2",
        market_feed_enabled=True,
        max_quantity="10000",
        min_notional="5",
        price_tick="0.01",
        database_path=tmp_path / "paper.db",
        log_path=tmp_path / "orders.jsonl",
        kill_switch_path=tmp_path / "STOP",
        webhook_secret="a" * 32,
        admin_token="b" * 32,
    )


def signal(**changes):
    data = dict(
        signal_id="V6_SOL_LONG:123",
        timestamp=datetime.now(UTC),
        symbol="SOLUSDT",
        timeframe="5m",
        strategy="V6_SOL_LONG",
        action="LONG",
        price="150",
        stop_loss="145",
    )
    return Signal(**(data | changes))


def test_profile_enforcement(tmp_path):
    s = v6_settings(tmp_path)
    check_runtime(s)
    validate_scope(signal(), s)
    with pytest.raises(ValueError):
        validate_scope(signal(action="SHORT", stop_loss="155"), s)
    with pytest.raises(ValueError):
        validate_scope(signal(strategy="OTHER"), s)
    with pytest.raises(ValueError):
        validate_scope(signal(take_profit="160"), s)
    with pytest.raises(ValueError):
        check_runtime(s.model_copy(update={"market_feed_enabled": False}))


def test_feed_validation_and_stop(tmp_path):
    engine = Engine(v6_settings(tmp_path))
    feed = engine.feed
    feed.thread = SimpleNamespace(is_alive=lambda: True)
    assert not feed.fresh()
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"symbol": "SOLUSDT", "price": "150", "time": int(time.time() * 1000)}
        )
    )
    with httpx.Client(transport=transport) as client:
        feed.poll_once(client)
    assert feed.fresh()
    engine.store.enqueue(signal(), 100)
    engine.process_one()
    position = engine.state()["position"]
    assert position["side"] == "LONG"
    assert Decimal(position["take_profit"]) > Decimal("160")
    assert Decimal(position["quantity"]) * Decimal(position["entry"]) <= 5000
    engine.tick("SOLUSDT", Decimal("144"))
    assert engine.state()["position"] is None
    feed.last_success = time.monotonic() - 31
    assert not engine.state()["entries_enabled"]


@pytest.mark.parametrize(
    "price,age,symbol",
    [("NaN", 0, "SOLUSDT"), ("-1", 0, "SOLUSDT"), ("150", 60, "SOLUSDT"), ("150", 0, "BTCUSDT")],
)
def test_invalid_feed_never_updates(tmp_path, price, age, symbol):
    engine = Engine(v6_settings(tmp_path))
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json={"symbol": symbol, "price": price, "time": int((time.time() - age) * 1000)}
        )
    )
    with httpx.Client(transport=transport) as client, pytest.raises(ValueError):
        engine.feed.poll_once(client)
    assert engine.feed.price is None


def test_price_deviation_rejected(tmp_path):
    engine = Engine(v6_settings(tmp_path))
    engine.feed.thread = SimpleNamespace(is_alive=lambda: True)
    engine.feed.last_success = time.monotonic()
    engine.feed.price = Decimal("160")
    engine.store.enqueue(signal(), 100)
    engine.process_one()
    assert engine.store.signal_status("V6_SOL_LONG:123")["status"] == "REJECTED"
    assert engine.state()["position"] is None


def test_restart_preserves_v6_position_and_disabled_state(tmp_path):
    s = v6_settings(tmp_path)
    engine = Engine(s)
    engine.feed.thread = SimpleNamespace(is_alive=lambda: True)
    engine.feed.last_success = time.monotonic()
    engine.feed.price = Decimal("150")
    engine.store.enqueue(signal(), 100)
    engine.process_one()
    engine.control(False)
    restored = Engine(s)
    assert restored.state()["position"]["signal_id"] == "V6_SOL_LONG:123"
    assert not restored.state()["entries_enabled"]
    restored.tick("SOLUSDT", Decimal("144"))
    assert restored.state()["position"] is None
