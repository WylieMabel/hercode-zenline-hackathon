"""
Pipeline step orchestration.

Each function returns (success: bool, message: str, data: any).
Called by streamlit_app.py inside st.status blocks.
"""

import json
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # app/

import scoring as _scoring
import compiler as _compiler

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
MODEL = "claude-sonnet-4-6"

CONFIG_PROMPT = """\
You are configuring a retail signal detection pipeline for an outdoor retailer.

Inputs:
- Company location: {location}
- Market / category: {market}
- Price range: {price_range}

Return a JSON object with exactly these keys:
  "keywords"          list of 4–6 specific search keywords to monitor (trend names, product types, etc.)
  "markets"           list of markets to scan — always include CH and DACH
  "signal_types"      list of signal types: social, search, competitor, weather, api
  "price_filter_note" string describing the price filter, or "no filter"
  "summary"           one sentence describing the search focus

Return ONLY valid JSON, no markdown.
"""


def generate_config(
    location: str,
    market: str,
    price_min=None,
    price_max=None,
) -> dict:
    price_range = "no filter"
    if price_min or price_max:
        lo = f"CHF {price_min}" if price_min else "any"
        hi = f"CHF {price_max}" if price_max else "any"
        price_range = f"{lo} – {hi}"

    fallback = {
        "keywords": ["gorpcore", "trail running packs", "fastpacking", "ultralight hiking", "alpine crossover"],
        "markets": ["CH", "DACH", "US", "DE"],
        "signal_types": ["social", "search", "competitor", "weather", "api"],
        "price_filter_note": price_range,
        "summary": f"Scanning {market} signals for {location} with price filter: {price_range}.",
    }

    if not CLAUDE_API_KEY:
        return fallback

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        prompt = CONFIG_PROMPT.format(location=location, market=market, price_range=price_range)
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception:
        return fallback


def run_scraper() -> tuple[bool, str]:
    script = os.path.join(PROJECT_ROOT, "scraper_pipeline.py")
    if not os.path.exists(script):
        return False, "scraper_pipeline.py not found in project root."
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=PROJECT_ROOT,
        )
        out = (result.stdout or "")[-1200:]
        if result.returncode == 0:
            return True, out or "Scraper completed."
        err = (result.stderr or "")[-400:]
        return False, f"Scraper exited with code {result.returncode}.\n{err}"
    except subprocess.TimeoutExpired:
        return False, "Scraper timed out after 180s."
    except Exception as exc:
        return False, str(exc)


def run_scoring() -> tuple[bool, str, list[dict]]:
    raw_path = os.path.join(PROJECT_ROOT, "raw_signals.csv")
    scored_path = os.path.join(PROJECT_ROOT, "scored_opportunities.csv")

    if not os.path.exists(raw_path):
        return False, "raw_signals.csv not found — run the scraper first.", []

    try:
        rows = _scoring.score_signals(raw_path, scored_path)
        return True, f"Scored {len(rows)} signals → scored_opportunities.csv", rows
    except Exception as exc:
        return False, str(exc), []


def run_compiler(scored_rows: list[dict], sales_context: str = "") -> tuple[bool, str, list[dict]]:
    try:
        opps = _compiler.compile_opportunities(scored_rows, sales_context)
        return True, f"Compiled {len(opps)} opportunities.", opps
    except Exception as exc:
        return False, str(exc), []
