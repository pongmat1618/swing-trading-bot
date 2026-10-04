V6.0 SOLUSDT LONG CORE — FROZEN VALIDATION BUILD

Recommended chart
- SOLUSDT
- 5-minute chart

Frozen logic
4H: HH + HL, Close > EMA25, EMA25 rising
15m: EMA25 pullback, bullish candle, HL preserved, close-position >= 60%
5m: micro structure break OR bullish rejection, RSI OR MACD confirmation

Execution
- Long only
- Structural SL = 15m structure swing - 0.10 x ATR(14)
- TP = 2R
- Risk = 1% of current equity
- Max notional = 5x equity
- One position at a time
- Setup expiry = 90 minutes

Costs
- Commission in Pine = 0.05% per side
- Slippage default = 2 ticks; adjust to the actual symbol/exchange
- Funding is not modeled by TradingView Strategy Tester

MCP baseline from the locked V6 setup
Raw: 12 trades, 7W/5L, WR 58.33%, PF 2.68, +9.24%
Base cost stress test: PF 2.14, +7.16%
Conservative stress test: PF 1.99, +6.47%

Important
- MCP validation window was only ~17 days / 5,000 five-minute bars.
- Do not treat this as proof of a durable edge.
- Validate 3 months, 6 months, then 12 months without changing the frozen parameters.

Implementation note
The MCP simulator can size from the next 5m open after confirmation. Pine must submit the market order before that next open exists, so quantity is estimated from the signal-bar close. SL/TP are recalculated from the actual Strategy Tester fill price. Exact MCP/Pine equity matching is therefore not guaranteed.
