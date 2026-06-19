"""Step 2 enrichment: extract trend facets from collected signals."""

from __future__ import annotations

import json
import os
import re
from collections import Counter

from pipeline_config import PROJECT_ROOT

INSIGHTS_PATH = os.path.join(PROJECT_ROOT, "trend_insights.json")

FACET_KEYS = [
    "trends", "products", "features", "materials",
    "aesthetics", "color_palettes", "recommendations",
]

MATERIAL_WORDS = ["merino", "dyneema", "pertex", "gore-tex", "nylon", "polyester", "fleece", "down", "canvas"]
FEATURE_WORDS = ["waterproof", "breathable", "ultralight", "modular", "pfas-free", "dwr", "insulated", "packable"]
AESTHETIC_WORDS = ["gorpcore", "minimal", "earth tone", "technical", "alpine", "streetwear", "heritage"]
COLOR_WORDS = ["olive", "sand", "stone", "black", "orange", "neon", "earth", "navy", "beige"]


def _rule_based_insights(signals: list[dict]) -> dict:
    texts = []
    url_map: dict[str, list[str]] = {k: [] for k in FACET_KEYS}

    for s in signals:
        text = " ".join(
            str(s.get(f, "")) for f in ("signal_name", "product_name", "brand", "keyword")
        ).lower()
        texts.append(text)
        url = s.get("url", "")

        for word in MATERIAL_WORDS:
            if word in text:
                url_map["materials"].append(url)
        for word in FEATURE_WORDS:
            if word in text:
                url_map["features"].append(url)
        for word in AESTHETIC_WORDS:
            if word in text:
                url_map["aesthetics"].append(url)
        for word in COLOR_WORDS:
            if word in text:
                url_map["color_palettes"].append(url)

    combined = " ".join(texts)
    kw_counts = Counter()
    for s in signals:
        if s.get("signal_type") in ("social", "search", "web"):
            kw_counts[s.get("keyword", "")] += 1

    trends = [k for k, _ in kw_counts.most_common(6) if k and k != "N/A"]
    products = list({s.get("product_name") for s in signals if s.get("product_name") not in (None, "", "N/A")})[:8]

    def top_hits(words: list[str], n: int = 5) -> list[str]:
        return [w for w in words if w in combined][:n]

    insights = {
        "trends": trends,
        "products": products,
        "features": top_hits(FEATURE_WORDS),
        "materials": top_hits(MATERIAL_WORDS),
        "aesthetics": top_hits(AESTHETIC_WORDS),
        "color_palettes": top_hits(COLOR_WORDS),
        "recommendations": [
            "Monitor rising search terms in non-CH markets for transferability",
            "Test-buy products in categories competitors list but client does not",
        ],
        "provenance": {k: list(dict.fromkeys(v))[:5] for k, v in url_map.items()},
        "extraction_method": "rule_based",
    }
    return insights


def _claude_insights(signals: list[dict], config: dict) -> dict | None:
    api_key = os.environ.get("CLAUDE_API_KEY", "")
    if not api_key:
        return None
    try:
        import anthropic

        sample = signals[:40]
        lines = "\n".join(
            f"- {s.get('signal_name')} | source={s.get('source')} | market={s.get('market')} | {s.get('url')}"
            for s in sample
        )
        prompt = f"""Extract retail trend facets from these signals for {config.get('market')} in {config.get('location')}.
Return JSON with keys: trends, products, features, materials, aesthetics, color_palettes, recommendations (all lists of strings).
Add provenance: object mapping each facet key to list of source URLs that support items.
Signals:
{lines}
Return ONLY valid JSON."""

        client = anthropic.Anthropic(api_key=api_key)
        raw = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        ).content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        data["extraction_method"] = "claude"
        return data
    except Exception as exc:
        print(f"  [trend_extraction] Claude failed ({exc}); rule-based fallback.")
        return None


def extract_trend_facets(signals: list[dict], config: dict) -> dict:
    insights = _claude_insights(signals, config) or _rule_based_insights(signals)
    with open(INSIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2)
    return insights


def load_trend_insights(path: str = INSIGHTS_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
