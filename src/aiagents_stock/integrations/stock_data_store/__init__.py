"""Integration adapter for the stock-data-store submodule."""

from src.aiagents_stock.integrations.stock_data_store.service import (
    StockDataStoreService,
    stock_data_store_service,
)

__all__ = ["StockDataStoreService", "stock_data_store_service"]
