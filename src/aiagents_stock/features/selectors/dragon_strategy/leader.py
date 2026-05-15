"""Dragon leader screening and scoring."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from src.aiagents_stock.features.selectors.dragon_strategy.data import normalize_limit_up_pool, normalize_stock_code
from src.aiagents_stock.features.selectors.dragon_strategy.indicators import check_volume_and_trend, support_resistance, to_float
from src.aiagents_stock.features.selectors.dragon_strategy.models import DragonStrategyConfig, LeaderCandidate, TradePlan


def board_type(lianban_count: int) -> str:
    if lianban_count == 2:
        return "1进2"
    if lianban_count == 3:
        return "2进3"
    if lianban_count >= 4:
        return "高位连板"
    return "首板"


def leader_level(score: float) -> str:
    if score >= 80:
        return "总龙头"
    if score >= 60:
        return "主线龙头"
    if score >= 40:
        return "板块龙头"
    return "补涨龙"


def _time_minutes(time_text: str) -> int:
    try:
        parts = str(time_text).split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 24 * 60


def _score_limit_time(time_text: str) -> float:
    minutes = _time_minutes(time_text)
    if minutes <= 9 * 60 + 35:
        return 100.0
    if minutes <= 9 * 60 + 45:
        return 70.0
    if minutes <= 10 * 60:
        return 40.0
    return 20.0


def _score_consecutive(lianban_count: int) -> float:
    if lianban_count >= 7:
        return 100.0
    if lianban_count >= 5:
        return 80.0
    if lianban_count >= 3:
        return 60.0
    if lianban_count >= 2:
        return 40.0
    return 20.0


def _score_sector_rank(lianban_count: int, sector_stocks: list[dict[str, Any]]) -> float:
    if not sector_stocks:
        return 80.0 if lianban_count >= 5 else 60.0 if lianban_count >= 3 else 40.0
    max_lianban = max(int(stock.get("lianban_count", 1) or 1) for stock in sector_stocks)
    if lianban_count >= max_lianban and max_lianban >= 3:
        return 100.0
    if lianban_count >= max_lianban - 1:
        return 80.0
    if lianban_count >= max_lianban - 2:
        return 60.0
    return 40.0


def _score_drive_effect(stock: dict[str, Any], sector_stocks: list[dict[str, Any]]) -> float:
    follow_limit_count = max(0, len(sector_stocks) - 1)
    if follow_limit_count >= 5:
        return 100.0
    if follow_limit_count >= 3:
        return 70.0
    if follow_limit_count >= 1:
        return 50.0
    seal_amount = to_float(stock.get("seal_amount"), 0.0) or 0.0
    if seal_amount >= 3e8:
        return 100.0
    if seal_amount >= 1e8:
        return 80.0
    if seal_amount >= 5e7:
        return 60.0
    return 40.0


def calculate_leader_score(stock: dict[str, Any], sector_stocks: Optional[list[dict[str, Any]]] = None) -> Dict[str, float]:
    sector_stocks = sector_stocks or []
    lianban = int(stock.get("lianban_count", stock.get("连板数", 1)) or 1)
    detail = {
        "sector_rank_score": _score_sector_rank(lianban, sector_stocks),
        "consecutive_score": _score_consecutive(lianban),
        "limit_time_score": _score_limit_time(str(stock.get("first_limit_time", stock.get("涨停时间", "")))),
        "drive_effect_score": _score_drive_effect(stock, sector_stocks),
        "resistance_score": float(stock.get("resistance_score", 60.0) or 60.0),
    }
    detail["total_score"] = round(
        detail["sector_rank_score"] * 0.35
        + detail["consecutive_score"] * 0.25
        + detail["limit_time_score"] * 0.20
        + detail["drive_effect_score"] * 0.15
        + detail["resistance_score"] * 0.05,
        1,
    )
    return detail


def _stock_info_value(info: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in info and info[key] not in (None, ""):
            return info[key]
    return default


def _list_days(list_date: Any, date: str) -> int:
    if not list_date:
        return 99999
    try:
        return (datetime.strptime(date.replace("-", ""), "%Y%m%d") - datetime.strptime(str(list_date).replace("-", ""), "%Y%m%d")).days
    except Exception:
        return 99999


def _build_trade_plan(code: str, price: Optional[float], daily: pd.DataFrame | None, level: str) -> Optional[TradePlan]:
    if not price or price <= 0:
        return None
    levels = support_resistance(daily if daily is not None else pd.DataFrame(), float(price))
    supports = levels["supports"]
    targets = levels["targets"][:3]
    if level in ("总龙头", "主线龙头"):
        stop = supports[-1] if supports else price * 0.95
    elif level == "板块龙头":
        stop = min(supports[-1] if supports else price * 0.95, price * 0.95)
    else:
        stop = price * 0.95
    risk = price - stop
    rr = round((targets[0] - price) / risk, 2) if targets and risk > 0 else None
    position = {
        "总龙头": "30-40%",
        "主线龙头": "20-30%",
        "板块龙头": "10-20%",
        "补涨龙": "5-10%",
    }.get(level, "5-10%")
    return TradePlan(
        current_price=round(float(price), 2),
        stop_loss=round(float(stop), 2),
        targets=[round(float(target), 2) for target in targets],
        support_levels=[round(float(item), 2) for item in supports],
        risk_reward=rr,
        position_advice=position,
    )


def _passes_basic_filters(
    row: dict[str, Any],
    info: Dict[str, Any],
    date: str,
    config: DragonStrategyConfig,
) -> tuple[bool, list[str], list[str], Optional[float], Optional[float]]:
    reasons: list[str] = []
    risks: list[str] = []
    code = normalize_stock_code(row.get("code", ""))
    name = str(row.get("name", ""))
    circ_market_cap = to_float(row.get("circ_market_cap"), 0.0) or 0.0
    if circ_market_cap > 100000:
        circ_market_cap = circ_market_cap / 100000000
    if not circ_market_cap:
        circ_market_cap = (to_float(_stock_info_value(info, "流通市值"), 0.0) or 0.0) / 100000000
    price = to_float(row.get("latest_price"), 0.0) or 0.0
    if not price:
        price = to_float(_stock_info_value(info, "最新价", "最新价格"), 0.0) or 0.0

    if "ST" in name.upper() or "退" in name:
        risks.append("ST/退市风险标的")
        return False, reasons, risks, circ_market_cap, price
    if not (config.min_circ_market_cap <= circ_market_cap <= config.max_circ_market_cap):
        risks.append(f"流通市值不在{config.min_circ_market_cap}-{config.max_circ_market_cap}亿")
        return False, reasons, risks, circ_market_cap, price
    if not (config.min_price <= price <= config.max_price):
        risks.append(f"价格不在{config.min_price}-{config.max_price}元")
        return False, reasons, risks, circ_market_cap, price
    if _list_days(_stock_info_value(info, "上市时间", "上市日期"), date) < config.min_list_days:
        risks.append(f"上市未满{config.min_list_days}天")
        return False, reasons, risks, circ_market_cap, price
    reasons.append("基础属性通过")
    return True, reasons, risks, circ_market_cap, price


def screen_limit_up_candidates(
    limit_up_df: pd.DataFrame,
    stock_info_by_code: Dict[str, Dict[str, Any]] | None = None,
    daily_by_code: Dict[str, pd.DataFrame] | None = None,
    config: DragonStrategyConfig | None = None,
    date: str | None = None,
) -> List[LeaderCandidate]:
    """Apply strict dragon MVP filters and score remaining limit-up stocks."""
    cfg = config or DragonStrategyConfig()
    trade_date = (date or datetime.now().strftime("%Y%m%d")).replace("-", "")
    stock_info_by_code = stock_info_by_code or {}
    daily_by_code = daily_by_code or {}
    frame = normalize_limit_up_pool(limit_up_df) if "code" not in limit_up_df.columns else limit_up_df.copy()
    if frame.empty:
        return []

    sector_records = {
        sector: group.to_dict("records")
        for sector, group in frame.groupby("sector", dropna=False)
    }

    candidates: List[LeaderCandidate] = []
    for row in frame.to_dict("records"):
        code = normalize_stock_code(row.get("code"))
        info = stock_info_by_code.get(code, {})
        daily = daily_by_code.get(code, pd.DataFrame())
        passed, reasons, risks, circ_cap, price = _passes_basic_filters(row, info, trade_date, cfg)
        if not passed:
            continue

        volume_trend = check_volume_and_trend(
            daily,
            cfg.turnover_min,
            cfg.turnover_max,
            cfg.volume_ratio_min,
            cfg.volume_growth_min,
        )
        if not volume_trend["volume_pass"]:
            continue
        reasons.append("量能通过")
        if not volume_trend["trend_pass"]:
            continue
        reasons.append("趋势通过")

        first_time = str(row.get("first_limit_time", ""))
        if first_time and _time_minutes(first_time) > _time_minutes(cfg.min_first_limit_time):
            continue
        if int(row.get("explode_count", 0) or 0) != 0:
            continue
        seal_amount = to_float(row.get("seal_amount"), 0.0) or 0.0
        if circ_cap and seal_amount / (circ_cap * 100000000) < cfg.seal_amount_to_float_cap_min:
            continue
        reasons.append("涨停质量通过")

        sector = str(row.get("sector") or "未分类")
        score_detail = calculate_leader_score(row, sector_records.get(sector, []))
        level = leader_level(score_detail["total_score"])
        candidate = LeaderCandidate(
            code=code,
            name=str(row.get("name", "")),
            sector=sector,
            lianban_count=int(row.get("lianban_count", 1) or 1),
            board_type=board_type(int(row.get("lianban_count", 1) or 1)),
            first_limit_time=first_time,
            seal_amount=seal_amount,
            circ_market_cap=round(circ_cap, 2) if circ_cap else None,
            price=round(float(price), 2) if price else None,
            score=score_detail["total_score"],
            level=level,
            score_detail=score_detail,
            trade_plan=_build_trade_plan(code, price, daily, level),
            reasons=reasons,
            risks=risks,
            raw=row,
        )
        candidates.append(candidate)

    candidates.sort(key=lambda item: (-item.lianban_count, item.first_limit_time or "99:99:99", item.circ_market_cap or 999999))
    return candidates[: cfg.max_stock_count]
