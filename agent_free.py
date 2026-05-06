"""
Financial News Alert Agent v2 — FREE VERSION
เพิ่มเติมจาก v1:
- Earnings Checker: SET + US หุ้น (Beat/Miss/In-line)
- Morning Briefing: ทุกวันตี 7 โมงเช้า (Bangkok)
- Thai stock keywords เพิ่มเติม
- ค่าใช้จ่าย: ฟรี 100%
"""

import asyncio
import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, date
from zoneinfo import ZoneInfo

import httpx

# ── Config ────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID      = os.environ["TELEGRAM_CHAT_ID"]

BANGKOK_TZ            = ZoneInfo("Asia/Bangkok")
SCAN_INTERVAL_MINUTES = 20
DIGEST_INTERVAL_HOURS = 3
MORNING_BRIEFING_HOUR = 8   # 08:00 Bangkok

# ── RSS Sources ───────────────────────────────────────────────────────
NEWS_SOURCES = {
    "SET_THAI": [
        "https://www.set.or.th/th/market/news-and-alert/news/rss",
        "https://www.thansettakij.com/rss",
        "https://www.posttoday.com/rss/src/business.xml",
        "https://www.bangkokbiznews.com/rss/data/business.xml",
        "https://feeds.feedburner.com/MoneyAndBanking",
    ],
    "US_MARKETS": [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC,^IXIC&region=US&lang=en-US",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.marketwatch.com/marketwatch/topstories/",
        "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    ],
    "ASIA_MARKETS": [
        "https://asia.nikkei.com/rss/feed/nar",
        "https://www.scmp.com/rss/2/feed",
    ],
    "COMMODITY": [
        "https://oilprice.com/rss/main",
        "https://www.kitco.com/rss/KitcoNewsRSS.xml",
    ],
    "MACRO_FED": [
        "https://www.federalreserve.gov/feeds/press_all.xml",
        "https://feeds.feedburner.com/zerohedge/feed",
        "https://www.imf.org/en/News/rss",
    ],
    "GEOPOLITICS": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.reuters.com/world/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ],
    "EARNINGS": [
        # แหล่งข่าวผลประกอบการไทย
        "https://www.set.or.th/th/market/news-and-alert/news/rss",
        "https://www.thansettakij.com/rss",
        "https://www.bangkokbiznews.com/rss/data/business.xml",
        "https://www.prachachat.net/finance/rss",
    ],
}

# ── หุ้นไทยที่ติดตาม (เพิ่มหรือลบได้) ──────────────────────────────
THAI_STOCKS = [
    # ธนาคาร
    "KBANK", "SCB", "BBL", "KTB", "TTB", "BAY", "TISCO", "KKP",
    # พลังงาน
    "PTT", "PTTEP", "PTTGC", "TOP", "IRPC", "BCP", "SPRC",
    # ขนส่ง / สนามบิน
    "AOT", "AAV", "BA", "THAI",
    # ค้าปลีก
    "CPALL", "BJC", "HMPRO", "CRC", "ROBINS",
    # อสังหาฯ
    "LH", "AP", "SIRI", "ORI", "PSH",
    # เทคโนโลยี / ICT
    "ADVANC", "TRUE", "DTAC", "INTUCH",
    # อาหาร
    "CPF", "TU", "MINT", "OSP",
    # อื่นๆ
    "SCC", "SCCC", "DELTA", "HANA", "KCE",
]

# ── หุ้นสหรัฐที่ติดตาม ────────────────────────────────────────────────
US_STOCKS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA",
    "JPM", "BAC", "GS", "MS", "WFC",
    "XOM", "CVX", "COP",
    "BRK", "V", "MA", "UNH",
]

# ── Keyword Scoring ───────────────────────────────────────────────────
CRITICAL_KEYWORDS = {
    "federal reserve": 90, "fed rate": 90, "interest rate decision": 90,
    "rate hike": 85, "rate cut": 85, "emergency meeting": 95,
    "market crash": 95, "circuit breaker": 95, "trading halt": 90,
    "flash crash": 95, "plunge": 75, "sell-off": 70,
    "oil price surge": 85, "opec cut": 85, "energy crisis": 90,
    "war declared": 99, "military strike": 95, "nuclear": 95,
    "invasion": 90, "sanctions": 80, "strait of hormuz": 95,
    "taiwan strait": 90,
    "bank failure": 95, "bank run": 90, "bankrupt": 85,
    "liquidity crisis": 90, "credit default": 85,
    "ตลาดหุ้นไทยร่วง": 85, "ขึ้นดอกเบี้ย": 85, "ลดดอกเบี้ย": 85,
    "กนง": 85, "วิกฤต": 80, "ฉุกเฉิน": 85, "ล้มละลาย": 85,
    "ธนาคารแห่งประเทศไทย": 75, "ค่าเงินบาทอ่อน": 80,
}

