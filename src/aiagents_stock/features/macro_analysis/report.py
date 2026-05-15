"""Markdown rendering helpers for macro analysis reports."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def generate_macro_analysis_markdown(result_data: Dict[str, Any]) -> str:
    """Build a readable markdown report from macro analysis results."""
    parts: List[str] = [
        "# 宏观分析报告",
        f"**分析时间**: {result_data.get('timestamp', '-')}",
        "**分析框架**: 宏观总量 × 政策流动性 × 行业映射 × 优质标的",
    ]

    if result_data.get("error"):
        parts.append(f"## 分析异常\n{result_data.get('error')}")

    errors = result_data.get("errors") or []
    if errors:
        parts.append("## 数据提示\n" + "\n".join(f"- {item}" for item in errors[:8]))

    agents = result_data.get("agents_analysis") or {}
    sector_view = result_data.get("sector_view") or {}
    stock_view = result_data.get("stock_view") or {}

    chief = _agent_analysis(agents, "chief")
    if chief:
        parts.append(f"## 一、首席策略观点\n{chief}")

    macro = _agent_analysis(agents, "macro")
    if macro:
        parts.append(f"## 二、宏观总量分析\n{macro}")

    policy = _agent_analysis(agents, "policy")
    if policy:
        parts.append(f"## 三、政策与流动性\n{policy}")

    sector_parts: List[str] = []
    if sector_view.get("market_view"):
        sector_parts.append(f"**市场判断**: {sector_view.get('market_view')}")
    sector_parts.extend(_format_sector_list("看多板块", sector_view.get("bullish_sectors")))
    sector_parts.extend(_format_sector_list("看空板块", sector_view.get("bearish_sectors")))
    watch_signals = sector_view.get("watch_signals") or []
    if watch_signals:
        sector_parts.append("**观察信号**")
        sector_parts.extend(f"- {item}" for item in watch_signals[:8])
    sector_analysis = _agent_analysis(agents, "sector")
    if sector_analysis:
        sector_parts.append(sector_analysis)
    if sector_parts:
        parts.append("## 四、行业映射\n" + "\n\n".join(sector_parts))

    stock_parts: List[str] = []
    stock_parts.extend(_format_stock_list("推荐标的", stock_view.get("recommended_stocks")))
    stock_parts.extend(_format_stock_list("观察名单", stock_view.get("watchlist")))
    stock_analysis = _agent_analysis(agents, "stock")
    if stock_analysis:
        stock_parts.append(stock_analysis)
    if stock_parts:
        parts.append("## 五、优质标的\n" + "\n\n".join(stock_parts))

    parts.append("## 风险提示\n宏观分析用于策略研判和组合管理输入，不构成任何确定性收益承诺。")
    return "\n\n".join(part for part in parts if part)


def extract_macro_analysis_summary(result_data: Dict[str, Any], limit: int = 500) -> str:
    if result_data.get("error"):
        return _compact(f"分析失败: {result_data.get('error')}", limit)

    sector_view = result_data.get("sector_view") or {}
    stock_view = result_data.get("stock_view") or {}
    agents = result_data.get("agents_analysis") or {}

    pieces: List[str] = []
    if sector_view.get("market_view"):
        pieces.append(str(sector_view["market_view"]))

    bullish = _names_from_items(sector_view.get("bullish_sectors"), "sector")[:4]
    if bullish:
        pieces.append("看多板块: " + "、".join(bullish))

    stocks = _names_from_items(stock_view.get("recommended_stocks"), "name")[:4]
    if stocks:
        pieces.append("推荐标的: " + "、".join(stocks))

    chief = _first_paragraph(_agent_analysis(agents, "chief"))
    if chief:
        pieces.append(chief)

    return _compact("；".join(pieces) or "宏观分析已完成。", limit)


def _agent_analysis(agents: Dict[str, Any], key: str) -> str:
    agent = agents.get(key) if isinstance(agents, dict) else None
    if not isinstance(agent, dict):
        return ""
    return str(agent.get("analysis") or "").strip()


def _format_sector_list(title: str, items: Any) -> List[str]:
    rows = [item for item in _iter_dicts(items)]
    if not rows:
        return []
    lines = [f"**{title}**"]
    for item in rows[:8]:
        name = item.get("sector") or item.get("name") or "-"
        confidence = item.get("confidence")
        logic = item.get("logic") or item.get("reason") or ""
        suffix = f"（置信度 {confidence}）" if confidence not in (None, "") else ""
        lines.append(f"- {name}{suffix}: {logic}")
    return lines


def _format_stock_list(title: str, items: Any) -> List[str]:
    rows = [item for item in _iter_dicts(items)]
    if not rows:
        return []
    lines = [f"**{title}**"]
    for item in rows[:10]:
        code = item.get("code") or ""
        name = item.get("name") or item.get("stock_name") or "-"
        sector = item.get("sector") or ""
        reason = item.get("reason") or item.get("logic") or ""
        label = f"{name}({code})" if code else str(name)
        if sector:
            label = f"{label} / {sector}"
        lines.append(f"- {label}: {reason}")
    return lines


def _iter_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _names_from_items(value: Any, key: str) -> List[str]:
    return [str(item.get(key)) for item in _iter_dicts(value) if item.get(key)]


def _first_paragraph(text: str) -> str:
    for part in str(text or "").splitlines():
        part = part.strip()
        if part:
            return part
    return ""


def _compact(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    return clean[:limit].rstrip() if len(clean) > limit else clean
