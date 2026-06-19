import csv
import os

SCORED_SIGNALS_PATH = os.path.join(os.path.dirname(__file__), "../../scored_opportunities.csv")
EXAMPLE_SIGNALS_PATH = os.path.join(os.path.dirname(__file__), "../../examples/signals.csv")

# Caps how many rows go into the system prompt -- the prompt is resent on
# every chat turn, so an uncapped 190+ row dump would burn API budget fast.
TOP_N_SIGNALS = 40


def _resolve_path(path: str | None) -> str:
    if path:
        return path
    if os.path.exists(SCORED_SIGNALS_PATH):
        return SCORED_SIGNALS_PATH
    return EXAMPLE_SIGNALS_PATH


def load_signals(path: str | None = None, top_n: int = TOP_N_SIGNALS) -> list[dict]:
    resolved_path = _resolve_path(path)
    with open(resolved_path, newline="", encoding="utf-8") as f:
        signals = list(csv.DictReader(f))

    def score(s: dict) -> float:
        try:
            return float(s.get("signal_score", 0))
        except (TypeError, ValueError):
            return 0.0

    signals.sort(key=score, reverse=True)
    return signals[:top_n]


def format_signals_for_prompt(signals: list[dict]) -> str:
    if not signals:
        return "No signal data available."
    lines = []
    for s in signals:
        lines.append(
            f"- [score {s.get('signal_score', '?')}, confidence: {s.get('confidence', '?')}] "
            f"{s.get('signal_name', 'Unknown')} | brand: {s.get('brand', '')} | "
            f"market: {s.get('market', '')} | source: {s.get('source', '')} | {s.get('url', '')}"
            + (f"\n  notes: {s['notes']}" if s.get("notes") else "")
        )
    return "\n".join(lines)
