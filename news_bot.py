import requests
import json
import os
import hashlib
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
FINNHUB_KEY = os.environ.get("FINNHUB_KEY", "")
SEEN_FILE = "seen_links.json"
NEWS_FILE = "docs/news.json"
US_NEWS_FILE = "docs/us_news.json"
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

US_SOURCE_MAP = {
    'bloomberg': '📊 Bloomberg',
    'reuters': '📡 Reuters',
    'cnbc': '📺 CNBC',
    'cnn': '🔴 CNN',
    'seeking alpha': '📈 Seeking Alpha',
    'marketwatch': '📉 MarketWatch',
    'wall street journal': '📰 WSJ',
    'wsj': '📰 WSJ',
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

def translate_text(text):
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q={quote(text)}"
        r = requests.get(url, timeout=8)
        data = r.json()
        return ''.join(i[0] for i in data[0] if i[0])
    except:
        return None

def format_kr_message(item):
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

def format_us_message(item, translated):
    src = item.get('source', '').lower()
    emoji_name = next((v for k, v in US_SOURCE_MAP.items() if k in src), f"🌐 {item.get('source','')}")
    time_str = datetime.fromtimestamp(item['datetime'], tz=KST).strftime("%H:%M")
    msg = f"🇺🇸 <b>{emoji_name}</b> {time_str}\n"
    msg += f"{item['headline']}\n"
    if translated:
        msg += f"<i>▶ {translated}</i>\n"
    if item.get('related'):
        tickers = ' '.join(f"${t.strip()}" for t in item['related'].split(',')[:3])
        msg += f"{tickers}\n"
    msg += f"<a href=\"{item['url']}\">기사 보기 →</a>"
    return msg

def naver_search(query, display=20):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
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
            print(f"네이버 API 오류 [{query}]: {r.status_code}")
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

def fetch_kr_news():
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
                "title": title, "link": link,
                "pub_date": pub_date.isoformat(),
                "source_id": src["id"], "source_name": src["name"],
                "is_breaking": is_breaking(title), "is_scoop": is_scoop(title),
            })

    for query in BREAKING_QUERIES:
        items = naver_search(query, display=20)
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
                "title": title, "link": link,
                "pub_date": pub_date.isoformat(),
                "source_id": src_id, "source_name": src_name,
                "is_breaking": is_breaking(title), "is_scoop": is_scoop(title),
            })

    all_items.sort(key=lambda x: x["pub_date"], reverse=True)
    return all_items

def fetch_us_news():
    if not FINNHUB_KEY:
        print("Finnhub API 키 없음")
        return []
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": FINNHUB_KEY},
            timeout=10
        )
        if r.status_code != 200:
            print(f"Finnhub 오류: {r.status_code}")
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        cutoff_ts = int(cutoff.timestamp())
        items = [i for i in r.json() if i.get('datetime', 0) > cutoff_ts]
        print(f"[Finnhub] {len(items)}개")
        return items
    except Exception as e:
        print(f"Finnhub 예외: {e}")
        return []

def save_news(items, filepath):
    os.makedirs("docs", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            "total": len(items),
            "items": items
        }, f, ensure_ascii=False, indent=2)
    print(f"{filepath} 저장: {len(items)}개")

def load_existing(filepath):
    if os.path.exists(filepath):
        with open(filepath) as f:
            return json.load(f).get("items", [])
    return []

def main():
    seen = load_seen()

    # ── 한국 뉴스 ──────────────────────────
    kr_fresh = fetch_kr_news()
    kr_new_count = 0
    for item in kr_fresh:
        h = link_hash(item["link"])
        if h not in seen:
            seen.add(h)
            kr_new_count += 1
            if item["is_breaking"] or item["is_scoop"]:
                send_telegram(format_kr_message(item))
    print(f"한국 신규 기사 {kr_new_count}개")

    existing_kr = load_existing(NEWS_FILE)
    kr_links = {i["link"] for i in kr_fresh}
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    merged_kr = kr_fresh + [i for i in existing_kr if i["link"] not in kr_links and i["pub_date"] > cutoff_iso]
    merged_kr.sort(key=lambda x: x["pub_date"], reverse=True)
    save_news(merged_kr[:200], NEWS_FILE)

    # ── 미국 뉴스 ──────────────────────────
    us_fresh = fetch_us_news()
    cutoff_ts = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    us_new_count = 0

    for item in us_fresh:
        h = link_hash(item.get("url", item.get("headline", "")))
        if h not in seen:
            seen.add(h)
            us_new_count += 1
            # 텔레그램 전송 (번역 포함)
            translated = translate_text(item.get("headline", ""))
            send_telegram(format_us_message(item, translated))
    print(f"미국 신규 기사 {us_new_count}개")

    existing_us = load_existing(US_NEWS_FILE)
    us_urls = {i.get("url") for i in us_fresh}
    merged_us = us_fresh + [i for i in existing_us if i.get("url") not in us_urls and i.get("datetime", 0) > cutoff_ts]
    merged_us.sort(key=lambda x: x.get("datetime", 0), reverse=True)
    save_news(merged_us[:200], US_NEWS_FILE)

    save_seen(seen)

if __name__ == "__main__":
    main()
