from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine import Engine
from app.exchange.paper import PaperExchange
from app.storage import QueueFull, SignalConflict
from tests.conftest import execute, make_signal

D = Decimal


@pytest.mark.parametrize("action,side", [("LONG", "LONG"), ("SHORT", "SHORT")])
def test_entry_and_protection(engine, action, side):
    result = execute(engine, make_signal(action=action))
    assert result["status"] == "PROCESSED"
    assert result["result"]["status"] == "FILLED"
    state = engine.state()
    assert state["position"]["side"] == side
    assert result["result"]["stop_order"]["reduce_only"]
    assert result["result"]["tp_order"]["reduce_only"]


@pytest.mark.parametrize(
    "entry,closing", [("LONG", "CLOSE_LONG"), ("SHORT", "CLOSE_SHORT"), ("LONG", "CLOSE_ALL")]
)
def test_close_is_reduce_only_and_never_flips(engine, entry, closing):
    execute(engine, make_signal(action=entry))
    result = execute(engine, make_signal("close", closing))
    assert result["result"]["status"] == "CLOSED"
    assert result["result"]["reduce_only"] is True
    assert engine.state()["position"] is None
    assert execute(engine, make_signal("close-again", closing))["result"]["status"] == "NO_POSITION"


def test_wrong_side_close_skipped(engine):
    execute(engine, make_signal())
    assert execute(engine, make_signal("close", "CLOSE_SHORT"))["result"]["status"] == "SKIPPED"
    assert engine.state()["position"]["side"] == "LONG"


def test_opposite_entry_does_not_reverse(engine):
    execute(engine, make_signal())
    result = execute(engine, make_signal("short", "SHORT"))
    assert result["result"]["status"] == "SKIPPED"
    assert engine.state()["position"]["side"] == "LONG"


@pytest.mark.parametrize(
    "action,price,reason,balance",
    [
        ("LONG", "98000", "STOP_LOSS", "990"),
        ("LONG", "103000", "TAKE_PROFIT", "1015"),
        ("SHORT", "102000", "STOP_LOSS", "990"),
        ("SHORT", "97000", "TAKE_PROFIT", "1015"),
        ("LONG", "96000", "STOP_LOSS", "980"),
    ],
)
def test_triggers_and_gap_losses(engine, action, price, reason, balance):
    execute(engine, make_signal(action=action))
    state = engine.tick("BTCUSDT", D(price))
    assert state["trigger"]["reason"] == reason
    assert state["position"] is None
    assert D(state["balance"]) == D(balance)


def test_fee_pnl_accounting(engine):
    engine.settings.paper_fee_rate = D("0.0005")
    execute(engine, make_signal())
    before = D(engine.state()["balance"])
    assert before < D(1000)
    result = engine.tick("BTCUSDT", D(103000))["trigger"]
    assert D(result["balance"]) == D(1000) + D(result["net_pnl"])


@pytest.mark.parametrize("action,stop", [("LONG", "98000"), ("SHORT", "102000")])
def test_modeled_stop_cost_includes_slippage_and_fees_on_actual_exit(engine, action, stop):
    engine.settings.quantity_step = D("0.00000001")
    engine.settings.paper_fee_rate = D("0.0005")
    engine.settings.paper_slippage_bps = D("2")
    result = execute(engine, make_signal(action=action))
    expected_loss = D(result["result"]["estimated_stop_loss"])
    closed = engine.tick("BTCUSDT", D(stop))["trigger"]
    actual_loss = -D(closed["net_pnl"])
    assert actual_loss == expected_loss
    assert actual_loss <= D("10")


def test_duplicates_survive_restart_and_close(engine, settings):
    signal = make_signal()
    execute(engine, signal)
    engine.tick("BTCUSDT", D(103000))
    restarted = Engine(settings)
    status, duplicate = restarted.store.enqueue(signal, 100)
    assert status == "PROCESSED" and duplicate
    assert not restarted.process_one()
    assert restarted.state()["position"] is None
    assert D(restarted.state()["balance"]) == D(1015)


