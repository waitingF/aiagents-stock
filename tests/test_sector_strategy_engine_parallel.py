from __future__ import annotations

import sys
import threading
import time
import types
import unittest
from unittest.mock import patch

sys.modules.setdefault("openai", types.SimpleNamespace(OpenAI=object))
sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None))

from src.aiagents_stock.features.sector_strategy import engine as sector_engine


class FakeSectorStrategyAgents:
    started = []
    lock = threading.Lock()

    def __init__(self, model=None, delay: float = 0.25):
        self.model = model
        self.delay = delay

    @classmethod
    def reset(cls):
        cls.started = []

    def _result(self, key: str):
        with self.lock:
            self.started.append(key)
        time.sleep(self.delay)
        return {
            "agent_name": key,
            "analysis": f"{key} analysis",
            "timestamp": "2026-05-16 12:00:00",
        }

    def macro_strategist_agent(self, market_data, news_data):
        return self._result("macro")

    def sector_diagnostician_agent(self, sectors_data, concepts_data, market_data):
        return self._result("sector")

    def fund_flow_analyst_agent(self, fund_flow_data, north_flow_data, sectors_data):
        return self._result("fund")

    def market_sentiment_decoder_agent(self, market_data, sectors_data, concepts_data):
        return self._result("sentiment")


class SectorStrategyEngineParallelTest(unittest.TestCase):
    def test_four_sector_agents_run_concurrently_and_keep_result_order(self):
        FakeSectorStrategyAgents.reset()
        engine = object.__new__(sector_engine.SectorStrategyEngine)
        engine.model = "fake-model"

        data = {
            "market_overview": {},
            "news": [],
            "sectors": {},
            "concepts": {},
            "sector_fund_flow": {},
            "north_flow": {},
        }

        with patch.object(sector_engine, "SectorStrategyAgents", FakeSectorStrategyAgents):
            start = time.perf_counter()
            results = engine._run_agent_analyses_parallel(data)
            elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.7)
        self.assertEqual(list(results.keys()), ["macro", "sector", "fund", "sentiment"])
        self.assertCountEqual(FakeSectorStrategyAgents.started, ["macro", "sector", "fund", "sentiment"])


if __name__ == "__main__":
    unittest.main()
