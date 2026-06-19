"""
LLM compilation step: top scored signals → ranked business opportunities.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm_client import MODEL, messages_create, resolve_api_key

MAX_SIGNALS = 20

FAKE_DATA_PATH = os.path.join(PROJECT_ROOT, "data_generation", "fake_data.csv")
SCORED_SIGNALS_PATH = os.path.join(PROJECT_ROOT, "scored_opportunities.csv")
RECOMMENDATIONS_PATH = os.path.join(PROJECT_ROOT, "ranked_recommendations.csv")

RECOMMENDATION_COLUMNS = [
    "rank", "signal_score", "opportunity", "opportunity_type", "first_observed_market",
    "evidence_summary", "evidence_urls", "transferability", "coverage_status",
    "recommended_action", "confidence", "risks",
    "products", "features", "materials", "aesthetics", "color_palettes",
    "recommended_workflow", "competitor_gap",
]

# From docs/challenge.md — opportunities are not only products
OPPORTUNITY_TYPES = (
    "product_type", "material", "feature", "aesthetic", "color_palette",
    "brand", "price_gap", "merchandising", "usage_occasion", "content_community",
)

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

COMPILE_PROMPT = """\
You are a retail intelligence analyst for a Swiss outdoor retailer (DACH market).

Top scored market signals:
{signals}

Trend facets extracted from evidence:
{facets}

Competitor assortment gaps (brands/categories at rivals but not client):
{gaps}

{sales_block}

Identify the top 8–10 distinct business opportunities for a Swiss/DACH outdoor retailer.
Cover MULTIPLE opportunity types — not only products. Include at least:
  - 1 material or technology opportunity
  - 1 aesthetic or colour_palette opportunity
  - 1 product_type OR brand opportunity
  - 1 feature, merchandising, or price_gap if supported by evidence

For EACH return JSON with keys:
  rank, opportunity, opportunity_type (one of: OPPORTUNITY_TYPES_PLACEHOLDER),
  description, evidence (list of 2-3 bullets with source names),
  first_observed_market, evidence_urls (copied EXACTLY from signals — never invent),
  transferability, action, confidence (low|medium|high), risks,
  products (list), features (list), materials (list), aesthetics (list), color_palettes (list),
  recommended_workflow (monitor|test|buy|launch),
  competitor_gap (one sentence if relevant)

Return ONLY a valid JSON array. Keep every string value short (under 120 chars).
Escape double quotes inside strings with backslash. No markdown fences, no commentary.
""".replace("OPPORTUNITY_TYPES_PLACEHOLDER", ", ".join(OPPORTUNITY_TYPES))


def _parse_opportunities_json(raw: str) -> list[dict]:
    """Parse LLM JSON array; raise ValueError if unrecoverable."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        raise ValueError("no JSON array found in LLM response")
    return json.loads(match.group(0))


def _attach_signal_scores(opportunities: list[dict], signals: list[dict]) -> None:
    """For each opportunity, find the highest-scoring signal whose name overlaps, attach as signal_score."""
    for opp in opportunities:
        if "signal_score" in opp:
            continue
        opp_text = (opp.get("opportunity", "") + " " + opp.get("description", "")).lower()
        opp_words = set(w for w in re.split(r"\W+", opp_text) if len(w) > 3)
        best = 0.0
        for s in signals:
            sig_text = s.get("signal_name", "").lower()
            sig_words = set(w for w in re.split(r"\W+", sig_text) if len(w) > 3)
            if opp_words & sig_words:
                best = max(best, float(s.get("signal_score", 0)))
        opp["signal_score"] = round(best, 4) if best else 0.30


def _finalize_opportunities(
    opportunities: list[dict],
    valid_urls: set[str],
    gap_hints: dict,
    insights: dict,
    category_volume: dict[str, int],
    signals: list[dict] | None = None,
) -> list[dict]:
    for opp in opportunities:
        cited = opp.get("evidence_urls", []) or []
        opp["evidence_urls"] = [u for u in cited if u in valid_urls]
        opp.setdefault("first_observed_market", "N/A")
        opp.setdefault("opportunity_type", "product_type")
        opp.setdefault("recommended_workflow", "monitor")
        opp.setdefault("competitor_gap", gap_hints.get("summary", ""))
        for key in ("products", "features", "materials", "aesthetics", "color_palettes"):
            opp.setdefault(key, insights.get(key, [])[:3])
        combined = opp.get("opportunity", "") + " " + opp.get("description", "")
        opp["coverage_status"] = _compute_coverage_status(combined, category_volume)
    if signals:
        _attach_signal_scores(opportunities, signals)
    opportunities.sort(key=lambda o: float(o.get("signal_score", 0)), reverse=True)
    for i, opp in enumerate(opportunities, 1):
        opp["rank"] = i
    return opportunities


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


