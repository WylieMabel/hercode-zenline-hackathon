import os

import anthropic

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024

_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY) if CLAUDE_API_KEY else None


def chat(system_prompt: str, history: list[dict], user_message: str, max_tokens: int = MAX_TOKENS) -> str:
    """
    Send a message and return the assistant reply.

    history is a list of {"role": "user"|"assistant", "content": str} dicts
    representing the conversation so far (not including user_message).
    """
    messages = history + [{"role": "user", "content": user_message}]

    if not _client:
        return _call_placeholder(system_prompt, messages)

    try:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
    except anthropic.APIError as exc:
        return f"[CLAUDE API ERROR] {exc}"


def _call_placeholder(system_prompt: str, messages: list[dict]) -> str:
    last = messages[-1]["content"] if messages else ""
    return (
        f"[PLACEHOLDER RESPONSE]\n"
        f"System prompt length: {len(system_prompt)} chars\n"
        f"Turn {len(messages)} | Last user message: \"{last[:80]}\"\n"
        f"Set CLAUDE_API_KEY to enable real responses."
    )
