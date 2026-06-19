"""
Retail trend signal ingestion pipeline.

Collects raw market signals from three prongs (macro/cultural, commercial/
competitor, local Swiss environmental) and merges them into raw_signals.csv.

All sources are free and lightweight by design:
- Reddit: public .json endpoints (no PRAW, no OAuth) -- often IP-blocked from
  datacenter/cloud networks; falls back to mock posts when blocked.
- Google Trends: pytrends (unofficial, no API key)
- TikTok: mock generator (official API needs business approval; web scraping
  is CAPTCHA-walled even from a real browser)
- Outdoor publication RSS (GearJunkie, Outside Online): no auth, no JS
- YouTube Data API v3: OPTIONAL. Real keyword search needs a free, self-serve
  API key (set env var YOUTUBE_API_KEY). Falls back to mock data if unset.
- REI / Bergfreunde: BeautifulSoup scrape with static-HTML fallback on block
- Weather: open-meteo.com (free, no auth)

Run: python3 scraper_pipeline.py
Output: raw_signals.csv in the current directory.
"""

from __future__ import annotations

import csv
import os
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, date
from typing import Any

import requests

COLUMNS = [
    "source", "market", "keyword", "signal_name", "signal_type",
    "product_name", "brand", "price", "rank", "url", "observed_at",
]

NA = "N/A"
HEADERS = {"User-Agent": "zenline-trend-scout/0.1 (hackathon prototype)"}
REQUEST_TIMEOUT = 10


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_row(**kwargs: Any) -> dict:
    row = {col: NA for col in COLUMNS}
    row.update(kwargs)
    row["observed_at"] = now_iso()
    for col in COLUMNS:
        if row.get(col) in (None, ""):
            row[col] = NA
    return row


# ---------------------------------------------------------------------------
# Module 1: Macro / Cultural Signals
# ---------------------------------------------------------------------------

REDDIT_FALLBACK_POSTS = {
    "ultralight": [
        ("Switched to a 6oz pack and never looked back - gorpcore everyday too", 412, "r1a1"),
        ("Fastpacking the Wind River Range in 4 days, gear list inside", 287, "r1a2"),
        ("Best ultralight rain shells for shoulder season 2026?", 198, "r1a3"),
        ("Trail running packs vs hydration vests - which do you actually use?", 156, "r1a4"),
        ("Cottage gear brands are quietly outpacing the majors on innovation", 233, "r1a5"),
    ],
    "climbing": [
        ("Gorpcore aesthetic is taking over the gym, change my mind", 301, "r2a1"),
        ("Approach shoes that double as everyday trail running shoes?", 145, "r2a2"),
        ("Fastpacking into multi-pitch routes - anyone doing this regularly?", 99, "r2a3"),
        ("Why are trail running packs showing up at the crag now", 122, "r2a4"),
        ("New alpine kit roundup: lighter, faster, more technical fabrics", 176, "r2a5"),
    ],
}


def fetch_reddit_signals() -> list[dict]:
    """Pull post titles + engagement from public subreddit JSON feeds."""
    subreddits = ["ultralight", "climbing"]
    rows: list[dict] = []

    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/new.json?limit=15"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            children = resp.json()["data"]["children"]
            if not children:
                raise ValueError("empty response")

            for child in children:
                post = child.get("data", {})
                title = post.get("title", "").strip()
                if not title:
                    continue
                score = post.get("score")
                permalink = post.get("permalink")
                rows.append(make_row(
                    source="reddit",
                    market="US",
                    keyword=sub,
                    signal_name=title[:120],
                    signal_type="social",
                    rank=score if score is not None else NA,
                    url=f"https://www.reddit.com{permalink}" if permalink else NA,
                ))
            print(f"  [reddit] r/{sub}: {len(children)} posts parsed (live).")
        except Exception as exc:
            print(f"  [reddit] r/{sub} live fetch blocked ({exc}); using fallback mock posts.")
            for title, score, post_id in REDDIT_FALLBACK_POSTS[sub]:
                rows.append(make_row(
                    source="reddit_fallback_mock",
                    market="US",
                    keyword=sub,
                    signal_name=title,
                    signal_type="social",
                    rank=score,
                    url=f"https://www.reddit.com/r/{sub}/comments/{post_id}/",
                ))

    return rows


