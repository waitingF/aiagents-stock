"""Service functions for stock analysis workflows.

This module keeps analysis orchestration free of Streamlit so it can be
reused by batch jobs, CLI commands, tests, and future API entrypoints.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from src.aiagents_stock.core import config
from src.aiagents_stock.core.parallel import ParallelTask, run_parallel_tasks
from src.aiagents_stock.features.stock_analysis.agents import StockAnalysisAgents
from src.aiagents_stock.features.stock_analysis.data import StockDataFetcher
from src.aiagents_stock.features.stock_analysis.repository import db


DEFAULT_ANALYSTS_CONFIG = {
    "technical": True,
    "fundamental": True,
    "fund_flow": True,
    "risk": True,
    "sentiment": False,
    "news": False,
}


def fetch_stock_data(symbol: str, period: str) -> Tuple[Dict[str, Any], Any, Optional[Dict[str, Any]]]:
    """Fetch stock info, historical data with indicators, and latest indicators."""
    fetcher = StockDataFetcher()
    stock_info = fetcher.get_stock_info(symbol)
    stock_data = fetcher.get_stock_data(symbol, period)

    if isinstance(stock_data, dict) and "error" in stock_data:
        return stock_info, None, None

    stock_data_with_indicators = fetcher.calculate_technical_indicators(stock_data)
    indicators = fetcher.get_latest_indicators(stock_data_with_indicators)

    return stock_info, stock_data_with_indicators, indicators


def parse_stock_list(stock_input: str) -> List[str]:
    """Parse stock codes from newline, comma, or whitespace separated text."""
    if not stock_input or not stock_input.strip():
        return []

    stock_list: List[str] = []
    for line in stock_input.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        if "," in line:
            codes = [code.strip() for code in line.split(",")]
            stock_list.extend([code for code in codes if code])
        elif " " in line:
            codes = [code.strip() for code in line.split()]
            stock_list.extend([code for code in codes if code])
        else:
            stock_list.append(line)

    seen = set()
    unique_list = []
    for code in stock_list:
        if code not in seen:
            seen.add(code)
            unique_list.append(code)

    return unique_list


def _fetch_supplemental_analysis_data(
    symbol: str,
    stock_data: Any,
    enabled_analysts_config: Dict[str, bool],
    data_fetch_max_workers: int = 6,
) -> Tuple[Any, Any, Any, Any, Any, Any]:
    """Fetch non-K-line analysis data sources concurrently."""
    fetcher = StockDataFetcher()
    is_chinese_stock = fetcher._is_chinese_stock(symbol)

    def financial_failure(exc: Exception) -> Dict[str, str]:
        return {"error": f"获取财务数据失败: {str(exc)}"}

    def optional_failure(_: Exception) -> None:
        return None

    def fetch_financial_data() -> Any:
        return StockDataFetcher().get_financial_data(symbol)

    def fetch_quarterly_data() -> Any:
        from src.aiagents_stock.features.stock_analysis.quarterly_report_data import QuarterlyReportDataFetcher

        return QuarterlyReportDataFetcher().get_quarterly_reports(symbol)

    def fetch_fund_flow_data() -> Any:
        from src.aiagents_stock.features.stock_analysis.fund_flow import FundFlowAkshareDataFetcher

        return FundFlowAkshareDataFetcher().get_fund_flow_data(symbol)

    def fetch_sentiment_data() -> Any:
        from src.aiagents_stock.features.stock_analysis.market_sentiment_data import MarketSentimentDataFetcher

        return MarketSentimentDataFetcher().get_market_sentiment_data(symbol, stock_data)

    def fetch_news_data() -> Any:
        from src.aiagents_stock.features.stock_analysis.qstock_news_data import QStockNewsDataFetcher

        return QStockNewsDataFetcher().get_stock_news(symbol)

    def fetch_risk_data() -> Any:
        return StockDataFetcher().get_risk_data(symbol)

    task_specs: List[Tuple[str, Callable[[], Any], Callable[[Exception], Any]]] = [
        ("financial_data", fetch_financial_data, financial_failure),
    ]

    if enabled_analysts_config.get("fundamental", True) and is_chinese_stock:
        task_specs.append(("quarterly_data", fetch_quarterly_data, optional_failure))

    if enabled_analysts_config.get("fund_flow", True) and is_chinese_stock:
        task_specs.append(("fund_flow_data", fetch_fund_flow_data, optional_failure))

    if enabled_analysts_config.get("sentiment", False) and is_chinese_stock:
        task_specs.append(("sentiment_data", fetch_sentiment_data, optional_failure))

    if enabled_analysts_config.get("news", False) and is_chinese_stock:
        task_specs.append(("news_data", fetch_news_data, optional_failure))

    if enabled_analysts_config.get("risk", True) and is_chinese_stock:
        task_specs.append(("risk_data", fetch_risk_data, optional_failure))

    results = {
        "financial_data": None,
        "quarterly_data": None,
        "fund_flow_data": None,
        "sentiment_data": None,
        "news_data": None,
        "risk_data": None,
    }
    max_workers = max(1, min(len(task_specs), data_fetch_max_workers))
    task_results = run_parallel_tasks(
        [
            ParallelTask(task_key, fetch_func, on_error=failure_handler)
            for task_key, fetch_func, failure_handler in task_specs
        ],
        max_workers=max_workers,
    )
    results.update(task_results)

    return (
        results["financial_data"],
        results["quarterly_data"],
        results["fund_flow_data"],
        results["sentiment_data"],
        results["news_data"],
        results["risk_data"],
    )


def analyze_single_stock_for_batch(
    symbol: str,
    period: str,
    enabled_analysts_config: Optional[Dict[str, bool]] = None,
    selected_model: Optional[str] = None,
    data_fetch_max_workers: int = 6,
) -> Dict[str, Any]:
    """Analyze a single stock for batch workflows and return structured results."""
    try:
        if selected_model is None:
            selected_model = config.DEFAULT_MODEL_NAME

        if enabled_analysts_config is None:
            enabled_analysts_config = DEFAULT_ANALYSTS_CONFIG.copy()

        stock_info, stock_data, indicators = fetch_stock_data(symbol, period)

        if "error" in stock_info:
            return {"symbol": symbol, "error": stock_info["error"], "success": False}

        if stock_data is None:
            return {"symbol": symbol, "error": "无法获取股票历史数据", "success": False}

        (
            financial_data,
            quarterly_data,
            fund_flow_data,
            sentiment_data,
            news_data,
            risk_data,
        ) = _fetch_supplemental_analysis_data(
            symbol,
            stock_data,
            enabled_analysts_config,
            data_fetch_max_workers=data_fetch_max_workers,
        )

        agents = StockAnalysisAgents(model=selected_model)
        agents_results = agents.run_multi_agent_analysis(
            stock_info,
            stock_data,
            indicators,
            financial_data,
            fund_flow_data,
            sentiment_data,
            news_data,
            quarterly_data,
            risk_data,
            enabled_analysts=enabled_analysts_config,
        )

        discussion_result = agents.conduct_team_discussion(agents_results, stock_info)
        final_decision = agents.make_final_decision(discussion_result, stock_info, indicators)

        saved_to_db = False
        db_error = None
        try:
            record_id = db.save_analysis(
                symbol=stock_info.get("symbol", ""),
                stock_name=stock_info.get("name", ""),
                period=period,
                stock_info=stock_info,
                agents_results=agents_results,
                discussion_result=discussion_result,
                final_decision=final_decision,
            )
            saved_to_db = True
            print(f"✅ {symbol} 成功保存到数据库，记录ID: {record_id}")
        except Exception as exc:
            db_error = str(exc)
            print(f"❌ {symbol} 保存到数据库失败: {db_error}")

        return {
            "symbol": symbol,
            "success": True,
            "stock_info": stock_info,
            "indicators": indicators,
            "agents_results": agents_results,
            "discussion_result": discussion_result,
            "final_decision": final_decision,
            "saved_to_db": saved_to_db,
            "db_error": db_error,
        }

    except Exception as exc:
        return {"symbol": symbol, "error": str(exc), "success": False}
