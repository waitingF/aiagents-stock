"""Portfolio review helpers.

This module is intentionally dependency-light so review generation can be
tested without loading the full stock-analysis stack.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


def extract_first_price_range(price_text) -> tuple:
    """Extract the first two numeric prices from a model-generated range."""
    if not price_text:
        return None, None

    numbers = re.findall(r"\d+(?:\.\d+)?", str(price_text))
    if len(numbers) < 2:
        return None, None

    try:
        return float(numbers[0]), float(numbers[1])
    except (ValueError, TypeError):
        return None, None


def extract_first_price(price_text):
    """Extract the first numeric price from model output."""
    if not price_text:
        return None

    numbers = re.findall(r"\d+(?:\.\d+)?", str(price_text))
    if not numbers:
        return None

    try:
        return float(numbers[0])
    except (ValueError, TypeError):
        return None


def safe_float(value):
    """Convert a value to float when possible."""
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return extract_first_price(value)


def build_next_watchpoints(current_record: Dict, final_decision: Dict) -> List[str]:
    """生成下次复盘关注点。"""
    watchpoints = []
    entry_min = safe_float(current_record.get("entry_min"))
    entry_max = safe_float(current_record.get("entry_max"))
    take_profit = safe_float(current_record.get("take_profit"))
    stop_loss = safe_float(current_record.get("stop_loss"))

    if entry_min is not None and entry_max is not None:
        watchpoints.append(f"是否进入或站稳进场区间 {entry_min:.2f}-{entry_max:.2f}")
    if take_profit is not None:
        watchpoints.append(f"是否触及止盈位 {take_profit:.2f}")
    if stop_loss is not None:
        watchpoints.append(f"是否跌破止损位 {stop_loss:.2f}")

    risk_warning = final_decision.get("risk_warning")
    if risk_warning:
        watchpoints.append(str(risk_warning)[:80])

    return watchpoints[:4] or ["跟踪价格、成交量和资金面是否支持当前评级"]


def build_review_summary(code: str, name: str, review_status: str,
                         price_change_pct, plan_check_parts: List[str],
                         rating_change: str) -> str:
    """生成一行复盘摘要。"""
    if price_change_pct is None:
        price_text = "价格变化暂无可比数据"
    else:
        direction = "上涨" if price_change_pct >= 0 else "下跌"
        price_text = f"较上次{direction}{abs(price_change_pct):.2f}%"

    plan_text = "；".join(plan_check_parts[:2])
    return f"{code} {name}：{review_status}，{price_text}，{plan_text}，评级 {rating_change}。"


def build_portfolio_review(previous_record: Optional[Dict],
                           current_record: Dict,
                           stock: Dict,
                           final_decision: Dict) -> Dict:
    """基于上一条历史和本次分析生成持仓复盘。"""
    code = stock.get("code", "")
    name = stock.get("name", "")
    current_price = safe_float(current_record.get("current_price"))
    current_rating = current_record.get("rating", "未知")
    current_confidence = safe_float(current_record.get("confidence"))
    operation_advice = current_record.get("operation_advice") or current_record.get("summary") or "暂无操作建议"

    if not previous_record:
        summary = f"{code} {name} 首次建立持仓分析基线，后续分析将基于本次交易计划复盘。"
        return {
            "review_status": "首次分析",
            "price_change_pct": None,
            "target_hit": False,
            "entry_hit": False,
            "take_profit_hit": False,
            "stop_loss_hit": False,
            "rating_change": "首次分析",
            "plan_check": "暂无上一期计划，本次记录作为后续复盘基线。",
            "price_review": "暂无上一期价格用于对比。",
            "logic_change": "首次分析，暂无历史逻辑变化。",
            "risk_change": current_record.get("risk_warning") or "暂无风险提示。",
            "action_adjustment": operation_advice,
            "next_watchpoints": build_next_watchpoints(current_record, final_decision),
            "review_summary": summary,
        }

    previous_price = safe_float(previous_record.get("current_price"))
    price_change_pct = None
    if previous_price and current_price is not None:
        price_change_pct = (current_price - previous_price) / previous_price * 100

    prev_target = safe_float(previous_record.get("target_price"))
    prev_entry_min = safe_float(previous_record.get("entry_min"))
    prev_entry_max = safe_float(previous_record.get("entry_max"))
    prev_take_profit = safe_float(previous_record.get("take_profit"))
    prev_stop_loss = safe_float(previous_record.get("stop_loss"))

    target_hit = bool(current_price is not None and prev_target is not None and current_price >= prev_target)
    take_profit_hit = bool(current_price is not None and prev_take_profit is not None and current_price >= prev_take_profit)
    stop_loss_hit = bool(current_price is not None and prev_stop_loss is not None and current_price <= prev_stop_loss)
    entry_hit = bool(
        current_price is not None
        and prev_entry_min is not None
        and prev_entry_max is not None
        and prev_entry_min <= current_price <= prev_entry_max
    )

    previous_rating = previous_record.get("rating", "未知")
    rating_change = (
        f"{previous_rating} -> {current_rating}"
        if previous_rating != current_rating
        else f"{current_rating}（未变化）"
    )

    if stop_loss_hit:
        review_status = "失效"
    elif target_hit or take_profit_hit:
        review_status = "兑现"
    elif entry_hit or previous_rating != current_rating or (price_change_pct is not None and abs(price_change_pct) >= 3):
        review_status = "部分兑现"
    else:
        review_status = "待验证"

    plan_check_parts = []
    if entry_hit:
        plan_check_parts.append("当前价已落入上一期进场区间")
    elif prev_entry_min is not None and prev_entry_max is not None:
        plan_check_parts.append(f"当前价未落入上一期进场区间 {prev_entry_min:.2f}-{prev_entry_max:.2f}")
    if target_hit:
        plan_check_parts.append("已达到上一期目标价")
    if take_profit_hit:
        plan_check_parts.append("已达到上一期止盈位")
    if stop_loss_hit:
        plan_check_parts.append("已跌破上一期止损位")
    if not plan_check_parts:
        plan_check_parts.append("上一期关键交易位置暂未触发")

    if price_change_pct is None:
        price_review = "缺少上一期价格或本次价格，无法计算涨跌幅。"
    else:
        direction = "上涨" if price_change_pct >= 0 else "下跌"
        price_review = f"相对上一期分析价 {previous_price:.2f}，当前价 {current_price:.2f}，{direction} {abs(price_change_pct):.2f}%。"

    confidence_change = ""
    previous_confidence = safe_float(previous_record.get("confidence"))
    if previous_confidence is not None and current_confidence is not None:
        delta = current_confidence - previous_confidence
        if abs(delta) >= 0.1:
            confidence_change = f" 信心度由 {previous_confidence:g}/10 调整为 {current_confidence:g}/10。"

    logic_change = f"评级变化：{rating_change}。{confidence_change}".strip()

    previous_risk = previous_record.get("risk_warning") or "上一期未记录风险提示"
    current_risk = current_record.get("risk_warning") or "本期未记录风险提示"
    risk_change = (
        "风险提示未发生明显变化。"
        if previous_risk == current_risk
        else f"上一期风险：{previous_risk} 本期风险：{current_risk}"
    )

    review_summary = build_review_summary(
        code=code,
        name=name,
        review_status=review_status,
        price_change_pct=price_change_pct,
        plan_check_parts=plan_check_parts,
        rating_change=rating_change,
    )

    return {
        "review_status": review_status,
        "price_change_pct": round(price_change_pct, 2) if price_change_pct is not None else None,
        "target_hit": target_hit,
        "entry_hit": entry_hit,
        "take_profit_hit": take_profit_hit,
        "stop_loss_hit": stop_loss_hit,
        "rating_change": rating_change,
        "plan_check": "；".join(plan_check_parts) + "。",
        "price_review": price_review,
        "logic_change": logic_change,
        "risk_change": risk_change,
        "action_adjustment": operation_advice,
        "next_watchpoints": build_next_watchpoints(current_record, final_decision),
        "review_summary": review_summary,
    }