HIGH_KEYWORDS = {
    "inflation": 60, "cpi": 60, "gdp": 55, "pmi": 55,
    "earnings": 50, "revenue miss": 65, "profit warning": 70,
    "downgrade": 60, "merger": 55, "acquisition": 55,
    "tariff": 65, "trade war": 70, "recession": 70,
    "nonfarm payroll": 65, "jobs report": 60,
    "oil": 45, "gold": 40, "bitcoin": 45,
    "งบการเงิน": 50, "กำไร": 45, "ขาดทุน": 55,
    "ปันผล": 45, "ซื้อกิจการ": 60, "ควบรวม": 60,
    "ราคาน้ำมัน": 55, "เงินเฟ้อ": 60, "เฟด": 70,
    "ผลประกอบการ": 55, "รายได้": 40, "กำไรสุทธิ": 55,
    "ไตรมาส": 45, "งวด": 40,
}

# เพิ่ม keyword หุ้นไทยเข้า scoring
for ticker in THAI_STOCKS:
    HIGH_KEYWORDS[ticker.lower()] = 55
    HIGH_KEYWORDS[ticker] = 55

CATEGORY_PATTERNS = {
    "SET_THAI":    r"SET|ตลาดหลักทรัพย์|หุ้นไทย|mai|thai baht|บาท|ธปท|" + "|".join(THAI_STOCKS),
    "US_MARKETS":  r"S&P|nasdaq|dow jones|NYSE|wall street|US stock|" + "|".join(US_STOCKS),
    "ASIA_MARKETS":r"Nikkei|Hang Seng|Shanghai|Kospi|Singapore|ASX",
    "COMMODITY":   r"crude oil|brent|WTI|gold price|silver|copper|น้ำมัน|ทองคำ",
    "MACRO_FED":   r"Federal Reserve|Fed|ECB|BOJ|central bank|interest rate|inflation|GDP|เฟด|ธนาคารกลาง",
    "GEOPOLITICS": r"war|conflict|sanction|geopolit|military|NATO|สงคราม|ภูมิรัฐศาสตร์",
    "EARNINGS":    r"earnings|EPS|revenue|profit|quarterly|beat|miss|Q[1-4]|ผลประกอบการ|กำไร|ไตรมาส",
}

CATEGORY_TH = {
    "SET_THAI":    "หุ้นไทย 🇹🇭",
    "US_MARKETS":  "หุ้นสหรัฐ 🇺🇸",
    "ASIA_MARKETS":"หุ้นเอเชีย 🌏",
    "COMMODITY":   "สินค้าโภคภัณฑ์ 🛢️",
    "MACRO_FED":   "มหภาค/เฟด 🏦",
    "GEOPOLITICS": "ภูมิรัฐศาสตร์ 🌍",
    "EARNINGS":    "ผลประกอบการ 📊",
}


# ── Earnings Detection ────────────────────────────────────────────────
BEAT_KEYWORDS  = [
    # ภาษาไทย (หลัก)
    "ดีกว่าคาด", "สูงกว่าคาด", "เกินคาด", "เหนือคาด",
    "กำไรเพิ่ม", "กำไรโต", "กำไรสูงสุด", "กำไรสูงกว่า",
    "รายได้เพิ่ม", "รายได้โต", "ผลงานดี", "ทำนิวไฮ",
    # ภาษาอังกฤษ (รอง)
    "beat", "beats", "topped", "exceeded", "surpassed",
    "better than", "above estimates", "above expectations",
]
MISS_KEYWORDS  = [
    # ภาษาไทย (หลัก)
    "แย่กว่าคาด", "ต่ำกว่าคาด", "ไม่ถึงเป้า", "ต่ำกว่าประมาณการ",
    "กำไรลด", "กำไรร่วง", "กำไรหด", "กำไรต่ำกว่า",
    "ขาดทุนเพิ่ม", "ผลงานแย่", "ผิดหวัง", "ต่ำกว่าเป้า",
    # ภาษาอังกฤษ (รอง)
    "miss", "missed", "fell short", "below estimates",
    "below expectations", "disappointed", "weaker than expected",
]
INLINE_KEYWORDS = [
    "ตามคาด", "เป็นไปตามคาด", "สอดคล้องกับคาด", "ใกล้เคียงคาด",
    "in line", "inline", "met expectations", "as expected",
]

