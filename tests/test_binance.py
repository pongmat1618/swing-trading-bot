import hashlib
import hmac
from decimal import Decimal
from urllib.parse import parse_qs, urlencode

import httpx
import pytest

from app.exchange.binance_futures import (
    TESTNET_URL,
    AmbiguousOrderError,
    BinanceFutures,
    ExchangeError,
)


def adapter(handler):
    return BinanceFutures(
        "mock-key", "mock-secret", client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_market_signing_and_reduce_only():
    def handle(request):
        assert str(request.url).startswith(TESTNET_URL)
        assert request.headers["X-MBX-APIKEY"] == "mock-key"
        fields = parse_qs(request.content.decode())
        signature = fields.pop("signature")[0]
        query = urlencode({key: val[0] for key, val in fields.items()})
        assert signature == hmac.new(b"mock-secret", query.encode(), hashlib.sha256).hexdigest()
        assert fields["reduceOnly"] == ["true"]
        assert fields["type"] == ["MARKET"]
        return httpx.Response(200, json={"orderId": 123, "status": "FILLED"})

    assert (
        adapter(handle).place_market_order(
            "BTCUSDT", "SELL", Decimal("0.005"), "close-1", reduce_only=True
        )["orderId"]
        == 123
    )


@pytest.mark.parametrize(
    "method,kind", [("place_stop_loss", "STOP_MARKET"), ("place_take_profit", "TAKE_PROFIT_MARKET")]
)
def test_protection_uses_current_algo_endpoint(method, kind):
    def handle(request):
        assert request.url.path == "/fapi/v1/algoOrder"
        fields = parse_qs(request.content.decode())
        assert fields["type"] == [kind]
        assert fields["closePosition"] == ["true"]
        assert fields["workingType"] == ["MARK_PRICE"]
        assert "quantity" not in fields and "reduceOnly" not in fields
        assert fields["triggerPrice"] == ["98000"]
        return httpx.Response(200, json={"algoId": 1})

    getattr(adapter(handle), method)("BTCUSDT", "SELL", Decimal(98000), "protect-1")


def test_timeout_queries_order_without_second_post():
    calls = []

    def handle(request):
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("unknown", request=request)
        assert request.url.params["origClientOrderId"] == "entry-1"
        return httpx.Response(200, json={"orderId": 5, "status": "FILLED"})

    result = adapter(handle).place_market_order("BTCUSDT", "BUY", Decimal("0.001"), "entry-1")
    assert result["orderId"] == 5
    assert calls == ["POST", "GET"]


def test_unresolved_timeout_is_not_retried():
    calls = []

    def handle(request):
        calls.append(request.method)
        if request.method == "POST":
            return httpx.Response(503, json={"msg": "Unknown error"})
        return httpx.Response(400, json={"code": -2013})

    with pytest.raises(AmbiguousOrderError):
        adapter(handle).place_market_order("BTCUSDT", "BUY", Decimal("0.001"), "entry-1")
    assert calls == ["POST", "GET"]


def test_conditional_timeout_reconciles_client_algo_id():
    calls = []

    def handle(request):
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("unknown", request=request)
        assert request.url.params["clientAlgoId"] == "sl-1"
        return httpx.Response(200, json={"algoId": 8})

    assert adapter(handle).place_stop_loss("BTCUSDT", "SELL", Decimal(98000), "sl-1") == {
        "algoId": 8
    }
    assert calls == ["POST", "GET"]


def test_read_retry_is_bounded():
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(ExchangeError, match="3 attempts"):
        adapter(handle).get_balance()
    assert len(calls) == 3


def test_no_live_mode_even_with_keys():
    with pytest.raises(ValueError, match="LIVE is blocked"):
        BinanceFutures("key", "secret", mode="LIVE")


def test_close_fetches_position_and_uses_reduce_only():
    def handle(request):
        if request.method == "GET":
            return httpx.Response(
                200,
                json=[{"positionSide": "BOTH", "positionAmt": "-0.005", "entryPrice": "100000"}],
            )
        fields = parse_qs(request.content.decode())
        assert fields["side"] == ["BUY"]
        assert fields["reduceOnly"] == ["true"]
        return httpx.Response(200, json={"status": "FILLED"})

    adapter(handle).close_position("BTCUSDT", "close-1")


def test_hedge_mode_rejected():
    def handle(request):
        return httpx.Response(200, json=[{"positionSide": "LONG", "positionAmt": "0"}])

    with pytest.raises(ExchangeError, match="Hedge"):
        adapter(handle).get_position("BTCUSDT")


def test_cancel_regular_and_algo_orders():
    paths = []

    def handle(request):
        paths.append(request.url.path)
        if request.method == "GET":
            return httpx.Response(200, json=[{"positionSide": "BOTH", "positionAmt": "0"}])
        return httpx.Response(200, json={"code": 200})

    adapter(handle).cancel_open_orders("BTCUSDT")
    assert paths == ["/fapi/v3/positionRisk", "/fapi/v1/allOpenOrders", "/fapi/v1/algoOpenOrders"]
