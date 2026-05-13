from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("openai", types.SimpleNamespace(OpenAI=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))
sys.modules.setdefault("yfinance", types.SimpleNamespace(Ticker=object))
sys.modules.setdefault("akshare", types.SimpleNamespace())
sys.modules.setdefault("ta", types.SimpleNamespace())
sys.modules.setdefault("pywencai", types.SimpleNamespace())

from src.aiagents_stock.features.stock_analysis import service


class RecordingDataSource:
    calls = []
    delay = 0.0
    failures = set()
    is_chinese = True
    lock = threading.Lock()

    @classmethod
    def reset(cls, delay: float = 0.0, failures=None, is_chinese: bool = True):
        cls.calls = []
        cls.delay = delay
        cls.failures = set(failures or [])
        cls.is_chinese = is_chinese

    @classmethod
    def record(cls, name):
        with cls.lock:
            cls.calls.append(name)
        if cls.delay:
            time.sleep(cls.delay)
        if name in cls.failures:
            raise RuntimeError(f"{name} failed")
        return {"source": name}


class FakeStockDataFetcher:
    def _is_chinese_stock(self, symbol):
        return RecordingDataSource.is_chinese

    def get_financial_data(self, symbol):
        return RecordingDataSource.record("financial_data")

    def get_risk_data(self, symbol):
        return RecordingDataSource.record("risk_data")


class FakeQuarterlyReportDataFetcher:
    def get_quarterly_reports(self, symbol):
        return RecordingDataSource.record("quarterly_data")


class FakeFundFlowAkshareDataFetcher:
    def get_fund_flow_data(self, symbol):
        return RecordingDataSource.record("fund_flow_data")


class FakeMarketSentimentDataFetcher:
    def get_market_sentiment_data(self, symbol, stock_data):
        return RecordingDataSource.record("sentiment_data")


class FakeQStockNewsDataFetcher:
    def get_stock_news(self, symbol):
        return RecordingDataSource.record("news_data")


class FakeAgents:
    captured_args = None

    def __init__(self, model=None):
        self.model = model

    def run_multi_agent_analysis(
        self,
        stock_info,
        stock_data,
        indicators,
        financial_data,
        fund_flow_data,
        sentiment_data,
        news_data,
        quarterly_data,
        risk_data,
        enabled_analysts=None,
    ):
        FakeAgents.captured_args = {
            "financial_data": financial_data,
            "fund_flow_data": fund_flow_data,
            "sentiment_data": sentiment_data,
            "news_data": news_data,
            "quarterly_data": quarterly_data,
            "risk_data": risk_data,
            "enabled_analysts": enabled_analysts,
        }
        return {"technical": {"analysis": "ok"}}

    def conduct_team_discussion(self, agents_results, stock_info):
        return "discussion"

    def make_final_decision(self, discussion_result, stock_info, indicators):
        return {"rating": "持有"}


class FakeDb:
    def save_analysis(self, **kwargs):
        return 123


def fake_data_source_modules():
    return {
        "src.aiagents_stock.features.stock_analysis.quarterly_report_data": types.SimpleNamespace(
            QuarterlyReportDataFetcher=FakeQuarterlyReportDataFetcher
        ),
        "src.aiagents_stock.features.stock_analysis.fund_flow": types.SimpleNamespace(
            FundFlowAkshareDataFetcher=FakeFundFlowAkshareDataFetcher
        ),
        "src.aiagents_stock.features.stock_analysis.market_sentiment_data": types.SimpleNamespace(
            MarketSentimentDataFetcher=FakeMarketSentimentDataFetcher
        ),
        "src.aiagents_stock.features.stock_analysis.qstock_news_data": types.SimpleNamespace(
            QStockNewsDataFetcher=FakeQStockNewsDataFetcher
        ),
    }


