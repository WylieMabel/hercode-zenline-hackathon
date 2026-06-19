"""
LLM compilation step: top scored signals → ranked business opportunities.
"""

from __future__ import annotations

import csv
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
MODEL = "claude-sonnet-4-6"
MAX_SIGNALS = 20

FAKE_DATA_PATH = os.path.join(PROJECT_ROOT, "data_generation", "fake_data.csv")
SCORED_SIGNALS_PATH = os.path.join(PROJECT_ROOT, "scored_opportunities.csv")
RECOMMENDATIONS_PATH = os.path.join(PROJECT_ROOT, "ranked_recommendations.csv")

RECOMMENDATION_COLUMNS = [
    "rank", "opportunity", "first_observed_market", "evidence_summary",
    "evidence_urls", "transferability", "coverage_status",
    "recommended_action", "confidence", "risks",
    "products", "features", "materials", "aesthetics", "color_palettes",
    "recommended_workflow", "competitor_gap",
]

CATEGORY_KEYWORDS = {
    "Hiking Footwear": ["hiking boot", "hiking shoe", "approach shoe"],
    "Trail Running Shoes": ["trail running shoe", "trail run shoe", "speedgoat"],
    "Ski Equipment": ["ski ", "snowboard", "binding"],
    "Ski Apparel": ["ski jacket", "ski pant"],
    "Hiking Apparel": ["jacket", "hoodie", "fleece", "softshell", "apparel", "gorpcore"],
    "Climbing Gear": ["climbing", "carabiner", "quickdraw", "chalk", "harness"],
    "Backpacks": ["backpack", "rucksack", "daypack", "pack"],
    "Tents & Sleeping": ["tent", "sleeping bag", "sleeping pad", "fastpacking"],
    "Base Layers": ["base layer", "thermal", "merino"],
    "Accessories": ["headlamp", "gloves", "accessor"],
    "Navigation & Safety": ["gps", "compass", "avalanche", "beacon"],
    "Bike & MTB": ["bike", "mtb", "cycling"],
}

_client = None
if CLAUDE_API_KEY:
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    except ImportError:
        pass

COMPILE_PROMPT = """\
You are a retail intelligence analyst for a Swiss outdoor retailer (DACH market).

Top scored market signals:
{signals}

Trend facets extracted from evidence:
{facets}

Competitor assortment gaps (brands/categories at rivals but not client):
{gaps}

{sales_block}

Identify the top 3–5 distinct business opportunities. For EACH return JSON with keys:
  rank, opportunity, description, evidence (list of 2-3 bullets with source names),
  first_observed_market, evidence_urls (copied EXACTLY from signals — never invent),
  transferability, action, confidence (low|medium|high), risks,
  products (list), features (list), materials (list), aesthetics (list), color_palettes (list),
  recommended_workflow (monitor|test|buy|launch — from signal notes workflow= field),
  competitor_gap (one sentence on assortment gap if relevant)

Return ONLY a valid JSON array, no markdown.
"""


def _aggregate_category_volume(path: str = FAKE_DATA_PATH) -> dict[str, int]:
    if not os.path.exists(path):
        return {}
    counts: dict[str, int] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cat = row.get("Product Category")
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
    return counts


def _compute_coverage_status(opportunity_text: str, category_volume: dict[str, int]) -> str:
    text = opportunity_text.lower()
    best_category, best_hits = None, 0
    for category, triggers in CATEGORY_KEYWORDS.items():
        hits = sum(1 for t in triggers if t in text)
        if hits > best_hits:
            best_category, best_hits = category, hits
    if best_category is None:
        return "unknown"
    volume = category_volume.get(best_category, 0)
    if volume == 0:
        return "absent"
    return "covered" if volume >= 50 else "partially_covered"


def _extract_workflow(notes: str) -> str:
    if "workflow=launch" in notes:
        return "launch"
    if "workflow=buy" in notes:
        return "buy"
    if "workflow=test" in notes:
        return "test"
    return "monitor"


def _rule_based_opportunities(
    signals: list[dict],
    insights: dict,
    gap_hints: dict,
) -> list[dict]:
    """Deterministic fallback when no API key."""
    top = sorted(signals, key=lambda x: float(x.get("signal_score", 0)), reverse=True)[:5]
    opps = []
    gap_summary = gap_hints.get("summary", "No gap analysis available.")
    for i, s in enumerate(top[:3], 1):
        workflow = _extract_workflow(s.get("notes", ""))
        opps.append({
            "rank": i,
            "opportunity": s.get("signal_name", "Opportunity")[:60],
            "description": f"Signal from {s.get('source')} in market {s.get('market')} (score {s.get('signal_score')}).",
            "evidence": [f"{s.get('source')}: {s.get('signal_name')}"],
            "first_observed_market": s.get("market", "N/A"),
            "evidence_urls": [s.get("url")] if s.get("url") and s.get("url") != "N/A" else [],
            "transferability": "Assess CH/DACH fit based on market tag and regional signals.",
            "action": f"Recommended workflow: {workflow}",
            "confidence": s.get("confidence", "low"),
            "risks": "Rule-based compilation without LLM — verify evidence manually.",
            "products": insights.get("products", [])[:3],
            "features": insights.get("features", [])[:3],
            "materials": insights.get("materials", [])[:3],
            "aesthetics": insights.get("aesthetics", [])[:3],
            "color_palettes": insights.get("color_palettes", [])[:3],
            "recommended_workflow": workflow,
            "competitor_gap": gap_summary,
            "coverage_status": "unknown",
        })
    return opps or _placeholders()


