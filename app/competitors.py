"""Step 1: competitor discovery and product scraping."""

from __future__ import annotations

import csv
import json
import os
import re
from typing import Any

import requests

from geo import resolve_region
from pipeline_config import OUTDOOR_SCRAPER_PRESET, PROJECT_ROOT
from signals_common import NA, infer_product_category, make_row, now_iso

COMPETITOR_PRODUCTS_PATH = os.path.join(PROJECT_ROOT, "competitor_products.csv")
BUNDLED_COMPETITOR_PRODUCTS_PATH = os.path.join(PROJECT_ROOT, "competitors", "competitor_products.csv")
GAP_HINTS_PATH = os.path.join(PROJECT_ROOT, "competitor_gap_hints.json")

DECATHLON_HOUSE_BRANDS = {
    "quechua", "simond", "kiprun", "wedze", "forclaz", "tribord",
    "oxelo", "kalenji", "domyos", "decathlon",
}

BUNDLE_TYPE_TO_KEYWORD = {
    "Apparel": "apparel",
    "Footwear": "footwear",
    "Bags & Packs": "backpack",
    "Camping": "camping",
    "Climbing": "climbing",
    "Accessories": "accessories",
    "Equipment": "accessories",
    "Snow": "ski",
    "Cycling": "accessories",
    "Compression": "apparel",
    "Electronics": "accessories",
    "Nutrition": "accessories",
    "Safety": "accessories",
    "Other": "general",
}

HEADERS = {"User-Agent": "zenline-trend-scout/0.1 (hackathon prototype)"}
REQUEST_TIMEOUT = 10

# Registry of known retailers for Swiss outdoor vertical
RETAILER_REGISTRY: dict[str, dict] = {
    "bergfreunde": {
        "url": "https://www.bergfreunde.de/neuheiten/",
        "market": "DE/CH",
        "parser": "css",
        "item_sel": ".produkt",
        "title_sel": ".titel",
        "brand_sel": ".marke",
        "price_sel": ".preis",
        "fallback_products": [
            {"title": "Ultraleicht Laufrucksack 12L", "brand": "Salomon", "price": "79,95 EUR", "url": "https://www.bergfreunde.de/salomon-laufrucksack-12l/"},
            {"title": "Fastpacking Zelt 1-Personen", "brand": "MSR", "price": "349,00 EUR", "url": "https://www.bergfreunde.de/msr-fastpacking-zelt/"},
        ],
    },
    "rei": {
        "url": "https://www.rei.com/c/new-and-popular",
        "market": "US",
        "parser": "css",
        "item_sel": ".product",
        "title_sel": ".title",
        "brand_sel": ".brand",
        "price_sel": ".price",
        "fallback_products": [
            {"title": "Trailmade Trail Running Vest", "brand": "REI Co-op", "price": "$59.95", "url": "https://www.rei.com/product/trailmade-trail-running-vest"},
            {"title": "Speedgoat 6 Trail Running Shoe", "brand": "HOKA", "price": "$155.00", "url": "https://www.rei.com/product/hoka-speedgoat-6"},
        ],
    },
    "black_diamond": {
        "parser": "shopify_json",
        "base_url": "https://blackdiamondequipment.com",
        "market": "US",
        "collections": ["new-equipment", "new-mens-apparel"],
        "fallback_products": [
            {"title": "Stella-R Headlamp", "brand": "Black Diamond", "price": "54.95", "url": "https://blackdiamondequipment.com/products/stella-r-rechargeable-headlamp"},
        ],
    },
    "decathlon": {
        "parser": "shopify_json",
        "base_url": "https://www.decathlon.com",
        "market": "US",
        "collections": ["new-arrivals"],
        "is_client_default": True,
        "fallback_products": [
            {"title": "10L Laptop Backpack", "brand": "Decathlon", "price": "39.99", "url": "https://www.decathlon.com/products/10l-laptop-backpack"},
            {"title": "2 SECONDS EASY Fresh and Black - 3 Person", "brand": "Quechua", "price": "359.00", "url": "https://www.decathlon.com/products/2-seconds-easy-fresh-and-black-3-person"},
        ],
    },
    "columbia": {
        "url": "https://www.columbia.com/new-arrivals/",
        "market": "US",
        "parser": "jsonld",
        "default_brand": "Columbia",
        "fallback_products": [
            {"title": "Women's AmazeStretch Jacket", "brand": "Columbia", "price": "90.00 USD", "url": "https://www.columbia.com/p/womens-amazestretch-jacket-2154741.html"},
        ],
    },
    "patagonia": {
        "parser": "shopify_json",
        "base_url": "https://www.patagonia.com",
        "market": "US",
        "collections": ["new-arrivals", "web-specials"],
        "fallback_products": [
            {"title": "Nano Puff Jacket", "brand": "Patagonia", "price": "249.00", "url": "https://www.patagonia.com/product/mens-nano-puff-jacket/84212.html"},
            {"title": "Terravia Pack 18L", "brand": "Patagonia", "price": "129.00", "url": "https://www.patagonia.com/product/terravia-pack-18l/49000.html"},
            {"title": "Capilene Cool Daily Hoody", "brand": "Patagonia", "price": "45.00", "url": "https://www.patagonia.com/product/capilene-cool-daily-hoody/45215.html"},
        ],
    },
}

