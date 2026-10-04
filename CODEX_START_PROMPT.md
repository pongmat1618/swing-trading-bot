ทำงานกับ repository BTCUSDT Swing Trading Bot V1 นี้ อ่าน AGENTS.md,
README.md และ CODEX_CLOUD.md ก่อน เริ่มด้วย bash scripts/codex_setup.sh
และ bash scripts/codex_check.sh แล้วรายงานผลจริงเป็นภาษาไทย

ตรวจความพร้อมสำหรับการพัฒนาบน Cloud และแก้เฉพาะปัญหาที่ทำซ้ำได้
คง PAPER เป็นค่าเริ่มต้นและคงการปฏิเสธ TESTNET/LIVE
ไม่ส่งคำสั่งซื้อขาย ไม่ deploy และไม่ใช้ credentials จริง
ตรวจ durable queue, duplicate handling, restart recovery, risk sizing และ
การปิด position ขณะ disable โดยใช้ tests ที่มีอยู่ เพิ่ม regression test
เฉพาะเมื่อแก้พฤติกรรม แล้วรัน checks ที่เกี่ยวข้องให้ผ่าน

ยังไม่มี specification ของ V6 ใน repository อย่าเดาหรือเพิ่มกฎ V6
สรุปสิ่งที่พร้อม สิ่งที่ยังขาด และผล checks แยกจาก backtest/forward test
หากไม่มีปัญหา ให้รายงานตามจริง ไม่สร้างการแก้ไขโดยไม่จำเป็น
