# BTCUSDT Swing Trading Bot V1

สำหรับ Codex Cloud: อ่าน [CODEX_CLOUD.md](CODEX_CLOUD.md) และใช้ [CODEX_START_PROMPT.md](CODEX_START_PROMPT.md)

**สร้างแล้ว: TradingView → Webhook → ตรวจสัญญาณ → Risk Manager → Paper Futures Trading**

V1 จำลองซื้อขายในเครื่องเท่านั้น ไม่เรียก API ซื้อขาย Binance ไม่มี Trade Setup V4/V5
หรือ EMA/ATR ฝังในชั้น Execution สัญญาณส่งจุด SL และ optional TP เข้ามาได้
จึงเปลี่ยน Strategy ภายหลังได้โดยไม่รื้อ Paper engine

## สถานะความสามารถ

| ส่วน | V1 |
|---|---|
| Webhook + durable queue | ใช้งานได้ รับแล้วตอบ 202 ก่อนประมวลผล |
| LONG / SHORT / CLOSE_LONG / CLOSE_SHORT / CLOSE_ALL | ใช้งานได้ใน PAPER |
| SL / TP / ค่าธรรมเนียม / Slippage | จำลองผ่านราคาที่ส่งให้ Paper |
| Risk, Position sizing, 5x, 1 position | ใช้งานได้และกำหนดค่าได้ |
| Duplicate / Restart / Emergency disable | SQLite + transaction |
| Binance Futures TESTNET adapter | มีโค้ดและ mock tests แต่ยังไม่เชื่อม Engine |
| TESTNET service mode | ปฏิเสธตอน startup รอ V1.1 |
| LIVE service mode | ปฏิเสธตอน startup ไม่มี production endpoint |
| Strategy integration / Forward test | ขั้นต่อไป |

## เริ่มใน Windows (PowerShell)

ติดตั้ง Python 3.12+ แล้วแตก ZIP เข้าโฟลเดอร์ เปิด PowerShell ในโฟลเดอร์นี้:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m scripts.bootstrap
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.demo
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

`bootstrap` สร้าง `.env` พร้อม token สุ่ม 2 ตัว ไม่แสดง token และไม่เขียนทับไฟล์เดิม
ไม่ต้องใช้ Binance API Key สำหรับ PAPER ตั้ง `BOT_MODE=PAPER` ตามค่าเริ่มต้น
ถ้ามี `.env` เดิมที่ยังว่าง ให้ใส่ token คนละค่าอย่างน้อย 32 ตัวอักษร
ตัวอย่างสร้าง token: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

บน Linux/macOS ใช้ `python3 -m venv .venv` และแทนเส้นทาง Python ด้วย `.venv/bin/python`
ใช้ Python ที่ต้องการ 3.12+ อย่ารัน `scripts/send_signal.py` ตรง ๆ ให้ใช้ `-m scripts.send_signal`

