"""Social / macro signal collection (Module 1) driven by pipeline config."""

from __future__ import annotations

import os
import random

import requests

from signals_bundled import (
    SOCIAL_BUNDLED_PATH,
    SOCIAL_SIGNALS_PATH,
    YOUTUBE_BUNDLED_PATH,
    load_bundled_rows,
    use_bundled_social,
    use_bundled_youtube,
)
from social_keywords import build_youtube_queries
from signals_common import NA, make_row, write_signals_csv

HEADERS = {"User-Agent": "zenline-trend-scout/0.1 (hackathon prototype)"}
REQUEST_TIMEOUT = 10


def fetch_reddit_signals(config: dict) -> list[dict]:
    preset = config.get("scraper_preset", {})
    reddit = preset.get("reddit", {})
    market = reddit.get("market", "US")
    subreddits = config.get("subreddits") or list(reddit.get("subreddits", {}).keys())
    fallback_map = reddit.get("subreddits", {})
    rows: list[dict] = []

    for sub in subreddits:
        sub_key = sub.replace("r/", "")
        url = f"https://www.reddit.com/r/{sub_key}/new.json?limit=15"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            children = resp.json()["data"]["children"]
            for child in children:
                post = child.get("data", {})
                title = post.get("title", "").strip()
                if not title:
                    continue
                rows.append(make_row(
                    source="reddit",
                    market=market,
                    keyword=sub_key,
                    signal_name=title[:120],
                    signal_type="social",
                    rank=post.get("score", NA),
                    url=f"https://www.reddit.com{post.get('permalink', '')}",
                ))
        except Exception as exc:
            print(f"  [social/reddit] r/{sub_key} blocked ({exc}); fallback.")
            for title, score, pid in fallback_map.get(sub_key, fallback_map.get(sub, []))[:5]:
                rows.append(make_row(
                    source="reddit_fallback_mock",
                    market=market,
                    keyword=sub_key,
                    signal_name=title,
                    signal_type="social",
                    rank=score,
                    url=f"https://www.reddit.com/r/{sub_key}/comments/{pid}/",
                ))
    return rows


def fetch_youtube_signals(config: dict) -> list[dict]:
    if use_bundled_youtube(config):
        bundled = load_bundled_rows(YOUTUBE_BUNDLED_PATH)
        if bundled:
            print(f"  [social/youtube] loaded {len(bundled)} bundled rows.")
            return bundled

    keywords_cfg = config.get("scraper_preset", {}).get("keywords", {})
    queries = build_youtube_queries(config)
    api_key = os.environ.get("YOUTUBE_API_KEY")
    rows: list[dict] = []
    max_results = int(config.get("youtube_max_results", 15))
    orders = config.get("youtube_search_orders") or ["viewCount", "relevance"]

    if not api_key:
        for kw in queries:
            cfg = keywords_cfg.get(kw, {})
            fallback = cfg.get("youtube_fallback", [("Outdoor trends", "@scout", "yt-mock")])
            for title, channel, vid in fallback:
                rows.append(make_row(
                    source="youtube_fallback_mock",
                    market="global",
                    keyword=kw,
                    signal_name=f"Top video: '{title}'",
                    signal_type="social",
                    brand=channel,
                    url=f"https://www.youtube.com/watch?v={vid}",
                ))
        return rows

    seen_videos: set[str] = set()
    for kw in queries:
        for order in orders:
            try:
                resp = requests.get(
                    "https://www.googleapis.com/youtube/v3/search",
                    params={
                        "part": "snippet",
                        "q": kw,
                        "type": "video",
                        "order": order,
                        "maxResults": max_results,
                        "key": api_key,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                added = 0
                for item in resp.json().get("items", []):
                    snippet = item.get("snippet", {})
                    vid = item.get("id", {}).get("videoId")
                    if not vid or vid in seen_videos:
                        continue
                    seen_videos.add(vid)
                    rows.append(make_row(
                        source="youtube",
                        market="global",
                        keyword=kw,
                        signal_name=f"Top video: '{snippet.get('title', NA)}'",
                        signal_type="social",
                        brand=snippet.get("channelTitle", NA),
                        url=f"https://www.youtube.com/watch?v={vid}",
                    ))
                    added += 1
                print(f"  [social/youtube] '{kw}' ({order}): {added} videos.")
            except Exception as exc:
                print(f"  [social/youtube] '{kw}' ({order}) failed ({exc}).")
    print(f"  [social/youtube] {len(rows)} unique videos from {len(queries)} queries.")
    return rows


def generate_tiktok_mock_signals(config: dict) -> list[dict]:
    preset = config.get("scraper_preset", {}).get("tiktok", {})
    hashtags = config.get("hashtags") or preset.get("hashtags", ["#outdoor"])
    creators = preset.get("creator_pool", ["@outdoor.scout"])
    rows: list[dict] = []
    for tag in hashtags:
        for i in range(3):
            views = random.randint(500_000, 8_000_000)
            surge = round(random.uniform(15.0, 180.0), 1)
            rows.append(make_row(
                source="tiktok_mock",
                market="global",
                keyword=tag,
                signal_name=f"{tag} surge +{surge}% ({views:,} views) [simulated]",
                signal_type="social",
                brand=random.choice(creators),
                rank=views,
                url=f"https://www.tiktok.com/tag/{tag.lstrip('#')}",
            ))
    return rows


def _collect_social_live(config: dict) -> list[dict]:
    rows: list[dict] = []
    rows += fetch_reddit_signals(config)
    rows += fetch_youtube_signals(config)
    rows += generate_tiktok_mock_signals(config)
    return rows


def collect_social_signals(config: dict) -> list[dict]:
    if use_bundled_social(config):
        bundled = load_bundled_rows(SOCIAL_BUNDLED_PATH)
        if bundled:
            print(f"  [social] loaded {len(bundled)} bundled rows.")
            return bundled

    rows = _collect_social_live(config)
    write_signals_csv(rows, SOCIAL_SIGNALS_PATH)
    return rows
