"""
Scores raw_signals.csv into scored_opportunities.csv.

Bridges the gap between raw scraped evidence (scraper_pipeline.py's output)
and the scored, confidence-rated schema the chatbot expects (the Signal Row
shape demonstrated in examples/signals.csv -- same columns as raw_signals.csv
plus signal_score, confidence, notes, artifact_type, artifact_uri,
created_by_tool).

Two stages:
1. Cluster raw evidence rows into opportunity candidates (same brand, or same
   keyword/theme), and aggregate data_generation/fake_data.csv into
   category-level churn/return/spend stats.
2. Score each cluster with Claude in small batches -- evidence rows plus the
   matching category's customer stats go into one prompt, Claude returns a
   score/confidence/notes per cluster. Every row in a cluster inherits that
   cluster's score (evidence stays at full granularity, nothing is collapsed).

Falls back to a deterministic rule-based score (more corroborating sources
and live, non-mock evidence push the score up) when CLAUDE_API_KEY is unset,
so this can be tested for free before spending API budget.

Run: python3 analysis/score_opportunities.py
Output: scored_opportunities.csv in the repo root.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from typing import Any

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_SIGNALS_PATH = os.path.join(REPO_ROOT, "raw_signals.csv")
FAKE_DATA_PATH = os.path.join(REPO_ROOT, "data_generation", "fake_data.csv")
OUTPUT_PATH = os.path.join(REPO_ROOT, "scored_opportunities.csv")

sys.path.insert(0, os.path.join(REPO_ROOT, "chatbot"))
from shared import claude_client  # noqa: E402

OUTPUT_COLUMNS = [
    "source", "market", "keyword", "signal_name", "signal_type",
    "product_name", "brand", "price", "rank", "url", "signal_score",
    "confidence", "notes", "observed_at", "artifact_type", "artifact_uri",
    "created_by_tool",
]

CLUSTER_BATCH_SIZE = 5
MAX_EXAMPLES_PER_CLUSTER = 8

# Heuristic substring triggers mapping free text to data_generation's
# Product Category labels, so customer churn/spend stats can be matched to
# a cluster even though the two datasets don't share an explicit key.
CATEGORY_KEYWORDS = {
    "Hiking Footwear": ["hiking boot", "hiking shoe", "approach shoe"],
    "Trail Running Shoes": ["trail running shoe", "trail run shoe", "speedgoat", "momentum climbing shoe"],
    "Ski Equipment": ["ski ", "snowboard", "binding"],
    "Ski Apparel": ["ski jacket", "ski pant"],
    "Hiking Apparel": ["jacket", "hoodie", "fleece", "softshell", "half-zip", "shorts", "dress", "woven"],
    "Climbing Gear": ["climbing", "carabiner", "quickdraw", "chalk", "harness", "rope", "crash pad"],
    "Backpacks": ["backpack", "rucksack", "daypack", "sports bag", "laptop backpack"],
    "Tents & Sleeping": ["tent", "sleeping bag", "sleeping pad"],
    "Base Layers": ["base layer", "thermal", "merino"],
    "Accessories": ["headlamp", "cord", "gloves", "neck warmer", "bottle"],
    "Navigation & Safety": ["gps", "compass", "avalanche", "beacon"],
    "Bike & MTB": ["bike", "mtb", "mountain bike", "cycling"],
}

MOCK_MARKERS = ("_mock", "_fallback")


def aggregate_customer_data(path: str = FAKE_DATA_PATH) -> dict[str, dict]:
    """Group fake_data.csv by Product Category into churn/return/spend stats."""
    totals: dict[str, dict] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cat = row["Product Category"]
            stats = totals.setdefault(cat, {"n": 0, "churn": 0, "returns": 0, "spend": 0.0})
            stats["n"] += 1
            stats["churn"] += int(row["Churn"])
            stats["returns"] += int(row["Returns"])
            stats["spend"] += float(row["Total Purchase Amount"])

    return {
        cat: {
            "n": s["n"],
            "churn_rate": round(s["churn"] / s["n"], 3),
            "return_rate": round(s["returns"] / s["n"], 3),
            "avg_spend": round(s["spend"] / s["n"], 2),
        }
        for cat, s in totals.items()
    }


def match_category(text: str, customer_stats: dict[str, dict]) -> dict | None:
    text = text.lower()
    best_category, best_hits = None, 0
    for category, triggers in CATEGORY_KEYWORDS.items():
        hits = sum(1 for t in triggers if t in text)
        if hits > best_hits:
            best_category, best_hits = category, hits
    if best_category is None or best_category not in customer_stats:
        return None
    return {"category": best_category, **customer_stats[best_category]}


def cluster_key(row: dict) -> str:
    if row["signal_type"] == "competitor" and row.get("brand", "N/A") != "N/A":
        return f"brand::{row['brand'].strip().lower()}"
    kw = row["keyword"].strip().lower().lstrip("#")
    if kw.startswith("r/"):
        kw = kw[2:]
    return f"keyword::{kw}"


def build_clusters(rows: list[dict]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = {}
    for row in rows:
        clusters.setdefault(cluster_key(row), []).append(row)
    return clusters


def _has_mock_evidence(rows: list[dict]) -> bool:
    return any(any(marker in row["source"] for marker in MOCK_MARKERS) for row in rows)


def _cluster_summary(key: str, rows: list[dict], customer_stats: dict[str, dict]) -> dict:
    combined_text = " ".join(r["signal_name"] + " " + r["product_name"] for r in rows)
    category_match = match_category(combined_text, customer_stats)
    distinct_sources = sorted({r["source"] for r in rows})
    examples = [
        {"signal_name": r["signal_name"], "market": r["market"], "source": r["source"], "url": r["url"]}
        for r in rows[:MAX_EXAMPLES_PER_CLUSTER]
    ]
    return {
        "cluster_id": key,
        "evidence_count": len(rows),
        "distinct_sources": distinct_sources,
        "has_mock_evidence": _has_mock_evidence(rows),
        "examples": examples,
        "matching_customer_category": category_match,
    }


SCORING_SYSTEM_PROMPT = """\
You score retail trend signals for a Swiss outdoor retailer (DACH market). \
For each opportunity cluster you receive, assign:
- signal_score: float 0.0-1.0 (strength of the opportunity as evidence)
- confidence: "high", "medium", or "low"
- notes: 1-3 sentences, evidence-grounded. Reference specific sources/markets. \
If has_mock_evidence is true, say so explicitly and lower confidence accordingly \
-- mock/simulated data is not real evidence. If a matching_customer_category is \
present, factor its churn_rate/return_rate into your reasoning (e.g. low churn \
in that category supports testing a related opportunity; high churn is a risk \
flag). Always note whether the opportunity looks transferable to Switzerland/DACH \
or appears to be US/Asia-only so far.

