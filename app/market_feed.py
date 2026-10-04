"""Public last-trade polling for PAPER protection, never an exchange order API."""

import threading
import time
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.engine import Engine


class MarketFeed:
    def __init__(self, engine: "Engine"):
        self.engine = engine
        self.price: Decimal | None = None
        self.last_success: float | None = None
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def fresh(self) -> bool:
        return (
            self.last_success is not None
            and time.monotonic() - self.last_success <= self.engine.settings.market_stale_seconds
            and self.thread is not None
            and self.thread.is_alive()
        )

    def status(self) -> dict:
        return {"fresh": self.fresh(), "price": str(self.price) if self.price else None}

    def poll_once(self, client: httpx.Client) -> None:
        response = client.get(
            "https://fapi.binance.com/fapi/v2/ticker/price",
            params={"symbol": self.engine.settings.symbol},
        )
        response.raise_for_status()
        data = response.json()
        price = Decimal(data["price"])
        age = time.time() - int(data["time"]) / 1000
        if (
            data["symbol"] != self.engine.settings.symbol
            or not price.is_finite()
            or price <= 0
            or age > self.engine.settings.market_stale_seconds
            or age < -5
        ):
            raise ValueError("invalid or stale public market data")
        self.engine.tick(self.engine.settings.symbol, price)
        self.price = price
        self.last_success = time.monotonic()

    def _run(self) -> None:
        delay = self.engine.settings.market_poll_seconds
        with httpx.Client(timeout=5, follow_redirects=False) as client:
            while not self.stop_event.is_set():
                try:
                    self.poll_once(client)
                    delay = self.engine.settings.market_poll_seconds
                except Exception:
                    self.engine.logger.warning(
                        "MARKET_FEED_UNAVAILABLE", extra={"fields": {"error": "poll failed"}}
                    )
                    delay = min(max(delay * 2, 5), 60)
                self.stop_event.wait(delay)

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="market-feed", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=7)