def test_conflicting_duplicate_rejected(engine):
    signal = make_signal()
    execute(engine, signal)
    with pytest.raises(SignalConflict):
        engine.store.enqueue(signal.model_copy(update={"price": D(101000)}), 100)


def test_pending_queue_survives_restart(engine, settings):
    engine.store.enqueue(make_signal(), 100)
    restarted = Engine(settings)
    assert restarted.process_one()
    assert restarted.state()["position"] is not None


def test_position_and_stop_survive_restart(engine, settings):
    execute(engine, make_signal())
    restarted = Engine(settings)
    assert restarted.state()["position"]["quantity"] == "0.005"
    assert restarted.tick("BTCUSDT", D(98000))["trigger"]["reason"] == "STOP_LOSS"


def test_concurrent_signals_only_create_one_position(engine, settings):
    signals = [make_signal(f"s{i}") for i in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda s: engine.store.enqueue(s, 100), signals))
        list(pool.map(lambda _: Engine(settings).process_one(), range(8)))
    with engine.store.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) FROM audit WHERE event='ENTRY'").fetchone()[0] == 1
    assert engine.state()["position"]["quantity"] == "0.005"


def test_concurrent_duplicate_insert_is_atomic(engine):
    signal = make_signal()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: engine.store.enqueue(signal, 100), range(8)))
    assert sum(not duplicate for _, duplicate in results) == 1


def test_disable_keeps_exit_and_sl_active(engine):
    execute(engine, make_signal())
    engine.control(False)
    assert execute(engine, make_signal("another"))["result"]["status"] == "SKIPPED"
    assert execute(engine, make_signal("close", "CLOSE_ALL"))["result"]["status"] == "CLOSED"
    engine.control(True)
    execute(engine, make_signal("new-entry"))
    engine.control(False)
    assert engine.tick("BTCUSDT", D(98000))["trigger"]["reason"] == "STOP_LOSS"


def test_emergency_file_and_disabled_state_survive_restart(engine, settings):
    settings.kill_switch_path.touch()
    assert execute(engine, make_signal())["result"]["status"] == "SKIPPED"
    settings.kill_switch_path.unlink()
    engine.control(False)
    assert not Engine(settings).state()["entries_enabled"]


def test_config_disabled_cannot_be_overridden_by_admin(engine):
    engine.settings.trading_enabled = False
    engine.control(True)
    assert not engine.state()["entries_enabled"]


def test_stale_queue_signal_rejected(engine):
    old = datetime.now(UTC) - timedelta(seconds=301)
    result = execute(engine, make_signal(timestamp=old))
    assert result["status"] == "REJECTED"
    assert engine.state()["position"] is None


def test_queue_backpressure(engine):
    engine.store.enqueue(make_signal("one"), 1)
    with pytest.raises(QueueFull):
        engine.store.enqueue(make_signal("two"), 1)


def test_protection_failure_rolls_back_entry_and_disables(engine, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(PaperExchange, "place_stop_loss", fail)
    assert execute(engine, make_signal())["status"] == "FAILED"
    assert engine.state()["position"] is None
    assert engine.state()["balance"] == "1000"
    assert not engine.state()["entries_enabled"]


def test_no_cancellation_of_protection_while_open(engine):
    execute(engine, make_signal())
    with engine.store.transaction() as conn, pytest.raises(ValueError):
        PaperExchange(conn, engine.settings).cancel_open_orders("BTCUSDT")


def test_audit_has_all_order_fields(engine):
    execute(engine, make_signal())
    with engine.store.transaction() as conn:
        rows = conn.execute("SELECT event,fields FROM audit").fetchall()
    assert {r["event"] for r in rows} >= {"ENTRY", "STOP_LOSS", "TAKE_PROFIT", "SIGNAL_RESULT"}
    assert "exchange_order_id" in engine.settings.log_path.read_text()


def test_database_symbol_identity(engine, settings):
    settings.symbol = "SOLUSDT"
    with pytest.raises(ValueError, match="different"):
        Engine(settings)
