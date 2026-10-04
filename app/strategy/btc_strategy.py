from app.models.signal import Signal


class ExternalTradingViewStrategy:
    """V1 receives validated signals; it does not invent EMA/ATR or V4/V5 rules."""

    def next_signal(self) -> Signal | None:
        return None
