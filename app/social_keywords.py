"""Derive Google Trends query terms from social signal rows."""

from __future__ import annotations

import html
import re

TITLE_RE = re.compile(r"Top video: ['\"](.+)['\"]", re.S)

STOP_WORDS = {
    "the", "and", "for", "with", "your", "this", "that", "from", "what", "when",
    "how", "why", "best", "top", "video", "shorts", "review", "2024", "2025",
    "2026", "part", "watch", "don", "you", "are", "get", "our", "all", "new",
    "switched", "never", "looked", "inside", "gear", "list", "days", "just",
}


def _clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_from_youtube_row(row: dict) -> str:
    name = row.get("signal_name", "")
    match = TITLE_RE.search(name)
    return _clean_text(match.group(1) if match else name)


def _phrases_from_title(title: str, limit: int = 2) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", title.lower())
    phrases: list[str] = []
    seen: set[str] = set()

    for word in words:
        if word in STOP_WORDS or len(word) < 5:
            continue
        if word not in seen:
            phrases.append(word)
            seen.add(word)
        if len(phrases) >= limit:
            break

    for i in range(len(words) - 1):
        if words[i] in STOP_WORDS or words[i + 1] in STOP_WORDS:
            continue
        bigram = f"{words[i]} {words[i + 1]}"
        if bigram not in seen and len(bigram) <= 40:
            phrases.append(bigram)
            seen.add(bigram)
        if len(phrases) >= limit + 2:
            break
    return phrases


def build_youtube_queries(config: dict) -> list[str]:
    """Search queries for YouTube API — broader than Trends keywords alone."""
    queries: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        term = _clean_text(term).strip()
        if not term or len(term) < 3:
            return
        key = term.lower()
        if key in seen:
            return
        seen.add(key)
        queries.append(term)

    for kw in config.get("keywords") or []:
        add(kw)
    for kw in config.get("youtube_queries") or []:
        add(kw)
    for tag in config.get("hashtags") or []:
        add(tag.lstrip("#"))
    for term in (config.get("aesthetic_lexicon") or [])[:6]:
        add(term)
    for term in (config.get("materials_watchlist") or [])[:4]:
        add(term)
    for term in (config.get("features_watchlist") or [])[:4]:
        add(term)
    for seed in (config.get("product_seeds") or [])[:4]:
        add(seed)

    market = config.get("market", "")
    location = config.get("location", "")
    if market and location:
        add(f"{market} {location}")
    elif market:
        add(market)

    limit = int(config.get("youtube_query_limit", 16))
    return queries[:limit]


def extract_trends_keywords_from_social(social_rows: list[dict], config: dict) -> list[str]:
    """Turn social posts/videos into Google Trends search terms."""
    keywords: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        term = _clean_text(term).strip()
        if not term or len(term) < 3 or len(term) > 60:
            return
        key = term.lower()
        if key in seen:
            return
        seen.add(key)
        keywords.append(term)

    for kw in config.get("keywords") or []:
        add(kw)
    for seed in config.get("product_seeds") or []:
        add(seed)

    title_phrase_budget = int(config.get("trends_title_phrase_limit", 8))

    for row in social_rows:
        source = row.get("source", "")
        if source.startswith("youtube"):
            add(row.get("keyword", ""))
            for phrase in _phrases_from_title(_title_from_youtube_row(row), limit=2):
                add(phrase)
        elif "reddit" in source:
            add(row.get("keyword", ""))
            title = _clean_text(row.get("signal_name", ""))
            for phrase in _phrases_from_title(title, limit=1):
                add(phrase)
        elif source == "tiktok_mock":
            add(row.get("keyword", "").lstrip("#"))

    for tag in config.get("hashtags") or []:
        add(tag.lstrip("#"))
    for term in config.get("aesthetic_lexicon") or []:
        add(term)

    limit = int(config.get("trends_keyword_limit", 24))
    return keywords[:limit]