def _facet_opportunity(
    rank: int,
    opportunity_type: str,
    title: str,
    description: str,
    insights: dict,
    gap_hints: dict,
    workflow: str = "monitor",
    confidence: str = "medium",
    evidence: list[str] | None = None,
) -> dict:
    return {
        "rank": rank,
        "opportunity": title,
        "opportunity_type": opportunity_type,
        "description": description,
        "evidence": evidence or [description],
        "first_observed_market": "global",
        "evidence_urls": [],
        "transferability": "Assess CH/DACH fit using regional signals and multi-geo search trends.",
        "action": f"Recommended workflow: {workflow}",
        "confidence": confidence,
        "risks": "Derived from trend facet extraction; corroborate with live competitor data.",
        "products": insights.get("products", [])[:2],
        "features": insights.get("features", [])[:3] if opportunity_type == "feature" else insights.get("features", [])[:1],
        "materials": insights.get("materials", [])[:3] if opportunity_type == "material" else insights.get("materials", [])[:1],
        "aesthetics": insights.get("aesthetics", [])[:3] if opportunity_type == "aesthetic" else insights.get("aesthetics", [])[:1],
        "color_palettes": insights.get("color_palettes", [])[:3] if opportunity_type == "color_palette" else insights.get("color_palettes", [])[:1],
        "recommended_workflow": workflow,
        "competitor_gap": gap_hints.get("summary", ""),
        "coverage_status": "unknown",
    }


def _rule_based_opportunities(
    signals: list[dict],
    insights: dict,
    gap_hints: dict,
) -> list[dict]:
    """Diverse deterministic recommendations — products, materials, colours, brands, features."""
    opps: list[dict] = []
    rank = 1
    gap_summary = gap_hints.get("summary", "No gap analysis available.")
    top_signals = sorted(signals, key=lambda x: float(x.get("signal_score", 0)), reverse=True)

    # Top product signals — take up to 3
    for s in top_signals[:3]:
        workflow = _extract_workflow(s.get("notes", ""))
        name = s.get("signal_name", "Opportunity")
        if len(name) > 80:
            name = name[:77] + "..."
        score = float(s.get("signal_score", 0.3))
        opps.append({
            "rank": rank,
            "signal_score": score,
            "opportunity": name,
            "opportunity_type": "product_type",
            "description": (
                f"Top product signal from {s.get('source')} ({s.get('market')}), "
                f"score {score:.2f}."
            ),
            "evidence": [f"{s.get('source')}: {s.get('signal_name')}"],
            "first_observed_market": s.get("market", "N/A"),
            "evidence_urls": [s.get("url")] if s.get("url") and s.get("url") != "N/A" else [],
            "transferability": "Cross-check US/JP trend velocity vs CH before ranging.",
            "action": f"Recommended workflow: {workflow}",
            "confidence": s.get("confidence", "low"),
            "risks": "Compiled from scored signals (rule-based fallback).",
            "products": insights.get("products", [])[:3],
            "features": insights.get("features", [])[:2],
            "materials": insights.get("materials", [])[:2],
            "aesthetics": insights.get("aesthetics", [])[:2],
            "color_palettes": insights.get("color_palettes", [])[:2],
            "recommended_workflow": workflow,
            "competitor_gap": gap_summary,
            "coverage_status": "unknown",
        })
        rank += 1

    for mat in insights.get("materials", [])[:3]:
        opps.append(_facet_opportunity(
            rank, "material", f"Material watch: {mat}",
            f"'{mat}' appears across social and publication signals — monitor for niche-to-mainstream shift.",
            insights, gap_hints, workflow="monitor", confidence="medium",
            evidence=[f"Trend facet: material '{mat}'"],
        ))
        opps[-1]["signal_score"] = 0.55
        rank += 1

    palettes = insights.get("color_palettes") or []
    for p in palettes[:2]:
        opps.append(_facet_opportunity(
            rank, "color_palette", f"Colour direction: {p}",
            f"Palette '{p}' gaining visibility — align merchandising and buy to this direction.",
            insights, gap_hints, workflow="test", confidence="medium",
            evidence=[f"Trend facet: colour '{p}'"],
        ))
        opps[-1]["signal_score"] = 0.50
        rank += 1

    for aes in (insights.get("aesthetics") or [])[:2]:
        opps.append(_facet_opportunity(
            rank, "aesthetic", f"Aesthetic signal: {aes}",
            f"Vibe '{aes}' surfacing across social channels — relevant for content and assortment curation.",
            insights, gap_hints, workflow="monitor", confidence="medium",
            evidence=[f"Trend facet: aesthetic '{aes}'"],
        ))
        opps[-1]["signal_score"] = 0.48
        rank += 1

    for brand in gap_hints.get("gap_brands", [])[:3]:
        opps.append(_facet_opportunity(
            rank, "brand", f"Scout brand: {brand.title()}",
            f"Brand '{brand}' listed at multiple competitors but absent from client assortment.",
            insights, gap_hints, workflow="test", confidence="medium",
            evidence=[f"Competitor gap: brand '{brand}'"],
        ))
        opps[-1]["signal_score"] = 0.60
        rank += 1

    for cat in gap_hints.get("gap_categories", [])[:2]:
        opps.append(_facet_opportunity(
            rank, "price_gap", f"Category gap: {cat}",
            f"Category '{cat}' present at competitors but under-represented in client assortment.",
            insights, gap_hints, workflow="test", confidence="medium",
            evidence=[f"Competitor gap: category '{cat}'"],
        ))
        opps[-1]["signal_score"] = 0.58
        rank += 1

    for feat in insights.get("features", [])[:3]:
        opps.append(_facet_opportunity(
            rank, "feature", f"Feature trend: {feat}",
            f"Technical feature '{feat}' — evaluate supplier options and margin impact.",
            insights, gap_hints, workflow="monitor", confidence="low",
            evidence=[f"Trend facet: feature '{feat}'"],
        ))
        opps[-1]["signal_score"] = 0.42
        rank += 1

    # Sort by signal_score descending and re-number rank
    opps.sort(key=lambda o: float(o.get("signal_score", 0)), reverse=True)
    for i, o in enumerate(opps, 1):
        o["rank"] = i

    return opps or _placeholders()