def detect_earnings(title: str, desc: str) -> dict | None:
    """ตรวจว่าเป็นข่าว earnings และ beat/miss/inline ไหม — เน้นหุ้นไทย SET"""
    text = (title + " " + desc).lower()

    # สัญญาณข่าว earnings ภาษาไทยและอังกฤษ
    earnings_signals = [
        "ผลประกอบการ", "กำไรสุทธิ", "ไตรมาส", "งวด", "รายได้",
        "งบการเงิน", "ประกาศผล", "รายงานผล",
        "earnings", "eps", "quarterly", "profit", "revenue",
        "q1", "q2", "q3", "q4",
    ]
    if not any(s in text for s in earnings_signals):
        return None

    # หา ticker ไทยก่อน (เน้น SET)
    ticker_found = None
    for t in THAI_STOCKS:
        if t.lower() in text or t in title:
            ticker_found = t
            break
    # ถ้าไม่เจอไทย ค่อยหาสหรัฐ
    if not ticker_found:
        for t in US_STOCKS:
            if t.lower() in text or t in title:
                ticker_found = t
                break

    # ตรวจ beat/miss/inline
    result = "INLINE"
    for kw in BEAT_KEYWORDS:
        if kw in text:
            result = "BEAT"
            break
    if result == "INLINE":
        for kw in MISS_KEYWORDS:
            if kw in text:
                result = "MISS"
                break

    # หาตัวเลข % ถ้ามี
    pct = None
    pct_matches = re.findall(r"([+-]?\d+\.?\d*)\s*%", text)
    if pct_matches:
        pct = pct_matches[0]

    return {
        "ticker": ticker_found,
        "result": result,
        "pct": pct,
    }


def fmt_earnings_alert(article: dict, earnings: dict) -> str:
    """Format earnings alert message"""
    result = earnings["result"]
    ticker = earnings["ticker"] or "Unknown"
    pct    = earnings["pct"]

    if result == "BEAT":
        emoji, label, dir_e = "✅", "BEAT — ดีกว่าคาด", "📈"
    elif result == "MISS":
        emoji, label, dir_e = "❌", "MISS — แย่กว่าคาด", "📉"
    else:
        emoji, label, dir_e = "➡️", "IN-LINE — ตามคาด", "➡️"

    pct_line = f"ต่างจากคาด: {pct}%\n" if pct else ""

    return (
        f"📊 <b>EARNINGS ALERT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{emoji} <b>{label}</b> — {ticker}\n\n"
        f"📋 {article['title']}\n\n"
        f"{pct_line}"
        f"{dir_e} {article['description'][:200]}\n\n"
        f"🕐 {now_bkk()} (Bangkok)\n"
        f"🔗 <a href='{article['link']}'>อ่านต่อ</a>"
    )


# ── Morning Briefing ──────────────────────────────────────────────────
async def fetch_morning_data(client: httpx.AsyncClient) -> dict:
    """ดึงข้อมูลตลาดสำหรับ morning briefing"""
    headlines = []
    try:
        feeds = [
            "https://www.set.or.th/th/market/news-and-alert/news/rss",
            "https://www.thansettakij.com/rss",
            "https://feeds.marketwatch.com/marketwatch/topstories/",
        ]
        for url in feeds:
            articles = await fetch_rss(url, client)
            for a in articles[:2]:
                headlines.append(a["title"])
    except Exception:
        pass
    return {"headlines": headlines[:6]}


def fmt_morning_briefing(data: dict) -> str:
    """Format morning briefing 08:00"""
    now = datetime.now(BANGKOK_TZ)
    day_th = ["จันทร์", "อังคาร", "พุธ", "พฤหัส", "ศุกร์", "เสาร์", "อาทิตย์"]
    weekday = day_th[now.weekday()]
    date_str = now.strftime(f"วัน{weekday}ที่ %d/%m/%Y")

    headlines = data.get("headlines", [])
    headline_lines = ""
    for i, h in enumerate(headlines[:5], 1):
        headline_lines += f"{i}. {h}\n"

    return (
        f"🌅 <b>MORNING BRIEFING</b> — 08:00\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {date_str}\n\n"
        f"📰 <b>ข่าวสำคัญก่อนตลาดเปิด</b>\n"
        f"{headline_lines}\n"
        f"🇹🇭 <b>ตลาดไทยวันนี้</b>\n"
        f"• SET / mai เปิด 10:00 น.\n"
        f"• Pre-opening 9:30 น.\n\n"
        f"💡 <b>จุดที่ควรติดตามวันนี้</b>\n"
        f"• ข่าวบริษัทจดทะเบียนประกาศผลประกอบการ\n"
        f"• ตัวเลขเศรษฐกิจสำคัญที่จะประกาศ\n"
        f"• ทิศทางตลาดต่างประเทศคืนที่ผ่านมา\n\n"
        f"⚡ <i>Bot สแกนข่าวทุก {SCAN_INTERVAL_MINUTES} นาที ตลอด 24 ชม.</i>"
    )