def fetch_google_trends_signals() -> list[dict]:
    """Use pytrends to grab normalized search interest velocity."""
    keywords = ["gorpcore", "trail running packs", "fastpacking"]
    rows: list[dict] = []

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload(keywords, timeframe="today 3-m", geo="")
        df = pytrends.interest_over_time()
        if df.empty:
            raise ValueError("empty interest_over_time response")

        for kw in keywords:
            series = df[kw]
            recent = series.iloc[-4:]
            baseline = series.iloc[:4]
            velocity = (recent.mean() - baseline.mean()) if len(series) >= 8 else recent.mean()
            rows.append(make_row(
                source="google_trends",
                market="global",
                keyword=kw,
                signal_name=f"Search velocity for '{kw}'",
                signal_type="search",
                rank=round(float(velocity), 1),
                url="https://trends.google.com/trends/explore",
            ))
        print(f"  [google_trends] {len(rows)} keyword velocities computed.")
    except Exception as exc:
        print(f"  [google_trends] live fetch failed ({exc}); using fallback mock values.")
        for kw in keywords:
            rows.append(make_row(
                source="google_trends",
                market="global",
                keyword=kw,
                signal_name=f"Search velocity for '{kw}' (mock fallback)",
                signal_type="search",
                rank=random.randint(-10, 35),
                url="https://trends.google.com/trends/explore",
            ))

    return rows


TRENDS_RELATED_QUERIES_FALLBACK = {
    "gorpcore": ["gorpcore outfit", "gorpcore brands", "gorpcore jacket"],
    "trail running packs": ["best trail running vest", "trail running pack 10l", "salomon trail pack"],
    "fastpacking": ["fastpacking gear list", "fastpacking tent", "fastpacking vs ultralight backpacking"],
}


def fetch_google_trends_related_queries() -> list[dict]:
    """Use pytrends related_queries() to surface rising/top query expansions per keyword."""
    keywords = list(TRENDS_RELATED_QUERIES_FALLBACK.keys())
    rows: list[dict] = []

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload(keywords, timeframe="today 3-m", geo="")
        related = pytrends.related_queries()

        any_found = False
        for kw in keywords:
            for bucket in ("rising", "top"):
                df = related.get(kw, {}).get(bucket)
                if df is None or df.empty:
                    continue
                any_found = True
                for _, record in df.head(5).iterrows():
                    query = record.get("query", NA)
                    value = record.get("value", NA)
                    rows.append(make_row(
                        source="google_trends_related",
                        market="global",
                        keyword=kw,
                        signal_name=f"{bucket.capitalize()} related query: '{query}'",
                        signal_type="search",
                        rank=value,
                        url=f"https://trends.google.com/trends/explore?q={query}",
                    ))
        if not any_found:
            raise ValueError("empty related_queries response")
        print(f"  [google_trends_related] {len(rows)} related-query rows computed.")
    except Exception as exc:
        print(f"  [google_trends_related] live fetch failed ({exc}); using fallback mock values.")
        for kw, queries in TRENDS_RELATED_QUERIES_FALLBACK.items():
            for query in queries:
                rows.append(make_row(
                    source="google_trends_related_fallback_mock",
                    market="global",
                    keyword=kw,
                    signal_name=f"Related query (mock): '{query}'",
                    signal_type="search",
                    rank=random.randint(5, 100),
                    url=f"https://trends.google.com/trends/explore?q={query}",
                ))

    return rows


