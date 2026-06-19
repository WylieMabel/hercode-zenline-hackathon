"""
competitors/scrape_products.py

Scrapes products from competitor sites listed in extracted_websites.csv.

Strategy per domain (tried in order):
  1. Shopify JSON API  — /collections/all/products.json?limit=250&page=N
  2. Schema.org JSON-LD — <script type="application/ld+json"> Product objects
  3. Generic HTML — common breadcrumb + price + title CSS patterns

Material and feature fields are extracted from the product description text
using keyword lists (no LLM needed, works offline).

Output: competitors/competitor_products.csv

Run:
    python3 competitors/scrape_products.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DIR = Path(__file__).parent
SITES_CSV = DIR / "extracted_websites.csv"
OUTPUT_CSV = DIR / "competitor_products.csv"

OUTPUT_COLUMNS = [
    "product_type",
    "product_subtype",
    "price",
    "material",
    "brand",
    "competitor_name",
    "product_description",
    "feature",
    "original_site",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REQUEST_TIMEOUT = 12
CRAWL_DELAY = 1.2   # seconds between requests to the same domain

# ---------------------------------------------------------------------------
# Material & feature keyword extraction
# ---------------------------------------------------------------------------

MATERIAL_KEYWORDS: list[str] = [
    # Technical fabrics
    "Gore-Tex", "GORE-TEX", "Gore Tex", "Pertex", "Polartec", "POLARTEC",
    "PrimaLoft", "PRIMALOFT", "Thinsulate", "Outlast", "Schoeller",
    "Dyneema", "Cordura", "Ripstop", "ripstop",
    # Natural fibres
    "merino", "Merino", "wool", "Wool", "down", "Down", "cotton", "Cotton",
    "linen", "Linen", "hemp", "Hemp", "bamboo", "Bamboo",
    # Synthetics
    "nylon", "Nylon", "polyester", "Polyester", "spandex", "Spandex",
    "elastane", "Elastane", "lycra", "Lycra", "fleece", "Fleece",
    "softshell", "Softshell", "hardshell", "Hardshell",
    # Sustainability-flagged
    "recycled", "Recycled", "organic", "Organic", "bio-based",
    "TENCEL", "Tencel", "modal", "Modal",
]

FEATURE_KEYWORDS: list[str] = [
    "waterproof", "water-repellent", "water repellent", "DWR",
    "windproof", "wind-resistant", "wind resistant",
    "breathable", "breathability",
    "insulated", "insulation",
    "packable", "compressible", "lightweight", "ultralight", "ultra-light",
    "quick-dry", "quick dry", "moisture-wicking", "moisture wicking",
    "UV protection", "UPF", "sun protection",
    "reflective",
    "recycled", "sustainable", "bluesign", "Fair Trade",
    "PFAS-free", "PFC-free", "fluorocarbon-free",
    "stretch", "4-way stretch", "2-way stretch",
    "helmet-compatible", "hood",
    "articulated", "pre-shaped",
    "reinforced knees", "reinforced elbows",
    "zippered pockets", "chest pocket", "internal pockets",
    "removable hood", "detachable hood",
    "adjustable cuffs", "adjustable hem",
    "seam-sealed", "seam taped", "fully taped", "critically taped",
]


def extract_materials(text: str) -> str:
    found = []
    seen = set()
    for kw in MATERIAL_KEYWORDS:
        if kw.lower() in text.lower() and kw.lower() not in seen:
            found.append(kw)
            seen.add(kw.lower())
    return ", ".join(found)


def extract_features(text: str) -> str:
    found = []
    seen = set()
    for kw in FEATURE_KEYWORDS:
        if kw.lower() in text.lower() and kw.lower() not in seen:
            found.append(kw)
            seen.add(kw.lower())
    return ", ".join(found)


# ---------------------------------------------------------------------------
# Product type inference from tags / type strings
# ---------------------------------------------------------------------------

# Maps Shopify product_type or breadcrumb text → (product_type, product_subtype)
_TYPE_MAP: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"jacket|shell|anorak|windbreaker|parka", re.I), "Apparel", "Jacket"),
    (re.compile(r"trouser|pant|tight|short|bib", re.I), "Apparel", "Bottoms"),
    (re.compile(r"\bshirt\b|tee|t-shirt|jersey|baselayer|base.layer", re.I), "Apparel", "Top"),
    (re.compile(r"fleece|midlayer|mid.layer|insulated pullover", re.I), "Apparel", "Midlayer"),
    (re.compile(r"dress|skirt", re.I), "Apparel", "Dress/Skirt"),
    (re.compile(r"glove|mitten", re.I), "Accessories", "Gloves"),
    (re.compile(r"\bhat\b|beanie|cap|balaclava|buff", re.I), "Accessories", "Headwear"),
    (re.compile(r"sock", re.I), "Accessories", "Socks"),
    (re.compile(r"shoe|boot|sneaker|trail runner|approach", re.I), "Footwear", "Shoes"),
    (re.compile(r"sandal|flip.flop", re.I), "Footwear", "Sandals"),
    (re.compile(r"crampon|gaiter|crampon", re.I), "Footwear", "Accessories"),
    (re.compile(r"backpack|rucksack|daypack|pack\b", re.I), "Bags & Packs", "Backpack"),
    (re.compile(r"duffel|bag\b|tote", re.I), "Bags & Packs", "Bag"),
    (re.compile(r"tent|shelter|bivy|tarp", re.I), "Camping", "Shelter"),
    (re.compile(r"sleeping bag|quilt\b", re.I), "Camping", "Sleeping"),
    (re.compile(r"mat|pad\b|mattress", re.I), "Camping", "Sleep System"),
    (re.compile(r"stove|cooker|cookware|pot\b|pan\b", re.I), "Camping", "Cooking"),
    (re.compile(r"headlamp|lamp|lantern|light\b", re.I), "Equipment", "Lighting"),
    (re.compile(r"filter|water.*purif|purifier", re.I), "Equipment", "Water"),
    (re.compile(r"pole|trekking pole|ski pole", re.I), "Equipment", "Poles"),
    (re.compile(r"harness|belay|carabiner|rope|quickdraw|cam\b|nut\b|anchor", re.I), "Climbing", "Hardware"),
    (re.compile(r"helmet", re.I), "Safety", "Helmet"),
    (re.compile(r"ski\b|skis\b|ski boot", re.I), "Snow", "Ski"),
    (re.compile(r"snowboard|splitboard", re.I), "Snow", "Snowboard"),
    (re.compile(r"binding", re.I), "Snow", "Binding"),
    (re.compile(r"bike\b|bicycle|e-bike|ebike|mtb\b", re.I), "Cycling", "Bike"),
    (re.compile(r"helmet.*bike|bike.*helmet|cycling helmet", re.I), "Cycling", "Helmet"),
    (re.compile(r"cycling shoe|bike shoe", re.I), "Cycling", "Shoe"),
    (re.compile(r"jersey.*cycling|cycling.*jersey", re.I), "Cycling", "Apparel"),
    (re.compile(r"wheel|rim\b|tyre|tire", re.I), "Cycling", "Component"),
    (re.compile(r"compression sleeve|compression sock|compression tight", re.I), "Compression", "Compression"),
    (re.compile(r"sunglasses|goggle|eyewear", re.I), "Accessories", "Eyewear"),
    (re.compile(r"watch|gps|computer\b", re.I), "Electronics", "Wearable"),
    (re.compile(r"hydration|water bottle|flask|bladder", re.I), "Equipment", "Hydration"),
    (re.compile(r"nutrition|gel\b|bar\b|energy", re.I), "Nutrition", "Nutrition"),
]


def infer_type(text: str) -> tuple[str, str]:
    """Return (product_type, product_subtype) by matching text against _TYPE_MAP."""
    if not text:
        return ("Other", "")
    for pattern, ptype, psub in _TYPE_MAP:
        if pattern.search(text):
            return (ptype, psub)
    return ("Other", "")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_session = requests.Session()
_session.headers.update(HEADERS)


def get(url: str, **kwargs) -> requests.Response | None:
    try:
        resp = _session.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
        return resp
    except Exception as exc:
        print(f"    GET {url} failed: {exc}")
        return None


def normalise_domain(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith("http"):
        raw = "https://" + raw
    parsed = urlparse(raw)
    return parsed.netloc or raw


def base_url(domain_raw: str) -> str:
    d = domain_raw.strip()
    if not d.startswith("http"):
        d = "https://" + d
    return d.rstrip("/")


# ---------------------------------------------------------------------------
# Strategy 1: Shopify JSON API
# ---------------------------------------------------------------------------

def scrape_shopify(site_url: str, brand: str) -> list[dict]:
    products: list[dict] = []
    page = 1
    while True:
        url = f"{site_url}/collections/all/products.json?limit=250&page={page}"
        resp = get(url)
        if resp is None or resp.status_code != 200:
            break
        try:
            data = resp.json()
        except Exception:
            break
        items = data.get("products", [])
        if not items:
            break

        for p in items:
            title = p.get("title", "")
            ptype = p.get("product_type", "")
            tags = p.get("tags", [])
            desc_html = p.get("body_html", "") or ""
            desc = BeautifulSoup(desc_html, "html.parser").get_text(" ", strip=True)
            vendor = p.get("vendor") or brand
            variants = p.get("variants") or [{}]
            price = variants[0].get("price", "")

            type_text = " ".join([title, ptype] + (tags if isinstance(tags, list) else []))
            pt, ps = infer_type(type_text)
            if ps == "" and ptype:
                ps = ptype

            products.append({
                "product_type": pt,
                "product_subtype": ps,
                "price": price,
                "material": extract_materials(desc),
                "brand": vendor,
                "product_description": desc[:500],
                "feature": extract_features(desc),
                "original_site": site_url,
            })

        print(f"    [shopify] page {page}: {len(items)} products")
        page += 1
        time.sleep(CRAWL_DELAY)

    return products


def is_shopify(site_url: str) -> bool:
    resp = get(f"{site_url}/cart.json")
    if resp and resp.status_code == 200:
        try:
            resp.json()
            return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Strategy 2: Schema.org JSON-LD Product
# ---------------------------------------------------------------------------

def _parse_jsonld_product(data: dict, site_url: str, brand: str) -> dict | None:
    if data.get("@type") not in ("Product",):
        return None
    name = data.get("name", "")
    desc = data.get("description", "") or ""
    brand_obj = data.get("brand") or {}
    vendor = brand_obj.get("name", "") if isinstance(brand_obj, dict) else str(brand_obj)
    vendor = vendor or brand
    offers = data.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = offers.get("price", "") or offers.get("lowPrice", "")
    currency = offers.get("priceCurrency", "")
    price_str = f"{price} {currency}".strip() if price else ""

    categories = []
    for key in ("category", "breadcrumb"):
        val = data.get(key)
        if val:
            categories.append(str(val))

    type_text = " ".join([name] + categories)
    pt, ps = infer_type(type_text)

    return {
        "product_type": pt,
        "product_subtype": ps,
        "price": price_str,
        "material": extract_materials(desc),
        "brand": vendor,
        "product_description": desc[:500],
        "feature": extract_features(desc),
        "original_site": site_url,
    }


def _extract_jsonld_from_soup(soup: BeautifulSoup) -> list[dict]:
    results = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        if isinstance(data, list):
            results.extend(data)
        elif isinstance(data, dict):
            results.append(data)
            results.extend(data.get("@graph", []))
    return results


def scrape_jsonld_from_page(page_url: str, site_url: str, brand: str) -> list[dict]:
    resp = get(page_url)
    if resp is None or resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")
    nodes = _extract_jsonld_from_soup(soup)
    products = []
    for node in nodes:
        row = _parse_jsonld_product(node, site_url, brand)
        if row:
            products.append(row)
    return products


# ---------------------------------------------------------------------------
# Strategy 3: Generic HTML — find product listing pages then scrape each PDP
# ---------------------------------------------------------------------------

PRODUCT_LINK_PATTERNS = re.compile(
    r"/product[s]?/|/shop/|/collections?/|/artikel/|/neu/|/kategorie/",
    re.I,
)

PRICE_PATTERN = re.compile(
    r'(?:CHF|EUR?|USD?|\$|€|Fr\.?)\s*[\d,\']+(?:\.\d{1,2})?'
    r'|[\d,\']+(?:\.\d{1,2})?\s*(?:CHF|EUR?|USD?|\$|€)',
    re.I,
)


def _find_product_links(soup: BeautifulSoup, base: str) -> list[str]:
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full = urljoin(base, href)
        if PRODUCT_LINK_PATTERNS.search(full) and urlparse(full).netloc == urlparse(base).netloc:
            links.add(full)
    return list(links)[:40]  # cap to avoid infinite crawls


def scrape_generic(site_url: str, brand: str) -> list[dict]:
    resp = get(site_url)
    if resp is None or resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.content, "html.parser")

    # First try JSON-LD on the homepage (sometimes full product graph is here)
    nodes = _extract_jsonld_from_soup(soup)
    products = []
    for node in nodes:
        row = _parse_jsonld_product(node, site_url, brand)
        if row:
            products.append(row)

    if products:
        return products

    # Follow product category links and scrape each
    category_links = _find_product_links(soup, site_url)
    visited: set[str] = {site_url}

    for cat_url in category_links[:8]:
        if cat_url in visited:
            continue
        visited.add(cat_url)
        cat_resp = get(cat_url)
        if cat_resp is None or cat_resp.status_code != 200:
            continue
        cat_soup = BeautifulSoup(cat_resp.content, "html.parser")

        # Try JSON-LD on the category page
        for node in _extract_jsonld_from_soup(cat_soup):
            row = _parse_jsonld_product(node, site_url, brand)
            if row:
                products.append(row)

        time.sleep(CRAWL_DELAY)

    return products


# ---------------------------------------------------------------------------
# Per-site configuration overrides
# ---------------------------------------------------------------------------

# Some sites need a non-root collection URL or have a known scrape strategy.
# Keys are lowercased domain fragments.
SITE_OVERRIDES: dict[str, dict] = {
    "mammut.ch":          {"strategy": "jsonld", "category_paths": ["/en/c/new-arrivals", "/en/c/jackets"]},
    "mammut.com":         {"strategy": "jsonld", "category_paths": ["/en-ch/c/new-arrivals"]},
    "on-running.com":     {"strategy": "jsonld", "category_paths": ["/en-ch/mens", "/en-ch/womens"]},
    "scott-sports.com":   {"strategy": "jsonld", "category_paths": ["/en/sport/running", "/en/sport/cycling"]},
    "baechli-bergsport.ch": {"strategy": "jsonld", "category_paths": ["/neuheiten", "/angebote"]},
    "intersport.ch":      {"strategy": "jsonld", "category_paths": ["/de/c/sale", "/de/c/neuheiten"]},
    "ochsner-sport.ch":   {"strategy": "jsonld", "category_paths": ["/de/c/neuheiten"]},
    "ochsnersport.ch":    {"strategy": "jsonld", "category_paths": ["/de/c/neuheiten"]},
    # decathlon.ch is Cloudflare-blocked; decathlon.com is Shopify and works fine
    "decathlon.ch":       {"strategy": "shopify_redirect", "redirect_url": "https://www.decathlon.com"},
    "eu.patagonia.com":   {"strategy": "jsonld", "category_paths": ["/ch/en/shop/mens-jackets", "/ch/en/shop/womens-jackets"]},
    "burton.com":         {"strategy": "jsonld", "category_paths": ["/us/en/c/snowboards", "/us/en/c/outerwear"]},
    "thenorthface-store.ch": {"strategy": "jsonld", "category_paths": ["/de/c/neuheiten"]},
    "keller-sports.ch":   {"strategy": "jsonld", "category_paths": ["/running", "/skiing"]},
    "transa.ch":          {"strategy": "jsonld", "category_paths": ["/de/neuheiten"]},
    "athleticum.ch":      {"strategy": "jsonld", "category_paths": ["/de/neuheiten"]},
}

KNOWN_SHOPIFY: set[str] = {
    "factionskis.com",
    "compressport.com",
    "ridestore.com",
    "fwapparel.com",
    "dahusports.com",
    "snowlife.ch",
    "mellos1986.com",
    "napapijri.com",
    "assos.com",
    "stoeckli.ch",
    "hajk.ch",
}


def scrape_site(domain_raw: str, company: str) -> list[dict]:
    url = base_url(domain_raw)
    domain = normalise_domain(domain_raw)
    brand = company.split("/")[0].strip()

    print(f"\n→ {domain} ({brand})")

    # Skip non-retail informational sites
    skip_domains = {"wfsgi.org", "europeanoutdoorgroup.com", "intercycle.com", "tds-rad.ch"}
    if any(s in domain for s in skip_domains):
        print("  Skipping (non-retail)")
        return []

    # Check known Shopify stores first
    if any(k in domain for k in KNOWN_SHOPIFY):
        print("  Strategy: Shopify JSON")
        products = scrape_shopify(url, brand)
    else:
        # Check site overrides
        override = None
        for key, cfg in SITE_OVERRIDES.items():
            if key in domain:
                override = cfg
                break

        if override:
            if override.get("strategy") == "shopify_redirect":
                redirect = override["redirect_url"]
                print(f"  Strategy: Shopify JSON (redirect → {redirect})")
                products = scrape_shopify(redirect, brand)
            else:
                print("  Strategy: JSON-LD (category paths)")
                products = []
                for path in override.get("category_paths", []):
                    page_url = url + path
                    rows = scrape_jsonld_from_page(page_url, url, brand)
                    products.extend(rows)
                    print(f"    {path}: {len(rows)} products")
                    time.sleep(CRAWL_DELAY)
        elif is_shopify(url):
            print("  Strategy: Shopify JSON (detected)")
            products = scrape_shopify(url, brand)
        else:
            print("  Strategy: generic HTML / JSON-LD crawl")
            products = scrape_generic(url, brand)

    for row in products:
        row["competitor_name"] = company

    return products


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_sites() -> list[tuple[str, str]]:
    with open(SITES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [(row["Company/Context"].strip(), row["Website Link"].strip()) for row in reader]


def main() -> None:
    sites = load_sites()
    print(f"Loaded {len(sites)} sites from {SITES_CSV}\n")

    all_products: list[dict] = []

    for company, domain in sites:
        try:
            rows = scrape_site(domain, company)
        except Exception as exc:
            print(f"  ERROR on {domain}: {exc}")
            rows = []
        all_products.extend(rows)
        print(f"  Total so far: {len(all_products)} products")

    print(f"\n=== Done. {len(all_products)} products collected. Writing to {OUTPUT_CSV} ===")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_products)

    print(f"Written to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
