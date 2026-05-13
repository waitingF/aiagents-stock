from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.aiagents_stock.features.stock_pool.repository import (
    HOLDING_POOL_NAME,
    WATCHLIST_POOL_NAME,
    StockPoolRepository,
)


class StockPoolRepositoryTest(unittest.TestCase):
    def test_system_pools_are_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)

            pools = repo.list_pools()

        self.assertEqual([pool["name"] for pool in pools[:2]], [HOLDING_POOL_NAME, WATCHLIST_POOL_NAME])
        self.assertTrue(pools[0]["is_system"])
        self.assertTrue(pools[1]["is_system"])

    def test_same_code_can_exist_in_multiple_pools_but_not_duplicate_same_pool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            holding = repo.get_holding_pool()
            watchlist = repo.get_watchlist_pool()

            first_id = repo.add_item(holding["id"], "600519.SH", "贵州茅台", auto_monitor=True)
            second_id = repo.add_item(watchlist["id"], "600519.SH", "贵州茅台")
            duplicate_id = repo.add_item(holding["id"], "600519.SH", "贵州茅台", note="updated")

            holding_items = repo.list_items(holding["id"])
            watchlist_items = repo.list_items(watchlist["id"])

        self.assertEqual(first_id, duplicate_id)
        self.assertNotEqual(first_id, second_id)
        self.assertEqual(len(holding_items), 1)
        self.assertEqual(len(watchlist_items), 1)
        self.assertEqual(holding_items[0]["note"], "updated")
        self.assertTrue(holding_items[0]["created_at"])

    def test_legacy_portfolio_migrates_to_holding_pool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            legacy_path = Path(tmpdir) / "portfolio_stocks.db"
            self._create_legacy_portfolio_db(legacy_path)

            repo = StockPoolRepository(
                Path(tmpdir) / "stock_pools.db",
                legacy_portfolio_db_path=legacy_path,
                auto_migrate=True,
            )
            holding = repo.get_holding_pool()
            items = repo.list_items(holding["id"])
            history = repo.get_analysis_history(pool_id=holding["id"])

            repo.migrate_legacy_portfolio()
            items_after_second_run = repo.list_items(holding["id"])
            history_after_second_run = repo.get_analysis_history(pool_id=holding["id"])

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["code"], "000001.SZ")
        self.assertEqual(items[0]["cost_price"], 10.5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["rating"], "买入")
        self.assertEqual(len(items_after_second_run), 1)
        self.assertEqual(len(history_after_second_run), 1)

    def _create_legacy_portfolio_db(self, path: Path):
        with sqlite3.connect(path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE portfolio_stocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    cost_price REAL,
                    quantity INTEGER,
                    note TEXT,
                    auto_monitor BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE portfolio_analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    portfolio_stock_id INTEGER NOT NULL,
                    analysis_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rating TEXT,
                    confidence REAL,
                    current_price REAL,
                    target_price REAL,
                    entry_min REAL,
                    entry_max REAL,
                    take_profit REAL,
                    stop_loss REAL,
                    summary TEXT,
                    operation_advice TEXT,
                    holding_period TEXT,
                    position_size TEXT,
                    risk_warning TEXT,
                    final_decision_json TEXT,
                    review_status TEXT,
                    review_summary TEXT,
                    review_json TEXT
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO portfolio_stocks
                (code, name, cost_price, quantity, note, auto_monitor, created_at, updated_at)
                VALUES ('000001.SZ', '平安银行', 10.5, 1000, 'legacy', 1, '2026-05-01 10:00:00', '2026-05-01 10:00:00')
                """
            )
            cursor.execute(
                """
                INSERT INTO portfolio_analysis_history
                (portfolio_stock_id, analysis_time, rating, confidence, current_price, target_price,
                 entry_min, entry_max, take_profit, stop_loss, summary)
                VALUES (1, '2026-05-02 15:05:00', '买入', 8.0, 11.0, 12.0, 10.0, 10.5, 12.5, 9.8, 'summary')
                """
            )
            conn.commit()


if __name__ == "__main__":
    unittest.main()

