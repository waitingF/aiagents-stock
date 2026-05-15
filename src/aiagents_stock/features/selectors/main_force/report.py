"""Report helpers for the main-force selector."""

from __future__ import annotations

import base64
import html
from datetime import datetime
from typing import Any, Dict

import pandas as pd


def _safe(value: Any, default: str = "N/A") -> str:
    if value is None or value == "":
        return default
    return str(value)


def generate_main_force_markdown_report(analyzer: Any, result: Dict[str, Any]) -> str:
    """Generate a Markdown report from main-force selector output."""

    result = result or {}
    params = result.get("params") or {}
    recommendations = result.get("final_recommendations") or []
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# 主力选股AI分析报告",
        "",
        f"**生成时间**: {current_time}",
        "",
        "## 选股参数",
        "",
        "| 项目 | 值 |",
        "| --- | --- |",
        f"| 起始日期 | {_safe(params.get('start_date'))} |",
        f"| 市值范围 | {_safe(params.get('min_market_cap'), '50')}亿 - {_safe(params.get('max_market_cap'), '5000')}亿 |",
        f"| 最大涨跌幅 | {_safe(params.get('max_range_change'), '50')}% |",
        f"| 初始数据量 | {_safe(result.get('total_fetched'), '0')} |",
        f"| 筛选后数量 | {_safe(result.get('filtered_count'), '0')} |",
        f"| 最终推荐 | {len(recommendations)} |",
        "",
        "## AI分析师报告",
        "",
    ]

    for attr, title in [
        ("fund_flow_analysis", "资金流向分析师"),
        ("industry_analysis", "行业板块及市场热点分析师"),
        ("fundamental_analysis", "财务基本面分析师"),
    ]:
        content = getattr(analyzer, attr, None) if analyzer is not None else None
        if content:
            lines.extend([f"### {title}", "", str(content), ""])

    lines.extend(["## 精选推荐股票", ""])
    if recommendations:
        for rec in recommendations:
            stock_data = rec.get("stock_data") or {}
            lines.extend(
                [
                    f"### 第{_safe(rec.get('rank'))}名 {rec.get('symbol', '')} - {rec.get('name', '')}",
                    "",
                    f"**推荐理由**: {_safe(rec.get('reason'), '暂无')}",
                    "",
                    f"- 所属行业: {_safe(stock_data.get('industry'))}",
                    f"- 市值: {_safe(stock_data.get('market_cap'))}",
                    f"- 主力资金流向: {_safe(stock_data.get('main_fund_inflow'))}",
                    f"- 区间涨跌幅: {_safe(stock_data.get('range_change'))}",
                    f"- 市盈率: {_safe(stock_data.get('pe_ratio'))}",
                    f"- 市净率: {_safe(stock_data.get('pb_ratio'))}",
                    "",
                ]
            )
    else:
        lines.extend(["暂无推荐股票", ""])

    raw_stocks = getattr(analyzer, "raw_stocks", None) if analyzer is not None else None
    if isinstance(raw_stocks, pd.DataFrame) and not raw_stocks.empty:
        lines.extend(["## 候选股票列表", ""])
        preview = raw_stocks.head(100)
        columns = list(preview.columns[:8])
        lines.append("| 序号 | " + " | ".join(map(str, columns)) + " |")
        lines.append("| --- | " + " | ".join("---" for _ in columns) + " |")
        for index, (_, row) in enumerate(preview.iterrows(), 1):
            values = [str(index)] + [_safe(row.get(col), "") for col in columns]
            lines.append("| " + " | ".join(values) + " |")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "本报告由AI系统生成，仅供研究参考，不构成投资建议。投资有风险，入市需谨慎。",
        ]
    )
    return "\n".join(lines)


def generate_html_content(markdown_content: str) -> str:
    body = html.escape(markdown_content).replace("\n", "<br />\n")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>主力选股AI分析报告</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.65; max-width: 1120px; margin: 0 auto; padding: 32px; color: #111827; }}
  </style>
</head>
<body>{body}</body>
</html>"""


def create_download_link(content: str, filename: str, link_text: str = "下载Markdown报告") -> str:
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return f'<a href="data:text/markdown;base64,{b64}" download="{html.escape(filename)}">{html.escape(link_text)}</a>'


def create_html_download_link(content: str, filename: str, link_text: str = "下载HTML报告") -> str:
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return f'<a href="data:text/html;base64,{b64}" download="{html.escape(filename)}">{html.escape(link_text)}</a>'


def display_report_download_section(*_args: Any, **_kwargs: Any) -> None:
    raise RuntimeError("Streamlit UI has been removed. Use FastAPI report endpoints or React actions instead.")
