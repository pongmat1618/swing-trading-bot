import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.models.signal import Signal
from app.utils.config import check_runtime
from tests.conftest import make_signal


def payload(settings, **overrides):
    return {
        **make_signal(**overrides).model_dump(mode="json"),
        "secret": settings.webhook_secret.get_secret_value(),
    }


def wait_result(client, signal_id, headers):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = client.get(f"/signals/{signal_id}", headers=headers).json()
        if result.get("status") != "QUEUED":
            return result
        time.sleep(0.01)
    raise AssertionError("worker did not finish")


def test_full_http_lifecycle(settings):
    admin = {"Authorization": f"Bearer {settings.admin_token.get_secret_value()}"}
    body = payload(settings)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        response = client.post("/webhook/tradingview", json=body)
        assert response.status_code == 202
        assert wait_result(client, "entry-1", admin)["result"]["status"] == "FILLED"
        assert client.post("/webhook/tradingview", json=body).json()["duplicate"]
        assert client.get("/state", headers=admin).json()["position"]["side"] == "LONG"
        assert (
            client.post(
                "/paper/tick", headers=admin, json={"symbol": "BTCUSDT", "price": 103000}
            ).json()["position"]
            is None
        )
        assert client.get("/signals/missing", headers=admin).status_code == 404


def test_auth_is_separate(settings):
    body = payload(settings)
    with TestClient(create_app(settings)) as client:
        assert client.get("/state").status_code == 401
        body["secret"] = "wrong"
        assert client.post("/webhook/tradingview", json=body).status_code == 401
        body["secret"] = "ภาษาไทย"
        assert client.post("/webhook/tradingview", json=body).status_code == 401
        webhook_header = {"Authorization": f"Bearer {settings.webhook_secret.get_secret_value()}"}
        assert client.get("/state", headers=webhook_header).status_code == 401
        assert (
            client.post("/webhook/tradingview", json=body, headers=webhook_header).status_code
            == 202
        )
        result = wait_result(
            client,
            "entry-1",
            {"Authorization": f"Bearer {settings.admin_token.get_secret_value()}"},
        )
        assert result["status"] == "PROCESSED"
    assert settings.webhook_secret.get_secret_value() not in settings.log_path.read_text()
    with client.app.state.engine.store.transaction() as conn:
        text = conn.execute("SELECT payload FROM signals").fetchone()[0]
        assert "secret" not in text


@pytest.mark.parametrize(
    "bad",
    [
        {"action": "BUY"},
        {"stop_loss": None},
        {"price": 0},
        {"price": "NaN"},
        {"price": "Infinity"},
        {"stop_loss": 101000},
        {"take_profit": 99000},
        {"extra_field": "unexpected"},
    ],
)
def test_invalid_schema_does_not_echo_secret(settings, bad):
    body = payload(settings)
    body.update(bad)
    with TestClient(create_app(settings)) as client:
        response = client.post("/webhook/tradingview", json=body)
        assert response.status_code == 422
        assert settings.webhook_secret.get_secret_value() not in response.text


@pytest.mark.parametrize(
    "bad",
    [
        {"symbol": "SOLUSDT"},
        {"timeframe": "1H"},
        {"timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
        {"timestamp": (datetime.now(UTC) + timedelta(minutes=2)).isoformat()},
    ],
)
def test_scope_and_timestamp(settings, bad):
    body = payload(settings)
    body.update(bad)
    with TestClient(create_app(settings)) as client:
        assert client.post("/webhook/tradingview", json=body).status_code == 422


def test_naive_datetime_rejected():
    data = make_signal().model_dump()
    data["timestamp"] = datetime(2026, 10, 4)
    with pytest.raises(ValidationError):
        Signal.model_validate(data)


def test_conflicting_id_returns_409(settings):
    with TestClient(create_app(settings)) as client:
        body = payload(settings)
        assert client.post("/webhook/tradingview", json=body).status_code == 202
        body["price"] = "100001"
        assert client.post("/webhook/tradingview", json=body).status_code == 409


@pytest.mark.parametrize("mode", ["LIVE", "TESTNET"])
def test_non_paper_mode_blocked(settings, mode):
    settings.mode = mode
    with pytest.raises(ValueError, match="PAPER only"):
        with TestClient(create_app(settings)):
            pass


def test_missing_or_shared_tokens_fail_startup(settings):
    from pydantic import SecretStr

    settings.webhook_secret = SecretStr("")
    with pytest.raises(ValueError):
        check_runtime(settings)
    settings.webhook_secret = settings.admin_token
    with pytest.raises(ValueError, match="separate"):
        check_runtime(settings)


def test_request_body_limit(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/webhook/tradingview",
            content=b"x" * 16385,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert len(response.content) < 100


def test_malformed_json_is_rejected_without_echo(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/webhook/tradingview",
            content=b'{"secret":"sensitive"',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422
        assert "sensitive" not in response.text
