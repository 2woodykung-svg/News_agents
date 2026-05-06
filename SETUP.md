# 📡 News Agent (Free Version) — Setup Guide

## สิ่งที่ต้องมี
- Python 3.11+
- Telegram Bot Token + Chat ID
- ไม่ต้องมี API key ใดๆ ทั้งสิ้น ✅

---

## Run ใน 3 ขั้นตอน

```bash
# 1. ติดตั้ง dependency (มีแค่ 1 ตัว)
pip install httpx

# 2. ตั้งค่า Telegram credentials
cp .env.example .env
nano .env   # ใส่ TELEGRAM_BOT_TOKEN และ TELEGRAM_CHAT_ID

# 3. Run
export $(cat .env | xargs)
python agent_free.py
```

---

## Deploy 24/7 ฟรีบน Railway.app

1. สร้าง repo บน GitHub แล้ว upload ไฟล์ทั้งหมด
2. ไปที่ **railway.app** → New Project → Deploy from GitHub
3. เลือก repo → Add Environment Variables:
   - `TELEGRAM_BOT_TOKEN` = ใส่ค่าจริง
   - `TELEGRAM_CHAT_ID`   = ใส่ค่าจริง
4. Railway จะ detect `requirements.txt` และ deploy อัตโนมัติ
5. ✅ ทำงาน 24/7 ฟรี (Railway มี free tier $5/เดือน credit)

> **หมายเหตุ Railway**: Free tier อาจ sleep หลัง idle — แนะนำ
> upgrade plan $5/เดือน เพื่อให้ run ตลอดเวลา

---

## วิธีหา Telegram Credentials

### Bot Token
1. ใน Telegram ค้นหา **@BotFather**
2. พิมพ์ `/newbot` → ตั้งชื่อ → ได้ Token

### Chat ID (ของตัวเอง)
1. ค้นหา **@userinfobot**
2. พิมพ์ `/start` → ดู ID ที่ได้

### Chat ID ของ Group/Channel
1. Add bot เข้า group ก่อน
2. เปิด browser ไปที่:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. ดู `"chat":{"id": -100xxxxxxxxx}` → นั่นคือ group ID

---

## ข้อจำกัดของ Free Version vs AI Version

| ฟีเจอร์ | Free (Keyword) | AI (Claude Haiku) |
|---------|---------------|-------------------|
| ค่าใช้จ่าย | ฟรี 100% | ~$17-20/เดือน |
| ความแม่นยำ | ~70-75% | ~90-95% |
| สรุปภาษาไทย | ❌ ใช้ title เดิม | ✅ แปลและสรุปเอง |
| บริบทซับซ้อน | ❌ พลาดบ้าง | ✅ เข้าใจ nuance |
| False positive | มีบ้าง | น้อยมาก |

---

## ปรับแต่ง Keywords

หากต้องการเพิ่ม keyword เฉพาะบริษัทที่ติดตาม แก้ใน `agent_free.py`:

```python
HIGH_KEYWORDS = {
    # เพิ่ม keyword บริษัทที่สนใจ
    "ptt": 55,
    "kbank": 55,
    "aot": 55,
    "cpall": 50,
    ...
}
```

---

## อัปเกรดเป็น AI Version ได้เมื่อไหร่ก็ได้

เมื่อพร้อมจ่าย $17-20/เดือน → ใช้ `agent.py` จากโฟลเดอร์ `news_agent/`
แล้วเพิ่ม `ANTHROPIC_API_KEY` ใน environment variables
ระบบจะเปลี่ยนจาก keyword scoring → Claude AI classify ทันที
