"""Markdown reporting interface."""

from __future__ import annotations

from typing import Protocol


class MarkdownReport(Protocol):
    """Object that can render itself as markdown."""

    def to_markdown(self) -> str:
        """Return markdown content."""
