# เตรียมใช้โปรเจกต์กับ Codex Cloud

## สิ่งที่พร้อมแล้ว
- Python 3.12+, dependency versions ตามไฟล์ requirements เดิม
- AGENTS.md อธิบายโครงสร้าง ขอบเขต และคำสั่งตรวจสอบ
- scripts/codex_setup.sh ติดตั้ง dependency และสร้าง .env สำหรับ PAPER
- scripts/codex_check.sh รัน pytest, Ruff และ offline demo
- ไม่รวม .env, credentials, .venv, SQLite หรือ logs ใน ZIP

## นำเข้าซอร์ส
แตก ZIP แล้วใช้เนื้อหาภายใน btc-swing-trading-bot เป็น root ของ repository
(ให้ AGENTS.md, README.md, requirements-dev.txt และ app/ อยู่ที่ root)
นำซอร์สขึ้น repository ที่คุณเชื่อมกับ Codex หรือเปิดเป็นโครงการใน Cloud
ตามช่องทางนำเข้าที่บัญชีของคุณมี การเตรียม ZIP นี้ยังไม่ได้สร้าง repository
หรือเชื่อมบัญชีให้ และยังไม่ได้รันใน Codex Cloud จริง

## ติดตั้งและตรวจสอบ
เลือก Python 3.12 หรือใหม่กว่า เมื่อเปิดโครงการแล้วรันจาก root:

```bash
bash scripts/codex_setup.sh
bash scripts/codex_check.sh
```

ในขั้นตอนสร้าง environment ให้ขอ Python 3.12+ และกำหนด Install script:

```bash
bash scripts/codex_setup.sh
```

หากใช้ Legacy environment ที่มี Setup/Maintenance script ใช้คำสั่งเดียวกัน
สำหรับ environment ปัจจุบัน ให้ตรวจและ Republish เมื่อเปลี่ยน dependency
Setup ต้องเข้าถึง package registry เพื่อติดตั้ง dependency; tests และ demo
ทำงาน offline ได้หลังติดตั้ง ไม่ต้องใส่ Binance API key หรือ OpenAI API key
ใช้ .venv/bin/python โดยตรง เพราะ export ใน setup shell อาจไม่คงอยู่ใน task

## ข้อความเริ่มงานสำหรับ Codex
คัดลอกข้อความใน CODEX_START_PROMPT.md ไปวางใน task แรก

## ทดลองเว็บเซอร์วิสใน environment

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log
```

ใช้ terminal อีกอันเรียก http://127.0.0.1:8000/health ใน environment เดียวกัน
localhost นี้ไม่ได้เป็น public TradingView webhook; การเปิด preview ขึ้นกับ
environment ที่ใช้ หยุด server หลังทดลอง

## สถานะและงานถัดไป
V1 มี PAPER execution จากสัญญาณภายนอก ยังไม่มี V6/Pine/automatic price feed
และปฏิเสธ TESTNET/LIVE ตอน startup ห้ามอ้างว่า forward test หรือ backtest
ผ่านแล้วจาก demo ที่ใช้ราคาสังเคราะห์ Codex ใช้พัฒนาและตรวจสอบซอร์ส;
หากต้องการให้บอทรันต่อเนื่อง ต้องเตรียม deployment สำหรับโฮสต์แยก

## ขั้นตอนใน UI ปัจจุบัน
1. นำซอร์สขึ้น GitHub repository ที่คุณเลือก
2. เลือก Work in > Cloud > Select environment > Create environment
3. เลือก repository แล้ว Get started
4. ขอให้ setup ใช้ Python 3.12+, รัน bash scripts/codex_setup.sh และ
   bash scripts/codex_check.sh โดยคง PAPER และไม่เริ่ม server อัตโนมัติ
5. ตรวจ setup report แล้ว Publish
6. เลือก Start a new task แล้ววาง CODEX_START_PROMPT.md

อ้างอิง OpenAI (ตรวจเมื่อ 2026-10-04):
https://learn.chatgpt.com/docs/environments/cloud-environments
