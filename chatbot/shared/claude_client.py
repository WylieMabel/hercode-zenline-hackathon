import os

# To enable real responses: set CLAUDE_API_KEY in your environment and
# uncomment the anthropic import + swap out the _call_placeholder below.
#
# import anthropic
# _client = anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
MODEL = "claude-sonnet-4-6"


def chat(system_prompt: str, history: list[dict], user_message: str) -> str:
    """
    Send a message and return the assistant reply.

    history is a list of {"role": "user"|"assistant", "content": str} dicts
    representing the conversation so far (not including user_message).
    """
    messages = history + [{"role": "user", "content": user_message}]

    if not CLAUDE_API_KEY:
        return _call_placeholder(system_prompt, messages)

    # --- Uncomment when ready to use real API ---
    # response = _client.messages.create(
    #     model=MODEL,
    #     max_tokens=1024,
    #     system=system_prompt,
    #     messages=messages,
    # )
    # return response.content[0].text

    return _call_placeholder(system_prompt, messages)


def _call_placeholder(system_prompt: str, messages: list[dict]) -> str:
    last = messages[-1]["content"] if messages else ""
    return (
        f"[PLACEHOLDER RESPONSE]\n"
        f"System prompt length: {len(system_prompt)} chars\n"
        f"Turn {len(messages)} | Last user message: \"{last[:80]}\"\n"
        f"Set CLAUDE_API_KEY to enable real responses."
    )