def compile_opportunities(
    signals: list[dict],
    sales_context: str = "",
    insights: dict | None = None,
    gap_hints: dict | None = None,
) -> list[dict]:
    insights = insights or {}
    gap_hints = gap_hints or {}

    if not signals:
        return _placeholders()

    top_signals = sorted(signals, key=lambda x: float(x.get("signal_score", 0)), reverse=True)[:MAX_SIGNALS]
    valid_urls = {s.get("url", "") for s in top_signals if s.get("url") and s.get("url") != "N/A"}

    signal_lines = "\n".join(
        f"- [score {s.get('signal_score')}, {s.get('confidence')}] {s.get('signal_name')} | "
        f"brand: {s.get('brand')} | market: {s.get('market')} | source: {s.get('source')} | "
        f"notes: {s.get('notes', '')} | {s.get('url')}"
        for s in top_signals
    )
    facets = json.dumps({k: insights.get(k, []) for k in (
        "trends", "products", "features", "materials", "aesthetics", "color_palettes"
    )}, indent=2)
    gaps = json.dumps(gap_hints, indent=2)
    sales_block = f"Customer data:\n{sales_context}" if sales_context else ""

    if not _client:
        opps = _rule_based_opportunities(top_signals, insights, gap_hints)
        category_volume = _aggregate_category_volume()
        for opp in opps:
            opp["coverage_status"] = _compute_coverage_status(
                opp.get("opportunity", "") + " " + opp.get("description", ""),
                category_volume,
            )
        return opps

    prompt = COMPILE_PROMPT.format(signals=signal_lines, facets=facets, gaps=gaps, sales_block=sales_block)
    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=3072,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        opportunities = json.loads(raw)
    except Exception as exc:
        return [{
            "rank": 1,
            "opportunity": "Compilation error",
            "description": str(exc),
            "evidence": [],
            "first_observed_market": "N/A",
            "evidence_urls": [],
            "transferability": "",
            "coverage_status": "unknown",
            "action": "Check CLAUDE_API_KEY and retry.",
            "confidence": "low",
            "risks": "LLM compilation failed.",
            "recommended_workflow": "monitor",
            "competitor_gap": "",
        }]

    category_volume = _aggregate_category_volume()
    for opp in opportunities:
        cited = opp.get("evidence_urls", []) or []
        opp["evidence_urls"] = [u for u in cited if u in valid_urls]
        opp.setdefault("first_observed_market", "N/A")
        opp.setdefault("recommended_workflow", "monitor")
        opp.setdefault("competitor_gap", gap_hints.get("summary", ""))
        for key in ("products", "features", "materials", "aesthetics", "color_palettes"):
            opp.setdefault(key, insights.get(key, [])[:3])
        combined = opp.get("opportunity", "") + " " + opp.get("description", "")
        opp["coverage_status"] = _compute_coverage_status(combined, category_volume)

    return opportunities


def _placeholders() -> list[dict]:
    return [{
        "rank": 1,
        "opportunity": "Pipeline complete — set CLAUDE_API_KEY for richer compilation",
        "description": "Signals scored successfully. Rule-based or LLM compilation available.",
        "evidence": ["See scored_opportunities.csv"],
        "first_observed_market": "N/A",
        "evidence_urls": [],
        "transferability": "N/A",
        "coverage_status": "unknown",
        "action": "Export CLAUDE_API_KEY and rerun.",
        "confidence": "low",
        "risks": "No LLM key configured.",
        "recommended_workflow": "monitor",
        "competitor_gap": "",
        "products": [], "features": [], "materials": [], "aesthetics": [], "color_palettes": [],
    }]


def write_recommendations_csv(opportunities: list[dict], path: str = RECOMMENDATIONS_PATH) -> None:
    rows = []
    for opp in opportunities:
        evidence_bullets = "; ".join(opp.get("evidence", []) or [])
        rows.append({
            "rank": opp.get("rank", ""),
            "opportunity": opp.get("opportunity", ""),
            "first_observed_market": opp.get("first_observed_market", "N/A"),
            "evidence_summary": opp.get("description", "") + (f" Evidence: {evidence_bullets}" if evidence_bullets else ""),
            "evidence_urls": "; ".join(opp.get("evidence_urls", []) or []),
            "transferability": opp.get("transferability", ""),
            "coverage_status": opp.get("coverage_status", "unknown"),
            "recommended_action": opp.get("action", ""),
            "confidence": opp.get("confidence", ""),
            "risks": opp.get("risks", ""),
            "products": "; ".join(opp.get("products", []) or []),
            "features": "; ".join(opp.get("features", []) or []),
            "materials": "; ".join(opp.get("materials", []) or []),
            "aesthetics": "; ".join(opp.get("aesthetics", []) or []),
            "color_palettes": "; ".join(opp.get("color_palettes", []) or []),
            "recommended_workflow": opp.get("recommended_workflow", "monitor"),
            "competitor_gap": opp.get("competitor_gap", ""),
        })

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RECOMMENDATION_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_recommendations(path: str = RECOMMENDATIONS_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    if not os.path.exists(SCORED_SIGNALS_PATH):
        print(f"scored_opportunities.csv not found; run scorer first.")
        sys.exit(1)
    with open(SCORED_SIGNALS_PATH, newline="", encoding="utf-8") as f:
        scored = list(csv.DictReader(f))
    opps = compile_opportunities(scored)
    write_recommendations_csv(opps)
    print(f"Wrote {len(opps)} rows -> {RECOMMENDATIONS_PATH}")
