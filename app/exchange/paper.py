import json
import sqlite3
from decimal import Decimal
from typing import Any

from app.models.signal import Position
from app.risk.risk_manager import TradePlan
from app.storage import Store
from app.utils.config import Settings


class PaperExchange:
    """All methods run inside the caller's single SQLite transaction."""

    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn = conn
        self.settings = settings
        self.plan: TradePlan | None = None
        self.strategy = ""
        self.signal_id = ""

    def get_balance(self) -> Decimal:
        return Decimal(Store.get(self.conn, "balance"))

    def get_position(self, symbol: str) -> Position | None:
        raw = Store.get(self.conn, "position")
        position = Position.model_validate_json(raw) if raw and raw != "null" else None
        if position and position.symbol != symbol:
            raise ValueError("database contains another symbol")
        return position

    def get_current_price(self, symbol: str) -> Decimal:
        price = Store.get(self.conn, f"price:{symbol}")
        if price is None:
            raise ValueError("no simulated price yet")
        return Decimal(price)

    def set_price(self, symbol: str, price: Decimal) -> None:
        Store.set(self.conn, f"price:{symbol}", str(price))

    def set_leverage(self, symbol: str, leverage: int) -> None:
        Store.set(self.conn, f"leverage:{symbol}", str(leverage))

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        client_order_id: str,
        *,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        if reduce_only:
            position = self.get_position(symbol)
            if position is None:
                return {"status": "NO_POSITION"}
            closing_side = "SELL" if position.side == "LONG" else "BUY"
            if side != closing_side or quantity != position.quantity:
                raise ValueError("only full reduce-only closes are supported")
            return self.close_position(symbol, client_order_id)
        if side not in ("BUY", "SELL"):
            raise ValueError("invalid order side")
        if self.get_position(symbol) is not None:
            raise ValueError("existing position; no pyramiding or automatic reversal")
        if self.plan is None or quantity != self.plan.quantity:
            raise ValueError("a risk plan is required")
        plan = self.plan
        fee = quantity * plan.entry * self.settings.paper_fee_rate
        position = Position(
            symbol=symbol,
            side="LONG" if side == "BUY" else "SHORT",
            entry=plan.entry,
            quantity=quantity,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            entry_fee=fee,
            strategy=self.strategy,
            signal_id=self.signal_id,
        )
        Store.set(self.conn, "balance", str(self.get_balance() - fee))
        Store.set(self.conn, "position", position.model_dump_json())
        result = {
            "status": "FILLED",
            "exchange_order_id": f"paper-{client_order_id}",
            "symbol": symbol,
            "side": side,
            "entry": str(plan.entry),
            "quantity": str(quantity),
            "stop_loss": str(plan.stop_loss),
            "take_profit": str(plan.take_profit),
            "fee": str(fee),
            "strategy": self.strategy,
            "signal_id": self.signal_id,
            "estimated_stop_loss": str(plan.estimated_loss),
            "risk_budget": str(plan.risk_budget),
        }
        Store.audit(self.conn, "ENTRY", result)
        return result

    def _protect(
        self, symbol: str, side: str, price: Decimal, client_order_id: str, kind: str
    ) -> dict[str, Any]:
        position = self.get_position(symbol)
        if position is None or side != ("SELL" if position.side == "LONG" else "BUY"):
            raise ValueError("protection must close an existing position")
        expected = position.stop_loss if kind == "STOP_LOSS" else position.take_profit
        if price != expected:
            raise ValueError("protection price differs from risk plan")
        result = {
            "status": "NEW",
            "type": kind,
            "symbol": symbol,
            "side": side,
            "trigger_price": str(price),
            "reduce_only": True,
            "exchange_order_id": f"paper-{client_order_id}",
            "strategy": position.strategy,
            "signal_id": position.signal_id,
        }
        Store.audit(self.conn, kind, result)
        return result

    def place_stop_loss(
        self, symbol: str, side: str, price: Decimal, client_order_id: str
    ) -> dict[str, Any]:
        return self._protect(symbol, side, price, client_order_id, "STOP_LOSS")

    def place_take_profit(
        self, symbol: str, side: str, price: Decimal, client_order_id: str
    ) -> dict[str, Any]:
        return self._protect(symbol, side, price, client_order_id, "TAKE_PROFIT")

    def close_position(self, symbol: str, client_order_id: str) -> dict[str, Any]:
        position = self.get_position(symbol)
        if position is None:
            return {"status": "NO_POSITION"}
        direction = Decimal(1 if position.side == "LONG" else -1)
        mark = self.get_current_price(symbol)
        exit_price = mark * (1 - direction * self.settings.paper_slippage_bps / 10000)
        gross = direction * (exit_price - position.entry) * position.quantity
        exit_fee = position.quantity * exit_price * self.settings.paper_fee_rate
        balance = self.get_balance() + gross - exit_fee
        Store.set(self.conn, "balance", str(balance))
        Store.set(self.conn, "position", "null")
        result = {
            "status": "CLOSED",
            "exchange_order_id": f"paper-{client_order_id}",
            "symbol": symbol,
            "side": "SELL" if position.side == "LONG" else "BUY",
            "entry": str(position.entry),
            "exit": str(exit_price),
            "quantity": str(position.quantity),
            "reduce_only": True,
            "gross_pnl": str(gross),
            "exit_fee": str(exit_fee),
            "net_pnl": str(gross - exit_fee - position.entry_fee),
            "balance": str(balance),
            "strategy": position.strategy,
            "signal_id": position.signal_id,
        }
        Store.audit(self.conn, "EXIT", result)
        self.cancel_open_orders(symbol)
        return result

    def cancel_open_orders(self, symbol: str) -> None:
        if self.get_position(symbol) is not None:
            raise ValueError("cannot remove protection while a paper position is open")
        Store.audit(self.conn, "CANCEL_PROTECTION", {"symbol": symbol})

    def check_triggers(self, symbol: str) -> dict[str, Any] | None:
        position = self.get_position(symbol)
        if position is None:
            return None
        price = self.get_current_price(symbol)
        long = position.side == "LONG"
        stop_hit = price <= position.stop_loss if long else price >= position.stop_loss
        tp_hit = price >= position.take_profit if long else price <= position.take_profit
        if not (stop_hit or tp_hit):
            return None
        reason = "STOP_LOSS" if stop_hit else "TAKE_PROFIT"
        # Fill at observed tick, including gaps and adverse slippage; never assume SL guaranteed.
        result = self.close_position(symbol, f"{position.signal_id}-{reason}")
        result["reason"] = reason
        Store.audit(self.conn, "TRIGGER", result)
        return result

    def snapshot(self, symbol: str) -> dict[str, Any]:
        position = self.get_position(symbol)
        price = Store.get(self.conn, f"price:{symbol}")
        unrealized = Decimal(0)
        margin = Decimal(0)
        if position and price:
            direction = Decimal(1 if position.side == "LONG" else -1)
            unrealized = direction * (Decimal(price) - position.entry) * position.quantity
            leverage = Decimal(Store.get(self.conn, f"leverage:{symbol}") or self.settings.leverage)
            margin = position.entry * position.quantity / leverage
        return {
            "mode": "PAPER",
            "balance": str(self.get_balance()),
            "equity": str(self.get_balance() + unrealized),
            "unrealized_pnl": str(unrealized),
            "used_margin": str(margin),
            "available": str(self.get_balance() + unrealized - margin),
            "mark_price": price,
            "position": json.loads(position.model_dump_json()) if position else None,
        }
