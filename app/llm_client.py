"""Create Anthropic clients from a per-call API key (never logged or persisted)."""

from __future__ import annotations

import os
from typing import Any

MODEL = "claude-sonnet-4-6"


def resolve_api_key(api_key: str | None = None) -> str:
    """Prefer explicit key from the caller; fall back to env for CLI/scripts only."""
    if api_key and str(api_key).strip():
        return str(api_key).strip()
    return os.environ.get("CLAUDE_API_KEY", "").strip()


def create_client(api_key: str | None = None) -> Any | None:
    key = resolve_api_key(api_key)
    if not key:
        return None
    try:
        import anthropic

        return anthropic.Anthropic(api_key=key)
    except ImportError:
        return None


def messages_create(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str = MODEL,
    max_tokens: int = 1024,
    system: str | None = None,
) -> str | None:
    """Run a single user-message completion. Returns text or None if unavailable."""
    client = create_client(api_key)
    if not client:
        return None
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    return response.content[0].text.strip()