# Human labels for UI / docs
RETAILER_LABELS = {k: k.replace("_", " ").title() for k in RETAILER_REGISTRY}

COMPETITOR_COLUMNS = [
    "source", "market", "keyword", "signal_name", "signal_type",
    "product_name", "brand", "price", "rank", "url", "observed_at", "is_client",
    "material", "feature", "product_type", "product_subtype", "competitor_name",
]


def list_registry_slugs() -> list[str]:
    return sorted(RETAILER_REGISTRY.keys())


def list_bundled_retailers(path: str = BUNDLED_COMPETITOR_PRODUCTS_PATH) -> list[str]:
    """Unique retailer names from the offline competitor catalog."""
    if not os.path.exists(path):
        return []
    names: set[str] = set()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("competitor_name") or "").strip()
            if name:
                names.add(name)
    return sorted(names)


def _slugify_retailer(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "competitor"


def _market_from_site(url: str) -> str:
    host = (url or "").lower()
    if ".ch" in host:
        return "CH"
    if ".de" in host or ".at" in host:
        return "DE"
    if ".fr" in host:
        return "FR"
    if ".com" in host or ".us" in host:
        return "US"
    return "GLOBAL"


def _product_name_from_bundle(row: dict) -> str:
    desc = (row.get("product_description") or "").strip()
    if desc:
        name = desc.split(".")[0].strip()
        if len(name) > 120:
            return name[:117] + "..."
        return name
    parts = [row.get("brand"), row.get("product_subtype"), row.get("product_type")]
    return " ".join(p for p in parts if p) or "Unknown product"


def _keyword_from_bundle(row: dict) -> str:
    product_type = (row.get("product_type") or "").strip()
    if product_type in BUNDLE_TYPE_TO_KEYWORD:
        return BUNDLE_TYPE_TO_KEYWORD[product_type]
    subtype = (row.get("product_subtype") or "").strip()
    return infer_product_category(f"{subtype} {row.get('product_description', '')}", row.get("brand", ""))


def _is_client_product(row: dict, client: str) -> bool:
    if not client:
        return False
    client_l = client.lower()
    for field in ("competitor_name", "brand", "original_site"):
        val = (row.get(field) or "").lower()
        if client_l in val or val in client_l:
            return True
    if "decathlon" in client_l:
        brand = (row.get("brand") or "").lower()
        site = (row.get("original_site") or "").lower()
        if brand in DECATHLON_HOUSE_BRANDS or "decathlon" in site:
            return True
    return False


def _bundled_row_to_pipeline(row: dict, client: str) -> dict:
    competitor_name = (row.get("competitor_name") or "Unknown").strip()
    title = _product_name_from_bundle(row)
    brand = (row.get("brand") or NA).strip() or NA
    site = (row.get("original_site") or NA).strip() or NA
    is_client = _is_client_product(row, client)
    source = _slugify_retailer(competitor_name)
    if is_client:
        source = f"{source}_client"

    pipeline_row = _make_product_row(
        source=source,
        market=_market_from_site(site),
        title=title,
        brand=brand,
        price=(row.get("price") or NA).strip() or NA,
        url=site,
        is_client=is_client,
    )
    pipeline_row["keyword"] = _keyword_from_bundle(row)
    pipeline_row["material"] = (row.get("material") or "").strip()
    pipeline_row["feature"] = (row.get("feature") or "").strip()
    pipeline_row["product_type"] = (row.get("product_type") or "").strip()
    pipeline_row["product_subtype"] = (row.get("product_subtype") or "").strip()
    pipeline_row["competitor_name"] = competitor_name
    if pipeline_row["material"] or pipeline_row["feature"]:
        extras = []
        if pipeline_row["material"]:
            extras.append(f"material: {pipeline_row['material']}")
        if pipeline_row["feature"]:
            extras.append(f"feature: {pipeline_row['feature']}")
        pipeline_row["signal_name"] = f"{pipeline_row['signal_name']} ({'; '.join(extras)})"
    return pipeline_row


def load_bundled_competitor_products(config: dict) -> list[dict]:
    """Load pre-scraped catalog from competitors/competitor_products.csv."""
    path = BUNDLED_COMPETITOR_PRODUCTS_PATH
    if not os.path.exists(path):
        return []

    client = (config.get("client_company") or "").strip()
    seen: set[tuple] = set()
    products: list[dict] = []

    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (
                row.get("competitor_name", ""),
                row.get("brand", ""),
                row.get("product_description", ""),
                row.get("price", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            products.append(_bundled_row_to_pipeline(row, client))

    retailers = sorted({p.get("competitor_name", "") for p in products if p.get("competitor_name")})
    config["competitors"] = retailers
    config["competitor_data_source"] = "bundled"
    config["competitors_skipped"] = config.get("competitors_skipped") or []
    print(
        f"  [competitors] loaded {len(products)} products from bundled catalog "
        f"({len(retailers)} retailers)."
    )
    return products


def _match_registry_slug(name: str) -> str | None:
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    if key in RETAILER_REGISTRY:
        return key
    for reg_key in RETAILER_REGISTRY:
        if reg_key in key or key in reg_key:
            return reg_key
    return None


def normalize_competitor_slugs(names: list[str]) -> tuple[list[str], list[str]]:
    """Map requested names to registry slugs. Returns (matched, skipped)."""
    matched: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()
    for name in names:
        slug = _match_registry_slug(name)
        if slug and slug not in seen:
            matched.append(slug)
            seen.add(slug)
        elif not slug:
            skipped.append(name)
    return matched, skipped


def resolve_competitors(config: dict) -> list[tuple[str, dict, bool]]:
    """Return list of (name, retailer_cfg, is_client)."""
    client = (config.get("client_company") or "").strip().lower()
    requested = config.get("competitors") or list(RETAILER_REGISTRY.keys())
    matched, skipped = normalize_competitor_slugs(requested)
    config["competitors_requested"] = requested
    config["competitors_skipped"] = skipped
    names = matched or list(RETAILER_REGISTRY.keys())[:5]
    config["competitors"] = names
    if skipped:
        print(f"  [competitors] skipped unregistered retailers: {', '.join(skipped)}")
    resolved: list[tuple[str, dict, bool]] = []
    for key in names:
        cfg = RETAILER_REGISTRY[key]
        is_client = bool(client and (client in key or client in cfg.get("base_url", "")))
        if cfg.get("is_client_default") and client and "decathlon" in client:
            is_client = True
        resolved.append((key, cfg, is_client))
    if client and not any(c[2] for c in resolved):
        for key, cfg in RETAILER_REGISTRY.items():
            if client in key:
                resolved.append((key, cfg, True))
                break
    return resolved


def _make_product_row(
    source: str,
    market: str,
    title: str,
    brand: str,
    price: str,
    url: str,
    is_client: bool = False,
) -> dict:
    category = infer_product_category(title, brand)
    row = make_row(
        source=source,
        market=market,
        keyword=category,
        signal_name=f"New arrival: {title}",
        signal_type="competitor",
        product_name=title,
        brand=brand,
        price=price,
        url=url,
    )
    row["is_client"] = "true" if is_client else "false"
    return row


def _parse_retailer_css(html: str, cfg: dict, source: str, is_client: bool) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for item in soup.select(cfg["item_sel"]):
        title_el = item.select_one(cfg["title_sel"])
        brand_el = item.select_one(cfg["brand_sel"])
        price_el = item.select_one(cfg["price_sel"])
        link_el = item.find("a", href=True)
        title = title_el.get_text(strip=True) if title_el else NA
        if title == NA:
            continue
        rows.append(_make_product_row(
            source=source,
            market=cfg["market"],
            title=title,
            brand=brand_el.get_text(strip=True) if brand_el else NA,
            price=price_el.get_text(strip=True) if price_el else NA,
            url=link_el["href"] if link_el else NA,
            is_client=is_client,
        ))
    return rows


def _parse_retailer_jsonld(html: str, cfg: dict, source: str, is_client: bool) -> list[dict]:
    rows: list[dict] = []
    scripts = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    for script in scripts:
        try:
            data = json.loads(script)
        except json.JSONDecodeError:
            continue
        if not (isinstance(data, dict) and data.get("@type") == "ItemList"):
            continue
        for element in data.get("itemListElement", []):
            product = element.get("item", {})
            if product.get("@type") != "Product":
                continue
            title = product.get("name")
            if not title:
                continue
            offer = product.get("offers", {})
            price = offer.get("price")
            currency = offer.get("priceCurrency", "")
            rows.append(_make_product_row(
                source=source,
                market=cfg["market"],
                title=title,
                brand=cfg.get("default_brand", NA),
                price=f"{price} {currency}".strip() if price else NA,
                url=product.get("url", NA),
                is_client=is_client,
            ))
    return rows


def _fetch_shopify_products(name: str, cfg: dict, is_client: bool) -> list[dict]:
    rows: list[dict] = []
    for collection in cfg["collections"]:
        url = f"{cfg['base_url']}/collections/{collection}/products.json?limit=20"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            for product in resp.json().get("products", []):
                title = product.get("title")
                if not title:
                    continue
                variant = (product.get("variants") or [{}])[0]
                handle = product.get("handle")
                rows.append(_make_product_row(
                    source=name,
                    market=cfg["market"],
                    title=title,
                    brand=product.get("vendor", NA),
                    price=variant.get("price", NA),
                    url=f"{cfg['base_url']}/products/{handle}" if handle else NA,
                    is_client=is_client,
                ))
            print(f"  [competitors/{name}] collection '{collection}': live products.")
        except Exception as exc:
            print(f"  [competitors/{name}] {collection} failed ({exc}).")
    return rows


PARSERS = {"css": _parse_retailer_css, "jsonld": _parse_retailer_jsonld}


def scrape_competitor_products(config: dict) -> list[dict]:
    rows: list[dict] = []
    for name, cfg, is_client in resolve_competitors(config):
        if cfg.get("parser") == "shopify_json":
            parsed = _fetch_shopify_products(name, cfg, is_client)
            if parsed:
                rows.extend(parsed)
                continue
        elif cfg.get("parser") in PARSERS:
            try:
                resp = requests.get(cfg["url"], headers=HEADERS, timeout=REQUEST_TIMEOUT)
                if resp.status_code in (403, 429):
                    raise RuntimeError(f"blocked status={resp.status_code}")
                resp.raise_for_status()
                parsed = PARSERS[cfg["parser"]](resp.text, cfg, name, is_client)
                if parsed:
                    rows.extend(parsed)
                    continue
            except Exception as exc:
                print(f"  [competitors/{name}] scrape failed ({exc}); fallback.")
        fallback = [
            _make_product_row(
                source=f"{name}_fallback_mock",
                market=cfg["market"],
                title=p["title"],
                brand=p["brand"],
                price=p["price"],
                url=p["url"],
                is_client=is_client,
            )
            for p in cfg.get("fallback_products", [])
        ]
        rows.extend(fallback)
    return rows


def compute_gap_hints(products: list[dict]) -> dict:
    client_brands: set[str] = set()
    client_categories: set[str] = set()
    competitor_brands: dict[str, int] = {}
    competitor_categories: dict[str, int] = {}

    for p in products:
        brand = (p.get("brand") or "").strip().lower()
        cat = (p.get("keyword") or "general").strip().lower()
        is_client = p.get("is_client") == "true"
        if is_client:
            if brand and brand != "n/a":
                client_brands.add(brand)
            client_categories.add(cat)
        else:
            if brand and brand != "n/a":
                competitor_brands[brand] = competitor_brands.get(brand, 0) + 1
            competitor_categories[cat] = competitor_categories.get(cat, 0) + 1

    gap_brands = [b for b, n in competitor_brands.items() if n >= 2 and b not in client_brands]
    gap_categories = [c for c, n in competitor_categories.items() if n >= 3 and c not in client_categories]

    return {
        "gap_brands": gap_brands[:15],
        "gap_categories": gap_categories[:10],
        "client_brand_count": len(client_brands),
        "competitor_brand_count": len(competitor_brands),
        "summary": (
            f"{len(gap_brands)} brands and {len(gap_categories)} categories "
            f"appear at competitors but not in client assortment scrape."
        ),
    }


def write_competitor_products(products: list[dict], path: str = COMPETITOR_PRODUCTS_PATH) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COMPETITOR_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(products)


def write_gap_hints(hints: dict, path: str = GAP_HINTS_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hints, f, indent=2)


def find_competitors(config: dict) -> tuple[list[dict], dict]:
    use_live = config.get("competitor_data_source") == "live"
    products: list[dict] = []

    if not use_live:
        products = load_bundled_competitor_products(config)

    if not products:
        if not use_live:
            print("  [competitors] bundled catalog missing or empty; falling back to live scrape.")
        products = scrape_competitor_products(config)
        config["competitor_data_source"] = "live"

    hints = compute_gap_hints(products)
    write_competitor_products(products)
    write_gap_hints(hints)
    if config.get("competitor_data_source") != "bundled":
        config["competitors"] = [name for name, _, _ in resolve_competitors(config)]
    return products, hints
