"""Vertical presets — tuned defaults per market, extensible for new verticals."""

from __future__ import annotations

from copy import deepcopy

# Keys must match slugs in competitors.RETAILER_REGISTRY to be scrapeable.
SWISS_OUTDOOR_PRESET = {
    "vertical_id": "swiss_outdoor",
    "label": "Swiss outdoor",
    "keywords": [
        "gorpcore", "trail running packs", "fastpacking",
        "ultralight hiking", "alpine crossover",
    ],
    "competitors": [
        "bergfreunde", "rei", "patagonia", "black_diamond", "decathlon", "columbia",
    ],
    "hashtags": ["#gorpcore", "#trailrunning", "#fastpacking", "#alpinestyle"],
    "subreddits": ["ultralight", "climbing", "trailrunning", "CampingGear"],
    "aesthetic_lexicon": [
        "gorpcore", "alpine minimal", "earth tones", "technical casual", "heritage outdoor",
    ],
    "materials_watchlist": [
        "merino", "pertex", "dyneema", "recycled nylon", "gore-tex", "primaloft",
    ],
    "features_watchlist": [
        "PFAS-free DWR", "modular vest", "ultralight pack", "approach shoe", "vegan insulation",
    ],
    "color_palettes_watchlist": [
        "olive and stone", "sand and charcoal", "earth neutrals", "high-vis accent",
    ],
    "compare_markets": ["CH", "US", "JP"],
    "opportunity_types_focus": [
        "product_type", "material", "feature", "aesthetic", "color_palette",
        "brand", "price_gap", "merchandising",
    ],
}

# Add future verticals here, e.g. "korean skincare": { ... }
VERTICAL_PRESETS: dict[str, dict] = {
    "swiss outdoor": SWISS_OUTDOOR_PRESET,
    "swiss_outdoor": SWISS_OUTDOOR_PRESET,
    "outdoor": SWISS_OUTDOOR_PRESET,
}


def match_vertical(market: str, location: str = "") -> str:
    """Resolve market/location text to a preset key."""
    text = f"{market} {location}".lower()
    if "skincare" in text or "beauty" in text or "makeup" in text:
        return "swiss outdoor"  # placeholder until skincare preset exists
    if "outdoor" in text or "swiss" in text or "alpine" in text or "hiking" in text:
        return "swiss outdoor"
    for key in VERTICAL_PRESETS:
        if key in text:
            return key
    return "swiss outdoor"


def apply_vertical_preset(config: dict) -> dict:
    """Merge vertical defaults into config without overwriting explicit user fields."""
    preset_key = match_vertical(config.get("market", ""), config.get("location", ""))
    preset = deepcopy(VERTICAL_PRESETS.get(preset_key, SWISS_OUTDOOR_PRESET))
    config["vertical_id"] = preset.get("vertical_id", preset_key.replace(" ", "_"))
    config["vertical_label"] = preset.get("label", preset_key)

    for field in (
        "keywords", "competitors", "hashtags", "subreddits",
        "aesthetic_lexicon", "materials_watchlist", "features_watchlist",
        "color_palettes_watchlist", "compare_markets", "opportunity_types_focus",
    ):
        if field in preset and not config.get(field):
            config[field] = preset[field]
        elif field in preset and field == "competitors" and config.get("competitors") == []:
            config[field] = preset[field]
    return config
