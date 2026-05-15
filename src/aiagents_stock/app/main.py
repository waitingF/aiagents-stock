"""Streamlit application entrypoint."""

from __future__ import annotations

from src.aiagents_stock.infrastructure.network.proxy import disable_proxy_env


disable_proxy_env()

from src.aiagents_stock.app.legacy import main


__all__ = ["main"]
