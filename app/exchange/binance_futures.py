"""TESTNET adapter preparation for V1.1; deliberately not wired into V1's engine.

No production base URL or automatic live fallback. Mock-tested only.
Order writes are never blindly retried after an uncertain outcome.
"""

import hashlib
import hmac
import re
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx

from app.models.signal import PositionView

TESTNET_URL = "https://demo-fapi.binance.com"


class ExchangeError(RuntimeError):
    pass


class AmbiguousOrderError(ExchangeError):
    """Pause execution and reconcile; never place a replacement order blindly."""


class BinanceFutures:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        *,
        mode: str = "TESTNET",
        client: httpx.Client | None = None,
    ):
        if mode != "TESTNET":
            raise ValueError("this V1 adapter supports TESTNET only; LIVE is blocked")
        if not api_key or not api_secret:
            raise ValueError("TESTNET API credentials are required")
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = client or httpx.Client(timeout=5, follow_redirects=False)

    def shutdown(self) -> None:
        self._client.close()

    def _request(
        self, method: str, path: str, params: dict[str, Any] | None = None, *, signed: bool = True
    ):
        original = params or {}
        for attempt in range(3 if method == "GET" else 1):
            data = dict(original)
            headers = {}
            if signed:
                data.update(timestamp=int(time.time() * 1000), recvWindow=5000)
                query = urlencode(data)
                data["signature"] = hmac.new(
                    self._api_secret.encode(), query.encode(), hashlib.sha256
                ).hexdigest()
                headers["X-MBX-APIKEY"] = self._api_key
            query = urlencode(data)
            try:
                if method in ("GET", "DELETE"):
                    response = self._client.request(
                        method, TESTNET_URL + path, params=query, headers=headers
                    )
                else:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    response = self._client.request(
                        method, TESTNET_URL + path, content=query, headers=headers
                    )
                if response.status_code >= 500 or response.status_code == 408:
                    raise httpx.ReadTimeout("exchange outcome uncertain")
                if response.status_code == 429 and method == "GET" and attempt < 2:
                    time.sleep(0.1 * (2**attempt))
                    continue
                try:
                    body = response.json()
                except ValueError:
                    if method != "GET":
                        raise AmbiguousOrderError("invalid exchange response; reconcile") from None
                    raise ExchangeError("invalid exchange response") from None
                if response.is_error or (isinstance(body, dict) and body.get("code", 0) < 0):
                    code = body.get("code", "unknown") if isinstance(body, dict) else "unknown"
                    raise ExchangeError(f"exchange rejected request (code={code})")
                return body
            except httpx.TransportError:
                if method != "GET":
                    raise AmbiguousOrderError(
                        "write outcome unknown; reconcile before retry"
                    ) from None
                if attempt == 2:
                    raise ExchangeError("exchange read failed after 3 attempts") from None
                time.sleep(0.1 * (2**attempt))
        raise ExchangeError("exchange request failed")

    @staticmethod
    def _order_fields(symbol: str, side: str, client_order_id: str) -> None:
        if not re.fullmatch(r"[A-Z0-9]{5,20}", symbol) or side not in ("BUY", "SELL"):
            raise ValueError("invalid order symbol or side")
        if not re.fullmatch(r"[.A-Za-z0-9_:/-]{1,36}", client_order_id):
            raise ValueError("invalid client order id")

    def get_balance(self) -> Decimal:
        rows = self._request("GET", "/fapi/v3/balance")
        for row in rows:
            if row["asset"] == "USDT":
                return Decimal(row["availableBalance"])
        raise ExchangeError("USDT balance missing")

    def get_position(self, symbol: str) -> PositionView | None:
        rows = self._request("GET", "/fapi/v3/positionRisk", {"symbol": symbol})
        for row in rows:
            if row["positionSide"] != "BOTH":
                raise ExchangeError("One-way Mode required; Hedge Mode is unsupported")
            amount = Decimal(row["positionAmt"])
            if amount:
                return PositionView(
                    symbol=symbol,
                    side="LONG" if amount > 0 else "SHORT",
                    entry=Decimal(row["entryPrice"]),
                    quantity=abs(amount),
                )
        return None

    def get_current_price(self, symbol: str) -> Decimal:
        row = self._request("GET", "/fapi/v1/premiumIndex", {"symbol": symbol}, signed=False)
        return Decimal(row["markPrice"])

    def get_symbol_filters(self, symbol: str) -> dict[str, Any]:
        data = self._request("GET", "/fapi/v1/exchangeInfo", signed=False)
        for item in data["symbols"]:
            if item["symbol"] == symbol:
                return {f["filterType"]: f for f in item["filters"]}
        raise ExchangeError("symbol missing from exchange info")

    def set_leverage(self, symbol: str, leverage: int) -> None:
        if not 1 <= leverage <= 125:
            raise ValueError("invalid leverage")
        self._request("POST", "/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage})

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        client_order_id: str,
        *,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        self._order_fields(symbol, side, client_order_id)
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError("invalid quantity")
        fields = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": str(quantity),
            "newClientOrderId": client_order_id,
            "newOrderRespType": "RESULT",
            "reduceOnly": "true" if reduce_only else "false",
        }
        try:
            return self._request("POST", "/fapi/v1/order", fields)
        except AmbiguousOrderError:
            try:
                return self._request(
                    "GET",
                    "/fapi/v1/order",
                    {"symbol": symbol, "origClientOrderId": client_order_id},
                )
            except ExchangeError:
                raise AmbiguousOrderError("market order unresolved; pause and reconcile") from None

    def _protection(
        self, symbol: str, side: str, price: Decimal, client_order_id: str, kind: str
    ) -> dict[str, Any]:
        self._order_fields(symbol, side, client_order_id)
        if not price.is_finite() or price <= 0:
            raise ValueError("invalid trigger price")
        fields = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": side,
            "type": kind,
            "triggerPrice": str(price),
            "workingType": "MARK_PRICE",
            "closePosition": "true",
            "clientAlgoId": client_order_id,
        }
        try:
            return self._request("POST", "/fapi/v1/algoOrder", fields)
        except AmbiguousOrderError:
            try:
                return self._request("GET", "/fapi/v1/algoOrder", {"clientAlgoId": client_order_id})
            except ExchangeError:
                raise AmbiguousOrderError(
                    "protection order unresolved; pause and reconcile"
                ) from None

    def place_stop_loss(
        self, symbol: str, side: str, price: Decimal, client_order_id: str
    ) -> dict[str, Any]:
        return self._protection(symbol, side, price, client_order_id, "STOP_MARKET")

    def place_take_profit(
        self, symbol: str, side: str, price: Decimal, client_order_id: str
    ) -> dict[str, Any]:
        return self._protection(symbol, side, price, client_order_id, "TAKE_PROFIT_MARKET")

    def close_position(self, symbol: str, client_order_id: str) -> dict[str, Any]:
        position = self.get_position(symbol)
        if position is None:
            return {"status": "NO_POSITION"}
        return self.place_market_order(
            symbol,
            "SELL" if position.side == "LONG" else "BUY",
            position.quantity,
            client_order_id,
            reduce_only=True,
        )

    def cancel_open_orders(self, symbol: str) -> None:
        if self.get_position(symbol) is not None:
            raise ExchangeError("close and confirm flat before cancelling protection")
        self._request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": symbol})
        self._request("DELETE", "/fapi/v1/algoOpenOrders", {"symbol": symbol})
