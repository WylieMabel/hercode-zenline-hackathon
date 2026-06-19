"""Offline bundled signal CSVs — avoid repeat API calls during demos."""

from __future__ import annotations

import csv
import os

from pipeline_config import PROJECT_ROOT
from signals_common import SIGNAL_COLUMNS

BUNDLED_DIR = os.path.join(PROJECT_ROOT, "data", "bundled")
SOCIAL_BUNDLED_PATH = os.path.join(BUNDLED_DIR, "social_signals.csv")
YOUTUBE_BUNDLED_PATH = os.path.join(BUNDLED_DIR, "youtube_signals.csv")
REGIONAL_BUNDLED_PATH = os.path.join(BUNDLED_DIR, "regional_signals.csv")
TRENDS_BUNDLED_PATH = os.path.join(BUNDLED_DIR, "google_trends_signals.csv")

SOCIAL_SIGNALS_PATH = os.path.join(PROJECT_ROOT, "social_signals.csv")
GOOGLE_TRENDS_SIGNALS_PATH = os.path.join(PROJECT_ROOT, "google_trends_signals.csv")

SOCIAL_SOURCES = ("reddit", "youtube", "tiktok")

REGIONAL_SOURCES = (
    "open_meteo",
    "open_meteo_uv_aqi",
    "open_meteo_daylight",
    "nager_date",
    "exchangerate_host",
    "gearjunkie_rss",
    "outside_online_rss",
    "bergsteiger_rss",
)


def use_bundled_youtube(config: dict) -> bool:
    return _data_source(config, "youtube_data_source") != "live"


def use_bundled_social(config: dict) -> bool:
    return _data_source(config, "social_data_source", "bundled") != "live"


def _data_source(config: dict, key: str, default: str = "bundled") -> str:
    return config.get(key, config.get("signals_data_source", default))


def use_bundled_regional(config: dict) -> bool:
    return _data_source(config, "regional_data_source") != "live"


def use_bundled_trends(config: dict) -> bool:
    return _data_source(config, "trends_data_source") != "live"


def is_social_row(row: dict) -> bool:
    source = row.get("source", "")
    return any(token in source for token in SOCIAL_SOURCES)


def load_bundled_rows(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_bundled_rows(path: str, rows: list[dict]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SIGNAL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
