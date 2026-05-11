"""Scheduler lifecycle interface."""

from __future__ import annotations

from typing import Protocol


class SchedulerService(Protocol):
    """Common scheduler lifecycle methods."""

    def start(self) -> None:
        """Start the scheduler."""

    def stop(self) -> None:
        """Stop the scheduler."""

    def status(self) -> dict:
        """Return current scheduler status."""
