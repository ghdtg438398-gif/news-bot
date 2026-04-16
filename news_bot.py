import feedparser
import requests
import json
import os
import hashlib
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SEEN_FILE = "seen_links.json"
NEWS_FILE = "docs/news.json"
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

def is_breaking(title):
    return any(kw in title for kw in BREAKING_KEYWORDS)

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-2000:], f)

def link_hash(link):
    return hashlib.md5(link.encode()).hexdigest()

def parse_date(entry):
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
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

def format_message(item):
    emoji = SOURCE_EMOJI.get(item["source_id"], "📌")
    breaking_badge = "🔴 <b>[속보]</b> " if item["is_breaking"] else ""
    time_str = datetime.fromisoformat(item["pub_date"]).astimezone(KST).strftime("%H:%M")
    return (
        f"{breaking_badge}{emoji} <b>{item['source_name']}</b> {time_str}\n"
        f"{item['title']}\n"
        f"<a href=\"{item['link']}\">기사 보기 →</a>"
    )

def fetch_feed(feed):
    try:
        parsed = feedparser.parse(feed["url"])
        items = []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
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
                "pub_date": pub_date.isoformat(),
                "source_id": feed["id"],
                "source_name": feed["name"],
                "is_breaking": is_breaking(title),
            })
        return items
    except Exception as e:
        print(f"[{feed['id']}] RSS 수집 실패: {e}")
        return []

def load_existing_news():
    if os.path.exists(NEWS_FILE):
        with open(NEWS_FILE) as f:
            data = json.load(f)
            return data.get("items", [])
    return []

def save_news(all_items):
    os.makedirs("docs", exist_ok=True)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
    filtered = [i for i in all_items if i["pub_date"] > cutoff]
    filtered.sort(key=lambda x: x["pub_date"], reverse=True)
    filtered = filtered[:200]
    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(filtered),
        "breaking": sum(1 for i in filtered if i["is_breaking"]),
        "items": filtered
    }
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"news.json 저장 완료: {len(filtered)}개")

def main():
    seen = load_seen()
    new_items = []
    all_fresh = []

    for feed in RSS_FEEDS:
        items = fetch_feed(feed)
        all_fresh.extend(items)
        for item in items:
            h = link_hash(item["link"])
            if h not in seen:
                seen.add(h)
                new_items.append(item)

    # 텔레그램: 속보만 전송
    new_items.sort(key=lambda x: (not x["is_breaking"], x["pub_date"]))
    print(f"신규 기사 {len(new_items)}개 발견")
    for item in new_items:
        if item["is_breaking"]:
            send_telegram(format_message(item))

    # JSON 저장: 기존 + 신규 병합
    existing = load_existing_news()
    seen_links = {i["link"] for i in all_fresh}
    merged = all_fresh + [i for i in existing if i["link"] not in seen_links]
    save_news(merged)
    save_seen(seen)

if __name__ == "__main__":
    main()
