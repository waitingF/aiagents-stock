from __future__ import annotations

import pandas as pd
import sys
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))

from src.aiagents_stock.integrations.stock_data_store.loader import ensure_stock_data_store_loaded
from src.aiagents_stock.integrations.market_data.cache import LocalDataCache
from src.aiagents_stock.integrations.market_data.providers import DataSourceManager
from src.aiagents_stock.integrations.stock_data_store.service import StockDataStoreService


class FakeTushareApi:
    def __init__(self):
        self.daily_calls = 0
        self.stock_basic_calls = 0
        self.daily_basic_calls = 0

    def daily(self, **kwargs):
        self.daily_calls += 1
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260511",
                    "open": 10.0,
                    "high": 10.8,
                    "low": 9.9,
                    "close": 10.5,
                    "pre_close": 10.0,
                    "change": 0.5,
                    "pct_chg": 5.0,
                    "vol": 1234.0,
                    "amount": 5678.0,
                }
            ]
        )

    def stock_basic(self, **kwargs):
        self.stock_basic_calls += 1
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "area": "深圳",
                    "industry": "银行",
                    "market": "主板",
                    "list_date": "19910403",
                }
            ]
        )

    def daily_basic(self, **kwargs):
        self.daily_basic_calls += 1
        return pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20260511",
                    "close": 10.5,
                    "turnover_rate": 1.2,
                    "volume_ratio": 0.9,
                    "pe": 6.1,
                    "pe_ttm": 6.5,
                    "pb": 0.7,
                    "total_mv": 1000000.0,
                    "circ_mv": 900000.0,
                }
            ]
        )


class FakeTushareModule:
    def __init__(self, api):
        self.api = api
        self.pro_api_calls = []
        self.pro_bar_calls = []
        self.set_token_calls = []

    def pro_api(self, token=None):
        self.pro_api_calls.append(token)
        return self.api

    def pro_bar(self, **kwargs):
        self.pro_bar_calls.append(kwargs)
        return self.api.daily()

    def set_token(self, token):
        self.set_token_calls.append(token)


class TushareCacheAndProviderTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = self.enterContext(__import__("tempfile").TemporaryDirectory())

    def test_local_cache_hits_same_day_and_refreshes_next_day(self):
        current_day = {"value": "2026-05-12"}
        cache = LocalDataCache(self.tmpdir, today_provider=lambda: current_day["value"])
        calls = {"count": 0}

        def fetch():
            calls["count"] += 1
            return pd.DataFrame([{"value": calls["count"]}])

        first = cache.get_or_fetch("demo", {"symbol": "000001"}, fetch)
        second = cache.get_or_fetch("demo", {"symbol": "000001"}, fetch)
        current_day["value"] = "2026-05-13"
        third = cache.get_or_fetch("demo", {"symbol": "000001"}, fetch)

        self.assertEqual(first.iloc[0]["value"], 1)
        self.assertEqual(second.iloc[0]["value"], 1)
        self.assertEqual(third.iloc[0]["value"], 2)
        self.assertEqual(calls["count"], 2)

    def test_local_cache_returns_stale_value_when_refresh_fails(self):
        current_day = {"value": "2026-05-12"}
        cache = LocalDataCache(self.tmpdir, today_provider=lambda: current_day["value"])
        cache.get_or_fetch("demo", {"symbol": "000001"}, lambda: pd.DataFrame([{"value": 1}]))

        current_day["value"] = "2026-05-13"

        def failing_fetch():
            raise RuntimeError("network down")

        stale = cache.get_or_fetch("demo", {"symbol": "000001"}, failing_fetch)

        self.assertEqual(stale.iloc[0]["value"], 1)

    def test_data_source_manager_initializes_tushare_without_global_set_token(self):
        fake_api = FakeTushareApi()
        fake_tushare = FakeTushareModule(fake_api)
        cache = LocalDataCache(self.tmpdir, today_provider=lambda: "2026-05-12")

        with patch.dict("os.environ", {"TUSHARE_TOKEN": "test-token"}), patch.dict(
            sys.modules, {"tushare": fake_tushare}
        ):
            manager = DataSourceManager(cache=cache, start_cache_scheduler=False)

        self.assertTrue(manager.tushare_available)
        self.assertIs(manager.tushare_api, fake_api)
        self.assertEqual(fake_tushare.pro_api_calls, ["test-token"])
        self.assertEqual(fake_tushare.set_token_calls, [])

    def test_data_source_manager_passes_api_to_tushare_pro_bar(self):
        fake_api = FakeTushareApi()
        fake_tushare = FakeTushareModule(fake_api)
        cache = LocalDataCache(self.tmpdir, today_provider=lambda: "2026-05-12")
        manager = DataSourceManager(tushare_api=fake_api, cache=cache, start_cache_scheduler=False)

        with patch.dict(sys.modules, {"tushare": fake_tushare}):
            df = manager._get_tushare_hist_data("000001", start_date="20260501", end_date="20260512", adjust="qfq")

        self.assertEqual(len(fake_tushare.pro_bar_calls), 1)
        self.assertIs(fake_tushare.pro_bar_calls[0]["api"], fake_api)
        self.assertEqual(df.iloc[0]["date"], pd.Timestamp("2026-05-11"))

    def test_stock_data_store_tushare_client_avoids_global_set_token(self):
        ensure_stock_data_store_loaded()
        from stock_data_store.clients.tushare import TushareClient

        fake_api = FakeTushareApi()
        fake_tushare = FakeTushareModule(fake_api)

        with patch.dict(sys.modules, {"tushare": fake_tushare}):
            client = TushareClient(token="test-token", retry=0)
            df = client.get_daily_bars("000001.SZ", start_date="20260501", end_date="20260512")

        self.assertEqual(fake_tushare.pro_api_calls, ["test-token"])
        self.assertEqual(fake_tushare.set_token_calls, [])
        self.assertEqual(len(fake_tushare.pro_bar_calls), 1)
        self.assertIs(fake_tushare.pro_bar_calls[0]["api"], fake_api)
        self.assertEqual(df.iloc[0]["ts_code"], "000001.SZ")

    def test_data_source_manager_uses_tushare_and_normalizes_daily(self):
        fake_api = FakeTushareApi()
        cache = LocalDataCache(self.tmpdir, today_provider=lambda: "2026-05-12")
        empty_store = StockDataStoreService(data_root=f"{self.tmpdir}/empty_stock_data")

        with patch("src.aiagents_stock.integrations.market_data.providers.stock_data_store_service", empty_store):
            manager = DataSourceManager(tushare_api=fake_api, cache=cache, start_cache_scheduler=False)
            df = manager.get_stock_hist_data("000001", start_date="20260501", end_date="20260512", adjust="")
            second = manager.get_stock_hist_data("000001", start_date="20260501", end_date="20260512", adjust="")

        self.assertEqual(fake_api.daily_calls, 1)
        self.assertEqual(df.iloc[0]["date"], pd.Timestamp("2026-05-11"))
        self.assertEqual(df.iloc[0]["volume"], 123400.0)
        self.assertEqual(df.iloc[0]["amount"], 5678000.0)
        self.assertTrue(second.equals(df))

    def test_data_source_manager_enriches_basic_info_with_daily_basic(self):
        fake_api = FakeTushareApi()
        cache = LocalDataCache(self.tmpdir, today_provider=lambda: "2026-05-12")
        manager = DataSourceManager(tushare_api=fake_api, cache=cache, start_cache_scheduler=False)

        info = manager.get_stock_basic_info("000001")

        self.assertEqual(info["name"], "平安银行")
        self.assertEqual(info["industry"], "银行")
        self.assertEqual(info["pe_ratio"], 6.5)
        self.assertEqual(info["pb_ratio"], 0.7)
        self.assertEqual(info["market_cap"], 1000000.0)


if __name__ == "__main__":
    unittest.main()
