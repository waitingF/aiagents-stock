"""Shared prompt helpers for LLM-backed features."""

from __future__ import annotations

from typing import Dict, List


def system_user_messages(system_prompt: str, user_prompt: str) -> List[Dict[str, str]]:
    """Build a standard chat-completion message list."""
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
