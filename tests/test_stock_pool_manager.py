from __future__ import annotations

import tempfile
import types
import unittest
import sys
import csv
from pathlib import Path
from unittest.mock import patch

sys.modules.setdefault("openai", types.SimpleNamespace(OpenAI=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))
sys.modules.setdefault("yfinance", types.SimpleNamespace(Ticker=object))
sys.modules.setdefault("akshare", types.SimpleNamespace())
sys.modules.setdefault("ta", types.SimpleNamespace())
sys.modules.setdefault("pywencai", types.SimpleNamespace())

from src.aiagents_stock.features.stock_pool.manager import StockPoolManager
from src.aiagents_stock.features.stock_pool.repository import StockPoolRepository


def fake_analysis(symbol, period, enabled_analysts_config, selected_model):
    return {
        "success": True,
        "stock_info": {
            "symbol": symbol,
            "name": f"{symbol} name",
            "current_price": 10.0,
        },
        "final_decision": {
            "rating": "买入",
            "confidence_level": 8,
            "target_price": "12.00",
            "entry_range": "9.50-10.00",
            "take_profit": "12.50",
            "stop_loss": "9.00",
            "operation_advice": "继续观察并分批介入",
            "holding_period": "中期",
            "position_size": "三成",
            "risk_warning": "注意回撤",
        },
    }


