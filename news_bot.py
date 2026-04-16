import feedparser
import requests
import json
import os
import hashlib
from datetime import datetime, timezone, timedelta

# ── 설정 ──────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE = "seen_links.json"
KST = timezone(timedelta(hours=9))

BREAKING_KEYWORDS = ["[속보]", "속보", "[긴급]", "긴급", "[단독]", "단독"]

RSS_FEEDS = [
    {"id": "yna",      "name": "연합뉴스", "url": "https://www.yna.co.kr/RSS/news.xml"},
    {"id": "ytn",      "name": "YTN",      "url": "https://www.ytn.co.kr/rss/rss.xml"},
    {"id": "mbc",      "name": "MBC",      "url": "https://imnews.imbc.com/rss/news/news_00.xml"},
    {"id": "kbs",      "name": "KBS",      "url": "https://world.kbs.co.kr/rss/rss_news.xml"},
    {"id": "hankyung", "name": "한국경제", "url": "https://feeds.hankyung.com/articles/all.xml"},
    {"id": "mk",       "name": "매일경제", "url": "https://www.mk.co.kr/rss/30000001/"},
    {"id": "kmib",     "name": "국민일보", "url": "https://www.kmib.co.kr/rss/kmibRssAll.xml"},
    {"id": "chosun",   "name": "조선일보", "url": "https://www.chosun.com/arc/outboundfeeds/rss/"},
    {"id": "seoul",    "name": "서울신문", "url": "https://www.seoul.co.kr/xml/rss/rss_news.xml"},
]

SOURCE_EMOJI = {
    "yna": "📰", "ytn": "📺", "mbc": "📺", "kbs": "📺",
    "hankyung": "💹", "mk": "💹", "kmib": "🗞️", "chosun": "🗞️", "seoul": "🗞️",
}

# ── 유틸 ──────────────────────────────────────────────
def is_breaking(title: str) -> bool:
    return any(kw in title for kw in BREAKING_KEYWORDS)

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-2000:], f)  # 최대 2000개 유지

def link_hash(link: str) -> str:
    return hashlib.md5(link.encode()).hexdigest()

def parse_date(entry) -> datetime:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)

# ── 텔레그램 전송 ──────────────────────────────────────
def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

def format_message(item: dict) -> str:
    emoji = SOURCE_EMOJI.get(item["source_id"], "📌")
    breaking_badge = "🔴 <b>[속보]</b> " if item["is_breaking"] else ""
    time_str = item["pub_date"].astimezone(KST).strftime("%H:%M")
    return (
        f"{breaking_badge}{emoji} <b>{item['source_name']}</b> {time_str}\n"
        f"{item['title']}\n"
        f"<a href=\"{item['link']}\">기사 보기 →</a>"
    )

# ── RSS 수집 ──────────────────────────────────────────
def fetch_feed(feed: dict) -> list:
    try:
        parsed = feedparser.parse(feed["url"])
        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        for entry in parsed.entries[:30]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            if not title or not link:
                continue
            pub_date = parse_date(entry)
            if pub_date < cutoff:
                continue
            items.append({
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "source_id": feed["id"],
                "source_name": feed["name"],
                "is_breaking": is_breaking(title),
            })
        return items
    except Exception as e:
        print(f"[{feed['id']}] RSS 수집 실패: {e}")
        return []

# ── 메인 ─────────────────────────────────────────────
def main():
    seen = load_seen()
    new_items = []

    for feed in RSS_FEEDS:
        items = fetch_feed(feed)
        for item in items:
            h = link_hash(item["link"])
            if h not in seen:
                seen.add(h)
                new_items.append(item)

    # 속보 먼저, 그다음 최신순
    new_items.sort(key=lambda x: (not x["is_breaking"], -x["pub_date"].timestamp()))

    print(f"신규 기사 {len(new_items)}개 발견")

    for item in new_items:
        msg = format_message(item)
        send_telegram(msg)

    save_seen(seen)

if __name__ == "__main__":
    main()
