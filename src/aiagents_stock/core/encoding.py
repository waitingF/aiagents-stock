"""Console encoding helpers."""

from __future__ import annotations

import sys


def configure_console_encoding() -> None:
    """Make console output tolerant of Chinese text and status symbols."""

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
