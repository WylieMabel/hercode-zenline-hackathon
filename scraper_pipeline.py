"""
Retail trend signal ingestion pipeline (CLI wrapper).

Delegates to app modules. Prefer pipeline_runner.run_pipeline() from Streamlit.

Run: python3 scraper_pipeline.py --config pipeline_config.json
"""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "app"))

from pipeline_config import CONFIG_PATH, base_config, load_config, save_config
from pipeline_runner import run_signal_collection


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=CONFIG_PATH, help="Path to pipeline_config.json")
    parser.add_argument("--query", default=None, help="Legacy: build default config from query string")
    parser.add_argument("--preset", default=None, help="Legacy preset name (ignored if --config exists)")
    args = parser.parse_args()

    if os.path.exists(args.config):
        config = load_config(args.config)
    else:
        query = args.query or args.preset or "swiss outdoor"
        config = base_config(location="Switzerland", market=query)
        save_config(config, args.config)
        print(f"  [config] wrote default config to {args.config}")

    ok, msg, count = run_signal_collection(config)
    print(msg)
    if not ok:
        sys.exit(1)
    print(f"Done: {count} rows in raw_signals.csv")


if __name__ == "__main__":
    main()
