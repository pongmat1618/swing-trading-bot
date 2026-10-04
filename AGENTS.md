# BTC Swing Trading Bot

## Scope and architecture
Python 3.12+, FastAPI, SQLite durable queue, external TradingView signals.
This is a PAPER execution service. The V6_SOL_LONG profile uses the frozen
Pine webhook bridge and a public last-trade price feed; EXTERNAL keeps V1 behavior.
Standalone Python V6 signal generation is not implemented. Never invent V6 rules or describe demo P&L as backtest results.
Binance adapter has mocked tests but is not wired into the engine.
Preserve PAPER defaults and the startup rejection of TESTNET/LIVE unless a
separate task explicitly authorizes implementing those modes.

## Development
Run from the repository root:
- Setup: `bash scripts/codex_setup.sh`
- Verify: `bash scripts/codex_check.sh`
- Local service: `.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log`
Use explicit `.venv/bin/python`; setup shell exports do not persist.
Do not leave the service running after a task.

## Invariants
Keep Decimal-based sizing, fee/slippage accounting, duplicate conflict detection,
atomic transactions, restart recovery, and close actions while trading is disabled.
Do not log tokens or commit .env, SQLite databases, logs, or generated credentials.
Tests and offline demo do not require exchange keys or external market access.
Add focused regression tests when changing execution, persistence, auth, or risk.
Summarize changes and actual validation in Thai. Separate mocked results from
real exchange tests. Do not deploy or place exchange orders as part of setup.
