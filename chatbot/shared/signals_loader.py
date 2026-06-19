import csv
import os

SIGNALS_PATH = os.path.join(os.path.dirname(__file__), "../../examples/signals.csv")


def load_signals(path: str = SIGNALS_PATH) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def format_signals_for_prompt(signals: list[dict]) -> str:
    if not signals:
        return "No signal data available."
    lines = []
    for s in signals:
        lines.append(
            f"- [{s.get('signal_score', '?')} confidence: {s.get('confidence', '?')}] "
            f"{s.get('signal_name', 'Unknown')} | {s.get('brand', '')} | "
            f"{s.get('market', '')} | {s.get('source', '')} | {s.get('url', '')}"
        )
    return "\n".join(lines)