ทดสอบ server ที่ [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
Swagger schema อยู่ที่ [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
เปิดหน้าดังกล่าวไม่ทำให้ส่งออเดอร์เอง

## ทดสอบส่งสัญญาณ

เปิด PowerShell อีกหน้าต่างในโฟลเดอร์เดิม ขณะ server ทำงาน:

```powershell
.\.venv\Scripts\python.exe -m scripts.send_signal --action LONG --price 100000 --stop 98000
.\.venv\Scripts\python.exe -m scripts.send_signal --action CLOSE_ALL --price 100100
.\.venv\Scripts\python.exe -m scripts.send_signal --action SHORT --price 100000 --stop 102000
```

สคริปต์ใช้ `.env` สร้าง timestamp UTC ปัจจุบันและ ID ใหม่ทุกครั้ง
ID เดิมต้องใช้ payload เดิมทั้งหมด รวม timestamp ถ้าเปลี่ยนข้อมูลด้วย ID เดิมจะตอบ 409
จึงไม่ใช้ `--id` เดิมเมื่อส่งคำสั่งใหม่ด้วยสคริปต์นี้
ผล 202 คือบันทึกลง queue แล้ว ดูผลจริงที่ `GET /signals/{signal_id}` โดยใช้ ADMIN_TOKEN

`python -m scripts.demo` เป็นการจำลองแบบ offline ครบวงจรในฐานข้อมูลชั่วคราว
ตรวจ Long → TP, Short → SL, duplicate, disable → close และ restart
ตัวเลขกำไรใน demo เป็นสถานการณ์สังเคราะห์เพื่อเช็ก Engine ไม่ใช่ backtest ของ Strategy

## ตั้งค่าและ Position sizing

`config.yaml` มีค่าทดลองเริ่มต้น:

| ค่า | เริ่มต้น | ความหมาย |
|---|---:|---|
| symbol / timeframe | BTCUSDT / 4H | ต้องตรงกับสัญญาณ |
| leverage | 5 | ใช้จำกัด margin; ไม่คูณความเสี่ยง 1% ซ้ำ |
| risk_per_trade | 0.01 | งบขาดทุนที่ SL แบบจำลอง = 1% ของ equity |
| reward_risk_ratio | 1.5 | ระยะราคา TP / SL เมื่อสัญญาณไม่ได้ส่ง TP |
| max_open_positions | 1 | ไม่เพิ่มไม้ ไม่กลับฝั่งอัตโนมัติ |
| max_notional / max_quantity | 10000 USDT / 1 BTC | เพดานเพิ่มเติม |
| margin_utilization | 0.9 | ใช้ margin ได้สูงสุด 90% ของ available |
| paper_initial_balance | 1000 USDT | ทุนจำลอง ตั้งค่าเองได้ ไม่ใช่ยอดเงินจริง |
| paper_fee_rate | 0.0005 | ค่าธรรมเนียมจำลองต่อฝั่ง ไม่ใช่อัตราจริงของบัญชี |
| paper_slippage_bps | 2 | ราคาเติมคลาดเคลื่อนในทางเสียเปรียบ 0.02% ต่อฝั่ง |
| quantity_step / price_tick | 0.001 / 0.1 | ตัวกรองจำลอง ต้องตรวจใหม่เมื่อเชื่อม Exchange |
| max_signal_age_seconds | 300 | ปฏิเสธสัญญาณเก่าเกิน 5 นาที |

งบเสี่ยง = equity × risk_per_trade
ขนาด Position = งบเสี่ยง / (ระยะ SL + exit slippage + entry/exit fees ต่อหน่วย)
แล้วจำกัดด้วย margin, max_notional, max_quantity และปัดลงตาม quantity_step
ถ้าต่ำกว่า min_quantity หรือ min_notional จะปฏิเสธ ไม่ปัดขึ้นเพิ่มความเสี่ยง
ส่ง `take_profit` เองได้; RR ใน config เป็น fallback ของระยะราคา ไม่ใช่ net RR หลังค่าธรรมเนียม
Price gap ผ่าน SL อาจทำให้ขาดทุนจริงของ Paper เกินงบ 1% ได้

ยอดจำลองเริ่มต้นใช้เฉพาะสร้างฐานข้อมูลครั้งแรก เปลี่ยนค่าใน YAML ไม่รีเซ็ตยอดเดิม
หยุด server และใช้ `database_path` ใหม่ถ้าต้องการบัญชีจำลองอีกชุด
อย่าใช้ฐานข้อมูลเดียวกันกับคนละ symbol เก็บ database และ logs ไว้เมื่ออัปเดตโค้ด

## Webhook payload

```json
{
  "signal_id": "V5-BTCUSDT-4H-LONG-unique-event-id",
  "timestamp": "2026-10-04T06:48:48Z",
  "symbol": "BTCUSDT",
  "action": "LONG",
  "strategy": "V5",
  "timeframe": "4H",
  "price": "100000",
  "stop_loss": "98000",
  "take_profit": "103000"
}
```

timestamp ด้านบนเป็นตัวอย่าง ต้องแทนด้วยเวลาเกิดสัญญาณจริง
LONG ต้อง SL < price และ TP > price; SHORT กลับด้าน; TP ไม่บังคับ
CLOSE_* ต้องไม่มี SL/TP แต่ยังต้องมี price, ID และ timestamp
สัญญาณเข้าไม่มี SL จะตอบ 422 เพราะไม่มีข้อมูลคำนวณขนาด Position
ไม่ใช้ตัวอย่าง price-only จากขั้นออกแบบเพื่อส่งออเดอร์
ส่ง symbol แบบ `BTCUSDT` ไม่ใช้ `BINANCE:BTCUSDT.P`; ส่ง timeframe `4H` ไม่ใช่ `240`

Webhook รับ `Authorization: Bearer WEBHOOK_SECRET` สำหรับ client ที่ใส่ header ได้
TradingView ใช้ field `secret` เพิ่มใน JSON โดยมีเฉพาะ token ของ webhook นี้
ไม่ใส่ API Secret, ADMIN_TOKEN หรือรหัสผ่านบัญชีใน Alert
Server ตัด secret ออกก่อนบันทึก DB/log และไม่ echo body เมื่อ schema ผิด

## เชื่อม TradingView เมื่อ Strategy พร้อม

1. นำ Strategy ที่สรุปแล้วไปสร้าง alert message ให้มี ID คงที่ต่อเหตุการณ์
   (strategy + symbol + timeframe + bar/event ID + action) และ timestamp เวลาเกิดจริง
   ให้ใช้ bar close ถ้าต้องการกันสัญญาณระหว่างแท่งจาก Strategy ไม่ได้บังคับใน Engine
2. ให้ Pine สร้าง JSON ด้วย SL/TP เป็นตัวเลขจาก Strategy เดียวกัน
   ถ้าจุด SL อยู่ในตัวแปรของ Pine ให้สร้าง message ผ่าน `alert()` หรือ `alert_message`
   แล้วใช้ placeholder ที่ตรงชนิด Alert; อย่าใช้ `{{plot(...)}}` เดาว่าตรงกับตัวแปร
3. Webhook URL: `https://YOUR_HOST/webhook/tradingview`
   ต้องใช้ public HTTPS reverse proxy บน port 443 เพื่อเข้าถึง server ในเครื่อง/โฮสต์
   `localhost:8000` ใช้ได้เฉพาะทดสอบในเครื่อง ยังไม่ใช่ URL สำหรับ TradingView
4. เปิด 2FA และสร้าง Alert แล้วตรวจ 202 กับผลจาก `/signals/{signal_id}`
   Alert เดิมที่ retry ต้องใช้ payload เดิมเพื่อป้องกันการเปิดซ้ำ
5. `examples/tradingview_long.json.template` เป็น template มี TradingView placeholders และช่อง SL
   ต้องแทนค่าทุกช่องก่อนใช้ ไม่ใช่ JSON ที่ส่งให้ API ได้ทันที

TradingView รับ webhook port 80/443 และยกเลิกเมื่อ server ตอบช้ากว่า 3 วินาที
V1 บันทึก queue แล้วตอบทันที งานซื้อขายจำลองทำใน worker
ตอบ 503 เมื่อฐานข้อมูล busy หรือ queue เต็ม ต้อง retry payload เดิม
202 ไม่รับรองว่าออเดอร์ถูกเปิดแล้ว ตรวจสถานะ `PROCESSED / REJECTED / FAILED`
`PROCESSED` อาจมีผล `SKIPPED` หรือ `NO_POSITION` ให้อ่าน result ด้วย

อ้างอิง: [TradingView webhook configuration](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/)

## ราคาจำลองและ API

**V1 ไม่มี live market feed** `price` ในสัญญาณและ `/paper/tick` เป็นราคาจำลองที่ผู้ใช้ส่งมา
ถ้าไม่มี tick ใหม่ SL/TP จะไม่รู้ว่าราคาตลาดเปลี่ยน การทดสอบต่อเนื่องต้องเพิ่ม price feeder
ขั้น V1.1 จะเชื่อม mark price และ reconciliation จริง ราคาสังเคราะห์ไม่ใช่ราคาปัจจุบัน BTC

| Endpoint | สิทธิ์ | หน้าที่ |
|---|---|---|
| GET /health | ไม่ใช้ token | PAPER + worker heartbeat |
| POST /webhook/tradingview | WEBHOOK_SECRET | ตรวจและบันทึก queue |
| GET /state | Bearer ADMIN_TOKEN | balance, equity, margin, position |
| GET /signals/{id} | Bearer ADMIN_TOKEN | ผลประมวลผล |
| POST /paper/tick | Bearer ADMIN_TOKEN | ส่งราคาจำลอง `{"symbol":"BTCUSDT","price":"98000"}` |
| POST /admin/trading | Bearer ADMIN_TOKEN | `{"enabled":false}` หยุด entry ใหม่ |

ตัวอย่าง PowerShell สำหรับ tick/ดูสถานะ: อ่าน ADMIN_TOKEN จาก `.env` ในเครื่อง แล้ว:

```powershell
$botAdminToken = Read-Host "ADMIN_TOKEN"
$botHeaders = @{ Authorization = "Bearer $botAdminToken" }
Invoke-RestMethod http://127.0.0.1:8000/state -Headers $botHeaders
Invoke-RestMethod http://127.0.0.1:8000/paper/tick -Method Post -Headers $botHeaders -ContentType "application/json" -Body '{"symbol":"BTCUSDT","price":"98000"}'
Invoke-RestMethod http://127.0.0.1:8000/admin/trading -Method Post -Headers $botHeaders -ContentType "application/json" -Body '{"enabled":false}'
```

## หยุด Entry ฉุกเฉิน

- สร้างไฟล์ `STOP_TRADING` ที่โฟลเดอร์โปรเจกต์: `New-Item STOP_TRADING -ItemType File`
- หรือเรียก `/admin/trading` ด้วย `enabled:false` ซึ่งคงอยู่หลัง restart
- หรือใช้ `TRADING_ENABLED=false` แล้ว restart; admin override ค่านี้ไม่ได้

ทั้งสามวิธีหยุดเฉพาะ entry ใหม่ CLOSE และ Paper SL/TP ยังทำงานเมื่อมีราคาใหม่
ไม่ auto-liquidate Position ปัจจุบัน ถ้าต้องการปิดให้ส่ง CLOSE_ALL ด้วยราคาจำลองปัจจุบัน
เปิดใหม่ต้องนำ kill file ออก ตั้ง environment อนุญาต และ admin enabled=true
ถ้าสัญญาณ entry ถูก skip แล้วไม่ replay เอง ต้องรอสัญญาณใหม่และ ID ใหม่

SQLite transaction บันทึก entry/protection/balance/result/audit พร้อมกัน
เมื่อจำลองติดตั้ง protection ล้มเหลว จะ rollback ทั้ง entry และปิด entry ใหม่
Paper exactly-once อยู่ภายในฐานข้อมูลนี้ ไม่ใช่คำรับประกัน exactly-once บน Exchange
`logs/orders.jsonl` เป็น structured execution summary; SQLite `audit` เก็บทุก order/event
ถ้าระบบเสียหายก่อนเขียน log ไฟล์ ให้ใช้งาน audit ที่ commit แล้วเป็นหลัก

## TESTNET และ LIVE

มี `app/exchange/binance_futures.py` แยกออกมาเพื่อใช้ต่อใน V1.1:
อ่าน balance/position/mark price/filters, leverage, market order, SL/TP, close และ cancel
คำสั่งปิดใช้ reduceOnly; protective conditional orders ใช้ closePosition
รองรับ One-way Mode เท่านั้น API key/secret ต้องส่งมาจาก environment ในขั้น integration
TESTNET base URL คือ `https://demo-fapi.binance.com`
SL/TP ใช้ `/fapi/v1/algoOrder`; ยกเลิกทั้ง regular และ algo orders หลังยืนยันว่า flat
read retry ได้จำกัดครั้ง; write timeout จะ query ด้วย client ID
ถ้ายังไม่ทราบผลให้หยุด reconcile ห้ามส่ง order ใหม่ซ้ำโดยเดา

Adapter ทดสอบด้วย mock HTTP เท่านั้น ไม่ได้ส่งคำสั่งบน Testnet จริง
V1 engine ไม่ import adapter; ตั้ง BOT_MODE=TESTNET หรือ LIVE จะ startup ไม่ผ่าน
การเปิดใช้งาน V1.1 ต้องเพิ่ม account reconciliation, filters/precision, protective-order recovery,
actual fill sizing, handling partial fills และ price feed ก่อนต่อคำสั่งครบวงจร
LIVE ยังไม่มีวิธีเปิดใน V1 และไม่มี production URL ใน adapter

อ้างอิงที่ตรวจระหว่างทำ:
[Binance general info](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info),
[Binance Futures trade endpoints](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade)

## Docker

หลังสร้าง `.env`: `docker compose up --build`
API ผูกกับ localhost:8000; ใช้ reverse proxy เมื่อจะรับ Alert จากภายนอก
SQLite และ logs อยู่ใน named volumes แยกจาก image จึงคงอยู่เมื่อ restart/rebuild
ใช้ `/admin/trading` เพื่อ disable ใน Docker; kill file ของเครื่องไม่ได้ mount ใน container
รัน 1 worker ตามค่าเริ่มต้น Dockerfile; ไม่ได้ทดสอบ Docker build ในสภาพแวดล้อมที่สร้างชุดนี้

## ตรวจโค้ดและขอบเขตการจำลอง

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

Unit/integration tests ตรวจ risk sizing, fees, margin caps, validation, HTTP flow, duplicates,
concurrency, crash rollback, restart, long/short/closing, trigger gaps และ mocked Binance requests
ค่าผลทดสอบอยู่ใน `VALIDATION.md`

Paper ไม่จำลอง liquidation, maintenance margin, funding, order book, market impact หรือ intrabar path
ราคาทุก tick ถือว่าเป็นลำดับที่ส่งเข้ามา TP/SL เติมที่ tick ที่สังเกตพร้อม adverse slippage
ไม่มี strategy backtest, performance claim หรือการเชื่อม TradingView/public hosting ในขั้นนี้

## โครงสร้าง

- `app/main.py`, `app/webhook/`: HTTP + authentication + queue acceptance
- `app/engine.py`, `app/storage.py`: worker + atomic paper execution + SQLite journal
- `app/risk/`: risk sizing และเพดาน Position
- `app/exchange/`: protocol, paper และ isolated TESTNET adapter
- `app/strategy/`: interface ว่างรอ Strategy ที่สรุปแล้ว
- `app/models/`, `app/utils/`: validated data, config, structured logging
- `tests/`, `scripts/`, `examples/`: tests, local bootstrap/demo และ webhook template
