"""Shared signal row helpers used across pipeline modules."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from typing import Any

SIGNAL_COLUMNS = [
    "source", "market", "keyword", "signal_name", "signal_type",
    "product_name", "brand", "price", "rank", "url", "observed_at",
]

NA = "N/A"

CATEGORY_TRIGGERS = {
    "backpack": ["backpack", "rucksack", "daypack", "pack", "vest"],
    "footwear": ["shoe", "boot", "sneaker", "sandal"],
    "apparel": ["jacket", "hoodie", "fleece", "softshell", "pant", "shorts", "dress"],
    "climbing": ["climbing", "carabiner", "harness", "rope", "chalk"],
    "camping": ["tent", "sleeping bag", "sleeping pad"],
    "accessories": ["headlamp", "gloves", "bottle", "cord"],
    "ski": ["ski", "snowboard", "binding"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_row(**kwargs: Any) -> dict:
    row = {col: NA for col in SIGNAL_COLUMNS}
    row.update(kwargs)
    row["observed_at"] = kwargs.get("observed_at", now_iso())
    for col in SIGNAL_COLUMNS:
        if row.get(col) in (None, ""):
            row[col] = NA
    return row


def infer_product_category(title: str, brand: str = "") -> str:
    text = f"{title} {brand}".lower()
    best_cat, best_hits = "general", 0
    for cat, triggers in CATEGORY_TRIGGERS.items():
        hits = sum(1 for t in triggers if t in text)
        if hits > best_hits:
            best_cat, best_hits = cat, hits
    return best_cat


def dedupe_rows(rows: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for row in rows:
        key = (row.get("source"), row.get("keyword"), row.get("product_name"), row.get("url"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def write_signals_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SIGNAL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_signals_csv(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def extract_product_tokens(titles: list[str], limit: int = 8) -> list[str]:
    """Pull recurring product-type phrases from competitor titles."""
    counts: dict[str, int] = {}
    stop = {"the", "and", "for", "with", "men", "women", "new", "pro", "lite", "ultra"}
    for title in titles:
        words = re.findall(r"[a-zA-Z0-9]+", title.lower())
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if words[i] in stop or words[i + 1] in stop:
                continue
            counts[bigram] = counts.get(bigram, 0) + 1
        for w in words:
            if len(w) > 4 and w not in stop:
                counts[w] = counts.get(w, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    return [term for term, _ in ranked[:limit]]
