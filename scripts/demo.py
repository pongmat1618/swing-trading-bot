"""Offline end-to-end PAPER demo. No credentials or network requests to an exchange."""

import json
import secrets
import tempfile
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`.*")
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import SecretStr  # noqa: E402

from app.main import create_app  # noqa: E402
from app.utils.config import Settings  # noqa: E402


def run_demo() -> dict:
    with tempfile.TemporaryDirectory(prefix="btc-paper-demo-") as directory:
        root = Path(directory)
        settings = Settings(
            database_path=root / "paper.sqlite3",
            log_path=root / "orders.jsonl",
            kill_switch_path=root / "STOP_TRADING",
            webhook_secret=SecretStr(secrets.token_urlsafe(32)),
            admin_token=SecretStr(secrets.token_urlsafe(32)),
        )
        webhook = {"Authorization": f"Bearer {settings.webhook_secret.get_secret_value()}"}
        admin = {"Authorization": f"Bearer {settings.admin_token.get_secret_value()}"}
        checks = []
        with TestClient(create_app(settings)) as client:

            def send(signal_id, action, price, stop=None):
                body = {
                    "signal_id": signal_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "symbol": "BTCUSDT",
                    "action": action,
                    "strategy": "DEMO",
                    "timeframe": "4H",
                    "price": price,
                }
                if stop:
                    body["stop_loss"] = stop
                response = client.post("/webhook/tradingview", json=body, headers=webhook)
                assert response.status_code == 202, response.text
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    result = client.get(f"/signals/{signal_id}", headers=admin).json()
                    if result["status"] != "QUEUED":
                        assert result["status"] == "PROCESSED", result
                        return body, result
                    time.sleep(0.01)
                raise RuntimeError("paper worker timeout")

            body, long = send("demo-long", "LONG", "100000", "98000")
            assert long["result"]["status"] == "FILLED"
            checks.append("LONG with SL/TP and fee-aware risk sizing")
            duplicate = client.post("/webhook/tradingview", json=body, headers=webhook).json()
            assert duplicate["duplicate"]
            checks.append("duplicate ignored")
            take_profit = client.post(
                "/paper/tick", headers=admin, json={"symbol": "BTCUSDT", "price": "103100"}
            ).json()
            assert take_profit["trigger"]["reason"] == "TAKE_PROFIT"
            checks.append("TP closed LONG")
            _, short = send("demo-short", "SHORT", "100000", "102000")
            assert short["result"]["status"] == "FILLED"
            stop = client.post(
                "/paper/tick", headers=admin, json={"symbol": "BTCUSDT", "price": "102000"}
            ).json()
            assert stop["trigger"]["reason"] == "STOP_LOSS"
            checks.append("SL closed SHORT")
            send("demo-long-again", "LONG", "100000", "98000")
            client.post("/admin/trading", headers=admin, json={"enabled": False}).raise_for_status()
            _, closed = send("demo-close", "CLOSE_ALL", "100000")
            assert closed["result"]["status"] == "CLOSED"
            _, disabled = send("demo-disabled", "LONG", "100000", "98000")
            assert disabled["result"]["status"] == "SKIPPED"
            checks.append("entry disable preserves reduce-only closing")
            final = client.get("/state", headers=admin).json()
            assert final["position"] is None
        with TestClient(create_app(settings)) as client:
            restored = client.get("/state", headers=admin).json()
            assert restored["balance"] == final["balance"]
            assert not restored["entries_enabled"]
            checks.append("state restored after restart")
        return {
            "mode": "PAPER",
            "initial_balance": "1000",
            "final_balance": final["balance"],
            "position": final["position"],
            "checks": checks,
            "note": "Synthetic execution checks, not strategy backtest results.",
        }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, indent=2))
