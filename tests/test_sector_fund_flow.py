from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.aiagents_stock.features.sector_strategy.fund_flow import SectorFundFlowAnalyzer
from src.aiagents_stock.features.sector_strategy.fund_flow_repository import SectorFundFlowRepository


class FakeTushareSectorFundFlowApi:
    def __init__(self) -> None:
        self.index_classify_calls = []
        self.index_member_all_calls = []
        self.moneyflow_calls = []
        self.daily_calls = []

    def trade_cal(self, **kwargs):
        return pd.DataFrame(
            [
                {"cal_date": "20260511", "is_open": 1},
                {"cal_date": "20260512", "is_open": 1},
            ]
        )

    def index_classify(self, **kwargs):
        self.index_classify_calls.append(kwargs)
        return pd.DataFrame(
            [
                {"index_code": "801001", "industry_name": "科技服务", "level": "L2", "is_pub": "1"},
                {"index_code": "801002", "industry_name": "金融服务", "level": "L2", "is_pub": "1"},
            ]
        )

    def index_member_all(self, **kwargs):
        self.index_member_all_calls.append(kwargs)
        code = str(kwargs.get("l2_code", "")).replace(".SI", "")
        if code == "801001":
            return pd.DataFrame(
                [
                    {"l2_code": "801001.SI", "l2_name": "科技服务", "ts_code": "000001.SZ", "name": "科技A"},
                    {"l2_code": "801001.SI", "l2_name": "科技服务", "ts_code": "000002.SZ", "name": "科技B"},
                ]
            )
        if code == "801002":
            return pd.DataFrame(
                [
                    {"l2_code": "801002.SI", "l2_name": "金融服务", "ts_code": "000003.SZ", "name": "金融A"},
                ]
            )
        return pd.DataFrame()

    def moneyflow(self, **kwargs):
        trade_date = kwargs.get("trade_date")
        self.moneyflow_calls.append(trade_date)
        rows_by_date = {
            "20260511": [
                _flow_row("000001.SZ", 100, 60),
                _flow_row("000002.SZ", -20, -10),
                _flow_row("000003.SZ", 50, 30),
            ],
            "20260512": [
                _flow_row("000001.SZ", 40, 20),
                _flow_row("000002.SZ", 30, 15),
                _flow_row("000003.SZ", -10, -5),
            ],
        }
        return pd.DataFrame(rows_by_date.get(trade_date, []))

    def daily(self, **kwargs):
        trade_date = kwargs.get("trade_date")
        self.daily_calls.append(trade_date)
        rows_by_date = {
            "20260511": [
                {"ts_code": "000001.SZ", "close": 10.0, "pct_chg": 1.0},
                {"ts_code": "000002.SZ", "close": 20.0, "pct_chg": -1.0},
                {"ts_code": "000003.SZ", "close": 30.0, "pct_chg": 0.5},
            ],
            "20260512": [
                {"ts_code": "000001.SZ", "close": 10.5, "pct_chg": 5.0},
                {"ts_code": "000002.SZ", "close": 21.0, "pct_chg": 5.0},
                {"ts_code": "000003.SZ", "close": 29.0, "pct_chg": -3.0},
            ],
        }
        return pd.DataFrame(rows_by_date.get(trade_date, []))


def _flow_row(ts_code: str, net: float, main: float) -> dict:
    return {
        "ts_code": ts_code,
        "buy_sm_amount": max(net - main, 0),
        "sell_sm_amount": max(-(net - main), 0),
        "buy_md_amount": 0,
        "sell_md_amount": 0,
        "buy_lg_amount": max(main, 0),
        "sell_lg_amount": max(-main, 0),
        "buy_elg_amount": 0,
        "sell_elg_amount": 0,
        "net_mf_amount": net,
    }


class SectorFundFlowAnalyzerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.repository = SectorFundFlowRepository(Path(self.tmpdir.name) / "sector_fund_flow.db")
        self.api = FakeTushareSectorFundFlowApi()
        self.analyzer = SectorFundFlowAnalyzer(
            tushare_api=self.api,
            repository=self.repository,
            today_provider=lambda: "20260512",
        )

    def test_analyze_aggregates_sector_and_stock_fund_flow(self):
        result = self.analyzer.analyze(
            range_type="custom",
            start_date="20260511",
            end_date="20260512",
            sector_level="L2",
            top_sectors=5,
            top_stocks=2,
            max_workers=1,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["sector_source"], "SW2021")
        self.assertEqual(result["sector_level"], "L2")
        self.assertEqual(result["summary"]["trade_days_count"], 2)
        self.assertEqual(result["summary"]["sector_count"], 2)
        self.assertEqual(result["summary"]["total_net_mf_amount"], 190)

        top_sector = result["sector_rank"][0]
        self.assertEqual(top_sector["sector_name"], "科技服务")
        self.assertEqual(top_sector["net_mf_amount"], 150)
        self.assertEqual(top_sector["main_net_amount"], 85)
        self.assertEqual(top_sector["positive_stock_count"], 2)
        self.assertEqual(top_sector["top_stocks"][0]["ts_code"], "000001.SZ")
        self.assertEqual(top_sector["top_stocks"][0]["net_mf_amount"], 140)
        self.assertEqual(top_sector["top_stocks"][0]["close"], 10.5)
        self.assertEqual(top_sector["top_stocks"][0]["pct_chg"], 5.0)

        self.assertEqual(result["outflow_rank"][0]["sector_name"], "金融服务")
        self.assertEqual(result["report_id"], 1)

        saved = self.repository.get_report(1)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["result"]["sector_rank"][0]["sector_name"], "科技服务")

    def test_analyze_reuses_daily_cache_without_refetching_moneyflow(self):
        first = self.analyzer.analyze(
            range_type="custom",
            start_date="20260511",
            end_date="20260512",
            max_workers=1,
        )
        self.assertTrue(first["success"])
        self.assertEqual(self.api.moneyflow_calls, ["20260511", "20260512"])
        self.assertEqual(self.api.daily_calls, ["20260511", "20260512"])

        second = self.analyzer.analyze(
            range_type="custom",
            start_date="20260511",
            end_date="20260512",
            max_workers=1,
        )

        self.assertTrue(second["success"])
        self.assertEqual(self.api.moneyflow_calls, ["20260511", "20260512"])
        self.assertEqual(self.api.daily_calls, ["20260511", "20260512"])
        self.assertEqual(second["diagnostics"]["cached_dates"], ["20260511", "20260512"])
        self.assertEqual(len(self.repository.list_reports()), 2)


if __name__ == "__main__":
    unittest.main()