# ── Scoring & Utilities ───────────────────────────────────────────────
def score_article(title: str, desc: str) -> tuple[str, int, str]:
    text = (title + " " + desc).lower()
    score = 0

    for kw, pts in CRITICAL_KEYWORDS.items():
        if kw.lower() in text:
            score += pts
            break

    for kw, pts in HIGH_KEYWORDS.items():
        if kw.lower() in text:
            score += pts

    for pct_str in re.findall(r"(\d+\.?\d*)\s*%", text):
        pct = float(pct_str)
        if pct >= 5:   score += 80
        elif pct >= 3: score += 50
        elif pct >= 2: score += 30

    category = "MACRO_FED"
    for cat, pattern in CATEGORY_PATTERNS.items():
        if re.search(pattern, title + " " + desc, re.IGNORECASE):
            category = cat
            break

    if score >= 85:   impact = "CRITICAL"
    elif score >= 50: impact = "HIGH"
    elif score >= 25: impact = "MEDIUM"
    else:             impact = "LOW"

    return impact, score, category


def get_direction_emoji(title: str) -> str:
    t = title.lower()
    for w in ["fall","drop","crash","decline","plunge","miss","warn","ร่วง","ลด","ขาดทุน","วิกฤต"]:
        if w in t: return "📉"
    for w in ["rise","gain","surge","rally","beat","exceed","grow","jump","เพิ่ม","ขึ้น","กำไร","เติบโต"]:
        if w in t: return "📈"
    return "➡️"

def now_bkk() -> str:
    return datetime.now(BANGKOK_TZ).strftime("%d/%m/%Y %H:%M")

def news_hash(title: str, source: str) -> str:
    return hashlib.md5(f"{title}{source}".encode()).hexdigest()[:12]


# ── RSS Fetcher ───────────────────────────────────────────────────────
async def fetch_rss(url: str, client: httpx.AsyncClient) -> list[dict]:
    try:
        r = await client.get(url, timeout=12, follow_redirects=True)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
        items = []
        for e in entries[:10]:
            title = (e.findtext("title") or
                     e.findtext("atom:title", namespaces=ns) or "").strip()
            desc  = (e.findtext("description") or
                     e.findtext("summary") or
                     e.findtext("atom:summary", namespaces=ns) or "").strip()[:400]
            link  = e.findtext("link") or ""
            if not link:
                el = e.find("atom:link", ns)
                link = (el.get("href") if el is not None else "") or ""
            if title:
                items.append({"title": title, "description": desc,
                               "link": link, "source": url})
        return items
    except Exception as ex:
        print(f"[RSS] {url[:55]}: {ex}")
        return []


# ── Telegram ──────────────────────────────────────────────────────────
async def send_telegram(msg: str, client: httpx.AsyncClient) -> bool:
    try:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
        return r.status_code == 200
    except Exception as ex:
        print(f"[Telegram] {ex}")
        return False


def fmt_critical(article: dict, category: str, dir_emoji: str, score: int) -> str:
    cat_th = CATEGORY_TH.get(category, "ข่าวทั่วไป")
    return (
        f"🚨 <b>CRITICAL ALERT</b> — {cat_th}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{dir_emoji} <b>{article['title']}</b>\n\n"
        f"📋 {article['description'][:250]}\n\n"
        f"⚡ Score: {score} | 🕐 {now_bkk()} (Bangkok)\n"
        f"🔗 <a href='{article['link']}'>อ่านต่อ</a>"
    )


def fmt_digest(buffer: list[dict]) -> str:
    if not buffer:
        return ""
    high   = [x for x in buffer if x["impact"] == "HIGH"]
    medium = [x for x in buffer if x["impact"] == "MEDIUM"]
    lines  = [f"📊 <b>NEWS DIGEST</b> — {now_bkk()}", "━━━━━━━━━━━━━━━━━━━━"]

    if high:
        lines.append(f"\n🔴 <b>HIGH IMPACT ({len(high)} ข่าว)</b>")
        for x in high[:8]:
            cat = CATEGORY_TH.get(x["category"], "")
            lines.append(f"{x['dir_emoji']} {cat}  {x['article']['title']}")

    if medium:
        lines.append(f"\n🟡 <b>MEDIUM ({len(medium)} ข่าว)</b>")
        for x in medium[:6]:
            cat = CATEGORY_TH.get(x["category"], "")
            lines.append(f"• {cat}  {x['article']['title']}")

    lines.append(f"\n<i>สแกนทุก {SCAN_INTERVAL_MINUTES} นาที | Digest ทุก {DIGEST_INTERVAL_HOURS} ชม.</i>")
    return "\n".join(lines)


