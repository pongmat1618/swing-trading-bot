from dataclasses import dataclass
from decimal import Decimal

from app.models.signal import Action, Signal
from app.risk.position_size import floor_step, position_size
from app.utils.config import Settings


@dataclass(frozen=True)
class TradePlan:
    entry: Decimal
    quantity: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    risk_budget: Decimal
    estimated_loss: Decimal
    notional: Decimal


class RiskManager:
    def __init__(self, settings: Settings):
        self.settings = settings

    def plan(self, signal: Signal, equity: Decimal, available: Decimal) -> TradePlan:
        s = self.settings
        if equity <= 0 or available <= 0:
            raise ValueError("insufficient balance")
        if signal.action not in (Action.LONG, Action.SHORT) or signal.stop_loss is None:
            raise ValueError("entry signal required")
        long = signal.action == Action.LONG
        direction = Decimal(1 if long else -1)
        slip = s.paper_slippage_bps / 10000
        entry = signal.price * (1 + direction * slip)
        stop = floor_step(signal.stop_loss, s.price_tick)
        distance = direction * (entry - stop)
        if stop <= 0 or distance <= 0:
            raise ValueError("stop_loss invalid after tick rounding")
        tp = signal.take_profit or entry + direction * distance * s.reward_risk_ratio
        tp = floor_step(tp, s.price_tick)
        if tp <= 0 or direction * (tp - entry) <= 0:
            raise ValueError("take_profit invalid after rounding or slippage")
        # Include modeled adverse exit slippage and both commissions in stop-risk sizing.
        expected_exit = stop * (1 - direction * slip)
        loss_per_unit = (
            direction * (entry - expected_exit) + (entry + expected_exit) * s.paper_fee_rate
        )
        budget = equity * s.risk_per_trade
        margin_cap = (
            available * s.margin_utilization / (entry / s.leverage + entry * s.paper_fee_rate)
        )
        maximum = min(
            s.max_quantity, s.max_notional / entry, equity * s.leverage / entry, margin_cap
        )
        quantity = position_size(budget, loss_per_unit, maximum, s.quantity_step)
        if quantity < s.min_quantity or quantity * entry < s.min_notional:
            raise ValueError("position below exchange simulation minimums")
        return TradePlan(
            entry, quantity, stop, tp, budget, quantity * loss_per_unit, quantity * entry
        )