class StockAnalysisServiceParallelDataTest(unittest.TestCase):
    def test_supplemental_data_sources_run_concurrently(self):
        RecordingDataSource.reset(delay=0.2)
        enabled = {
            "fundamental": True,
            "fund_flow": True,
            "risk": True,
            "sentiment": True,
            "news": True,
        }

        with patch.object(service, "StockDataFetcher", FakeStockDataFetcher), patch.dict(
            sys.modules, fake_data_source_modules()
        ):
            start = time.perf_counter()
            result = service._fetch_supplemental_analysis_data(
                "000001",
                stock_data=[],
                enabled_analysts_config=enabled,
                data_fetch_max_workers=6,
            )
            elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.6)
        self.assertEqual(
            result,
            (
                {"source": "financial_data"},
                {"source": "quarterly_data"},
                {"source": "fund_flow_data"},
                {"source": "sentiment_data"},
                {"source": "news_data"},
                {"source": "risk_data"},
            ),
        )
        self.assertCountEqual(
            RecordingDataSource.calls,
            [
                "financial_data",
                "quarterly_data",
                "fund_flow_data",
                "sentiment_data",
                "news_data",
                "risk_data",
            ],
        )

    def test_disabled_or_non_chinese_sources_are_not_fetched(self):
        RecordingDataSource.reset(is_chinese=False)
        enabled = {
            "fundamental": True,
            "fund_flow": True,
            "risk": True,
            "sentiment": True,
            "news": True,
        }

        with patch.object(service, "StockDataFetcher", FakeStockDataFetcher), patch.dict(
            sys.modules, fake_data_source_modules()
        ):
            result = service._fetch_supplemental_analysis_data("AAPL", [], enabled)

        self.assertEqual(result, ({"source": "financial_data"}, None, None, None, None, None))
        self.assertEqual(RecordingDataSource.calls, ["financial_data"])

    def test_disabled_sources_are_not_fetched_for_chinese_stock(self):
        RecordingDataSource.reset(is_chinese=True)
        enabled = {
            "fundamental": False,
            "fund_flow": False,
            "risk": False,
            "sentiment": False,
            "news": False,
        }

        with patch.object(service, "StockDataFetcher", FakeStockDataFetcher), patch.dict(
            sys.modules, fake_data_source_modules()
        ):
            result = service._fetch_supplemental_analysis_data("000001", [], enabled)

        self.assertEqual(result, ({"source": "financial_data"}, None, None, None, None, None))
        self.assertEqual(RecordingDataSource.calls, ["financial_data"])

    def test_optional_source_failure_degrades_to_none(self):
        RecordingDataSource.reset(failures={"fund_flow_data"})
        enabled = {
            "fundamental": False,
            "fund_flow": True,
            "risk": False,
            "sentiment": False,
            "news": False,
        }

        with patch.object(service, "StockDataFetcher", FakeStockDataFetcher), patch.dict(
            sys.modules, fake_data_source_modules()
        ):
            result = service._fetch_supplemental_analysis_data("000001", [], enabled)

        self.assertEqual(result, ({"source": "financial_data"}, None, None, None, None, None))
        self.assertCountEqual(RecordingDataSource.calls, ["financial_data", "fund_flow_data"])

    def test_analyze_single_stock_uses_parallel_fetch_results_without_changing_flow(self):
        RecordingDataSource.reset()
        FakeAgents.captured_args = None
        stock_info = {"symbol": "000001", "name": "平安银行"}
        stock_data = [{"close": 10}]
        indicators = {"price": 10}
        enabled = {
            "technical": True,
            "fundamental": True,
            "fund_flow": True,
            "risk": True,
            "sentiment": True,
            "news": True,
        }

        with patch.object(service, "StockDataFetcher", FakeStockDataFetcher), patch.dict(
            sys.modules, fake_data_source_modules()
        ), patch.object(
            service, "fetch_stock_data", return_value=(stock_info, stock_data, indicators)
        ), patch.object(
            service, "StockAnalysisAgents", FakeAgents
        ), patch.object(
            service, "db", FakeDb()
        ):
            result = service.analyze_single_stock_for_batch(
                "000001",
                "1y",
                enabled_analysts_config=enabled,
                selected_model="fake-model",
            )

        self.assertTrue(result["success"])
        self.assertEqual(FakeAgents.captured_args["financial_data"], {"source": "financial_data"})
        self.assertEqual(FakeAgents.captured_args["quarterly_data"], {"source": "quarterly_data"})
        self.assertEqual(FakeAgents.captured_args["fund_flow_data"], {"source": "fund_flow_data"})
        self.assertEqual(FakeAgents.captured_args["sentiment_data"], {"source": "sentiment_data"})
        self.assertEqual(FakeAgents.captured_args["news_data"], {"source": "news_data"})
        self.assertEqual(FakeAgents.captured_args["risk_data"], {"source": "risk_data"})
        self.assertEqual(FakeAgents.captured_args["enabled_analysts"], enabled)


if __name__ == "__main__":
    unittest.main()