PUBLICATION_FEEDS = {
    "gearjunkie_rss": "https://gearjunkie.com/feed",
    "outside_online_rss": "https://www.outsideonline.com/feed",
}

PUBLICATION_FALLBACK = {
    "gearjunkie_rss": [
        ("The 7 Best Hut-to-Hut Hikes Around the World", "https://gearjunkie.com/outdoor/7-best-hut-to-hut-hikes-around-world"),
        ("The Only Women's Outdoor Pants I Wear: prAna Halle Pants Review", "https://gearjunkie.com/apparel/prana-halle-pants-review"),
    ],
    "outside_online_rss": [
        ("The Best Budget, Mid-Priced, and Splurgy Backpacking Tents", "https://www.outsideonline.com/outdoor-gear/camping/best-backpacking-tents/"),
    ],
}


def fetch_publication_rss_signals() -> list[dict]:
    """Pull real article titles from outdoor-gear publication RSS feeds (no auth, no JS)."""
    rows: list[dict] = []

    for source, feed_url in PUBLICATION_FEEDS.items():
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            if not items:
                raise ValueError("no <item> entries in feed")

            for item in items[:8]:
                title_el = item.find("title")
                link_el = item.find("link")
                title = title_el.text.strip() if title_el is not None and title_el.text else None
                if not title:
                    continue
                rows.append(make_row(
                    source=source,
                    market="US",
                    keyword="outdoor gear publication",
                    signal_name=title,
                    signal_type="web",
                    url=link_el.text.strip() if link_el is not None and link_el.text else NA,
                ))
            print(f"  [{source}] {len(items[:8])} articles parsed (live).")
        except Exception as exc:
            print(f"  [{source}] live fetch failed ({exc}); using fallback mock values.")
            for title, link in PUBLICATION_FALLBACK[source]:
                rows.append(make_row(
                    source=f"{source}_fallback_mock",
                    market="US",
                    keyword="outdoor gear publication",
                    signal_name=title,
                    signal_type="web",
                    url=link,
                ))

    return rows


YOUTUBE_FALLBACK_VIDEOS = {
    "gorpcore": [("Gorpcore Outfit Ideas for 2026", "@trailmaven", "yt-mock-1")],
    "trail running packs": [("Best Trail Running Vest Packs Tested", "@summitscout", "yt-mock-2")],
    "fastpacking": [("Fastpacking Gear List: Lighter and Faster", "@fastpack.fritz", "yt-mock-3")],
}


def fetch_youtube_signals() -> list[dict]:
    """Optional real source: YouTube Data API v3 keyword search.

    Needs a free, self-serve API key (env var YOUTUBE_API_KEY) -- unlike
    TikTok's business-approval gate, this is instant signup, no review.
    Falls back to mock data if the key is unset or the call fails.
    """
    keywords = list(YOUTUBE_FALLBACK_VIDEOS.keys())
    api_key = os.environ.get("YOUTUBE_API_KEY")
    rows: list[dict] = []

    if not api_key:
        print("  [youtube] YOUTUBE_API_KEY not set; using fallback mock values. "
              "Get a free key at https://console.cloud.google.com/apis/credentials "
              "(enable 'YouTube Data API v3') to pull real search results.")
        for kw, videos in YOUTUBE_FALLBACK_VIDEOS.items():
            for title, channel, video_id in videos:
                rows.append(make_row(
                    source="youtube_fallback_mock",
                    market="global",
                    keyword=kw,
                    signal_name=f"Top video: '{title}'",
                    signal_type="social",
                    brand=channel,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                ))
        return rows

    for kw in keywords:
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet", "q": kw, "type": "video",
                    "order": "viewCount", "maxResults": 5, "key": api_key,
                },
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                raise ValueError("empty search response")

            for item in items:
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId")
                rows.append(make_row(
                    source="youtube",
                    market="global",
                    keyword=kw,
                    signal_name=f"Top video: '{snippet.get('title', NA)}'",
                    signal_type="social",
                    brand=snippet.get("channelTitle", NA),
                    url=f"https://www.youtube.com/watch?v={video_id}" if video_id else NA,
                ))
            print(f"  [youtube] '{kw}': {len(items)} videos parsed (live).")
        except Exception as exc:
            print(f"  [youtube] '{kw}' live fetch failed ({exc}); using fallback mock values.")
            for title, channel, video_id in YOUTUBE_FALLBACK_VIDEOS[kw]:
                rows.append(make_row(
                    source="youtube_fallback_mock",
                    market="global",
                    keyword=kw,
                    signal_name=f"Top video: '{title}'",
                    signal_type="social",
                    brand=channel,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                ))

    return rows


