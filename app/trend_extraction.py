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


def _rule_based_insights(signals: list[dict], config: dict | None = None) -> dict:
    config = config or {}
    material_words = list(MATERIAL_WORDS) + [m.lower() for m in config.get("materials_watchlist", [])]
    feature_words = list(FEATURE_WORDS) + [f.lower() for f in config.get("features_watchlist", [])]
    aesthetic_words = list(AESTHETIC_WORDS) + [a.lower() for a in config.get("aesthetic_lexicon", [])]
    color_words = list(COLOR_WORDS) + [c.lower() for c in config.get("color_palettes_watchlist", [])]
    texts = []
    url_map: dict[str, list[str]] = {k: [] for k in FACET_KEYS}

    for s in signals:
        text = " ".join(
            str(s.get(f, "")) for f in ("signal_name", "product_name", "brand", "keyword")
        ).lower()
        texts.append(text)
        url = s.get("url", "")

        for word in material_words:
            if word in text:
                url_map["materials"].append(url)
        for word in feature_words:
            if word in text:
                url_map["features"].append(url)
        for word in aesthetic_words:
            if word in text:
                url_map["aesthetics"].append(url)
        for word in color_words:
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
        seen: list[str] = []
        for w in words:
            if w in combined and w not in seen:
                seen.append(w)
            if len(seen) >= n:
                break
        return seen

    insights = {
        "trends": trends,
        "products": products,
        "features": top_hits(feature_words),
        "materials": top_hits(material_words),
        "aesthetics": top_hits(aesthetic_words),
        "color_palettes": top_hits(color_words) or config.get("color_palettes_watchlist", [])[:4],
        "recommendations": [
            "Monitor rising search terms in non-CH markets for transferability",
            "Test-buy products in categories competitors list but client does not",
        ],
        "provenance": {k: list(dict.fromkeys(v))[:5] for k, v in url_map.items()},
        "extraction_method": "rule_based",
    }
    return insights


def _claude_insights(signals: list[dict], config: dict, api_key: str | None = None) -> dict | None:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from llm_client import MODEL, messages_create, resolve_api_key

    if not resolve_api_key(api_key):
        return None
    try:
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

        raw = messages_create(prompt, api_key=api_key, model=MODEL, max_tokens=1024)
        if not raw:
            return None
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        data["extraction_method"] = "claude"
        return data
    except Exception as exc:
        print(f"  [trend_extraction] Claude failed ({exc}); rule-based fallback.")
        return None


def extract_trend_facets(signals: list[dict], config: dict, api_key: str | None = None) -> dict:
    insights = _claude_insights(signals, config, api_key=api_key) or _rule_based_insights(signals, config)
    with open(INSIGHTS_PATH, "w", encoding="utf-8") as f:
        json.dump(insights, f, indent=2)
    return insights


def load_trend_insights(path: str = INSIGHTS_PATH) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)
