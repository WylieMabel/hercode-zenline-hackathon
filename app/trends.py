"""Step 4: multi-geo Google Trends with momentum and seasonal passes."""

from __future__ import annotations

import json
import os
import random
import time
from typing import Any

from pipeline_config import PROJECT_ROOT
from signals_common import NA, make_row

CACHE_DIR = os.path.join(PROJECT_ROOT, "cache")
TRANSFERABILITY_THRESHOLD = 5.0


def _cache_path(keyword: str, geo: str, window: str) -> str:
    safe = f"{keyword}_{geo}_{window}".replace(" ", "_").replace("/", "-")
    return os.path.join(CACHE_DIR, f"trends_{safe}.json")


def _velocity_from_series(series, mode: str = "momentum") -> float:
    """Compute velocity from interest-over-time series."""
    if series is None or len(series) < 4:
        return 0.0
    if mode == "seasonal" and len(series) >= 52:
        recent = series.iloc[-13:]
        prior = series.iloc[-26:-13]
        return float(recent.mean() - prior.mean())
    if len(series) >= 8:
        recent = series.iloc[-4:]
        baseline = series.iloc[:4]
        return float(recent.mean() - baseline.mean())
    return float(series.iloc[-4:].mean())


def _fetch_interest(keywords: list[str], geo: str, timeframe: str) -> dict[str, Any] | None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_key = _cache_path(keywords[0], geo or "global", timeframe)
    if os.path.exists(cache_key):
        with open(cache_key, encoding="utf-8") as f:
            return json.load(f)

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=0)
        pytrends.build_payload(keywords, timeframe=timeframe, geo=geo)
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return None
        payload = {kw: df[kw].tolist() for kw in keywords if kw in df.columns}
        with open(cache_key, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        time.sleep(1.5)
        return payload
    except Exception as exc:
        print(f"  [trends] fetch failed geo={geo} window={timeframe} ({exc}).")
        return None


def _market_label(geo: str) -> str:
    return "global" if not geo else geo


def _source_label(geo: str, pass_name: str) -> str:
    base = "google_trends_global" if not geo else f"google_trends_{geo}"
    return f"{base}_{pass_name}"


def collect_trends(config: dict, extra_keywords: list[str] | None = None) -> list[dict]:
    keywords = list(dict.fromkeys((config.get("keywords") or []) + (extra_keywords or [])))
    if not keywords:
        return []

    tw = config.get("time_windows", {})
    momentum_window = tw.get("trends_momentum", "today 3-m")
    seasonal_window = tw.get("trends_seasonal", "today 12-m")
    geos = [""] + list(config.get("compare_markets", ["CH", "US", "JP"]))
    rows: list[dict] = []
    velocities_by_kw: dict[str, dict[str, float]] = {}

    for i in range(0, len(keywords), 5):
        batch = keywords[i : i + 5]
        for pass_name, window, mode in (
            ("momentum", momentum_window, "momentum"),
            ("seasonal", seasonal_window, "seasonal"),
        ):
            for geo in geos:
                data = _fetch_interest(batch, geo, window)
                market = _market_label(geo)
                if not data:
                    for kw in batch:
                        rows.append(make_row(
                            source=_source_label(geo, pass_name) + "_fallback_mock",
                            market=market,
                            keyword=kw,
                            signal_name=f"Search velocity for '{kw}' (mock)",
                            signal_type="search",
                            rank=random.randint(-5, 25),
                            url="https://trends.google.com/trends/explore",
                        ))
                    continue
                import pandas as pd

                for kw in batch:
                    if kw not in data:
                        continue
                    series = pd.Series(data[kw])
                    velocity = round(_velocity_from_series(series, mode), 1)
                    note = f"window: {window}, geo: {market}, pass: {pass_name}"
                    rows.append(make_row(
                        source=_source_label(geo, pass_name),
                        market=market,
                        keyword=kw,
                        signal_name=f"Search velocity ({pass_name}) for '{kw}'",
                        signal_type="search",
                        rank=velocity,
                        url=f"https://trends.google.com/trends/explore?q={kw}&geo={geo}",
                    ))
                    rows[-1]["notes"] = note
                    velocities_by_kw.setdefault(kw, {})[f"{market}:{pass_name}"] = velocity

    # Transferability hints: US/JP stronger than CH
    ch_vel = {}
    for kw, markets in velocities_by_kw.items():
        ch_vel[kw] = markets.get("CH:momentum", markets.get("CH:seasonal", 0))
    for row in rows:
        kw = row.get("keyword")
        market = row.get("market")
        if market in ("US", "JP") and kw in ch_vel:
            try:
                v = float(row.get("rank", 0))
            except (TypeError, ValueError):
                continue
            if v - ch_vel[kw] > TRANSFERABILITY_THRESHOLD:
                row["notes"] = (row.get("notes") or "") + "; stronger abroad vs CH"

    # Related queries for primary geo
    try:
        from pytrends.request import TrendReq

        primary_geo = config.get("geo_code", "CH")
        pytrends = TrendReq(hl="en-US", tz=0)
        for i in range(0, min(len(keywords), 5), 5):
            batch = keywords[i : i + 5]
            pytrends.build_payload(batch, timeframe=momentum_window, geo=primary_geo)
            related = pytrends.related_queries()
            for kw in batch:
                for bucket in ("rising", "top"):
                    df = related.get(kw, {}).get(bucket)
                    if df is None or df.empty:
                        continue
                    for _, record in df.head(5).iterrows():
                        query = record.get("query", NA)
                        value = record.get("value", NA)
                        rows.append(make_row(
                            source=f"google_trends_related_{primary_geo}",
                            market=primary_geo,
                            keyword=kw,
                            signal_name=f"{bucket.capitalize()} related: '{query}'",
                            signal_type="search",
                            rank=value,
                            url=f"https://trends.google.com/trends/explore?q={query}&geo={primary_geo}",
                        ))
            time.sleep(1.5)
    except Exception as exc:
        print(f"  [trends/related] failed ({exc}).")

    return rows
