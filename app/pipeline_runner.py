"""
Pipeline step orchestration — six-step retail signal pipeline.

Steps:
  1. Competitor discovery → competitor_products.csv
  2. Config finalization + social signals
  3. Regional data collection
  4. Multi-geo Google Trends
  5. Scoring
  6. LLM compilation → ranked_recommendations.csv
"""

from __future__ import annotations

import json
import os
import sys

from llm_client import MODEL, messages_create, resolve_api_key

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import compiler as _compiler
import scoring as _scoring
from competitors import COMPETITOR_PRODUCTS_PATH, GAP_HINTS_PATH, find_competitors, list_registry_slugs, normalize_competitor_slugs
from geo import resolve_region
from pipeline_config import (
    CONFIG_PATH,
    base_config,
    finalize_config,
    load_config,
    merge_scraper_keywords,
    save_config,
)
from vertical_presets import match_vertical
from regional import collect_regional_signals
from signal_collection import collect_social_signals
from signals_common import dedupe_rows, write_signals_csv
from trend_extraction import extract_trend_facets, load_trend_insights
from trends import collect_trends

RAW_SIGNALS_PATH = os.path.join(PROJECT_ROOT, "raw_signals.csv")

CONFIG_PROMPT = """\
You are configuring a retail signal detection pipeline for vertical: {vertical_label}.

Inputs:
- Company location: {location}
- Market / category: {market}
- Client company: {client_company}
- Price range: {price_range}

Scrapeable competitor slugs (ONLY use ids from this list — others are ignored):
{available_competitors}

Return JSON with keys:
  keywords (4-6 search terms for this vertical),
  markets (include CH, DACH, US, JP),
  hashtags (3-5), subreddits (2-4),
  aesthetic_lexicon (4-6 style/vibe terms),
  materials_watchlist (4-6 materials to monitor),
  features_watchlist (4-6 product features/technologies),
  color_palettes_watchlist (3-5 colour directions),
  competitors (5-8 slugs from the scrapeable list above, prioritise CH/DACH relevance for Swiss outdoor),
  opportunity_types_focus (pick 4-6 from: product_type, material, feature, aesthetic, color_palette, brand, price_gap, merchandising, usage_occasion, content_community),
  summary (one sentence)

Return ONLY valid JSON, no markdown.
"""


def generate_config(
    location: str,
    market: str,
    client_company: str = "",
    price_min=None,
    price_max=None,
    time_horizon: str = "standard",
    api_key: str | None = None,
) -> dict:
    price_range = "no filter"
    if price_min or price_max:
        lo = f"CHF {price_min}" if price_min else "any"
        hi = f"CHF {price_max}" if price_max else "any"
        price_range = f"{lo} – {hi}"

    region = resolve_region(location)
    config = base_config(location, market, client_company, price_min, price_max, time_horizon)
    config["geo_code"] = region["geo"]
    vertical_key = match_vertical(market, location)
    config["vertical_key"] = vertical_key

    if not resolve_api_key(api_key):
        merge_scraper_keywords(config)
        return config

    try:
        prompt = CONFIG_PROMPT.format(
            vertical_label=config.get("vertical_label", vertical_key),
            location=location,
            market=market,
            client_company=client_company or "none",
            price_range=price_range,
            available_competitors=", ".join(list_registry_slugs()),
        )
        raw = messages_create(prompt, api_key=api_key, model=MODEL, max_tokens=1024)
        if not raw:
            merge_scraper_keywords(config)
            return config
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        llm_cfg = json.loads(raw)
        for key in (
            "keywords", "markets", "hashtags", "subreddits", "aesthetic_lexicon",
            "materials_watchlist", "features_watchlist", "color_palettes_watchlist",
            "opportunity_types_focus", "summary",
        ):
            if key in llm_cfg:
                config[key] = llm_cfg[key]
        if "competitors" in llm_cfg:
            config["competitors_requested"] = llm_cfg["competitors"]
            matched, skipped = normalize_competitor_slugs(llm_cfg["competitors"])
            config["competitors"] = matched or config.get("competitors", [])
            config["competitors_skipped"] = skipped
    except Exception as exc:
        print(f"  [config] LLM config failed ({exc}); using vertical preset defaults.")

    merge_scraper_keywords(config)
    return config


def run_competitors(config: dict) -> tuple[bool, str, list[dict], dict]:
    try:
        products, hints = find_competitors(config)
        titles = [p.get("product_name", "") for p in products if p.get("product_name")]
        finalize_config(config, titles)
        save_config(config)
        return True, f"Found {len(products)} competitor products", products, hints
    except Exception as exc:
        return False, str(exc), [], {}


