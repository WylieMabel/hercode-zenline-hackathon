"""
Unified scoring: raw_signals.csv → scored_opportunities.csv

Multi-dimensional deterministic scoring with optional Claude overlay.
Dimensions: momentum, early_market, innovation, gap, commercial_fit, actionability.
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from typing import Any

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _safe_float(val) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
RAW_SIGNALS_PATH = os.path.join(PROJECT_ROOT, "raw_signals.csv")
SCORED_PATH = os.path.join(PROJECT_ROOT, "scored_opportunities.csv")
GAP_HINTS_PATH = os.path.join(PROJECT_ROOT, "competitor_gap_hints.json")
INSIGHTS_PATH = os.path.join(PROJECT_ROOT, "trend_insights.json")
FAKE_DATA_PATH = os.path.join(PROJECT_ROOT, "data_generation", "fake_data.csv")

OUTPUT_COLUMNS = [
    "source", "market", "keyword", "signal_name", "signal_type",
    "product_name", "brand", "price", "rank", "url",
    "signal_score", "confidence", "notes", "observed_at",
    "artifact_type", "artifact_uri", "created_by_tool",
]

MOCK_MARKERS = ("_mock", "_fallback", "tiktok_mock", "tourism_anomaly_mock")

CATEGORY_KEYWORDS = {
    "Hiking Footwear": ["hiking boot", "hiking shoe", "approach shoe"],
    "Trail Running Shoes": ["trail running shoe", "trail run shoe", "speedgoat"],
    "Backpacks": ["backpack", "rucksack", "daypack", "pack", "vest"],
    "Hiking Apparel": ["jacket", "hoodie", "fleece", "softshell", "gorpcore"],
    "Climbing Gear": ["climbing", "carabiner", "harness"],
    "Tents & Sleeping": ["tent", "sleeping bag", "fastpacking"],
    "Base Layers": ["base layer", "merino", "thermal"],
}


def _is_mock(source: str) -> bool:
    return any(m in source for m in MOCK_MARKERS)


def infer_category(row: dict) -> str:
    text = f"{row.get('product_name', '')} {row.get('signal_name', '')} {row.get('keyword', '')}".lower()
    for cat, triggers in CATEGORY_KEYWORDS.items():
        if any(t in text for t in triggers):
            return cat
    return row.get("keyword", "general")


def cluster_key(row: dict) -> str:
    if row.get("signal_type") == "competitor":
        return f"product::{infer_category(row)}::{row.get('brand', 'na').strip().lower()}"
    if str(row.get("source", "")).startswith("google_trends"):
        return f"trend::{row.get('keyword', '')}::{row.get('market', '')}"
    kw = str(row.get("keyword", "unknown")).strip().lower().lstrip("#")
    if kw.startswith("r/"):
        kw = kw[2:]
    return f"keyword::{kw}"


def _workflow(score: float) -> str:
    if score < 0.45:
        return "monitor"
    if score < 0.65:
        return "test"
    if score < 0.80:
        return "buy"
    return "launch"


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _momentum_score(rows: list[dict]) -> float:
    scores = []
    for r in rows:
        src = r.get("source", "")
        if "google_trends" not in src:
            continue
        if "seasonal" in src:
            continue
        try:
            v = float(r.get("rank", 0))
            scores.append(min(1.0, max(0.0, (v + 10) / 40)))
        except (TypeError, ValueError):
            pass
    if not scores:
        social = sum(1 for r in rows if r.get("signal_type") == "social" and not _is_mock(r.get("source", "")))
        return min(0.5, 0.1 * social)
    return min(1.0, sum(scores) / len(scores))


def _early_market_score(rows: list[dict]) -> float:
    abroad, ch = [], []
    for r in rows:
        if "google_trends" not in r.get("source", ""):
            continue
        try:
            v = float(r.get("rank", 0))
        except (TypeError, ValueError):
            continue
        m = r.get("market", "")
        if m == "CH":
            ch.append(v)
        elif m in ("US", "JP", "global"):
            abroad.append(v)
    if not abroad:
        return 0.2
    a = sum(abroad) / len(abroad)
    c = sum(ch) / len(ch) if ch else 0
    delta = a - c
    if "stronger abroad" in " ".join(r.get("notes", "") for r in rows):
        return min(1.0, 0.5 + delta / 30)
    return min(1.0, max(0.0, 0.3 + delta / 40))


def _innovation_score(rows: list[dict], insights: dict) -> float:
    facet_count = sum(len(insights.get(k, [])) for k in ("features", "materials", "aesthetics"))
    web = sum(1 for r in rows if r.get("signal_type") == "web" and not _is_mock(r.get("source", "")))
    base = min(1.0, 0.15 * facet_count + 0.1 * web)
    return base


def _gap_score(rows: list[dict], gap_hints: dict) -> float:
    text = " ".join(
        f"{r.get('brand', '')} {r.get('product_name', '')} {r.get('keyword', '')}".lower()
        for r in rows
    )
    hits = 0
    for brand in gap_hints.get("gap_brands", []):
        if brand.lower() in text:
            hits += 1
    for cat in gap_hints.get("gap_categories", []):
        if cat.lower() in text:
            hits += 1
    if hits:
        return min(1.0, 0.4 + 0.15 * hits)
    if gap_hints.get("gap_brands") or gap_hints.get("gap_categories"):
        return 0.35
    return 0.15


def _commercial_fit(rows: list[dict]) -> float:
    if not os.path.exists(FAKE_DATA_PATH):
        return 0.3
    text = " ".join(r.get("signal_name", "") + " " + r.get("product_name", "") for r in rows).lower()
    for cat, triggers in CATEGORY_KEYWORDS.items():
        if any(t in text for t in triggers):
            return 0.55
    return 0.25


def _source_diversity(rows: list[dict]) -> float:
    live = {r["source"] for r in rows if not _is_mock(r.get("source", ""))}
    types = {r.get("signal_type", "") for r in rows}
    return min(1.0, len(live) / 5 * 0.6 + len(types) / 4 * 0.4)


def score_cluster(rows: list[dict], gap_hints: dict, insights: dict) -> dict:
    has_mock = any(_is_mock(r.get("source", "")) for r in rows)
    momentum = _momentum_score(rows)
    early = _early_market_score(rows)
    innovation = _innovation_score(rows, insights)
    gap = _gap_score(rows, gap_hints)
    commercial = _commercial_fit(rows)
    diversity = _source_diversity(rows)

    raw = (
        0.25 * momentum
        + 0.20 * early
        + 0.15 * innovation
        + 0.25 * gap
        + 0.10 * commercial
        + 0.05 * diversity
    )
    if has_mock and not any(not _is_mock(r.get("source", "")) for r in rows):
        raw = min(raw, 0.35)
    elif has_mock:
        raw *= 0.9

    score = round(min(1.0, raw), 2)
    confidence = "high" if score >= 0.65 else ("medium" if score >= 0.4 else "low")
    workflow = _workflow(score)
    live_sources = sorted({r["source"] for r in rows if not _is_mock(r.get("source", ""))})
    notes = (
        f"Cluster {len(rows)} rows | momentum={momentum:.2f} early_market={early:.2f} "
        f"innovation={innovation:.2f} gap={gap:.2f} | workflow={workflow} | "
        f"sources={', '.join(live_sources[:4])}"
    )
    if has_mock:
        notes += " | contains mock/simulated evidence"
    return {"signal_score": score, "confidence": confidence, "notes": notes, "recommended_workflow": workflow}


def build_clusters(rows: list[dict]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        clusters[cluster_key(row)].append(row)
    return dict(clusters)


def score_signals(
    input_path: str = RAW_SIGNALS_PATH,
    output_path: str = SCORED_PATH,
    gap_hints: dict | None = None,
    insights: dict | None = None,
) -> list[dict]:
    with open(input_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return []

    gap_hints = gap_hints or _load_json(GAP_HINTS_PATH)
    insights = insights or _load_json(INSIGHTS_PATH)
    clusters = build_clusters(rows)
    cluster_scores = {k: score_cluster(v, gap_hints, insights) for k, v in clusters.items()}

    scored: list[dict] = []
    for row in rows:
        ck = cluster_key(row)
        cs = cluster_scores[ck]
        scored_row = {
            **{c: row.get(c, "") for c in OUTPUT_COLUMNS},
            "signal_score": cs["signal_score"],
            "confidence": cs["confidence"],
            "notes": cs["notes"],
            "artifact_type": "csv",
            "artifact_uri": output_path,
            "created_by_tool": "scoring.py",
        }
        scored.append(scored_row)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(scored)

    return scored
