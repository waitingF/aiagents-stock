"""Compatibility UI for the legacy portfolio entry.

The portfolio page now reads and writes the system ``持仓`` stock pool.
"""

from src.aiagents_stock.features.stock_pool.ui import display_holding_pool_manager


def display_portfolio_manager():
    """Display the holding stock pool as the portfolio analysis page."""
    display_holding_pool_manager()

