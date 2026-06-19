"""
Usage:
    python main.py --mode retail
    python main.py --mode customer
    python main.py --mode customer --persona hiker|family|gear_enthusiast
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


def main():
    parser = argparse.ArgumentParser(description="Zenline Hackathon Chatbot")
    parser.add_argument(
        "--mode",
        choices=["retail", "customer"],
        required=True,
        help="retail = buyer assistant, customer = demographic persona interview",
    )
    parser.add_argument(
        "--persona",
        default="hiker",
        help="Persona to simulate in customer mode (hiker, family, gear_enthusiast)",
    )
    args = parser.parse_args()

    if args.mode == "retail":
        from retail_assistant import run
        run()
    elif args.mode == "customer":
        from customer_persona import run, list_personas
        if args.persona == "list":
            list_personas()
        else:
            run(args.persona)


if __name__ == "__main__":
    main()
