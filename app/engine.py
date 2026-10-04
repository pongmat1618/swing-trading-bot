import json
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from app.exchange.paper import PaperExchange
from app.models.signal import Action, Signal
from app.risk.risk_manager import RiskManager
from app.storage import Store, now_iso
from app.utils.config import Settings
from app.utils.logger import create_logger


def validate_scope(signal: Signal, settings: Settings) -> None:
    if signal.symbol != settings.symbol or signal.timeframe != settings.timeframe:
        raise ValueError("symbol or timeframe is not allowed")
    age = (datetime.now(UTC) - signal.timestamp).total_seconds()
    if age > settings.max_signal_age_seconds or age < -settings.max_future_seconds:
        raise ValueError("signal timestamp is stale or too far in the future")


class Engine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = Store(settings.database_path, str(settings.paper_initial_balance))
        self.risk = RiskManager(settings)
        self.logger = create_logger(settings.log_path)
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.healthy = True
        with self.store.transaction() as conn:
            identity = f"PAPER:{settings.symbol}"
            stored = Store.get(conn, "identity")
            if stored is not None and stored != identity:
                raise ValueError("database belongs to a different mode or symbol")
            Store.set(conn, "identity", identity)

    def entries_enabled(self, conn: sqlite3.Connection) -> bool:
        return (
            self.settings.trading_enabled
            and Store.get(conn, "enabled") == "true"
            and not self.settings.kill_switch_path.exists()
            and self.healthy
        )

    def start(self) -> None:
        self.thread = threading.Thread(target=self._worker, name="paper-worker", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout=3)

    def _worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                if self.process_one():
                    continue
            except Exception:
                self.healthy = False
                # Avoid logging credentials or request URLs from arbitrary exceptions.
                self.logger.error("WORKER_FAILED", extra={"fields": {"error": "internal error"}})
                return
            self.wake_event.wait(0.1)
            self.wake_event.clear()

    def process_one(self) -> bool:
        with self.store.transaction() as conn:
            row = conn.execute(
                "SELECT id,payload FROM signals WHERE status='QUEUED' ORDER BY rowid LIMIT 1"
            ).fetchone()
            if not row:
                return False
            conn.execute("SAVEPOINT execution")
            try:
                signal = Signal.model_validate_json(row["payload"])
                validate_scope(signal, self.settings)
                result = self._execute(conn, signal)
                status = "PROCESSED"
            except ValueError as exc:
                conn.execute("ROLLBACK TO execution")
                result = {"error": str(exc)}
                status = "REJECTED"
            except Exception:
                conn.execute("ROLLBACK TO execution")
                result = {"error": "internal execution error; entries disabled"}
                status = "FAILED"
                Store.set(conn, "enabled", "false")
            conn.execute("RELEASE execution")
            conn.execute(
                "UPDATE signals SET status=?,result=? WHERE id=?",
                (status, json.dumps(result, default=str), row["id"]),
            )
            fields = {"signal_id": row["id"], "status": status, **result}
            Store.audit(conn, "SIGNAL_RESULT", fields)
        self.logger.info("SIGNAL_RESULT", extra={"fields": fields})
        return True

    def _execute(self, conn: sqlite3.Connection, signal: Signal) -> dict[str, Any]:
        ex = PaperExchange(conn, self.settings)
        entry = signal.action in (Action.LONG, Action.SHORT)
        if entry and not self.entries_enabled(conn):
            return {"status": "SKIPPED", "reason": "new entries disabled"}
        if entry and ex.get_position(signal.symbol) is not None:
            return {"status": "SKIPPED", "reason": "existing position"}
        ex.set_price(signal.symbol, signal.price)
        triggered = ex.check_triggers(signal.symbol)
        if not entry:
            position = ex.get_position(signal.symbol)
            if position is None:
                return triggered or {"status": "NO_POSITION"}
            if signal.action != Action.CLOSE_ALL and signal.action != f"CLOSE_{position.side}":
                return {"status": "SKIPPED", "reason": "close action does not match side"}
            closing_side = "SELL" if position.side == "LONG" else "BUY"
            return ex.place_market_order(
                signal.symbol, closing_side, position.quantity, signal.signal_id, reduce_only=True
            )
        plan = self.risk.plan(signal, ex.get_balance(), ex.get_balance())
        ex.plan, ex.strategy, ex.signal_id = plan, signal.strategy, signal.signal_id
        ex.set_leverage(signal.symbol, self.settings.leverage)
        side = "BUY" if signal.action == Action.LONG else "SELL"
        closing = "SELL" if side == "BUY" else "BUY"
        result = ex.place_market_order(signal.symbol, side, plan.quantity, signal.signal_id)
        result["stop_order"] = ex.place_stop_loss(
            signal.symbol, closing, plan.stop_loss, f"{signal.signal_id}-sl"
        )
        result["tp_order"] = ex.place_take_profit(
            signal.symbol, closing, plan.take_profit, f"{signal.signal_id}-tp"
        )
        return result

    def tick(self, symbol: str, price) -> dict[str, Any]:
        if symbol != self.settings.symbol:
            raise ValueError("symbol is not allowed")
        with self.store.transaction() as conn:
            ex = PaperExchange(conn, self.settings)
            ex.set_price(symbol, price)
            result = ex.check_triggers(symbol)
            fields = {
                "timestamp": now_iso(),
                "symbol": symbol,
                "price": str(price),
                "trigger": result,
            }
            Store.audit(conn, "PRICE_TICK", fields)
            snapshot = ex.snapshot(symbol)
        self.logger.info("PRICE_TICK", extra={"fields": fields})
        return {"trigger": result, **snapshot}

    def state(self) -> dict[str, Any]:
        with self.store.transaction() as conn:
            return {
                **PaperExchange(conn, self.settings).snapshot(self.settings.symbol),
                "entries_enabled": self.entries_enabled(conn),
                "worker_healthy": self.healthy,
            }

    def control(self, enabled: bool) -> dict[str, Any]:
        with self.store.transaction() as conn:
            Store.set(conn, "enabled", "true" if enabled else "false")
            Store.audit(conn, "TRADING_CONTROL", {"enabled": enabled})
        return self.state()
