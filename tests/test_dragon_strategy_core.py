from __future__ import annotations

import os
import unittest

import pandas as pd

from src.aiagents_stock.features.selectors.dragon_strategy.backtest import BacktestEngine
from src.aiagents_stock.features.selectors.dragon_strategy.data import AkshareDragonDataProvider
from src.aiagents_stock.features.selectors.dragon_strategy.leader import screen_limit_up_candidates
from src.aiagents_stock.features.selectors.dragon_strategy.models import DragonStrategyConfig
from src.aiagents_stock.features.selectors.dragon_strategy.repository import DragonStrategyRepository
from src.aiagents_stock.features.selectors.dragon_strategy.sector import compute_sector_signals, normalize_industry_ranking
from src.aiagents_stock.features.selectors.dragon_strategy.sentiment import MarketEnvironmentService, evaluate_market_environment
from src.aiagents_stock.features.selectors.dragon_strategy.trend import scan_trend_tracking
from src.aiagents_stock.infrastructure.network.proxy import disable_proxy_env, without_proxy_env


def _daily_frame(length: int = 70, start: str = "2026-01-01") -> pd.DataFrame:
    dates = pd.date_range(start=start, periods=length, freq="B")
    closes = [10 + idx * 0.12 for idx in range(length)]
    volumes = [1000.0 for _ in range(length)]
    volumes[-2] = 1500.0
    volumes[-1] = 3000.0
    return pd.DataFrame(
        {
            "date": dates,
            "open": [price - 0.05 for price in closes],
            "high": [price + 0.25 for price in closes],
            "low": [price - 0.25 for price in closes],
            "close": closes,
            "volume": volumes,
            "amount": [80_000_000.0 for _ in closes],
            "turnover": [10.0 for _ in closes],
            "pct_chg": [1.0 for _ in closes],
        }
    )