Respond with ONLY a JSON array, no markdown fences, no commentary:
[{"cluster_id": "...", "signal_score": 0.0, "confidence": "...", "notes": "..."}]
"""


def _extract_json_array(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise ValueError(f"no JSON array found in response: {text[:200]}")
    return json.loads(match.group(0))


def score_clusters_with_claude(clusters: dict[str, list[dict]], customer_stats: dict[str, dict]) -> dict[str, dict]:
    summaries = [_cluster_summary(k, v, customer_stats) for k, v in clusters.items()]
    scores: dict[str, dict] = {}

    for i in range(0, len(summaries), CLUSTER_BATCH_SIZE):
        batch = summaries[i:i + CLUSTER_BATCH_SIZE]
        user_message = json.dumps(batch, indent=2)
        reply = claude_client.chat(SCORING_SYSTEM_PROMPT, [], user_message, max_tokens=2048)
        try:
            parsed = _extract_json_array(reply)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"  [score] batch {i // CLUSTER_BATCH_SIZE + 1} failed to parse ({exc}); "
                  f"falling back to rule-based scoring for this batch.")
            for summary in batch:
                scores[summary["cluster_id"]] = rule_based_score(clusters[summary["cluster_id"]])
            continue

        for item in parsed:
            scores[item["cluster_id"]] = {
                "signal_score": item.get("signal_score", 0.5),
                "confidence": item.get("confidence", "low"),
                "notes": item.get("notes", ""),
            }
        print(f"  [score] batch {i // CLUSTER_BATCH_SIZE + 1}: {len(parsed)} clusters scored (Claude).")

    return scores


def rule_based_score(rows: list[dict]) -> dict:
    """Deterministic fallback used when CLAUDE_API_KEY is unset.

    More independent (non-mock) sources corroborating the same cluster ->
    higher score and confidence. Mock-only evidence is capped low.
    """
    distinct_sources = {r["source"] for r in rows}
    live_sources = {s for s in distinct_sources if not any(m in s for m in MOCK_MARKERS)}

    if not live_sources:
        return {
            "signal_score": 0.25,
            "confidence": "low",
            "notes": (
                f"Rule-based fallback (no CLAUDE_API_KEY set): all {len(rows)} evidence row(s) are "
                f"simulated/mock data ({', '.join(sorted(distinct_sources))}); no live corroboration."
            ),
        }

    # Source diversity drives the score, not raw row count -- 59 SKUs from one
    # retailer is volume, not corroboration, and shouldn't outscore 3 distinct
    # sources agreeing. Row count only contributes a small, capped bonus.
    score = min(1.0, 0.3 + 0.2 * len(live_sources) + 0.01 * min(len(rows), 10))
    confidence = "high" if len(live_sources) >= 3 else "medium" if len(live_sources) >= 2 else "low"
    return {
        "signal_score": round(score, 2),
        "confidence": confidence,
        "notes": (
            f"Rule-based fallback (no CLAUDE_API_KEY set): {len(rows)} evidence row(s) across "
            f"{len(live_sources)} live source(s) ({', '.join(sorted(live_sources))})."
        ),
    }


def main() -> None:
    if not os.path.exists(RAW_SIGNALS_PATH):
        print(f"raw_signals.csv not found at {RAW_SIGNALS_PATH}; run scraper_pipeline.py first.")
        return

    with open(RAW_SIGNALS_PATH, newline="", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))

    customer_stats = aggregate_customer_data()
    print(f"Loaded {len(raw_rows)} raw signal rows and {len(customer_stats)} customer categories.")

    clusters = build_clusters(raw_rows)
    print(f"Built {len(clusters)} opportunity clusters.")

    using_claude = bool(claude_client.CLAUDE_API_KEY)
    if using_claude:
        print("CLAUDE_API_KEY set -- scoring clusters with Claude.")
        scores = score_clusters_with_claude(clusters, customer_stats)
    else:
        print("CLAUDE_API_KEY not set -- using deterministic rule-based fallback scoring "
              "(set CLAUDE_API_KEY to score with Claude instead).")
        scores = {key: rule_based_score(rows) for key, rows in clusters.items()}

    created_by = "score_opportunities.py + claude-sonnet-4-6" if using_claude else "score_opportunities.py (rule-based fallback)"

    output_rows = []
    for key, rows in clusters.items():
        score_info = scores.get(key, rule_based_score(rows))
        cluster_has_live_evidence = any(
            not any(marker in r["source"] for marker in MOCK_MARKERS) for r in rows
        )
        for row in rows:
            notes = score_info["notes"]
            # The cluster's score reflects corroboration across the whole
            # cluster, which can include both live and mock rows. A mock row
            # riding on a cluster's live-evidence score needs its own
            # per-row caveat, or a reader could mistake it for validated data.
            row_is_mock = any(marker in row["source"] for marker in MOCK_MARKERS)
            if row_is_mock and cluster_has_live_evidence:
                notes += (
                    f" (Caveat: this specific row's source, '{row['source']}', is simulated/mock data; "
                    "the score above reflects corroboration from the other live sources in this cluster.)"
                )
            output_rows.append({
                **row,
                "signal_score": score_info["signal_score"],
                "confidence": score_info["confidence"],
                "notes": notes,
                "artifact_type": "csv",
                "artifact_uri": "scored_opportunities.csv",
                "created_by_tool": created_by,
            })

    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {len(output_rows)} scored rows -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
