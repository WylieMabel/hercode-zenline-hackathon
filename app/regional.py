"""Step 3: regional context signals (weather, holidays, FX, local pubs)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import requests

from geo import resolve_region
from signals_bundled import REGIONAL_BUNDLED_PATH, load_bundled_rows, use_bundled_regional
from signals_common import NA, make_row

HEADERS = {"User-Agent": "zenline-trend-scout/0.1 (hackathon prototype)"}
REQUEST_TIMEOUT = 10

SWISS_PUBLICATION_FEEDS = {
    "bergsteiger_rss": {
        "url": "https://www.bergsteiger.de/rss.xml",
        "market": "CH",
        "fallback": [
            ("Neue Touren im Berner Oberland", "https://www.bergsteiger.de/"),
            ("Ultralight Ausrüstung im Test", "https://www.bergsteiger.de/"),
        ],
    },
}

US_PUBLICATION_FEEDS = {
    "gearjunkie_rss": {
        "url": "https://gearjunkie.com/feed",
        "market": "US",
        "fallback": [
            ("The 7 Best Hut-to-Hut Hikes Around the World", "https://gearjunkie.com/outdoor/7-best-hut-to-hut-hikes-around-world"),
        ],
    },
    "outside_online_rss": {
        "url": "https://www.outsideonline.com/feed",
        "market": "US",
        "fallback": [
            ("The Best Budget, Mid-Priced, and Splurgy Backpacking Tents", "https://www.outsideonline.com/outdoor-gear/camping/best-backpacking-tents/"),
        ],
    },
}


def _enabled(config: dict, key: str) -> bool:
    return key in config.get("regional_signals_enabled", ["weather", "uv_aqi", "holidays", "daylight", "fx", "publications"])


def fetch_temperature_anomaly(config: dict) -> list[dict]:
    if not _enabled(config, "weather"):
        return []
    region = resolve_region(config.get("location", "Switzerland"))
    years_back = int(config.get("time_windows", {}).get("weather_baseline_years", 5))
    cities = region.get("cities", {"Centroid": region["coords"]})
    rows: list[dict] = []

    for place, (lat, lon) in cities.items():
        try:
            cur_url = (
                "https://api.open-meteo.com/v1/forecast"
                f"?latitude={lat}&longitude={lon}&current=temperature_2m"
            )
            current = requests.get(cur_url, timeout=REQUEST_TIMEOUT).json()["current"]["temperature_2m"]
            temps: list[float] = []
            today = date.today()
            for y in range(1, years_back + 1):
                try:
                    target = today.replace(year=today.year - y)
                except ValueError:
                    target = today.replace(year=today.year - y, day=28)
                arch_url = (
                    "https://archive-api.open-meteo.com/v1/archive"
                    f"?latitude={lat}&longitude={lon}&start_date={target.isoformat()}"
                    f"&end_date={target.isoformat()}&daily=temperature_2m_mean&timezone=UTC"
                )
                vals = requests.get(arch_url, timeout=REQUEST_TIMEOUT).json().get("daily", {}).get("temperature_2m_mean", [])
                if vals and vals[0] is not None:
                    temps.append(vals[0])
            hist = sum(temps) / len(temps) if temps else None
            anomaly = round(current - hist, 1) if hist is not None else None
            rows.append(make_row(
                source="open_meteo",
                market=region["geo"],
                keyword="temperature anomaly",
                signal_name=f"{place}: {current}°C vs {round(hist, 1) if hist else NA}°C avg ({anomaly}°C anomaly)",
                signal_type="api",
                rank=anomaly if anomaly is not None else NA,
                url=f"https://open-meteo.com/en/docs?latitude={lat}&longitude={lon}",
            ))
        except Exception as exc:
            print(f"  [regional/weather] {place} failed ({exc}).")
    return rows


def fetch_uv_aqi(config: dict) -> list[dict]:
    if not _enabled(config, "uv_aqi"):
        return []
    region = resolve_region(config.get("location", "Switzerland"))
    lat, lon = region["coords"]
    rows: list[dict] = []
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&current=uv_index,european_aqi"
        )
        data = requests.get(url, timeout=REQUEST_TIMEOUT).json()["current"]
        uv = data.get("uv_index")
        aqi = data.get("european_aqi")
        rows.append(make_row(
            source="open_meteo_uv_aqi",
            market=region["geo"],
            keyword="uv and air quality",
            signal_name=f"UV index {uv}, European AQI {aqi}",
            signal_type="api",
            rank=uv if uv is not None else NA,
            url=f"https://open-meteo.com/en/docs?latitude={lat}&longitude={lon}",
        ))
    except Exception as exc:
        print(f"  [regional/uv_aqi] failed ({exc}).")
    return rows


def fetch_holidays(config: dict) -> list[dict]:
    if not _enabled(config, "holidays"):
        return []
    region = resolve_region(config.get("location", "Switzerland"))
    country = region["country_code"]
    forward_days = int(config.get("time_windows", {}).get("holidays_forward_days", 90))
    cutoff = date.today() + timedelta(days=forward_days)
    rows: list[dict] = []
    try:
        year = date.today().year
        url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
        holidays = requests.get(url, timeout=REQUEST_TIMEOUT).json()
        for h in holidays:
            hdate = date.fromisoformat(h["date"])
            if date.today() <= hdate <= cutoff:
                rows.append(make_row(
                    source="nager_date",
                    market=region["geo"],
                    keyword="public holiday",
                    signal_name=f"Upcoming holiday: {h['localName']} ({h['date']})",
                    signal_type="api",
                    url="https://date.nager.at/",
                ))
        print(f"  [regional/holidays] {len(rows)} upcoming holidays.")
    except Exception as exc:
        print(f"  [regional/holidays] failed ({exc}).")
    return rows


def fetch_daylight(config: dict) -> list[dict]:
    if not _enabled(config, "daylight"):
        return []
    region = resolve_region(config.get("location", "Switzerland"))
    lat, lon = region["coords"]
    forward = int(config.get("time_windows", {}).get("daylight_forward_days", 30))
    end = (date.today() + timedelta(days=forward)).isoformat()
    rows: list[dict] = []
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}&daily=sunrise,sunset,sunshine_duration"
            f"&start_date={date.today().isoformat()}&end_date={end}&timezone=Europe%2FZurich"
        )
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        daily = resp.json().get("daily", {})
        # sunshine_duration is in seconds; fall back to computing from sunrise/sunset
        durations = daily.get("sunshine_duration") or []
        if not durations:
            sunrises = daily.get("sunrise", [])
            sunsets = daily.get("sunset", [])
            durations = [
                (int(ss.split("T")[1].split(":")[0]) * 3600 + int(ss.split("T")[1].split(":")[1]) * 60)
                - (int(sr.split("T")[1].split(":")[0]) * 3600 + int(sr.split("T")[1].split(":")[1]) * 60)
                for sr, ss in zip(sunrises, sunsets) if sr and ss
            ]
        if durations:
            avg_hours = round(sum(durations) / len(durations) / 3600, 1)
            rows.append(make_row(
                source="open_meteo_daylight",
                market=region["geo"],
                keyword="daylight hours",
                signal_name=f"Avg daylight next {forward}d: {avg_hours}h",
                signal_type="api",
                rank=avg_hours,
                url=f"https://open-meteo.com/en/docs?latitude={lat}&longitude={lon}",
            ))
    except Exception as exc:
        print(f"  [regional/daylight] failed ({exc}).")
    return rows


def fetch_fx_rates(config: dict) -> list[dict]:
    if not _enabled(config, "fx"):
        return []
    region = resolve_region(config.get("location", "Switzerland"))
    base = region["currency"]
    rows: list[dict] = []
    try:
        url = f"https://api.exchangerate.host/latest?base={base}&symbols=USD,EUR,JPY,GBP"
        data = requests.get(url, timeout=REQUEST_TIMEOUT).json()
        rates = data.get("rates", {})
        note = ", ".join(f"{k}={v}" for k, v in rates.items())
        rows.append(make_row(
            source="exchangerate_host",
            market=region["geo"],
            keyword="currency rates",
            signal_name=f"FX context ({base} base): {note}",
            signal_type="api",
            url="https://exchangerate.host/",
        ))
        config["_fx_rates"] = rates
    except Exception as exc:
        print(f"  [regional/fx] failed ({exc}).")
    return rows


def fetch_publication_rss(config: dict) -> list[dict]:
    if not _enabled(config, "publications"):
        return []
    import xml.etree.ElementTree as ET

    region = resolve_region(config.get("location", "Switzerland"))
    limit = int(config.get("time_windows", {}).get("publication_rss_limit", 20))
    feeds = dict(US_PUBLICATION_FEEDS)
    if region["geo"] in ("CH", "DE"):
        feeds.update(SWISS_PUBLICATION_FEEDS)
    feeds.update(config.get("publication_feeds") or {})
    keyword_label = config.get("market", "outdoor") + " publication"
    rows: list[dict] = []

    for source, feed_cfg in feeds.items():
        market = feed_cfg.get("market", region["geo"])
        try:
            resp = requests.get(feed_cfg["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            items = ET.fromstring(resp.content).findall(".//item")
            for item in items[: min(8, limit)]:
                title_el = item.find("title")
                link_el = item.find("link")
                title = title_el.text.strip() if title_el is not None and title_el.text else None
                if title:
                    rows.append(make_row(
                        source=source,
                        market=market,
                        keyword=keyword_label,
                        signal_name=title,
                        signal_type="web",
                        url=link_el.text.strip() if link_el is not None and link_el.text else NA,
                    ))
        except Exception as exc:
            print(f"  [regional/rss/{source}] failed ({exc}); fallback.")
            for title, link in feed_cfg.get("fallback", []):
                rows.append(make_row(
                    source=f"{source}_fallback_mock",
                    market=market,
                    keyword=keyword_label,
                    signal_name=title,
                    signal_type="web",
                    url=link,
                ))
    return rows


def collect_regional_signals(config: dict) -> list[dict]:
    if use_bundled_regional(config):
        bundled = load_bundled_rows(REGIONAL_BUNDLED_PATH)
        if bundled:
            print(f"  [regional] loaded {len(bundled)} bundled rows.")
            return bundled

    rows: list[dict] = []
    rows += fetch_temperature_anomaly(config)
    rows += fetch_uv_aqi(config)
    rows += fetch_holidays(config)
    rows += fetch_daylight(config)
    rows += fetch_fx_rates(config)
    rows += fetch_publication_rss(config)
    return rows
