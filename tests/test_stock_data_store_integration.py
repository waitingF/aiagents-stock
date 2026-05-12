from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.aiagents_stock.cli.update_market_data import build_parser, _daily_args, _fundamental_args
from src.aiagents_stock.integrations.market_data.providers import DataSourceManager
from src.aiagents_stock.integrations.stock_data_store.loader import ensure_stock_data_store_loaded
from src.aiagents_stock.integrations.stock_data_store.service import StockDataStoreService


class FakeTushareApi:
    def __init__(self):
        self.daily_calls = 0

    def daily(self, **kwargs):
        self.daily_calls += 1
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260512",
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "pre_close": 1.0,
                    "change": 0.0,
                    "pct_chg": 0.0,
                    "vol": 1.0,
                    "amount": 1.0,
                }
            ]
        )


class StockDataStoreIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_submodule_loader_exposes_expected_package(self):
        module = ensure_stock_data_store_loaded()

        self.assertTrue(hasattr(module, "DataManager"))

    def test_service_reads_local_daily_bars_without_remote_api(self):
        service = StockDataStoreService(data_root=self.tmpdir / "stock_data")
        self._write_daily(service, "000001.SZ", close=12.34)

        df = service.read_daily("000001", start_date="2026-05-01", end_date="2026-05-12")

        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["symbol"], "000001")
        self.assertEqual(df.iloc[0]["date"], pd.Timestamp("2026-05-12"))
        self.assertEqual(df.iloc[0]["close"], 12.34)

    def test_data_source_manager_prefers_full_market_local_store(self):
        service = StockDataStoreService(data_root=self.tmpdir / "stock_data")
        self._write_daily(service, "000001.SZ", close=12.34)
        fake_api = FakeTushareApi()

        with patch("src.aiagents_stock.integrations.market_data.providers.stock_data_store_service", service):
            manager = DataSourceManager(tushare_api=fake_api, start_cache_scheduler=False)
            df = manager.get_stock_hist_data("000001", start_date="20260501", end_date="20260512", adjust="qfq")

        self.assertEqual(fake_api.daily_calls, 0)
        self.assertEqual(df.iloc[0]["close"], 12.34)

    def test_update_cli_argument_split(self):
        args = build_parser().parse_args(
            [
                "--all",
                "--symbols",
                "000001.SZ",
                "--limit",
                "10",
                "--force",
                "--datasets",
                "daily_basic",
                "--max-workers",
                "2",
            ]
        )

        self.assertIn("--max-workers", _daily_args(args))
        self.assertNotIn("--datasets", _daily_args(args))
        self.assertIn("--datasets", _fundamental_args(args))
        self.assertNotIn("--max-workers", _fundamental_args(args))

    def _write_daily(self, service: StockDataStoreService, symbol: str, close: float) -> None:
        daily_dir = service.daily_dir
        daily_dir.mkdir(parents=True, exist_ok=True)
        path = daily_dir / f"{symbol}.csv"
        pd.DataFrame(
            [
                {
                    "ts": "2026-05-12",
                    "open": 12.0,
                    "high": 12.5,
                    "low": 11.8,
                    "close": close,
                    "volume": 1000.0,
                }
            ]
        ).to_csv(path, index=False)


if __name__ == "__main__":
    unittest.main()
