import os
import sys

_CHATBOT_SHARED = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.abspath(os.path.join(_CHATBOT_SHARED, "..", "..", "app"))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from llm_client import MODEL, create_client, resolve_api_key

MAX_TOKENS = 1024


def chat(
    system_prompt: str,
    history: list[dict],
    user_message: str,
    max_tokens: int = MAX_TOKENS,
    api_key: str | None = None,
) -> str:
    """
    Send a message and return the assistant reply.

    Pass api_key from the UI session — it is not stored on disk or in env.
    """
    messages = history + [{"role": "user", "content": user_message}]
    client = create_client(api_key)

    if not client:
        return _call_placeholder(system_prompt, messages, api_key)

    try:
        import anthropic

        response = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
    except anthropic.APIError as exc:  # type: ignore[union-attr]
        return f"[CLAUDE API ERROR] {exc}"


def _call_placeholder(system_prompt: str, messages: list[dict], api_key: str | None) -> str:
    last = messages[-1]["content"] if messages else ""
    if not resolve_api_key(api_key):
        hint = "Enter your Claude API key in the sidebar (stored only for this session)."
    else:
        try:
            import anthropic  # noqa: F401
            hint = "API key provided but client could not be created."
        except ImportError:
            hint = "Install anthropic: pip install anthropic"
    return (
        f"[PLACEHOLDER RESPONSE]\n"
        f"System prompt length: {len(system_prompt)} chars\n"
        f"Turn {len(messages)} | Last user message: \"{last[:80]}\"\n"
        f"{hint}"
    )
