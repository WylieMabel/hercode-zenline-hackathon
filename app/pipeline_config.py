"""Pipeline configuration: defaults, presets, load/save."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from geo import resolve_region
from vertical_presets import apply_vertical_preset, match_vertical

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "pipeline_config.json")

DEFAULT_TIME_WINDOWS = {
    "trends_momentum": "today 3-m",
    "trends_seasonal": "today 12-m",
    "weather_baseline_years": 5,
    "social_lookback_days": 30,
    "holidays_forward_days": 90,
    "daylight_forward_days": 30,
    "publication_rss_limit": 20,
}

TIME_PRESETS = {
    "fast": {"trends_momentum": "today 3-m", "social_lookback_days": 14},
    "standard": {"trends_momentum": "today 3-m", "trends_seasonal": "today 12-m"},
    "seasonal": {
        "trends_momentum": "today 3-m",
        "trends_seasonal": "today 12-m",
        "weather_baseline_years": 10,
    },
}

# Scraper preset bundled with outdoor vertical defaults
OUTDOOR_SCRAPER_PRESET: dict[str, Any] = {
    "keywords": {
        "gorpcore": {
            "related_queries_fallback": ["gorpcore outfit", "gorpcore brands", "gorpcore jacket"],
            "youtube_fallback": [("Gorpcore Outfit Ideas for 2026", "@trailmaven", "yt-mock-1")],
        },
        "trail running packs": {
            "related_queries_fallback": ["best trail running vest", "trail running pack 10l", "salomon trail pack"],
            "youtube_fallback": [("Best Trail Running Vest Packs Tested", "@summitscout", "yt-mock-2")],
        },
        "fastpacking": {
            "related_queries_fallback": ["fastpacking gear list", "fastpacking tent", "fastpacking vs ultralight backpacking"],
            "youtube_fallback": [("Fastpacking Gear List: Lighter and Faster", "@fastpack.fritz", "yt-mock-3")],
        },
    },
    "reddit": {
        "market": "US",
        "subreddits": {
            "ultralight": [
                ("Switched to a 6oz pack and never looked back - gorpcore everyday too", 412, "r1a1"),
                ("Fastpacking the Wind River Range in 4 days, gear list inside", 287, "r1a2"),
                ("Best ultralight rain shells for shoulder season 2026?", 198, "r1a3"),
            ],
            "climbing": [
                ("Gorpcore aesthetic is taking over the gym, change my mind", 301, "r2a1"),
                ("Approach shoes that double as everyday trail running shoes?", 145, "r2a2"),
            ],
        },
    },
    "tiktok": {
        "hashtags": ["#gorpcore", "#trailrunning"],
        "creator_pool": ["@alpine.lena", "@trailmaven", "@gorpcore.daily", "@summitscout"],
    },
    "publications": {
        "keyword_label": "outdoor gear publication",
        "feeds": {},
    },
    "retailers": {},
}

PRESET_NAMES = {"swiss outdoor": "swiss outdoor"}


def default_time_windows(preset: str = "standard") -> dict:
    tw = deepcopy(DEFAULT_TIME_WINDOWS)
    tw.update(TIME_PRESETS.get(preset, {}))
    return tw


def base_config(
    location: str = "Switzerland",
    market: str = "Outdoor",
    client_company: str = "",
    price_min=None,
    price_max=None,
    time_horizon: str = "standard",
) -> dict:
    region = resolve_region(location)
    price_range = "no filter"
    if price_min or price_max:
        lo = f"CHF {price_min}" if price_min else "any"
        hi = f"CHF {price_max}" if price_max else "any"
        price_range = f"{lo} – {hi}"

    config = {
        "location": location,
        "market": market,
        "client_company": client_company or "",
        "price_min": price_min,
        "price_max": price_max,
        "price_filter_note": price_range,
        "geo_code": region["geo"],
        "currency": region["currency"],
        "compare_markets": ["CH", "US", "JP"],
        "markets": ["CH", "DACH", "US", "DE", "JP"],
        "keywords": [],
        "product_seeds": [],
        "hashtags": [],
        "subreddits": [],
        "youtube_queries": [],
        "aesthetic_lexicon": [],
        "materials_watchlist": [],
        "features_watchlist": [],
        "color_palettes_watchlist": [],
        "opportunity_types_focus": [],
        "signal_types": ["social", "search", "competitor", "weather", "api"],
        "regional_signals_enabled": ["weather", "uv_aqi", "holidays", "daylight", "fx", "publications"],
        "publication_feeds": {},
        "competitors": [],
        "competitors_requested": [],
        "competitors_skipped": [],
        "competitor_data_source": "bundled",
        "signals_data_source": "bundled",
        "social_data_source": "bundled",
        "youtube_data_source": "bundled",
        "regional_data_source": "bundled",
        "trends_data_source": "bundled",
        "youtube_max_results": 15,
        "youtube_query_limit": 16,
        "youtube_search_orders": ["viewCount", "relevance"],
        "trends_keyword_limit": 24,
        "scraper_preset": OUTDOOR_SCRAPER_PRESET,
        "time_windows": default_time_windows(time_horizon),
        "time_horizon": time_horizon,
        "run_id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline_version": "1.0",
        "persist_history": False,
        "summary": f"Scanning {market} signals for {location}" + (f" (client: {client_company})" if client_company else ""),
    }
    apply_vertical_preset(config)
    return config


def save_config(config: dict, path: str = CONFIG_PATH) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return path


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge_scraper_keywords(config: dict) -> dict:
    """Sync top-level keyword list into scraper_preset.keywords dict."""
    preset = config.setdefault("scraper_preset", deepcopy(OUTDOOR_SCRAPER_PRESET))
    kw_dict = preset.setdefault("keywords", {})
    for kw in config.get("keywords", []):
        if kw not in kw_dict:
            kw_dict[kw] = {
                "related_queries_fallback": [f"{kw} gear", f"best {kw}"],
                "youtube_fallback": [(f"{kw.title()} trends 2026", "@outdoorscout", f"yt-{kw[:6]}")],
            }
    return config


def finalize_config(config: dict, product_titles: list[str] | None = None) -> dict:
    """Enrich config after competitor scrape with product-derived seeds."""
    from signals_common import extract_product_tokens

    if product_titles:
        seeds = extract_product_tokens(product_titles)
        config["product_seeds"] = seeds
        existing = set(config.get("keywords", []))
        for seed in seeds[:4]:
            if seed not in existing:
                config.setdefault("keywords", []).append(seed)
                existing.add(seed)
    merge_scraper_keywords(config)
    return config
