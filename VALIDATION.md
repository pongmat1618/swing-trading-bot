# V1 validation — 2026-10-04

Environment: Python 3.12.14, Linux. Installed dependencies are pinned in requirements files.

| Check | Result |
|---|---|
| `python -m pytest -q` | **84 passed** |
| `ruff check .` | Passed |
| `ruff format --check .` | Passed |
| Offline `python -m scripts.demo` | Passed: LONG→TP, SHORT→SL, duplicate, disable/close, restart |
| Real Uvicorn + HTTP + `scripts.send_signal` | Passed: health, 202 queue, LONG fill, SL tick, flat |
| Binance adapter HTTP mocks | Passed: signature, reduce-only, algo SL/TP, read retry, timeout reconciliation |
| Real Binance Testnet / LIVE orders | Not performed; V1 service rejects both modes |
| Docker build / Windows execution | Not performed in this environment; instructions included |
| Strategy backtest / live market data | Not part of V1 |

Tests include risk sizing at dynamic balances, margin and notional caps, step rounding,
commission/slippage costs at the actual modeled exit price on both sides, schema/auth rejection,
timestamp freshness, duplicate conflicts, concurrent inserts/execution, queue persistence,
position recovery, atomic rollback when protection fails, and exit availability during disable.

Pytest emits one dependency deprecation warning from FastAPI/Starlette TestClient about its
HTTPX transport. There are no failed tests. Production HTTP smoke uses HTTPX directly and passed.

The demo's balances are synthetic execution checks, not returns from the user's trading strategy.
PAPER uses user-supplied prices; there is no automatic market feed in V1.

## Codex Cloud preparation — local recheck 2026-10-04

Python 3.12.14: setup script passed; shell syntax passed; 84 tests passed
with one Starlette/HTTPX deprecation warning; Ruff lint and format passed;
offline demo passed. Added AGENTS.md, setup/check scripts, Thai Cloud guide
and starter task prompt. No trading logic changed. No actual Codex Cloud
execution, repository upload, deployment, or exchange order was performed.
