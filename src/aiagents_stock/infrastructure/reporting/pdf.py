"""PDF reporting interface."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class PdfReport(Protocol):
    """Object that can export itself as a PDF file."""

    def to_pdf(self, output_path: str | Path) -> Path:
        """Write a PDF report and return its path."""
