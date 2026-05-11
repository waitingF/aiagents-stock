"""Service functions for stock analysis workflows.

This module keeps analysis orchestration free of Streamlit so it can be
reused by batch jobs, CLI commands, tests, and future API entrypoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from src.aiagents_stock.core import config
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


def analyze_single_stock_for_batch(
    symbol: str,
    period: str,
    enabled_analysts_config: Optional[Dict[str, bool]] = None,
    selected_model: Optional[str] = None,
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

        fetcher = StockDataFetcher()
        financial_data = fetcher.get_financial_data(symbol)

        quarterly_data = None
        enable_fundamental = enabled_analysts_config.get("fundamental", True)
        if enable_fundamental and fetcher._is_chinese_stock(symbol):
            try:
                from src.aiagents_stock.features.stock_analysis.quarterly_report_data import QuarterlyReportDataFetcher

                quarterly_fetcher = QuarterlyReportDataFetcher()
                quarterly_data = quarterly_fetcher.get_quarterly_reports(symbol)
            except Exception:
                pass

        enable_fund_flow = enabled_analysts_config.get("fund_flow", True)
        enable_sentiment = enabled_analysts_config.get("sentiment", False)
        enable_news = enabled_analysts_config.get("news", False)

        fund_flow_data = None
        if enable_fund_flow and fetcher._is_chinese_stock(symbol):
            try:
                from src.aiagents_stock.features.stock_analysis.fund_flow import FundFlowAkshareDataFetcher

                fund_flow_fetcher = FundFlowAkshareDataFetcher()
                fund_flow_data = fund_flow_fetcher.get_fund_flow_data(symbol)
            except Exception:
                pass

        sentiment_data = None
        if enable_sentiment and fetcher._is_chinese_stock(symbol):
            try:
                from src.aiagents_stock.features.stock_analysis.market_sentiment_data import MarketSentimentDataFetcher

                sentiment_fetcher = MarketSentimentDataFetcher()
                sentiment_data = sentiment_fetcher.get_market_sentiment_data(symbol, stock_data)
            except Exception:
                pass

        news_data = None
        if enable_news and fetcher._is_chinese_stock(symbol):
            try:
                from src.aiagents_stock.features.stock_analysis.qstock_news_data import QStockNewsDataFetcher

                news_fetcher = QStockNewsDataFetcher()
                news_data = news_fetcher.get_stock_news(symbol)
            except Exception:
                pass

        risk_data = None
        enable_risk = enabled_analysts_config.get("risk", True)
        if enable_risk and fetcher._is_chinese_stock(symbol):
            try:
                risk_data = fetcher.get_risk_data(symbol)
            except Exception:
                pass

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
