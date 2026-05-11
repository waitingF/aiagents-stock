"""Notification service interfaces."""

from __future__ import annotations

from typing import Protocol


class NotificationSender(Protocol):
    """Common protocol for text and markdown notifications."""

    def send_text(self, title: str, content: str) -> bool:
        """Send a plain text notification."""

    def send_markdown(self, title: str, content: str) -> bool:
        """Send a markdown notification."""

    def send_test(self) -> tuple[bool, str]:
        """Send a test notification and return status plus message."""
