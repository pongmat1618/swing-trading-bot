# V6 SOLUSDT PAPER — 24/7 deployment package

This build uses the exact frozen Pine entry logic, running on TradingView servers.
The Python service receives authenticated LONG alerts and executes PAPER orders.
It polls Binance public SOLUSDT perpetual last-trade prices every five seconds to
check PAPER SL/TP. No exchange API keys, testnet orders or real orders are used.

## Files and strategy identity

- `strategies/V6_0_SOLUSDT_Long_Core_Frozen.pine`: original source, unchanged.
- `strategies/V6_SOLUSDT_Webhook.pine`: original logic plus chart guard and JSON alerts.
- `config.v6.yaml`: SOLUSDT, 5m, 1% risk, 2R, maximum 5x equity, long-only profile.
- `compose.v6.yaml`: persistent storage, HTTPS proxy, health checks, restart policy.
- `deploy/v6-watchdog.*`: optional host timer to restart an unhealthy container.

This is a TradingView webhook bridge, not a standalone Python strategy port.
TradingView alerts must be created and remain active. Subscription/alert eligibility
and public exchange data access must be checked in the deployment account/region.
Use BINANCE:SOLUSDT.P, 5 minutes; keep the frozen strategy parameters unchanged.
The original Pine source does not contain an exact source/exchange identifier;
the bridge deliberately restricts it to Binance perpetual to match the price feed.

## Execution differences from Pine

Entry alert is emitted at the signal candle close, not at a next-bar simulated fill.
The bot uses the latest observed public price, rejects movement greater than 0.5%
from signal close, sizes with modeled fees/slippage, and computes TP at 2R from
its PAPER fill and rounded structural stop. Risk sizing therefore differs from Pine.
Simulation tick/lot/minimum settings are assumptions, not validated exchange rules.
Paper slippage is 2 basis points, whereas Pine uses 2 ticks. Margin utilization is
90%, which can bind below the frozen 5x notional ceiling. Funding and liquidation
are not modeled. Neither this package nor its offline tests validate a durable edge.

Polling can miss a brief intrapoll SL/TP crossing. Gaps close at observed prices.
A feed outage stops new entries after 30 seconds but cannot execute protective
exits while offline. On recovery protection uses the next observed price. This
PAPER implementation must not be described as exchange-side protection.
Original Pine simulated position state and the PAPER position may diverge after
rejected/missed alerts, price differences or restarts. Pine will withhold new alerts
while its own simulated position is open; it does not synchronize with the bot.

## Prepare a Google Cloud Compute Engine VM

Provisioning is not performed by this package. Use an Ubuntu VM with Docker
Engine and Docker Compose installed, a persistent boot disk, an external IP and
a domain pointing at that IP. Allow public TCP 80/443 and restrict administrative
SSH. Do not expose port 8000. VM/data access must allow Binance public futures API.
Cloud charges and project/region are chosen by the operator before provisioning.

Place this repository at `/opt/swing-trading-bot`. Copy `.env.example` to `.env`.
Generate two distinct 64-character hexadecimal values locally:

```bash
python3 -c 'import secrets; print(secrets.token_hex(32)); print(secrets.token_hex(32))'
```

Set WEBHOOK_SECRET and ADMIN_TOKEN to those values, BOT_DOMAIN to your actual
DNS name, BOT_MODE=PAPER, BOT_CONFIG=config.v6.yaml, and TRADING_ENABLED=true.
Leave exchange keys empty. Restrict `.env` permissions with `chmod 600 .env`.
Tokens are not committed to git and should not appear in screenshots or messages.

```bash
sudo systemctl enable --now docker
docker compose -f compose.v6.yaml up -d --build
curl --fail http://127.0.0.1:8000/health
docker compose -f compose.v6.yaml ps
```

These commands start the deployment and are for the operator; not run during
package preparation. Compose restart policy handles process crashes/reboots.
Docker health checks alone do not restart unhealthy containers. Install the timer:

```bash
sudo cp deploy/v6-watchdog.service deploy/v6-watchdog.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now v6-watchdog.timer
```

Health reports both queue worker and price-feed freshness. A timer restart does
not repair an upstream outage. Check host disk capacity, rotate/back up logs and
audit database, and monitor the VM externally. The application audit table and
orders JSONL currently have no automatic retention. Stop the service for a
consistent database backup; preserve volume ownership for UID 10001. Never run
two execution workers or duplicate stacks for the same strategy/account.

## Activate TradingView

1. Paste `strategies/V6_SOLUSDT_Webhook.pine` in Pine Editor and compile.
2. Add it to BINANCE:SOLUSDT.P on a 5-minute chart.
3. Enter the hexadecimal WEBHOOK_SECRET in the script input. Keep script private.
4. Create a strategy alert selecting **alert() function calls only**, not order fills.
5. Set webhook URL to `https://YOUR_DOMAIN/webhook/tradingview`.
6. Verify the alert expiration/settings and keep the alert active. Recreate the
   alert after code, inputs, timeframe or symbol changes: the server uses a snapshot.
7. Check authenticated `/state` over localhost and the signal/audit records after
   the next real entry signal. Do not claim delivery until observed end-to-end.

Pine compilation and actual TradingView delivery are not validated locally.
https://www.tradingview.com/pine-script-docs/concepts/alerts/
https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Symbol-Price-Ticker-v2

## Emergency operation

Authenticated POST `/admin/trading` with `{"enabled": false}` stops entries while
price-driven exits continue. Control survives restart. Admin endpoints are only
reachable on localhost; Caddy exposes just the webhook. To stop the entire stack:

```bash
docker compose -f compose.v6.yaml down
```

Do not add `-v` unless intentionally deleting persistent paper history. Never reuse
a BTC database as a SOL database. This V6 profile uses its own data volume/database.

## Verification

Run `bash scripts/codex_setup.sh`, then `bash scripts/codex_check.sh`.
Offline tests exercise profile guards, stale/invalid feed data, entry deviation,
PAPER SL/TP and capped sizing. They use mocked public API responses, not a real
exchange account. Existing execution/restart/duplicate tests remain in the suite.
