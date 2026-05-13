"""Compatibility scheduler for legacy portfolio imports.

Portfolio scheduled analysis now delegates to the stock-pool scheduler using the
system ``持仓`` pool.
"""

from src.aiagents_stock.features.stock_pool.scheduler import StockPoolScheduler, stock_pool_scheduler


class PortfolioScheduler(StockPoolScheduler):
    """Compatibility subclass for old imports."""


portfolio_scheduler = stock_pool_scheduler