class DragonStrategyCoreTest(unittest.TestCase):
    def test_market_data_calls_temporarily_disable_proxy_environment(self):
        original = {key: os.environ.get(key) for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "no_proxy")}
        try:
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"
            os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9"
            os.environ["ALL_PROXY"] = "http://127.0.0.1:9"
            os.environ["NO_PROXY"] = "localhost"
            os.environ["no_proxy"] = "localhost"

            with without_proxy_env():
                self.assertIsNone(os.environ.get("HTTP_PROXY"))
                self.assertIsNone(os.environ.get("HTTPS_PROXY"))
                self.assertIsNone(os.environ.get("ALL_PROXY"))
                self.assertEqual(os.environ.get("NO_PROXY"), "*")
                self.assertEqual(os.environ.get("no_proxy"), "*")

            self.assertEqual(os.environ.get("HTTP_PROXY"), "http://127.0.0.1:9")
            self.assertEqual(os.environ.get("HTTPS_PROXY"), "http://127.0.0.1:9")
            self.assertEqual(os.environ.get("ALL_PROXY"), "http://127.0.0.1:9")
            self.assertEqual(os.environ.get("NO_PROXY"), "localhost")
            self.assertEqual(os.environ.get("no_proxy"), "localhost")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_disable_proxy_env_applies_process_wide(self):
        original = {key: os.environ.get(key) for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "no_proxy")}
        try:
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"
            os.environ["HTTPS_PROXY"] = "http://127.0.0.1:9"
            os.environ["ALL_PROXY"] = "http://127.0.0.1:9"

            disable_proxy_env()

            self.assertIsNone(os.environ.get("HTTP_PROXY"))
            self.assertIsNone(os.environ.get("HTTPS_PROXY"))
            self.assertIsNone(os.environ.get("ALL_PROXY"))
            self.assertEqual(os.environ.get("NO_PROXY"), "*")
            self.assertEqual(os.environ.get("no_proxy"), "*")
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_provider_safe_frame_does_not_expose_proxy_to_fetcher(self):
        original = os.environ.get("HTTP_PROXY")
        observed = {}
        try:
            os.environ["HTTP_PROXY"] = "http://127.0.0.1:9"

            def fetcher():
                observed["HTTP_PROXY"] = os.environ.get("HTTP_PROXY")
                return pd.DataFrame({"value": [1]})

            frame = AkshareDragonDataProvider()._safe_frame(fetcher)

            self.assertIsNone(observed["HTTP_PROXY"])
            self.assertEqual(len(frame), 1)
            self.assertEqual(os.environ.get("HTTP_PROXY"), "http://127.0.0.1:9")
        finally:
            if original is None:
                os.environ.pop("HTTP_PROXY", None)
            else:
                os.environ["HTTP_PROXY"] = original

    def test_market_environment_service_does_not_crash_when_provider_disconnects(self):
        class FlakyProvider:
            def is_trade_day(self, date):
                return True

            def get_limit_up_pool(self, date):
                return pd.DataFrame()

            def get_limit_down_pool(self, date):
                return pd.DataFrame()

            def get_strong_pool(self, date):
                return pd.DataFrame()

            def get_explode_pool(self, date):
                return pd.DataFrame()

            def get_board_pool(self, date):
                return pd.DataFrame()

            def get_index_daily(self, start_date, end_date):
                raise ConnectionError("remote closed connection")

            def get_yesterday_limit_up_count(self, date):
                return 0

            def get_north_money(self):
                return -100.0

            def get_market_activity(self):
                return 0, 1

        market = MarketEnvironmentService(FlakyProvider()).evaluate("20260515")

        self.assertFalse(market.passed)
        self.assertIn("get_index_daily", market.metrics["data_errors"])
        self.assertIn("数据源异常", market.message)

    def test_market_environment_passes_when_core_and_assist_conditions_pass(self):
        limit_up = pd.DataFrame(
            {
                "code": [f"000{i:03d}" for i in range(40)],
                "name": [f"股票{i}" for i in range(40)],
                "lianban_count": [5] + [1] * 39,
            }
        )
        limit_down = pd.DataFrame({"名称": [f"跌停{i}" for i in range(5)]})
        index_df = pd.DataFrame({"open": [100, 101, 102], "close": [101, 102, 103]})
        board_df = pd.DataFrame({"涨停家数": [15, 10, 5]})

        market = evaluate_market_environment(
            date="20260515",
            is_trade_day=True,
            limit_up_df=limit_up,
            limit_down_df=limit_down,
            explode_df=pd.DataFrame({"code": ["1"]}),
            board_df=board_df,
            index_df=index_df,
            yesterday_limit_up_count=30,
            north_money=-10,
            up_count=3000,
            down_count=1000,
        )

        self.assertTrue(market.passed)
        self.assertEqual(market.limit_up_count, 40)
        self.assertGreaterEqual(market.assist_pass_count, 3)

    def test_dragon_mvp_filters_and_scores_leader_candidate(self):
        limit_up = pd.DataFrame(
            [
                {
                    "code": "000001",
                    "name": "测试龙头",
                    "first_limit_time": "09:31:00",
                    "seal_amount": 120_000_000,
                    "lianban_count": 4,
                    "sector": "人工智能",
                    "circ_market_cap": 50,
                    "latest_price": 12.5,
                    "explode_count": 0,
                }
            ]
        )
        info = {"000001": {"上市日期": "20200101"}}
        daily = {"000001": _daily_frame()}

        candidates = screen_limit_up_candidates(
            limit_up,
            stock_info_by_code=info,
            daily_by_code=daily,
            config=DragonStrategyConfig(max_stock_count=3),
            date="20260515",
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].code, "000001")
        self.assertGreaterEqual(candidates[0].score, 60)
        self.assertIsNotNone(candidates[0].trade_plan)

    def test_sector_tracking_persists_history(self):
        industry = pd.DataFrame(
            {
                "板块名称": ["人工智能", "机器人", "煤炭"],
                "涨跌幅": [3.2, 2.1, -0.5],
            }
        )
        limit_up = pd.DataFrame(
            {
                "code": ["000001", "000002", "000003", "000004", "000005"],
                "name": ["A", "B", "C", "D", "E"],
                "sector": ["人工智能", "人工智能", "人工智能", "机器人", "机器人"],
                "lianban_count": [2, 1, 1, 1, 1],
            }
        )
        history = [
            {"trade_date": "20260514", "name": "人工智能", "rank": 3, "status": "active"},
            {"trade_date": "20260513", "name": "人工智能", "rank": 5, "status": "active"},
        ]
        signals = compute_sector_signals(industry, limit_up, history=history, date="20260515")

        ai_signal = next(item for item in signals if item.name == "人工智能")
        self.assertEqual(ai_signal.consecutive_days, 3)
        self.assertGreaterEqual(ai_signal.rating, 3)

        repo = DragonStrategyRepository(":memory:")
        repo.save_sector_signals("20260515", signals)
        saved = repo.get_recent_sector_history(limit_days=10, name="人工智能")

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["name"], "人工智能")
        self.assertEqual(saved[0]["consecutive_days"], 3)

    def test_sector_ranking_keeps_english_metrics_for_chinese_display(self):
        industry = pd.DataFrame(
            {
                "name": ["人工智能", "机器人"],
                "rank": [2, 1],
                "pct_chg": [3.2, 4.1],
                "amount": [120_000_000.0, 95_000_000.0],
                "up_stocks": [18, 12],
                "down_stocks": [3, 2],
                "flat_stocks": [1, 0],
            }
        )

        normalized = normalize_industry_ranking(industry)
        ai_row = normalized[normalized["name"] == "人工智能"].iloc[0]

        self.assertEqual(int(ai_row["rank"]), 2)
        self.assertEqual(float(ai_row["pct_chg"]), 3.2)
        self.assertEqual(float(ai_row["amount"]), 120_000_000.0)
        self.assertEqual(int(ai_row["stock_count"]), 22)
        self.assertEqual(int(ai_row["up_stocks"]), 18)

        signals = compute_sector_signals(industry, pd.DataFrame(), date="20260515")
        ai_signal = next(item for item in signals if item.name == "人工智能")

        self.assertEqual(ai_signal.rank, 2)
        self.assertEqual(ai_signal.pct_chg, 3.2)
        self.assertEqual(ai_signal.amount, 120_000_000.0)
        self.assertEqual(ai_signal.stock_count, 22)
        self.assertEqual(ai_signal.up_stocks, 18)

    def test_sector_ranking_derives_total_stock_count_from_up_down_counts(self):
        industry = pd.DataFrame(
            {
                "序号": [1],
                "板块": ["通用设备"],
                "涨跌幅": [1.27],
                "总成交额": [1144.08],
                "上涨家数": [139],
                "下跌家数": [108],
            }
        )

        normalized = normalize_industry_ranking(industry)
        row = normalized.iloc[0]

        self.assertEqual(row["name"], "通用设备")
        self.assertEqual(int(row["rank"]), 1)
        self.assertEqual(float(row["pct_chg"]), 1.27)
        self.assertEqual(float(row["amount"]), 1144.08)
        self.assertEqual(int(row["stock_count"]), 247)
        self.assertEqual(int(row["up_stocks"]), 139)

    def test_trend_scan_and_fixed_holding_backtest(self):
        daily = {"000001": _daily_frame()}
        quotes = pd.DataFrame(
            {
                "代码": ["000001"],
                "名称": ["趋势股"],
                "最新价": [18.3],
                "涨跌幅": [2.0],
                "成交额": [100_000_000],
                "所属行业": ["人工智能"],
            }
        )
        candidates = scan_trend_tracking(daily, quotes_df=quotes, top_n=5, min_score=40)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].sector, "人工智能")

        bt_daily = pd.DataFrame(
            {
                "date": pd.date_range(start="2026-05-01", periods=8, freq="B"),
                "open": [10, 10, 10.5, 10.8, 11.0, 11.2, 11.1, 11.3],
                "high": [10.2, 10.6, 10.9, 11.1, 11.4, 11.5, 11.3, 11.6],
                "low": [9.9, 9.8, 10.2, 10.6, 10.8, 11.0, 10.9, 11.1],
                "close": [10, 10.4, 10.8, 11.0, 11.2, 11.1, 11.3, 11.5],
            }
        )
        result = BacktestEngine().run_fixed_holding(
            signals=[{"code": "000001", "name": "趋势股", "signal_date": "20260501"}],
            daily_by_code={"000001": bt_daily},
            holding_days=5,
            stop_loss_pct=0.05,
        )

        self.assertEqual(result.summary["total_trades"], 1)
        self.assertGreater(result.trades[0]["return_pct"], 0)


if __name__ == "__main__":
    unittest.main()
