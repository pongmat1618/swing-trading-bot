from typing import Protocol

from app.models.signal import Signal


class Strategy(Protocol):
    """Optional future local strategy. Execution never imports proprietary rules."""

    def next_signal(self) -> Signal | None: ...
