"""Compatibility manager for legacy portfolio imports.

The portfolio feature now uses the system ``持仓`` stock pool as its storage and
analysis backend. This module preserves the old public object name for callers
that still import ``portfolio_manager``.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from src.aiagents_stock.features.stock_pool.manager import StockPoolManager, stock_pool_manager


class PortfolioManager:
    """Compatibility wrapper backed by the holding stock pool."""

    def __init__(self, stock_pool_backend: StockPoolManager = stock_pool_manager):
        self.stock_pool_backend = stock_pool_backend
        self.db = stock_pool_backend.db

    def _holding_pool_id(self) -> int:
        return self.stock_pool_backend.get_holding_pool()["id"]

    def add_stock(
        self,
        code: str,
        name: str,
        cost_price: Optional[float] = None,
        quantity: Optional[int] = None,
        note: str = "",
        auto_monitor: bool = True,
    ) -> Tuple[bool, str, Optional[int]]:
        return self.stock_pool_backend.add_stock(
            self._holding_pool_id(),
            code=code,
            name=name,
            cost_price=cost_price,
            quantity=quantity,
            note=note or "",
            auto_monitor=auto_monitor,
        )

    def update_stock(self, stock_id: int, **kwargs) -> Tuple[bool, str]:
        return self.stock_pool_backend.update_stock(stock_id, **kwargs)

    def delete_stock(self, stock_id: int) -> Tuple[bool, str]:
        return self.stock_pool_backend.remove_stock(stock_id)

    def get_stock(self, stock_id: int) -> Optional[Dict]:
        return self.db.get_item(stock_id)

    def get_all_stocks(self, auto_monitor_only: bool = False) -> List[Dict]:
        stocks = self.stock_pool_backend.list_stocks(self._holding_pool_id())
        if auto_monitor_only:
            return [stock for stock in stocks if stock.get("auto_monitor")]
        return stocks

    def search_stocks(self, keyword: str) -> List[Dict]:
        keyword = (keyword or "").lower()
        return [
            stock
            for stock in self.get_all_stocks()
            if keyword in stock.get("code", "").lower() or keyword in stock.get("name", "").lower()
        ]

    def get_stock_count(self) -> int:
        return self.db.count_items(self._holding_pool_id())

    def analyze_single_stock(self, stock_code: str, period="1y", selected_agents: List[str] = None) -> Dict:
        return self.stock_pool_backend.analyze_single_stock(stock_code, period, selected_agents)

    def batch_analyze_portfolio(
        self,
        mode="sequential",
        period="1y",
        selected_agents: List[str] = None,
        max_workers: int = 3,
        progress_callback=None,
        stock_codes: List[str] = None,
    ) -> Dict:
        return self.stock_pool_backend.batch_analyze_pools(
            pool_ids=[self._holding_pool_id()],
            scope="all",
            selected_codes=stock_codes,
            mode=mode,
            period=period,
            selected_agents=selected_agents,
            max_workers=max_workers,
            progress_callback=progress_callback,
        )

    def save_analysis_results(self, analysis_results: Dict) -> List[int]:
        if "saved_ids" in analysis_results:
            return analysis_results["saved_ids"]
        return self.stock_pool_backend.save_analysis_results(analysis_results)

    def get_analysis_history(self, stock_id: int, limit: int = 10) -> List[Dict]:
        item = self.db.get_item(stock_id)
        if not item:
            return []
        return self.db.get_analysis_history(
            pool_id=item["pool_id"],
            pool_item_id=stock_id,
            limit=limit,
        )

    def get_latest_analysis(self, stock_id: int) -> Optional[Dict]:
        item = self.db.get_item(stock_id)
        if not item:
            return None
        return self.db.get_latest_analysis(item["pool_id"], stock_id)

    def get_all_latest_analysis(self) -> List[Dict]:
        records = []
        for stock in self.get_all_stocks():
            latest = self.get_latest_analysis(stock["id"]) or {}
            merged = stock.copy()
            merged.update(latest)
            records.append(merged)
        return records

    def get_rating_changes(self, stock_id: int, days: int = 30) -> List[Tuple]:
        history = list(reversed(self.get_analysis_history(stock_id, limit=days * 3)))
        changes = []
        for previous, current in zip(history, history[1:]):
            if previous.get("rating") != current.get("rating"):
                changes.append((
                    current.get("analysis_time"),
                    previous.get("rating"),
                    current.get("rating"),
                ))
        return changes


portfolio_manager = PortfolioManager()