# ── Main Agent ────────────────────────────────────────────────────────
class NewsAgent:
    def __init__(self):
        self.seen:              set[str]   = set()
        self.buffer:            list[dict] = []
        self.last_digest:       float      = time.time()
        self.last_briefing_day: date | None = None

    async def run(self):
        print(f"[{now_bkk()}] 🚀 News Agent v2 started")
        async with httpx.AsyncClient() as client:
            await send_telegram(
                f"🤖 <b>News Agent v2 เริ่มทำงานแล้ว</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 SET | US | เอเชีย | Commodity | Macro | Geopolitics\n"
                f"📊 Earnings Checker: SET + US หุ้น\n"
                f"🌅 Morning Briefing: ทุกวัน 08:00 Bangkok\n"
                f"⚡ Critical → แจ้งทันที\n"
                f"💰 ค่าใช้จ่าย: <b>ฟรี 100%</b>\n"
                f"🕐 เริ่ม: {now_bkk()} (Bangkok)", client)

            while True:
                try:
                    await self.check_morning_briefing(client)
                    await self.scan(client)
                except Exception as ex:
                    print(f"[Loop Error] {ex}")
                await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)

    async def check_morning_briefing(self, client: httpx.AsyncClient):
        """ส่ง morning briefing ถ้าถึงเวลา 07:00 และยังไม่ได้ส่งวันนี้"""
        now = datetime.now(BANGKOK_TZ)
        today = now.date()
        if (now.hour == MORNING_BRIEFING_HOUR and
                self.last_briefing_day != today):
            print(f"[{now_bkk()}] 🌅 Sending morning briefing...")
            data = await fetch_morning_data(client)
            msg  = fmt_morning_briefing(data)
            ok   = await send_telegram(msg, client)
            if ok:
                self.last_briefing_day = today
                print(f"[{now_bkk()}] Morning briefing sent ✅")

    async def scan(self, client: httpx.AsyncClient):
        print(f"[{now_bkk()}] 🔍 Scanning...")
        tasks   = [fetch_rss(url, client)
                   for urls in NEWS_SOURCES.values() for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        fresh = []
        for batch in results:
            if isinstance(batch, list):
                for a in batch:
                    h = news_hash(a["title"], a["source"])
                    if h not in self.seen:
                        self.seen.add(h)
                        fresh.append(a)

        print(f"[{now_bkk()}] {len(fresh)} new articles")

        for article in fresh:
            # ตรวจ Earnings ก่อน
            earnings = detect_earnings(article["title"], article["description"])
            if earnings and earnings["result"] in ("BEAT", "MISS"):
                msg = fmt_earnings_alert(article, earnings)
                ok  = await send_telegram(msg, client)
                ticker = earnings.get("ticker", "")
                result = earnings.get("result", "")
                print(f"  📊 EARNINGS {result} {ticker} → {'✅' if ok else '❌'}")
                continue  # ข้ามการ score ปกติ

            # Score ข่าวทั่วไป
            impact, score, category = score_article(
                article["title"], article["description"])
            dir_emoji = get_direction_emoji(article["title"])

            if impact == "CRITICAL":
                msg = fmt_critical(article, category, dir_emoji, score)
                ok  = await send_telegram(msg, client)
                print(f"  🚨 CRITICAL score={score} → {article['title'][:50]} {'✅' if ok else '❌'}")
            elif impact in ("HIGH", "MEDIUM"):
                self.buffer.append({
                    "article": article, "impact": impact,
                    "category": category, "dir_emoji": dir_emoji,
                })
                print(f"  [{impact}] score={score} → {article['title'][:50]}")

        if time.time() - self.last_digest >= DIGEST_INTERVAL_HOURS * 3600:
            await self.flush_digest(client)

    async def flush_digest(self, client: httpx.AsyncClient):
        msg = fmt_digest(self.buffer)
        if msg:
            ok = await send_telegram(msg, client)
            print(f"[DIGEST] {len(self.buffer)} items → {'✅' if ok else '❌'}")
        self.buffer.clear()
        self.last_digest = time.time()


if __name__ == "__main__":
    agent = NewsAgent()
    asyncio.run(agent.run())
