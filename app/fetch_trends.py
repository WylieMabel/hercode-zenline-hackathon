"""
Standalone: extract keywords from raw_signals.csv → fetch 1-year Google Trends
for global + Swiss market only.

Two calls per keyword (global then CH), with conservative waits to stay under
Google's rate limit. Results cached in cache/ so re-runs are instant.

Output: trend_results.csv in the project root.

Run:
    python3 app/fetch_trends.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_APP_DIR)
sys.path.insert(0, _APP_DIR)
sys.path.insert(0, _PROJECT_ROOT)

from signals_common import make_row, write_signals_csv

RAW_SIGNALS_PATH = os.path.join(_PROJECT_ROOT, "raw_signals.csv")
OUTPUT_PATH = os.path.join(_PROJECT_ROOT, "trend_results.csv")
CACHE_DIR = os.path.join(_PROJECT_ROOT, "cache")

WINDOW = "today 12-m"
GEOS = [("", "global"), ("CH", "CH")]  # only 2 calls per keyword

INTER_CALL_SLEEP = 8    # seconds between each live API call
RETRY_SLEEP = 65        # seconds to wait after a 429

_SKIP_KEYWORDS = {
    "general", "n/a", "new arrivals", "outdoor gear publication",
    "swiss outdoor publication", "temperature anomaly", "hotel/hut booking rate",
    "uv and air quality", "public holiday", "currency rates", "daylight hours",
}
MIN_SIGNAL_COUNT = 2


def extract_keywords(path: str) -> list[str]:
    from collections import Counter
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    counts: Counter[str] = Counter()
    for row in rows:
        kw = row.get("keyword", "").strip().lstrip("#").lower()
        if kw and kw not in _SKIP_KEYWORDS:
            counts[kw] += 1
    keywords = [kw for kw, n in counts.most_common() if n >= MIN_SIGNAL_COUNT]
    print(f"Keywords ({len(keywords)}): {keywords}\n")
    return keywords


def _cache_path(keyword: str, geo: str) -> str:
    safe = f"{keyword}_{geo or 'global'}_{WINDOW}".replace(" ", "_").replace("/", "-")
    return os.path.join(CACHE_DIR, f"trends_{safe}.json")


def fetch_series(keyword: str, geo: str, geo_label: str) -> list[float] | None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = _cache_path(keyword, geo)

    if os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            data = json.load(f)
        series = data.get(keyword)
        print(f"  [{geo_label}] cached ✓")
        return series

    for attempt in range(2):
        try:
            from pytrends.request import TrendReq
            pytrends = TrendReq(hl="en-US", tz=0)
            pytrends.build_payload([keyword], timeframe=WINDOW, geo=geo)
            df = pytrends.interest_over_time()
            if df is None or df.empty or keyword not in df.columns:
                print(f"  [{geo_label}] empty response — skipping")
                return None
            series = df[keyword].tolist()
            with open(cache, "w", encoding="utf-8") as f:
                json.dump({keyword: series}, f)
            print(f"  [{geo_label}] fetched {len(series)} weeks ✓")
            time.sleep(INTER_CALL_SLEEP)
            return series
        except Exception as exc:
            if "429" in str(exc) and attempt == 0:
                print(f"  [{geo_label}] rate-limited — waiting {RETRY_SLEEP}s…")
                time.sleep(RETRY_SLEEP)
            else:
                print(f"  [{geo_label}] failed: {exc}")
                return None
    return None


def velocity(series: list[float]) -> float:
    if not series or len(series) < 4:
        return 0.0
    if len(series) >= 8:
        return round(float(sum(series[-4:]) / 4 - sum(series[:4]) / 4), 1)
    return round(float(sum(series[-4:]) / 4), 1)


def main() -> None:
    if not os.path.exists(RAW_SIGNALS_PATH):
        print(f"ERROR: {RAW_SIGNALS_PATH} not found — run the pipeline first.")
        sys.exit(1)

    keywords = extract_keywords(RAW_SIGNALS_PATH)
    if not keywords:
        print("No keywords found.")
        sys.exit(0)

    rows: list[dict] = []
    total_calls = len(keywords) * len(GEOS)
    done = 0

    for kw in keywords:
        print(f"── {kw} ({done * len(GEOS) + 1}–{done * len(GEOS) + len(GEOS)} of {total_calls} calls)")
        for geo, geo_label in GEOS:
            series = fetch_series(kw, geo, geo_label)
            if series is None:
                rows.append(make_row(
                    source="google_trends_fallback_mock",
                    market=geo_label,
                    keyword=kw,
                    signal_name=f"Search interest for '{kw}' — {geo_label} (mock)",
                    signal_type="search",
                    rank=0,
                    url=f"https://trends.google.com/trends/explore?q={kw}&geo={geo}",
                ))
                continue

            vel = velocity(series)
            rows.append(make_row(
                source="google_trends",
                market=geo_label,
                keyword=kw,
                signal_name=f"Search interest for '{kw}' — {geo_label}",
                signal_type="search",
                rank=vel,
                url=f"https://trends.google.com/trends/explore?q={kw}&geo={geo}",
            ))
            rows[-1]["notes"] = f"window={WINDOW}, geo={geo_label}, velocity={vel:+.1f}"
        done += 1

    write_signals_csv(rows, OUTPUT_PATH)
    live = sum(1 for r in rows if "mock" not in r.get("source", ""))
    print(f"\nDone. {len(rows)} rows → {OUTPUT_PATH}  ({live} live, {len(rows)-live} mock)")


if __name__ == "__main__":
    main()
