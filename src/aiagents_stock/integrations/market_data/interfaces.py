"""Market data provider interfaces."""

from __future__ import annotations

from typing import Any, Protocol


class MarketDataProvider(Protocol):
    """Common protocol for market data providers."""

    def get_stock_info(self, symbol: str) -> Any:
        """Return normalized stock metadata for a symbol."""

    def get_stock_data(self, symbol: str, period: str) -> Any:
        """Return historical market data for a symbol and period."""