def generate_tiktok_mock_signals() -> list[dict]:
    """Simulate structured TikTok hashtag metrics (official API needs approval)."""
    hashtags = ["#gorpcore", "#trailrunning"]
    creator_pool = [
        "@alpine.lena", "@trailmaven", "@gorpcore.daily", "@summitscout",
        "@fastpack.fritz", "@ridgewalker",
    ]
    rows: list[dict] = []

    for tag in hashtags:
        for i in range(3):
            views = random.randint(500_000, 12_000_000)
            surge_pct = round(random.uniform(15.0, 220.0), 1)
            creator = random.choice(creator_pool)
            video_id = f"{tag.lstrip('#')}-{i}-{random.randint(1000, 9999)}"
            rows.append(make_row(
                source="tiktok_mock",
                market="global",
                keyword=tag,
                signal_name=f"{tag} surge +{surge_pct}% ({views:,} views)",
                signal_type="social",
                brand=creator,
                rank=views,
                url=f"https://www.tiktok.com/tag/{tag.lstrip('#')}?ref={video_id}",
            ))
    print(f"  [tiktok_mock] {len(rows)} simulated hashtag rows generated.")
    return rows


# ---------------------------------------------------------------------------
# Module 2: Commercial & Competitor Signals
# ---------------------------------------------------------------------------

STATIC_FALLBACK_HTML = {
    "rei": """
    <ul class="products">
      <li class="product"><span class="title">Trailmade Trail Running Vest</span>
        <span class="brand">REI Co-op</span><span class="price">$59.95</span>
        <a href="https://www.rei.com/product/trailmade-trail-running-vest">link</a></li>
      <li class="product"><span class="title">Speedgoat 6 Trail Running Shoe</span>
        <span class="brand">HOKA</span><span class="price">$155.00</span>
        <a href="https://www.rei.com/product/hoka-speedgoat-6">link</a></li>
      <li class="product"><span class="title">Fastpack 40 Backpack</span>
        <span class="brand">Osprey</span><span class="price">$220.00</span>
        <a href="https://www.rei.com/product/osprey-fastpack-40">link</a></li>
      <li class="product"><span class="title">Gorpcore Tech Fleece Half-Zip</span>
        <span class="brand">Patagonia</span><span class="price">$129.00</span>
        <a href="https://www.rei.com/product/patagonia-tech-fleece">link</a></li>
    </ul>
    """,
    "bergfreunde": """
    <ul class="produkte">
      <li class="produkt"><span class="titel">Ultraleicht Laufrucksack 12L</span>
        <span class="marke">Salomon</span><span class="preis">79,95 EUR</span>
        <a href="https://www.bergfreunde.de/salomon-laufrucksack-12l/">link</a></li>
      <li class="produkt"><span class="titel">Fastpacking Zelt 1-Personen</span>
        <span class="marke">MSR</span><span class="preis">349,00 EUR</span>
        <a href="https://www.bergfreunde.de/msr-fastpacking-zelt/">link</a></li>
      <li class="produkt"><span class="titel">Gorpcore Softshelljacke</span>
        <span class="marke">Arc'teryx</span><span class="preis">259,00 EUR</span>
        <a href="https://www.bergfreunde.de/arcteryx-softshelljacke/">link</a></li>
      <li class="produkt"><span class="titel">Trailrunning Schuh Speed</span>
        <span class="marke">La Sportiva</span><span class="preis">149,90 EUR</span>
        <a href="https://www.bergfreunde.de/la-sportiva-speed/">link</a></li>
    </ul>
    """,
}

