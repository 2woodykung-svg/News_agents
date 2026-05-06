"""
Financial News Alert Agent — FREE VERSION
ไม่ใช้ Claude API เลย ใช้ keyword-based scoring แทน
- CRITICAL news → Telegram ทันที
- สรุปข่าวรอง → ทุก 3 ชั่วโมง
ค่าใช้จ่าย: ฟรี 100% (เฉพาะ Telegram Bot ฟรี + RSS ฟรี)
"""

import asyncio
import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

# ── Config ────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID      = os.environ["TELEGRAM_CHAT_ID"]

BANGKOK_TZ            = ZoneInfo("Asia/Bangkok")
SCAN_INTERVAL_MINUTES = 20
DIGEST_INTERVAL_HOURS = 3

# ── RSS Sources (ทั้งหมดฟรี) ──────────────────────────────────────────
NEWS_SOURCES = {
    "SET_THAI": [
        "https://www.set.or.th/th/market/news-and-alert/news/rss",
        "https://www.thansettakij.com/rss",
        "https://www.posttoday.com/rss/src/business.xml",
    ],
    "US_MARKETS": [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC,^IXIC&region=US&lang=en-US",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.marketwatch.com/marketwatch/topstories/",
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
}

# ── Keyword Scoring Engine (แทน AI) ──────────────────────────────────
# score >= 85 → CRITICAL | >= 50 → HIGH | >= 25 → MEDIUM | ต่ำกว่า → LOW

CRITICAL_KEYWORDS = {
    # Fed / ดอกเบี้ย
    "federal reserve": 90, "fed rate": 90, "interest rate decision": 90,
    "rate hike": 85, "rate cut": 85, "emergency meeting": 95,
    "quantitative easing": 80, "quantitative tightening": 80,
    # ตลาดพัง
    "market crash": 95, "circuit breaker": 95, "trading halt": 90,
    "flash crash": 95, "stock market collapse": 95, "black monday": 99,
    "plunge": 75, "sell-off": 70,
    # ราคาน้ำมัน
    "oil price surge": 85, "opec cut": 85, "opec+": 75,
    "crude oil spike": 85, "energy crisis": 90,
    # ภูมิรัฐศาสตร์รุนแรง
    "war declared": 99, "military strike": 95, "nuclear": 95,
    "invasion": 90, "sanctions": 80, "strait of hormuz": 95,
    "taiwan strait": 90,
    # วิกฤตธนาคาร
    "bank failure": 95, "bank run": 90, "bankrupt": 85,
    "liquidity crisis": 90, "credit default": 85,
    # ไทย
    "ตลาดหุ้นไทยร่วง": 85, "ขึ้นดอกเบี้ย": 85, "ลดดอกเบี้ย": 85,
    "กนง": 85, "วิกฤต": 80, "ฉุกเฉิน": 85, "ล้มละลาย": 85,
    "ธนาคารแห่งประเทศไทย": 75, "ค่าเงินบาทอ่อน": 80,
}

HIGH_KEYWORDS = {
    "inflation": 60, "cpi": 60, "gdp": 55, "pmi": 55,
    "earnings": 50, "revenue miss": 65, "profit warning": 70,
    "downgrade": 60, "merger": 55, "acquisition": 55,
    "tariff": 65, "trade war": 70, "recession": 70,
    "nonfarm payroll": 65, "jobs report": 60, "unemployment": 55,
    "oil": 45, "gold": 40, "bitcoin": 45, "crypto": 45,
    # ไทย
    "งบการเงิน": 50, "กำไร": 45, "ขาดทุน": 55, "ปันผล": 45,
    "ซื้อกิจการ": 60, "ควบรวม": 60, "ราคาน้ำมัน": 55,
    "เงินเฟ้อ": 60, "ส่งออก": 45, "ค่าเงิน": 55, "เฟด": 70,
}

CATEGORY_PATTERNS = {
    "SET_THAI":    r"SET|ตลาดหลักทรัพย์|หุ้นไทย|mai|thai baht|บาท|ธปท",
    "US_MARKETS":  r"S&P|nasdaq|dow jones|NYSE|wall street|US stock",
    "ASIA_MARKETS":r"Nikkei|Hang Seng|Shanghai|Kospi|Singapore|ASX",
    "COMMODITY":   r"crude oil|brent|WTI|gold price|silver|copper|commodity|น้ำมัน|ทองคำ",
    "MACRO_FED":   r"Federal Reserve|Fed|ECB|BOJ|central bank|interest rate|inflation|GDP|เฟด|ธนาคารกลาง",
    "GEOPOLITICS": r"war|conflict|sanction|geopolit|military|NATO|สงคราม|ภูมิรัฐศาสตร์",
}

CATEGORY_TH = {
    "SET_THAI":    "หุ้นไทย 🇹🇭",
    "US_MARKETS":  "หุ้นสหรัฐ 🇺🇸",
    "ASIA_MARKETS":"หุ้นเอเชีย 🌏",
    "COMMODITY":   "สินค้าโภคภัณฑ์ 🛢️",
    "MACRO_FED":   "มหภาค/เฟด 🏦",
    "GEOPOLITICS": "ภูมิรัฐศาสตร์ 🌍",
}

# ── Scoring Functions ─────────────────────────────────────────────────
def score_article(title: str, desc: str) -> tuple[str, int, str]:
    text = (title + " " + desc).lower()
    score = 0

    for kw, pts in CRITICAL_KEYWORDS.items():
        if kw.lower() in text:
            score += pts
            break  # นับแค่ critical keyword แรกที่เจอเพื่อป้องกัน over-score

    for kw, pts in HIGH_KEYWORDS.items():
        if kw.lower() in text:
            score += pts

    # ตรวจ % change ในข่าว เช่น "fell 4.5%" หรือ "ร่วง 3%"
    for pct_str in re.findall(r"(\d+\.?\d*)\s*%", text):
        pct = float(pct_str)
        if pct >= 5:   score += 80
        elif pct >= 3: score += 50
        elif pct >= 2: score += 30

    # Detect category
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
    neg = ["fall","drop","crash","decline","plunge","slip","tumble","sink",
           "lose","cut","miss","warn","ร่วง","ลด","ขาดทุน","วิกฤต","ล้ม"]
    pos = ["rise","gain","surge","rally","beat","exceed","grow","jump","soar",
           "record high","เพิ่ม","ขึ้น","กำไร","เติบโต","สูงสุด"]
    for w in neg:
        if w in t: return "📉"
    for w in pos:
        if w in t: return "📈"
    return "➡️"


# ── Utilities ─────────────────────────────────────────────────────────
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
        print(f"[RSS Error] {url[:55]}: {ex}")
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
        print(f"[Telegram Error] {ex}")
        return False


def fmt_critical(article: dict, category: str, dir_emoji: str, score: int) -> str:
    cat_th = CATEGORY_TH.get(category, "ข่าวทั่วไป")
    desc   = article["description"][:250] if article["description"] else ""
    return (
        f"🚨 <b>CRITICAL ALERT</b> — {cat_th}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{dir_emoji} <b>{article['title']}</b>\n\n"
        f"📋 {desc}\n\n"
        f"⚡ Impact Score: {score}\n"
        f"🕐 {now_bkk()} (Bangkok)\n"
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
            lines.append(f"{x['dir_emoji']} <b>{cat}</b>")
            lines.append(f"   {x['article']['title']}")

    if medium:
        lines.append(f"\n🟡 <b>MEDIUM ({len(medium)} ข่าว)</b>")
        for x in medium[:6]:
            cat = CATEGORY_TH.get(x["category"], "")
            lines.append(f"• {cat}  {x['article']['title']}")

    total = len(high) + len(medium)
    lines.append(f"\n📈 รวม {total} ข่าวสำคัญ | สแกนทุก {SCAN_INTERVAL_MINUTES} นาที")
    return "\n".join(lines)


# ── Main Agent ────────────────────────────────────────────────────────
class NewsAgent:
    def __init__(self):
        self.seen:        set[str]   = set()
        self.buffer:      list[dict] = []
        self.last_digest: float      = time.time()

    async def run(self):
        print(f"[{now_bkk()}] 🚀 Free News Agent started")
        async with httpx.AsyncClient() as client:
            await send_telegram(
                f"🤖 <b>News Agent เริ่มทำงานแล้ว</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 SET | หุ้นสหรัฐ | เอเชีย | Commodity | Macro | Geopolitics\n"
                f"⚡ Critical → แจ้งทันที\n"
                f"📊 High/Medium → สรุปทุก {DIGEST_INTERVAL_HOURS} ชม.\n"
                f"💰 ค่าใช้จ่าย: <b>ฟรี 100%</b>\n"
                f"🕐 เริ่ม: {now_bkk()} (Bangkok)", client)

            while True:
                try:
                    await self.scan(client)
                except Exception as ex:
                    print(f"[Loop Error] {ex}")
                await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)

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

        # ถึงเวลา digest หรือยัง
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