class StockPoolManagerTest(unittest.TestCase):
    def test_cross_pool_duplicate_stock_is_analyzed_once_and_written_to_each_pool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            manager = StockPoolManager(repository=repo, model="test-model")
            holding = repo.get_holding_pool()
            watchlist = repo.get_watchlist_pool()
            repo.add_item(holding["id"], "600519.SH", "贵州茅台", auto_monitor=True)
            repo.add_item(watchlist["id"], "600519.SH", "贵州茅台")
            repo.add_item(watchlist["id"], "000001.SZ", "平安银行")

            calls = []

            def recording_analysis(*args, **kwargs):
                calls.append(kwargs["symbol"])
                return fake_analysis(*args, **kwargs)

            with patch(
                "src.aiagents_stock.features.stock_pool.manager.analyze_single_stock_for_batch",
                side_effect=recording_analysis,
            ):
                result = manager.batch_analyze_pools(
                    [holding["id"], watchlist["id"]],
                    scope="all",
                    mode="sequential",
                )

            holding_history = repo.get_analysis_history(pool_id=holding["id"])
            watchlist_history = repo.get_analysis_history(pool_id=watchlist["id"])

        self.assertTrue(result["success"])
        self.assertCountEqual(calls, ["600519.SH", "000001.SZ"])
        self.assertEqual(calls.count("600519.SH"), 1)
        self.assertEqual(len(result["saved_ids"]), 3)
        self.assertEqual(len(holding_history), 1)
        self.assertEqual(len(watchlist_history), 2)
        self.assertTrue(all(record["review_json"] for record in holding_history + watchlist_history))

    def test_today_unanalysed_scope_filters_per_pool_item(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            manager = StockPoolManager(repository=repo, model="test-model")
            holding = repo.get_holding_pool()
            watchlist = repo.get_watchlist_pool()
            holding_item_id = repo.add_item(holding["id"], "600519.SH", "贵州茅台")
            repo.add_item(watchlist["id"], "600519.SH", "贵州茅台")
            repo.save_analysis_history(
                run_id=None,
                pool_id=holding["id"],
                pool_item_id=holding_item_id,
                code="600519.SH",
                name="贵州茅台",
                trading_date="2026-05-14",
                rating="持有",
            )

            targets = manager.build_analysis_targets(
                [holding["id"], watchlist["id"]],
                scope="today_unanalysed",
                trading_date="2026-05-14",
            )

        self.assertEqual(list(targets.keys()), ["600519.SH"])
        self.assertEqual(len(targets["600519.SH"]), 1)
        self.assertEqual(targets["600519.SH"][0]["pool_id"], watchlist["id"])

    def test_add_stock_resolves_name_when_only_code_is_provided(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            manager = StockPoolManager(repository=repo, model="test-model")
            holding = repo.get_holding_pool()

            with patch.object(
                manager,
                "_resolve_stock_name",
                wraps=lambda code, name: "贵州茅台" if code == "600519.SH" else code,
            ) as resolver:
                success, message, item_id = manager.add_stock(holding["id"], "600519.SH")

            item = repo.get_item(item_id)

        self.assertTrue(success, message)
        self.assertEqual(item["code"], "600519.SH")
        self.assertEqual(item["name"], "贵州茅台")
        resolver.assert_called_once_with("600519.SH", None)

    def test_manual_stock_name_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            manager = StockPoolManager(repository=repo, model="test-model")
            holding = repo.get_holding_pool()

            success, message, item_id = manager.add_stock(holding["id"], "600519.SH", name="手动名称")
            item = repo.get_item(item_id)

        self.assertTrue(success, message)
        self.assertEqual(item["name"], "手动名称")

    def test_resolve_a_share_name_uses_local_static_basic_without_stock_info_fetch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            stock_basic_path = Path(tmpdir) / "stock_basic.csv"
            with stock_basic_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=["ts_code", "symbol", "name"])
                writer.writeheader()
                writer.writerow({"ts_code": "600519.SH", "symbol": "600519", "name": "贵州茅台"})

            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            manager = StockPoolManager(repository=repo, model="test-model")
            holding = repo.get_holding_pool()

            with patch("src.aiagents_stock.features.stock_pool.manager.data_path", return_value=stock_basic_path):
                success, message, item_id = manager.add_stock(holding["id"], "600519.SH")

            item = repo.get_item(item_id)

        self.assertTrue(success, message)
        self.assertEqual(item["name"], "贵州茅台")

    def test_resolve_hk_name_does_not_use_realtime_or_history_stock_info_fetcher(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            manager = StockPoolManager(repository=repo, model="test-model")
            watchlist = repo.get_watchlist_pool()

            with patch.object(manager, "_resolve_hk_name_from_tushare_hk_basic", return_value="腾讯控股") as resolver:
                success, message, item_id = manager.add_stock(watchlist["id"], "00700.HK")

            item = repo.get_item(item_id)

        self.assertTrue(success, message)
        self.assertEqual(item["name"], "腾讯控股")
        resolver.assert_called_once_with("00700.HK")

    def test_resolve_hk_name_falls_back_to_akshare_spot_when_tushare_misses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            manager = StockPoolManager(repository=repo, model="test-model")
            watchlist = repo.get_watchlist_pool()

            with (
                patch.object(manager, "_resolve_hk_name_from_tushare_hk_basic", return_value=None),
                patch.object(manager, "_resolve_hk_name_from_akshare_spot", return_value="华润万象生活") as resolver,
            ):
                success, message, item_id = manager.add_stock(watchlist["id"], "01209")

            item = repo.get_item(item_id)

        self.assertTrue(success, message)
        self.assertEqual(item["name"], "华润万象生活")
        resolver.assert_called_once_with("01209")

    def test_add_existing_active_stock_does_not_resolve_name_again(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = StockPoolRepository(Path(tmpdir) / "stock_pools.db", auto_migrate=False)
            manager = StockPoolManager(repository=repo, model="test-model")
            watchlist = repo.get_watchlist_pool()
            item_id = repo.add_item(watchlist["id"], "01209", "01209")

            with patch.object(manager, "_resolve_name_from_static_sources") as resolver:
                success, message, returned_item_id = manager.add_stock(watchlist["id"], "01209", tags="港股")

            item = repo.get_item(item_id)

        self.assertTrue(success, message)
        self.assertEqual(returned_item_id, item_id)
        self.assertEqual(item["name"], "01209")
        self.assertEqual(item["tags"], "港股")
        resolver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
