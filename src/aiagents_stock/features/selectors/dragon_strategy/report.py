"""Markdown report rendering for dragon strategy results."""

from __future__ import annotations

from typing import Any

from src.aiagents_stock.features.selectors.dragon_strategy.models import DragonStrategyReport


def _condition_line(items: dict[str, bool]) -> str:
    if not items:
        return "-"
    return "；".join(f"{key}:{'通过' if value else '未过'}" for key, value in items.items())


def format_markdown_report(report: DragonStrategyReport, position: dict[str, Any] | None = None) -> str:
    market = report.market
    lines = [
        f"# 龙头战法日报 {report.report_date}",
        "",
        "## 市场环境",
        f"- 交易日：{'是' if market.is_trade_day else '否'}",
        f"- 环境结论：{market.message}",
        f"- 情绪阶段：{market.stage}，情绪分：{market.score}",
        f"- 涨停/跌停/最高连板：{market.limit_up_count}/{market.limit_down_count}/{market.max_lianban}",
        f"- 炸板率：{market.explode_rate:.1f}%",
        f"- 核心条件：{_condition_line(market.core_conditions)}",
        f"- 辅助条件：{_condition_line(market.assist_conditions)}",
    ]
    if position:
        caps = position.get("strategy_caps", {})
        lines.extend(
            [
                "",
                "## 仓位框架",
                f"- 情绪可用率：{position.get('usage_rate', 0)}%",
                f"- 策略参考总仓位：{position.get('total_position', 0)}%",
                f"- 龙头仓位上限：{caps.get('龙头战法', 0)}%",
                f"- 趋势轮动上限：{caps.get('趋势轮动', 0)}%",
                f"- 趋势跟踪上限：{caps.get('趋势跟踪', 0)}%",
            ]
        )

    lines.extend(["", "## 龙头候选"])
    if report.leaders:
        lines.append("|代码|名称|板块|连板|级别|分数|价格|止损|目标|")
        lines.append("|---|---|---|---:|---|---:|---:|---:|---|")
        for item in report.leaders:
            plan = item.trade_plan
            targets = ",".join(str(v) for v in plan.targets[:3]) if plan else ""
            stop = plan.stop_loss if plan else ""
            lines.append(
                f"|{item.code}|{item.name}|{item.sector}|{item.lianban_count}|"
                f"{item.level}|{item.score}|{item.price or ''}|{stop}|{targets}|"
            )
    else:
        lines.append("- 无符合 MVP 过滤条件的龙头候选。")

    lines.extend(["", "## 主线板块"])
    if report.sectors:
        lines.append("|板块|排名|涨幅|涨停数|连续性|阶段|评级|动作|")
        lines.append("|---|---:|---:|---:|---:|---|---:|---|")
        for item in report.sectors[:10]:
            lines.append(
                f"|{item.name}|{item.rank or ''}|{item.pct_chg or ''}|{item.limit_up_count}|"
                f"{item.consecutive_days}|{item.stage}|{item.rating}|{item.action}|"
            )
    else:
        lines.append("- 暂无板块状态。")

    lines.extend(["", "## 趋势跟踪"])
    if report.trend_tracking:
        lines.append("|代码|名称|板块|收盘|涨幅|趋势分|支撑|压力|")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|")
        for item in report.trend_tracking[:20]:
            lines.append(
                f"|{item.code}|{item.name}|{item.sector}|{item.close}|{item.pct_chg}|"
                f"{item.trend_score}|{item.support or ''}|{item.resistance or ''}|"
            )
    else:
        lines.append("- 暂无趋势跟踪候选。")

    if report.trend_rotation:
        lines.extend(["", "## 趋势轮动", f"- {report.trend_rotation.get('summary', '')}", f"- {report.trend_rotation.get('action', '')}"])

    lines.extend(["", "> 仅用于策略研究和复盘，不包含通知发送、自动交易或下单接口。"])
    return "\n".join(lines)
