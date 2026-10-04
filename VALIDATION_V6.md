# V6 package validation

- `bash scripts/codex_check.sh`: 92 tests passed, Ruff lint/format passed,
  synthetic execution demo passed.
- New tests use mocked HTTP responses. No exchange orders were sent.
- The frozen Pine file was reconstructed from its complete authoritative text;
  entry rules in the webhook variant remain identical, with only alert/guard additions.
- Real Binance public ticker connectivity was attempted but failed with ConnectError
  in this environment. The deployed VM still requires a real API connectivity check.
- Docker is unavailable here: image build, Compose startup, HTTPS certificate issuance
  and watchdog installation have not been exercised.
- Pine compilation, live TradingView alert delivery, cloud uptime and V6 strategy
  profitability are not verified by these checks.
- No Google Cloud resources provisioned. No TESTNET/LIVE modes enabled.