RETAILERS = {
    "rei": {
        "url": "https://www.rei.com/c/new-and-popular",
        "market": "US",
        "item_sel": ".product",
        "title_sel": ".title",
        "brand_sel": ".brand",
        "price_sel": ".price",
        "currency_hint": "$",
    },
    "bergfreunde": {
        "url": "https://www.bergfreunde.de/neuheiten/",
        "market": "DE/CH",
        "item_sel": ".produkt",
        "title_sel": ".titel",
        "brand_sel": ".marke",
        "price_sel": ".preis",
        "currency_hint": "EUR",
    },
}


def _parse_retailer_html(html: str, cfg: dict, source: str) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for item in soup.select(cfg["item_sel"]):
        title_el = item.select_one(cfg["title_sel"])
        brand_el = item.select_one(cfg["brand_sel"])
        price_el = item.select_one(cfg["price_sel"])
        link_el = item.find("a", href=True)

        title = title_el.get_text(strip=True) if title_el else NA
        if title == NA:
            continue
        rows.append(make_row(
            source=source,
            market=cfg["market"],
            keyword="new arrivals",
            signal_name=f"New arrival: {title}",
            signal_type="competitor",
            product_name=title,
            brand=brand_el.get_text(strip=True) if brand_el else NA,
            price=price_el.get_text(strip=True) if price_el else NA,
            url=link_el["href"] if link_el else NA,
        ))
    return rows


