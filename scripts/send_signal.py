"""Send a fresh manual signal to a running PAPER server; no strategy rules."""

import argparse
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--action",
        choices=["LONG", "SHORT", "CLOSE_LONG", "CLOSE_SHORT", "CLOSE_ALL"],
        required=True,
    )
    parser.add_argument("--price", required=True)
    parser.add_argument("--stop")
    parser.add_argument("--tp")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="4H")
    parser.add_argument("--strategy", default="MANUAL-DEMO")
    parser.add_argument("--id", default=None)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--trust-env",
        action="store_true",
        help="Use HTTP proxy settings from the environment (off for local demo)",
    )
    args = parser.parse_args()
    token = os.getenv("WEBHOOK_SECRET", "")
    if not token:
        parser.error("WEBHOOK_SECRET is missing; run python -m scripts.bootstrap")
    if args.action in ("LONG", "SHORT") and args.stop is None:
        parser.error("entry requires --stop")
    body = {
        "signal_id": args.id or str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "symbol": args.symbol,
        "action": args.action,
        "strategy": args.strategy,
        "timeframe": args.timeframe,
        "price": args.price,
    }
    if args.stop:
        body["stop_loss"] = args.stop
    if args.tp:
        body["take_profit"] = args.tp
    with httpx.Client(timeout=5, trust_env=args.trust_env) as client:
        response = client.post(
            args.url.rstrip("/") + "/webhook/tradingview",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
        print(
            json.dumps(
                {"http_status": response.status_code, "response": response.json()},
                ensure_ascii=False,
                indent=2,
            )
        )
        response.raise_for_status()


if __name__ == "__main__":
    main()
