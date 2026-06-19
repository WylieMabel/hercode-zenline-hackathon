"""
Scoring layer: raw_signals.csv → scored_opportunities.csv

Groups signals by keyword, computes a signal_score per cluster based on
source diversity, signal-type diversity, and Swiss/DACH market presence,
then writes every row back with score + confidence + notes attached.
"""

import csv
import os
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_SIGNALS_PATH = os.path.join(PROJECT_ROOT, "raw_signals.csv")
SCORED_PATH = os.path.join(PROJECT_ROOT, "scored_opportunities.csv")

OUTPUT_COLUMNS = [
    "source", "market", "keyword", "signal_name", "signal_type",
    "product_name", "brand", "price", "rank", "url",
    "signal_score", "confidence", "notes", "observed_at",
    "artifact_type", "artifact_uri", "created_by_tool",
]


def score_signals(
    input_path: str = RAW_SIGNALS_PATH,
    output_path: str = SCORED_PATH,
) -> list[dict]:
    with open(input_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return []

    # Build cluster stats per keyword
    clusters: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        clusters[row.get("keyword", "unknown")].append(row)

    cluster_scores: dict[str, float] = {}
    for keyword, cluster in clusters.items():
        sources = {r["source"] for r in cluster}
        types = {r.get("signal_type", "") for r in cluster}
        markets = {r.get("market", "") for r in cluster}

        # Remove mock/fallback sources from the diversity count so real
        # signals score higher than pure-mock clusters.
        real_sources = {s for s in sources if "mock" not in s and "fallback" not in s}

        source_score = min(len(real_sources) / 4.0 + len(sources) / 10.0, 1.0)
        type_score = min(len(types) / 3.0, 1.0)
        swiss_bonus = 0.15 if any(m in ("CH", "DE/CH") for m in markets) else 0.0

        raw = 0.5 * source_score + 0.3 * type_score + 0.2
        cluster_scores[keyword] = round(min(raw + swiss_bonus, 1.0), 2)

    # Write each row with its cluster score appended
    scored: list[dict] = []
    for row in rows:
        kw = row.get("keyword", "unknown")
        score = cluster_scores.get(kw, 0.3)
        confidence = "high" if score >= 0.65 else ("medium" if score >= 0.4 else "low")
        cluster = clusters[kw]
        n_sources = len({r["source"] for r in cluster})
        notes = f"{len(cluster)} signals from {n_sources} source(s) in cluster '{kw}'"

        scored_row = {
            **{c: row.get(c, "") for c in OUTPUT_COLUMNS},
            "signal_score": score,
            "confidence": confidence,
            "notes": notes,
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
