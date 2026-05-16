from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from src.aiagents_stock.features.longhubang.repository import LonghubangDatabase
from src.aiagents_stock.features.sector_strategy.repository import SectorStrategyDatabase


class StrategyReportPersistenceTest(unittest.TestCase):
    def setUp(self):
        try:
            import numpy as np
            import pandas as pd
        except ImportError as exc:
            raise unittest.SkipTest("numpy/pandas are required for persistence serialization tests") from exc

        self.np = np
        self.pd = pd

    def test_sector_strategy_report_saves_json_safe_analysis_result(self):
        np = self.np
        pd = self.pd
        with tempfile.TemporaryDirectory() as tmpdir:
            db = SectorStrategyDatabase(str(Path(tmpdir) / "sector_strategy.db"))

            report_id = db.save_analysis_report(
                data_date_range="2026-05-16",
                analysis_content={
                    "np_int": np.int64(7),
                    "nan": float("nan"),
                    "stamp": pd.Timestamp("2026-05-16 09:30:00"),
                    "frame": pd.DataFrame([{"sector": "AI", "score": np.float64(0.88), "empty": math.nan}]),
                },
                recommended_sectors=[{"sector_name": "AI", "score": np.float64(0.88)}],
                summary="test summary",
                confidence_score=np.float64(0.91),
                risk_level="medium",
                investment_horizon="short",
                market_outlook="neutral",
            )

            report = db.get_analysis_report(report_id)
            parsed = report["analysis_content_parsed"]
            reports = db.get_analysis_reports()

            self.assertEqual(parsed["np_int"], 7)
            self.assertIsNone(parsed["nan"])
            self.assertEqual(parsed["stamp"], "2026-05-16T09:30:00")
            self.assertEqual(parsed["frame"]["type"], "dataframe")
            self.assertIsNone(parsed["frame"]["records"][0]["empty"])
            self.assertEqual(report["recommended_sectors_parsed"][0]["score"], 0.88)
            self.assertIsInstance(reports, list)
            self.assertEqual(reports[0]["analysis_content_parsed"]["np_int"], 7)

    def test_longhubang_report_saves_json_safe_analysis_result(self):
        np = self.np
        pd = self.pd
        with tempfile.TemporaryDirectory() as tmpdir:
            db = LonghubangDatabase(str(Path(tmpdir) / "longhubang.db"))

            report_id = db.save_analysis_report(
                data_date_range="2026-05-16",
                analysis_content={
                    "scoring_ranking": pd.DataFrame(
                        [{"code": "000001", "score": np.float64(86.5), "flag": np.bool_(True)}]
                    ),
                    "generated_at": pd.Timestamp("2026-05-16 10:00:00"),
                },
                recommended_stocks=[{"code": "000001", "score": np.float64(86.5)}],
                summary="test summary",
            )

            report = db.get_analysis_report(report_id)
            parsed = report["analysis_content_parsed"]
            reports = db.get_analysis_reports()

            self.assertEqual(parsed["generated_at"], "2026-05-16T10:00:00")
            self.assertEqual(parsed["scoring_ranking"]["type"], "dataframe")
            self.assertEqual(parsed["scoring_ranking"]["records"][0]["score"], 86.5)
            self.assertIs(parsed["scoring_ranking"]["records"][0]["flag"], True)
            self.assertEqual(report["recommended_stocks"][0]["score"], 86.5)
            self.assertIsInstance(reports, list)
            self.assertEqual(reports[0]["analysis_content_parsed"]["generated_at"], "2026-05-16T10:00:00")


if __name__ == "__main__":
    unittest.main()
