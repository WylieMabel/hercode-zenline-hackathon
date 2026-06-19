from shared.signals_loader import load_signals, format_signals_for_prompt
from shared import claude_client

SYSTEM_PROMPT_TEMPLATE = """\
You are a retail intelligence analyst for a Swiss outdoor retailer operating in the DACH market.
Your job is to help buyers and merchandisers understand emerging market opportunities and decide what to act on.

You have access to the following market signals:

{signals}

When answering:
- Be direct and commercially minded. Buyers care about margin, timing, supplier access, and differentiation.
- Reference specific signals from the data when relevant (brand, score, source, market).
- Flag transferability risk if an opportunity is US/Asia-only and hasn't been seen in DACH yet.
- If a signal is weak or the evidence is thin, say so — don't oversell.
- Recommend a concrete next action (e.g. "request samples", "run a 4-week test buy", "monitor for 60 days").
"""


def build_system_prompt() -> str:
    signals = load_signals()
    return SYSTEM_PROMPT_TEMPLATE.format(signals=format_signals_for_prompt(signals))


def run():
    print("=== Retail Buyer Assistant ===")
    print("Ask about emerging opportunities, brands, or signals. Type 'quit' to exit.\n")

    system_prompt = build_system_prompt()
    history: list[dict] = []

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        reply = claude_client.chat(system_prompt, history, user_input)
        print(f"\nAssistant: {reply}\n")

        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": reply})
