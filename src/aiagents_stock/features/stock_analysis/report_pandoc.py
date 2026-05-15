"""Compatibility exports for the former Pandoc/Streamlit report module."""

from __future__ import annotations

from typing import Any, Dict

from src.aiagents_stock.features.stock_analysis.report import (
    create_markdown_download_link as create_download_link,
    generate_html_content,
    generate_markdown_report,
)


def generate_pdf_report(
    stock_info: Dict[str, Any],
    agents_results: Dict[str, Any],
    discussion_result: Any,
    final_decision: Any,
) -> Dict[str, str]:
    markdown = generate_markdown_report(stock_info, agents_results, discussion_result, final_decision)
    return {"markdown": markdown, "html": generate_html_content(markdown)}


def display_pdf_export_section(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("Streamlit UI has been removed. Use FastAPI report endpoints or React actions instead.")