def fetch_retailer_signals() -> list[dict]:
    rows: list[dict] = []
    for name, cfg in RETAILERS.items():
        try:
            resp = requests.get(cfg["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code in (403, 429) or "cloudflare" in resp.text.lower()[:2000]:
                raise RuntimeError(f"blocked (status={resp.status_code})")
            resp.raise_for_status()
            parsed = _parse_retailer_html(resp.text, cfg, name)
            if not parsed:
                raise RuntimeError("no products matched expected selectors")
            rows.extend(parsed)
            print(f"  [{name}] live scrape succeeded: {len(parsed)} products.")
        except Exception as exc:
            print(f"  [{name}] live scrape unavailable ({exc}); using static fallback HTML.")
            fallback_rows = _parse_retailer_html(STATIC_FALLBACK_HTML[name], cfg, f"{name}_fallback_mock")
            rows.extend(fallback_rows)
            print(f"  [{name}] fallback produced {len(fallback_rows)} products.")
    return rows


# ---------------------------------------------------------------------------
# Module 3: Local Swiss Environmental Signals
# ---------------------------------------------------------------------------

SWISS_LOCATIONS = {
    "Zürich": (47.3769, 8.5417),
    "St. Moritz": (46.4908, 9.8355),
    "Zermatt": (46.0207, 7.7491),
}


def _fetch_current_temp(lat: float, lon: float) -> float | None:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}&current=temperature_2m"
    )
    resp = requests.get(url, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["current"]["temperature_2m"]


def _fetch_historical_average(lat: float, lon: float, years_back: int = 5) -> float | None:
    """Average temperature for today's calendar date over the past N years."""
    today = date.today()
    temps: list[float] = []
    for years in range(1, years_back + 1):
        try:
            target = today.replace(year=today.year - years)
        except ValueError:
            target = today.replace(year=today.year - years, day=28)
        day_str = target.isoformat()
        url = (
            "https://archive-api.open-meteo.com/v1/archive"
            f"?latitude={lat}&longitude={lon}&start_date={day_str}&end_date={day_str}"
            "&daily=temperature_2m_mean&timezone=UTC"
        )
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            values = resp.json().get("daily", {}).get("temperature_2m_mean", [])
            if values and values[0] is not None:
                temps.append(values[0])
        except Exception:
            continue
    return sum(temps) / len(temps) if temps else None


def fetch_weather_signals() -> list[dict]:
    rows: list[dict] = []
    for place, (lat, lon) in SWISS_LOCATIONS.items():
        try:
            current = _fetch_current_temp(lat, lon)
            historical_avg = _fetch_historical_average(lat, lon)
        except Exception as exc:
            print(f"  [open-meteo] {place} fetch failed ({exc}); skipping.")
            continue

        if current is None:
            continue
        anomaly = round(current - historical_avg, 1) if historical_avg is not None else None

        rows.append(make_row(
            source="open_meteo",
            market="CH",
            keyword="temperature anomaly",
            signal_name=f"{place}: {current}°C vs {round(historical_avg, 1) if historical_avg is not None else NA}°C avg "
                        f"({'+' if anomaly and anomaly > 0 else ''}{anomaly if anomaly is not None else NA}°C anomaly)",
            signal_type="api",
            rank=anomaly if anomaly is not None else NA,
            url=f"https://open-meteo.com/en/docs?latitude={lat}&longitude={lon}",
        ))

        # Local tourism anomaly: combine weather anomaly with a mock booking multiplier.
        booking_multiplier = round(random.uniform(0.85, 1.6), 2)
        if anomaly is not None and anomaly > 4:
            booking_multiplier += round(random.uniform(0.2, 0.5), 2)
            demand_label = "HIGH demand for light alpine gear"
        elif anomaly is not None and anomaly < -4:
            demand_label = "HIGH demand for insulated/cold-weather gear"
            booking_multiplier += round(random.uniform(0.1, 0.3), 2)
        else:
            demand_label = "normal seasonal demand"
        booking_multiplier = round(booking_multiplier, 2)

        rows.append(make_row(
            source="tourism_anomaly_mock",
            market="CH",
            keyword="hotel/hut booking rate",
            signal_name=f"{place}: {demand_label} (booking multiplier x{booking_multiplier})",
            signal_type="manual",
            rank=booking_multiplier,
            url=f"https://open-meteo.com/en/docs?latitude={lat}&longitude={lon}",
        ))
        print(f"  [open-meteo] {place}: current={current}°C, anomaly={anomaly}.")

    return rows


# ---------------------------------------------------------------------------
# Merge, dedupe, write
# ---------------------------------------------------------------------------

def dedupe(rows: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for row in rows:
        key = (row["source"], row["keyword"], row["product_name"], row["url"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def write_csv(rows: list[dict], path: str = "raw_signals.csv") -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    all_rows: list[dict] = []

    print("=== Module 1: Macro / Cultural Signals ===")
    all_rows += fetch_reddit_signals()
    all_rows += fetch_google_trends_signals()
    all_rows += fetch_google_trends_related_queries()
    all_rows += fetch_publication_rss_signals()
    all_rows += fetch_youtube_signals()
    all_rows += generate_tiktok_mock_signals()
    print(f"Module 1 complete: {len(all_rows)} rows so far.\n")

    print("=== Module 2: Commercial & Competitor Signals ===")
    before = len(all_rows)
    all_rows += fetch_retailer_signals()
    print(f"Module 2 complete: +{len(all_rows) - before} rows.\n")

    print("=== Module 3: Local Swiss Environmental Signals ===")
    before = len(all_rows)
    all_rows += fetch_weather_signals()
    print(f"Module 3 complete: +{len(all_rows) - before} rows.\n")

    deduped = dedupe(all_rows)
    write_csv(deduped)

    print("=== Pipeline summary ===")
    print(f"Total rows collected: {len(all_rows)}")
    print(f"Rows after dedup: {len(deduped)}")
    print("Written to raw_signals.csv")


if __name__ == "__main__":
    main()