def compile_opportunities(
    signals: list[dict],
    sales_context: str = "",
    insights: dict | None = None,
    gap_hints: dict | None = None,
    api_key: str | None = None,
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

    if not resolve_api_key(api_key):
        opps = _rule_based_opportunities(top_signals, insights, gap_hints)
        category_volume = _aggregate_category_volume()
        for opp in opps:
            opp["coverage_status"] = _compute_coverage_status(
                opp.get("opportunity", "") + " " + opp.get("description", ""),
                category_volume,
            )
        return opps

    prompt = COMPILE_PROMPT.format(signals=signal_lines, facets=facets, gaps=gaps, sales_block=sales_block)
    category_volume = _aggregate_category_volume()
    fallback = _rule_based_opportunities(top_signals, insights, gap_hints)
    for opp in fallback:
        opp["coverage_status"] = _compute_coverage_status(
            opp.get("opportunity", "") + " " + opp.get("description", ""),
            category_volume,
        )

    try:
        raw = messages_create(prompt, api_key=api_key, model=MODEL, max_tokens=4096)
        if not raw:
            return fallback
        opportunities = _parse_opportunities_json(raw)
        return _finalize_opportunities(opportunities, valid_urls, gap_hints, insights, category_volume, signals=top_signals)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"  [compiler] LLM JSON parse failed ({exc}); using rule-based fallback.")
        for opp in fallback:
            opp["risks"] = f"LLM output was malformed ({exc}); showing rule-based recommendations."
        return fallback
    except Exception as exc:
        print(f"  [compiler] LLM call failed ({exc}); using rule-based fallback.")
        for opp in fallback:
            opp["risks"] = f"LLM compilation failed ({exc}); showing rule-based recommendations."
        return fallback


def _placeholders() -> list[dict]:
    return [{
        "rank": 1,
        "opportunity": "Pipeline complete — enter API key in sidebar for richer compilation",
        "opportunity_type": "product_type",
        "description": "Signals scored successfully. Provide your Claude API key in the sidebar for LLM compilation.",
        "evidence": ["See scored_opportunities.csv"],
        "first_observed_market": "N/A",
        "evidence_urls": [],
        "transferability": "N/A",
        "coverage_status": "unknown",
        "action": "Enter your Claude API key in the sidebar (session only, not saved to disk).",
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
            "signal_score": round(float(opp.get("signal_score", 0)), 4) if opp.get("signal_score") is not None else "",
            "opportunity": opp.get("opportunity", ""),
            "opportunity_type": opp.get("opportunity_type", "product_type"),
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
        rows = list(csv.DictReader(f))
    return [r for r in rows if r.get("opportunity") != "Compilation error"]


if __name__ == "__main__":
    if not os.path.exists(SCORED_SIGNALS_PATH):
        print(f"scored_opportunities.csv not found; run scorer first.")
        sys.exit(1)
    with open(SCORED_SIGNALS_PATH, newline="", encoding="utf-8") as f:
        scored = list(csv.DictReader(f))
    opps = compile_opportunities(scored)
    write_recommendations_csv(opps)
    print(f"Wrote {len(opps)} rows -> {RECOMMENDATIONS_PATH}")