def run_signal_collection(config: dict) -> tuple[bool, str, int]:
    try:
        all_rows: list[dict] = []
        print("=== Social signals ===")
        all_rows += collect_social_signals(config)
        print("=== Regional signals ===")
        all_rows += collect_regional_signals(config)
        insights_kw = []
        ti = load_trend_insights()
        if ti:
            insights_kw = ti.get("trends", [])
        print("=== Google Trends ===")
        all_rows += collect_trends(config, extra_keywords=insights_kw)

        # Include competitor products in raw signals
        if os.path.exists(COMPETITOR_PRODUCTS_PATH):
            import csv
            with open(COMPETITOR_PRODUCTS_PATH, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    all_rows.append({k: row.get(k, "") for k in row})

        deduped = dedupe_rows(all_rows)
        write_signals_csv(deduped, RAW_SIGNALS_PATH)
        return True, f"Collected {len(deduped)} signals → raw_signals.csv", len(deduped)
    except Exception as exc:
        return False, str(exc), 0


def run_trend_extraction(config: dict, api_key: str | None = None) -> tuple[bool, str, dict]:
    try:
        import csv
        with open(RAW_SIGNALS_PATH, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        insights = extract_trend_facets(rows, config, api_key=api_key)
        return True, f"Extracted {sum(len(insights.get(k, [])) for k in ('trends','products','features'))} facet items", insights
    except Exception as exc:
        return False, str(exc), {}


def run_scoring(gap_hints: dict | None = None, insights: dict | None = None) -> tuple[bool, str, list[dict]]:
    if not os.path.exists(RAW_SIGNALS_PATH):
        return False, "raw_signals.csv not found — run signal collection first.", []
    try:
        if gap_hints is None and os.path.exists(GAP_HINTS_PATH):
            with open(GAP_HINTS_PATH, encoding="utf-8") as f:
                gap_hints = json.load(f)
        if insights is None:
            insights = load_trend_insights()
        rows = _scoring.score_signals(RAW_SIGNALS_PATH, gap_hints=gap_hints, insights=insights)
        return True, f"Scored {len(rows)} signals → scored_opportunities.csv", rows
    except Exception as exc:
        return False, str(exc), []


def run_compiler(
    scored_rows: list[dict],
    sales_context: str = "",
    insights: dict | None = None,
    gap_hints: dict | None = None,
    api_key: str | None = None,
) -> tuple[bool, str, list[dict]]:
    try:
        if gap_hints is None and os.path.exists(GAP_HINTS_PATH):
            with open(GAP_HINTS_PATH, encoding="utf-8") as f:
                gap_hints = json.load(f)
        if insights is None:
            insights = load_trend_insights()
        opps = _compiler.compile_opportunities(
            scored_rows, sales_context, insights, gap_hints, api_key=api_key
        )
        _compiler.write_recommendations_csv(opps)
        return True, f"Compiled {len(opps)} opportunities → ranked_recommendations.csv", opps
    except Exception as exc:
        return False, str(exc), []


def run_pipeline(
    location: str,
    market: str,
    client_company: str = "",
    price_min=None,
    price_max=None,
    sales_context: str = "",
    time_horizon: str = "standard",
    api_key: str | None = None,
) -> dict:
    """Run all six steps; return summary dict."""
    config = generate_config(
        location, market, client_company, price_min, price_max, time_horizon, api_key=api_key
    )
    save_config(config)

    results: dict = {"config": config, "steps": {}}

    ok, msg, products, hints = run_competitors(config)
    results["steps"]["1_competitors"] = {"ok": ok, "message": msg, "count": len(products)}
    results["gap_hints"] = hints

    ok, msg, count = run_signal_collection(config)
    results["steps"]["2_4_signals"] = {"ok": ok, "message": msg, "count": count}

    ok, msg, insights = run_trend_extraction(config, api_key=api_key)
    results["steps"]["2_facets"] = {"ok": ok, "message": msg}
    results["insights"] = insights

    ok, msg, scored = run_scoring(hints, insights)
    results["steps"]["5_scoring"] = {"ok": ok, "message": msg, "count": len(scored)}

    ok, msg, opps = run_compiler(scored, sales_context, insights, hints, api_key=api_key)
    results["steps"]["6_compile"] = {"ok": ok, "message": msg, "count": len(opps)}
    results["opportunities"] = opps
    return results


# Legacy wrappers for gradual migration
def run_scraper(config_path: str = CONFIG_PATH) -> tuple[bool, str]:
    if not os.path.exists(config_path):
        return False, f"Config not found: {config_path}"
    config = load_config(config_path)
    ok, msg, _ = run_signal_collection(config)
    return ok, msg
