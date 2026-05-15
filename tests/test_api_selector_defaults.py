import sys
import types
from unittest.mock import Mock, patch

from src.aiagents_stock.api.routes import _run_selector, _selected_codes


def _main_force_module(analyzer_cls):
    module = types.ModuleType("src.aiagents_stock.features.selectors.main_force.analysis")
    module.MainForceAnalyzer = analyzer_cls
    return {"src.aiagents_stock.features.selectors.main_force.analysis": module}


def test_main_force_selector_applies_defaults_when_frontend_omits_filters():
    analyzer_cls = Mock()
    analyzer = analyzer_cls.return_value
    analyzer.run_full_analysis.return_value = {"success": True}

    with patch.dict(sys.modules, _main_force_module(analyzer_cls)):
        result = _run_selector("main-force", {"top_n": 6, "final_n": 6})

    assert result["success"] is True
    analyzer.run_full_analysis.assert_called_once_with(
        start_date=None,
        days_ago=90,
        final_n=6,
        max_range_change=30.0,
        min_market_cap=50.0,
        max_market_cap=5000.0,
    )


def test_main_force_selector_uses_start_date_without_days_offset():
    analyzer_cls = Mock()
    analyzer = analyzer_cls.return_value
    analyzer.run_full_analysis.return_value = {"success": True}

    with patch.dict(sys.modules, _main_force_module(analyzer_cls)):
        _run_selector("main-force", {"start_date": "2026-05-01"})

    assert analyzer.run_full_analysis.call_args.kwargs["start_date"] == "2026-05-01"
    assert analyzer.run_full_analysis.call_args.kwargs["days_ago"] is None


def test_selected_codes_normalizes_array_values():
    assert _selected_codes({"selected_codes": ["600519.sh", " 000001.sz ", ""]}) == ["600519.SH", "000001.SZ"]


def test_selected_codes_splits_comma_string():
    assert _selected_codes({"selected_codes": "600519.sh，000001.sz"}) == ["600519.SH", "000001.SZ"]
