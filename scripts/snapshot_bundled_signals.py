#!/usr/bin/env python3
"""
Capture social, regional, and Google Trends rows into data/bundled/*.csv.

Usage:
    # From last pipeline run + trends cache (no API keys needed):
    python3 scripts/snapshot_bundled_signals.py

    # Refresh via live APIs (needs YOUTUBE_API_KEY, network, pytrends):
    python3 scripts/snapshot_bundled_signals.py --live
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(PROJECT_ROOT, "app")
sys.path.insert(0, APP_DIR)
sys.path.insert(0, PROJECT_ROOT)

from pipeline_config import base_config, load_config, CONFIG_PATH  # noqa: E402
from regional import collect_regional_signals  # noqa: E402
from signal_collection import _collect_social_live  # noqa: E402
from signals_bundled import (  # noqa: E402
    REGIONAL_BUNDLED_PATH,
    REGIONAL_SOURCES,
    SOCIAL_BUNDLED_PATH,
    TRENDS_BUNDLED_PATH,
    YOUTUBE_BUNDLED_PATH,
    is_social_row,
    write_bundled_rows,
)
from signals_common import SIGNAL_COLUMNS  # noqa: E402
from social_keywords import extract_trends_keywords_from_social  # noqa: E402
from trends import collect_trends, rows_from_trends_cache  # noqa: E402

RAW_SIGNALS_PATH = os.path.join(PROJECT_ROOT, "raw_signals.csv")


def _filter_columns(rows: list[dict]) -> list[dict]:
    return [{col: row.get(col, "") for col in SIGNAL_COLUMNS} for row in rows]


def extract_social_from_raw() -> list[dict]:
    if not os.path.exists(RAW_SIGNALS_PATH):
        return []
    rows = []
    with open(RAW_SIGNALS_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if is_social_row(row):
                rows.append(row)
    return _filter_columns(rows)


def extract_youtube_from_social(social_rows: list[dict]) -> list[dict]:
    return _filter_columns([r for r in social_rows if "youtube" in r.get("source", "")])


def extract_regional_from_raw() -> list[dict]:
    if not os.path.exists(RAW_SIGNALS_PATH):
        return []
    rows = []
    with open(RAW_SIGNALS_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            src = row.get("source", "")
            if any(src == s or src.startswith(s) for s in REGIONAL_SOURCES):
                rows.append(row)
    return _filter_columns(rows)


def load_config_or_default() -> dict:
    if os.path.exists(CONFIG_PATH):
        return load_config()
    return base_config("Switzerland", "Swiss outdoor", "Decathlon")


def snapshot_live(config: dict) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    config = dict(config)
    config["social_data_source"] = "live"
    config["youtube_data_source"] = "live"
    config["regional_data_source"] = "live"
    config["trends_data_source"] = "live"

    social = _filter_columns(_collect_social_live(config))
    trends_keywords = extract_trends_keywords_from_social(social, config)
    config["trends_keywords_from_social"] = trends_keywords
    regional = _filter_columns(collect_regional_signals(config))
    trends = _filter_columns(collect_trends(config, extra_keywords=trends_keywords))
    youtube = extract_youtube_from_social(social)
    return social, youtube, regional, trends


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot bundled signal CSVs")
    parser.add_argument("--live", action="store_true", help="Fetch live APIs instead of exporting captures")
    args = parser.parse_args()
    config = load_config_or_default()

    if args.live:
        print("Fetching live social, regional, and Trends signals...")
        social, youtube, regional, trends = snapshot_live(config)
    else:
        print("Exporting from raw_signals.csv and cache/ (no API calls)...")
        social = extract_social_from_raw()
        youtube = extract_youtube_from_social(social)
        regional = extract_regional_from_raw()
        trends = rows_from_trends_cache(config)
        print(f"  Social: {len(social)} rows")
        print(f"  YouTube: {len(youtube)} rows")
        print(f"  Regional: {len(regional)} rows")
        print(f"  Trends: {len(trends)} rows from cache/")

    write_bundled_rows(SOCIAL_BUNDLED_PATH, social)
    write_bundled_rows(YOUTUBE_BUNDLED_PATH, youtube)
    write_bundled_rows(REGIONAL_BUNDLED_PATH, regional)
    write_bundled_rows(TRENDS_BUNDLED_PATH, trends)

    print(f"\nWrote {len(social)} → {SOCIAL_BUNDLED_PATH}")
    print(f"Wrote {len(youtube)} → {YOUTUBE_BUNDLED_PATH}")
    print(f"Wrote {len(regional)} → {REGIONAL_BUNDLED_PATH}")
    print(f"Wrote {len(trends)} → {TRENDS_BUNDLED_PATH}")


if __name__ == "__main__":
    main()
