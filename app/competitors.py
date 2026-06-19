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
GAP_HINTS_PATH = os.path.join(PROJECT_ROOT, "competitor_gap_hints.json")

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
}

COMPETITOR_COLUMNS = [
    "source", "market", "keyword", "signal_name", "signal_type",
    "product_name", "brand", "price", "rank", "url", "observed_at", "is_client",
]


def resolve_competitors(config: dict) -> list[tuple[str, dict, bool]]:
    """Return list of (name, retailer_cfg, is_client)."""
    client = (config.get("client_company") or "").strip().lower()
    names = config.get("competitors") or list(RETAILER_REGISTRY.keys())
    resolved: list[tuple[str, dict, bool]] = []
    for name in names:
        key = name.strip().lower().replace(" ", "_")
        if key not in RETAILER_REGISTRY:
            for reg_key in RETAILER_REGISTRY:
                if reg_key in key or key in reg_key:
                    key = reg_key
                    break
            else:
                continue
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
    products = scrape_competitor_products(config)
    hints = compute_gap_hints(products)
    write_competitor_products(products)
    write_gap_hints(hints)
    config["competitors"] = [name for name, _, _ in resolve_competitors(config)]
    return products, hints
