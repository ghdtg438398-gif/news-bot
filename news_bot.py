import requests
import json
import os
import hashlib
import re
from datetime import datetime, timezone, timedelta

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
SEEN_FILE = "seen_links.json"
NEWS_FILE = "docs/news.json"
KST = timezone(timedelta(hours=9))

BREAKING_KEYWORDS = ["[속보]", "속보", "[긴급]", "긴급"]
SCOOP_KEYWORDS = ["[단독]", "단독"]

SOURCES = [
    {"id": "yna",      "name": "연합뉴스", "query": "연합뉴스 속보"},
    {"id": "ytn",      "name": "YTN",      "query": "YTN 속보"},
    {"id": "mbc",      "name": "MBC",      "query": "MBC 뉴스 속보"},
    {"id": "kbs",      "name": "KBS",      "query": "KBS 뉴스 속보"},
    {"id": "hankyung", "name": "한국경제", "query": "한국경제 단독"},
    {"id": "mk",       "name": "매일경제", "query": "매일경제 단독"},
    {"id": "kmib",     "name": "국민일보", "query": "국민일보 속보"},
    {"id": "chosun",   "name": "조선일보", "query": "조선일보 단독"},
    {"id": "seoul",    "name": "서울신문", "query": "서울신문 속보"},
]

BREAKING_QUERIES = ["속보", "단독 뉴스", "긴급 뉴스"]

SOURCE_EMOJI = {
    "yna": "📰", "ytn": "📺", "mbc": "📺", "kbs": "📺",
    "hankyung": "💹", "mk": "💹", "kmib": "🗞️", "chosun": "🗞️", "seoul": "🗞️",
}

def is_breaking(title):
    return any(kw in title for kw in BREAKING_KEYWORDS)

def is_scoop(title):
    return any(kw in title for kw in SCOOP_KEYWORDS)

def strip_html(text):
    return re.sub(r'<[^>]+>', '', text).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'").strip()

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-3000:], f)

def link_hash(link):
    return hashlib.md5(link.encode()).hexdigest()

def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

def format_message(item):
    emoji = SOURCE_EMOJI.get(item["source_id"], "📌")
    if item["is_breaking"]:
        badge = "🔴 <b>[속보]</b> "
    elif item["is_scoop"]:
        badge = "🔵 <b>[단독]</b> "
    else:
        badge = ""
    time_str = datetime.fromisoformat(item["pub_date"]).astimezone(KST).strftime("%H:%M")
    return (
        f"{badge}{emoji} <b>{item['source_name']}</b> {time_str}\n"
        f"{item['title']}\n"
        f"<a href=\"{item['link']}\">기사 보기 →</a>"
    )

def naver_search(query, display=20):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        print("네이버 API 키 없음")
        return []
    try:
        r = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": query, "display": display, "sort": "date"},
            headers={
                "X-Naver-Client-Id": NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            timeout=10
        )
        if r.status_code != 200:
            print(f"네이버 API 오류 [{query}]: {r.status_code} {r.text[:100]}")
            return []
        return r.json().get("items", [])
    except Exception as e:
        print(f"네이버 API 예외 [{query}]: {e}")
        return []

def detect_source(title, description, link):
    text = (title + description + link).lower()
    if "연합뉴스" in text or "yna.co.kr" in text: return "yna", "연합뉴스"
    if "ytn" in text: return "ytn", "YTN"
    if "mbc" in text or "imbc" in text: return "mbc", "MBC"
    if "kbs" in text: return "kbs", "KBS"
    if "한국경제" in text or "hankyung" in text: return "hankyung", "한국경제"
    if "매일경제" in text or "mk.co.kr" in text: return "mk", "매일경제"
    if "국민일보" in text or "kmib" in text: return "kmib", "국민일보"
    if "조선일보" in text or "chosun" in text: return "chosun", "조선일보"
    if "서울신문" in text or "seoul.co.kr" in text: return "seoul", "서울신문"
    return "yna", "연합뉴스"

def fetch_all_news():
    all_items = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    seen_links = set()

    for src in SOURCES:
        items = naver_search(src["query"], display=10)
        print(f"[{src['id']}] {len(items)}개")
        for item in items:
            title = strip_html(item.get("title", ""))
            link = item.get("originallink") or item.get("link", "")
            if not title or not link or link in seen_links:
                continue
            try:
                pub_date = datetime.strptime(item.get("pubDate",""), "%a, %d %b %Y %H:%M:%S %z")
            except:
                pub_date = datetime.now(timezone.utc)
            if pub_date < cutoff:
                continue
            seen_links.add(link)
            all_items.append({
                "title": title,
                "link": link,
                "pub_date": pub_date.isoformat(),
                "source_id": src["id"],
                "source_name": src["name"],
                "is_breaking": is_breaking(title),
                "is_scoop": is_scoop(title),
            })

    for query in BREAKING_QUERIES:
        items = naver_search(query, display=20)
        print(f"[{query}] {len(items)}개")
        for item in items:
            title = strip_html(item.get("title", ""))
            link = item.get("originallink") or item.get("link", "")
            if not title or not link or link in seen_links:
                continue
            try:
                pub_date = datetime.strptime(item.get("pubDate",""), "%a, %d %b %Y %H:%M:%S %z")
            except:
                pub_date = datetime.now(timezone.utc)
            if pub_date < cutoff:
                continue
            src_id, src_name = detect_source(title, item.get("description",""), link)
            seen_links.add(link)
            all_items.append({
                "title": title,
                "link": link,
                "pub_date": pub_date.isoformat(),
                "source_id": src_id,
                "source_name": src_name,
                "is_breaking": is_breaking(title),
                "is_scoop": is_scoop(title),
            })

    all_items.sort(key=lambda x: x["pub_date"], reverse=True)
    return all_items

def load_existing_news():
    if os.path.exists(NEWS_FILE):
        with open(NEWS_FILE) as f:
            return json.load(f).get("items", [])
    return []

def save_news(items):
    os.makedirs("docs", exist_ok=True)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    filtered = [i for i in items if i["pub_date"] > cutoff]
    filtered.sort(key=lambda x: x["pub_date"], reverse=True)
    filtered = filtered[:200]
    with open(NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(filtered),
            "breaking": sum(1 for i in filtered if i["is_breaking"]),
            "items": filtered
        }, f, ensure_ascii=False, indent=2)
    print(f"news.json 저장: {len(filtered)}개")

def main():
    seen = load_seen()
    fresh = fetch_all_news()

    new_count = 0
    for item in fresh:
        h = link_hash(item["link"])
        if h not in seen:
            seen.add(h)
            new_count += 1
            if item["is_breaking"] or item["is_scoop"]:
                send_telegram(format_message(item))

    print(f"신규 기사 {new_count}개")

    existing = load_existing_news()
    fresh_links = {i["link"] for i in fresh}
    merged = fresh + [i for i in existing if i["link"] not in fresh_links]
    save_news(merged)
    save_seen(seen)

if __name__ == "__main__":
    main()
