import pandas as pd

from src.aiagents_stock.features.macro_analysis import data as macro_data
from src.aiagents_stock.features.macro_analysis.data import MacroAnalysisDataFetcher


class FakeMacroTushareApi:
    def __init__(self) -> None:
        self.calls = []

    def cn_pmi(self, fields=None):
        self.calls.append(("cn_pmi", fields))
        return pd.DataFrame(
            [
                {
                    "month": "202604",
                    "pmi010000": 50.4,
                    "pmi020100": 51.1,
                    "pmi030000": 51.3,
                },
                {
                    "month": "202603",
                    "pmi010000": 50.8,
                    "pmi020100": 50.6,
                    "pmi030000": 51.0,
                },
            ]
        )

    def cn_gdp(self, fields=None):
        self.calls.append(("cn_gdp", fields))
        return pd.DataFrame(
            [
                {"quarter": "2026Q1", "gdp": 260.0, "gdp_yoy": 5.0},
                {"quarter": "2025Q4", "gdp": 1000.0, "gdp_yoy": 4.8},
                {"quarter": "2025Q3", "gdp": 750.0, "gdp_yoy": 4.7},
                {"quarter": "2025Q2", "gdp": 500.0, "gdp_yoy": 4.6},
                {"quarter": "2025Q1", "gdp": 240.0, "gdp_yoy": 4.5},
            ]
        )


def test_tushare_pmi_fields_are_mapped_and_cached(tmp_path):
    fake_api = FakeMacroTushareApi()
    fetcher = MacroAnalysisDataFetcher(
        tushare_api=fake_api,
        cache_path=tmp_path / "macro_cache.json",
    )

    series = fetcher._fetch_macro_series(
        "composite_pmi",
        fetcher.NBS_SERIES_CONFIG["composite_pmi"],
    )

    assert series[0]["period_code"] == "202604"
    assert series[0]["value"] == 51.3
    assert series[0]["source"] == "tushare"
    assert series[0]["is_proxy"] is False
    assert fake_api.calls == [("cn_pmi", "month,pmi010000,pmi020100,pmi030000")]

    cached = fetcher._fetch_macro_series(
        "composite_pmi",
        fetcher.NBS_SERIES_CONFIG["composite_pmi"],
    )
    assert cached[0]["from_cache"] is True
    assert fake_api.calls == [("cn_pmi", "month,pmi010000,pmi020100,pmi030000")]


def test_industrial_yoy_uses_akshare_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(
        macro_data.ak,
        "macro_china_gyzjz",
        lambda: pd.DataFrame(
            [
                {"月份": "2026年04月份", "同比增长": 5.6, "累计增长": 6.1},
                {"月份": "2026年03月份", "同比增长": 6.0, "累计增长": 6.2},
            ]
        ),
        raising=False,
    )

    fetcher = MacroAnalysisDataFetcher(cache_path=tmp_path / "macro_cache.json")
    series = fetcher._fetch_macro_series(
        "industrial_yoy",
        fetcher.NBS_SERIES_CONFIG["industrial_yoy"],
    )

    assert series[0]["period_code"] == "202604"
    assert series[0]["value"] == 5.6
    assert series[0]["source"] == "akshare"
    assert series[0]["is_proxy"] is False


def test_gdp_qoq_proxy_is_marked_as_proxy(tmp_path, monkeypatch):
    fake_api = FakeMacroTushareApi()
    fetcher = MacroAnalysisDataFetcher(
        tushare_api=fake_api,
        cache_path=tmp_path / "macro_cache.json",
    )
    monkeypatch.setattr(
        fetcher,
        "_fetch_stats_release_series",
        lambda key, config: (_ for _ in ()).throw(RuntimeError("release unavailable")),
    )

    series = fetcher._fetch_macro_series(
        "gdp_qoq",
        fetcher.NBS_SERIES_CONFIG["gdp_qoq"],
    )

    assert series[0]["period_code"] == "2026Q1"
    assert series[0]["value"] == 4.0
    assert series[0]["source"] == "tushare_proxy"
    assert series[0]["is_proxy"] is True
    assert "非官方季调环比" in series[0]["note"]


def test_stats_release_gdp_qoq_table_parser_uses_official_value(tmp_path, monkeypatch):
    fetcher = MacroAnalysisDataFetcher(cache_path=tmp_path / "macro_cache.json")
    monkeypatch.setattr(
        fetcher,
        "_find_stats_release_urls",
        lambda key: ["https://www.stats.gov.cn/example.html"],
    )
    monkeypatch.setattr(
        fetcher,
        "_fetch_stats_release_text",
        lambda url: (
            "",
            "2026年一季度国内生产总值初步核算结果 表 3 GDP 环比增长速度 "
            "单位： % 年份 1 季度 2 季度 3 季度 4 季度 "
            "2025 1.1 1.1 1.1 1.2 2026 1.3 注：环比增长速度为经季节调整后与上一季度对比的增长速度。",
        ),
    )

    series = fetcher._fetch_macro_series(
        "gdp_qoq",
        fetcher.NBS_SERIES_CONFIG["gdp_qoq"],
    )

    assert series[0]["period_code"] == "2026Q1"
    assert series[0]["value"] == 1.3
    assert series[0]["source"] == "stats_release"
    assert series[0]["is_official"] is True
    assert series[0]["is_proxy"] is False
