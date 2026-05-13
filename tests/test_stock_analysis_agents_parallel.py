from __future__ import annotations

import sys
import time
import types
import unittest

sys.modules.setdefault("openai", types.SimpleNamespace(OpenAI=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))
from src.aiagents_stock.features.stock_analysis.agents import StockAnalysisAgents


class FakeStockAnalysisAgents(StockAnalysisAgents):
    def __init__(self, delay: float = 0.25):
        self.delay = delay

    def _result(self, agent_name: str):
        time.sleep(self.delay)
        return {
            "agent_name": agent_name,
            "agent_role": "test",
            "analysis": f"{agent_name} analysis",
            "focus_areas": [],
            "timestamp": "2026-05-13 12:00:00",
        }

    def technical_analyst_agent(self, stock_info, stock_data, indicators):
        return self._result("技术分析师")

    def fundamental_analyst_agent(self, stock_info, financial_data=None, quarterly_data=None):
        return self._result("基本面分析师")

    def fund_flow_analyst_agent(self, stock_info, indicators, fund_flow_data=None):
        return self._result("资金面分析师")

    def risk_management_agent(self, stock_info, indicators, risk_data=None):
        return self._result("风险管理师")

    def market_sentiment_agent(self, stock_info, sentiment_data=None):
        return self._result("市场情绪分析师")

    def news_analyst_agent(self, stock_info, news_data=None):
        return self._result("新闻分析师")


class FailingStockAnalysisAgents(FakeStockAnalysisAgents):
    def technical_analyst_agent(self, stock_info, stock_data, indicators):
        raise RuntimeError("technical failed")


class StockAnalysisAgentsParallelTest(unittest.TestCase):
    def test_enabled_analysts_run_concurrently_and_keep_result_order(self):
        agents = FakeStockAnalysisAgents(delay=0.25)
        enabled_analysts = {
            "technical": True,
            "fundamental": True,
            "fund_flow": True,
            "risk": True,
            "sentiment": True,
            "news": True,
        }

        start = time.perf_counter()
        results = agents.run_multi_agent_analysis(
            stock_info={"symbol": "000001", "name": "平安银行"},
            stock_data=[],
            indicators={},
            enabled_analysts=enabled_analysts,
            analyst_max_workers=6,
        )
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.7)
        self.assertEqual(
            list(results.keys()),
            [
                "technical",
                "fundamental",
                "fund_flow",
                "risk_management",
                "market_sentiment",
                "news",
            ],
        )

    def test_disabled_analysts_are_omitted_from_results(self):
        agents = FakeStockAnalysisAgents(delay=0)

        results = agents.run_multi_agent_analysis(
            stock_info={"symbol": "000001", "name": "平安银行"},
            stock_data=[],
            indicators={},
            enabled_analysts={
                "technical": True,
                "fundamental": False,
                "fund_flow": True,
                "risk": False,
                "sentiment": False,
                "news": False,
            },
        )

        self.assertEqual(list(results.keys()), ["technical", "fund_flow"])

    def test_analyst_exception_still_propagates_to_caller(self):
        agents = FailingStockAnalysisAgents(delay=0)

        with self.assertRaisesRegex(RuntimeError, "technical failed"):
            agents.run_multi_agent_analysis(
                stock_info={"symbol": "000001", "name": "平安银行"},
                stock_data=[],
                indicators={},
                enabled_analysts={
                    "technical": True,
                    "fundamental": False,
                    "fund_flow": False,
                    "risk": False,
                    "sentiment": False,
                    "news": False,
                },
            )


if __name__ == "__main__":
    unittest.main()
