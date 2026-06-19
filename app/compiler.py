"""
LLM compilation step: top scored signals → ranked business opportunities.

Sends the top N scored signals to Claude and asks it to synthesize them into
3-5 structured opportunity recommendations. Returns a list of dicts.
Falls back to placeholder objects when CLAUDE_API_KEY is not set.
"""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
MODEL = "claude-sonnet-4-6"
MAX_SIGNALS = 20

_client = None
if CLAUDE_API_KEY:
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
    except ImportError:
        pass

COMPILE_PROMPT = """\
You are a retail intelligence analyst for a Swiss outdoor retailer (DACH market).

Below are the top scored market signals from a multi-source signal detection pipeline.
Each line is one signal with its score, confidence, source, and URL.

Signals with signal_type "search_geo" are Google Trends market-comparison rows. Their rank
is the number of weeks that market's trend onset preceded Switzerland's. A positive rank means
that country is a leading indicator for Swiss demand — the higher the number, the more runway
the retailer has to act. Treat these as forward-looking evidence and reference them when
populating "lead_markets" and "why_now".

{signals}

{sales_block}

Identify the top 3–5 distinct business opportunities visible in this data.
For EACH opportunity return a JSON object with exactly these keys:

  "rank"            integer, 1 = highest priority
  "opportunity"     short name, 4–8 words
  "description"     one clear sentence describing what the opportunity is
  "sources"         list of objects, each with "name" (source identifier) and "url" (direct link) —
                    pull these from the signal lines above; include every distinct source that supports this opportunity
  "markets"         list of markets / geographies where this signal has been observed (e.g. ["US", "DE", "CH"])
  "lead_markets"    list of countries where this trend rose BEFORE Switzerland (from search_geo signals), e.g. ["JP", "US"] — empty list if none observed
  "why_now"         one sentence explaining what is driving this trend right now (cultural shift, technology, weather, regulation, etc.) — if lead_markets is non-empty, reference which country the signal came from first and how far ahead it was
  "signal_strength" one sentence summarising how strong and consistent the evidence is across sources
  "limitations"     one sentence on what evidence is missing, which sources are mock/estimated, or where the data is thin
  "transferability" one sentence: why this works (or doesn't) in Switzerland / DACH specifically
  "action"          specific recommended next action for the buyer team (e.g. "Request samples from X brand and run 4-week test buy in Hiking Footwear")
  "confidence"      "low" | "medium" | "high"
  "risks"           one sentence on the key commercial or timing risk

Return ONLY a valid JSON array with no markdown fences, no commentary.
"""


def compile_opportunities(
    signals: list[dict],
    sales_context: str = "",
) -> list[dict]:
    if not signals:
        return _placeholders()

    signal_lines = "\n".join(
        f"- [score {s.get('signal_score', '?')}, {s.get('confidence', '?')} confidence] "
        f"{s.get('signal_name', '')} | brand: {s.get('brand', 'N/A')} | "
        f"market: {s.get('market', 'N/A')} | source: {s.get('source', 'N/A')} | {s.get('url', '')}"
        for s in sorted(signals, key=lambda x: float(x.get("signal_score", 0)), reverse=True)[:MAX_SIGNALS]
    )

    sales_block = f"Customer data context (use to ground transferability):\n{sales_context}" if sales_context else ""
    prompt = COMPILE_PROMPT.format(signals=signal_lines, sales_block=sales_block)

    if not _client:
        return _placeholders()

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception as exc:
        return [_error_opp(str(exc))]


def _error_opp(msg: str) -> dict:
    return {
        "rank": 1,
        "opportunity": "Compilation error",
        "description": msg,
        "sources": [],
        "markets": [],
        "why_now": "",
        "signal_strength": "",
        "limitations": "LLM compilation failed.",
        "transferability": "",
        "action": "Check CLAUDE_API_KEY and retry.",
        "confidence": "low",
        "risks": "",
    }


def _placeholders() -> list[dict]:
    return [
        {
            "rank": 1,
            "opportunity": "Set CLAUDE_API_KEY to compile",
            "description": "Signal data was loaded and scored successfully. Set CLAUDE_API_KEY to run LLM compilation.",
            "sources": [],
            "markets": [],
            "why_now": "N/A — placeholder.",
            "signal_strength": "Scoring complete; signals available in scored_opportunities.csv.",
            "limitations": "LLM compilation not run — no API key configured.",
            "transferability": "N/A — placeholder response.",
            "action": "Export CLAUDE_API_KEY=your_key and rerun the pipeline.",
            "confidence": "low",
            "risks": "No LLM key configured.",
        }
    ]
