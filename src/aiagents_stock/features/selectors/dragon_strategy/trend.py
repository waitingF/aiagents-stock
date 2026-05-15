"""Trend rotation and trend-following scans."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from src.aiagents_stock.features.selectors.dragon_strategy.data import normalize_daily_frame, normalize_stock_code
from src.aiagents_stock.features.selectors.dragon_strategy.indicators import (
    check_ma_alignment,
    ma20_slope,
    support_resistance,
    to_float,
    trend_score,
)
from src.aiagents_stock.features.selectors.dragon_strategy.models import DragonStrategyConfig, SectorSignal, TrendCandidate


def _first_matching_column(frame: pd.DataFrame, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        for col in frame.columns:
            if pattern in str(col):
                return col
    return None


def normalize_realtime_quotes(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["code", "name", "close", "pct_chg", "amount", "sector"])
    source = frame.copy()
    col_map = {
        "code": _first_matching_column(source, ["代码"]),
        "name": _first_matching_column(source, ["名称", "简称"]),
        "close": _first_matching_column(source, ["最新价", "收盘", "价格"]),
        "pct_chg": _first_matching_column(source, ["涨跌幅"]),
        "amount": _first_matching_column(source, ["成交额"]),
        "sector": _first_matching_column(source, ["所属行业", "行业", "板块"]),
    }
    normalized = pd.DataFrame(index=source.index)
    for target, column in col_map.items():
        normalized[target] = source[column] if column else None
    normalized["code"] = normalized["code"].apply(normalize_stock_code)
    normalized["name"] = normalized["name"].fillna("").astype(str)
    for column in ["close", "pct_chg", "amount"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["sector"] = normalized["sector"].fillna("").astype(str)
    return normalized.reset_index(drop=True)


def _quote_map(quotes_df: pd.DataFrame | None) -> Dict[str, dict[str, Any]]:
    frame = normalize_realtime_quotes(quotes_df)
    if frame.empty:
        return {}
    return {normalize_stock_code(row["code"]): row for row in frame.to_dict("records")}


def _latest_daily_values(frame: pd.DataFrame) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {}
    daily = normalize_daily_frame(frame)
    if daily.empty:
        return {}
    latest = daily.iloc[-1]
    return {
        "close": to_float(latest.get("close"), 0.0) or 0.0,
        "pct_chg": to_float(latest.get("pct_chg"), 0.0) or 0.0,
        "amount": to_float(latest.get("amount"), 0.0) or 0.0,
    }


def scan_trend_tracking(
    daily_by_code: Dict[str, pd.DataFrame],
    quotes_df: pd.DataFrame | None = None,
    stock_meta_by_code: Dict[str, dict[str, Any]] | None = None,
    config: DragonStrategyConfig | None = None,
    top_n: int = 20,
    min_score: int = 60,
) -> List[TrendCandidate]:
    """Scan stock daily frames for trend-following candidates."""
    cfg = config or DragonStrategyConfig()
    quotes = _quote_map(quotes_df)
    stock_meta_by_code = stock_meta_by_code or {}
    candidates: list[TrendCandidate] = []

    for raw_code, frame in daily_by_code.items():
        code = normalize_stock_code(raw_code)
        daily = normalize_daily_frame(frame)
        if daily.empty or len(daily) < 60:
            continue
        quote = quotes.get(code, {})
        latest = _latest_daily_values(daily)
        close = to_float(quote.get("close"), latest.get("close", 0.0)) or 0.0
        pct_chg = to_float(quote.get("pct_chg"), latest.get("pct_chg", 0.0)) or 0.0
        amount = to_float(quote.get("amount"), latest.get("amount", 0.0)) or 0.0
        if not (cfg.min_price <= close <= max(cfg.max_price * 8, cfg.max_price)):
            continue
        if amount and amount < 50_000_000:
            continue
        if pct_chg < -3.0 or pct_chg >= 9.5:
            continue

        score_data = trend_score(daily)
        if score_data["score"] < min_score:
            continue
        aligned, _ = check_ma_alignment(daily)
        levels = support_resistance(daily, close)
        meta = stock_meta_by_code.get(code, {})
        candidate = TrendCandidate(
            code=code,
            name=str(quote.get("name") or meta.get("name") or meta.get("名称") or code),
            close=round(float(close), 2),
            pct_chg=round(float(pct_chg), 2),
            amount=round(float(amount), 2),
            trend_score=float(score_data["score"]),
            ma_aligned=aligned,
            ma20_slope=ma20_slope(daily),
            rsi_zone=str(score_data.get("rsi_zone", "")),
            volume_ratio=float(score_data.get("volume_ratio", 0.0)),
            support=levels["supports"][0] if levels.get("supports") else None,
            resistance=levels["targets"][0] if levels.get("targets") else None,
            details=list(score_data.get("details", [])),
            sector=str(quote.get("sector") or meta.get("sector") or meta.get("所属行业") or ""),
        )
        candidates.append(candidate)

    candidates.sort(key=lambda item: (-item.trend_score, -item.pct_chg, -item.amount))
    return candidates[:top_n]


def generate_rotation_signals(
    sector_signals: Iterable[SectorSignal],
    trend_candidates: Iterable[TrendCandidate] | None = None,
    top_n_per_sector: int = 3,
) -> dict[str, Any]:
    """Combine mainline sectors and trend candidates into rotation guidance."""
    sectors = sorted(
        [sector for sector in sector_signals if sector.status != "fading" and sector.rating >= 2],
        key=lambda item: (-item.rating, item.rank if item.rank is not None else 9999),
    )
    candidates = list(trend_candidates or [])
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sector in sectors:
        matched = [item.to_dict() for item in candidates if item.sector and item.sector == sector.name]
        if matched:
            grouped[sector.name] = matched[:top_n_per_sector]

    if not sectors:
        action = "无清晰主线，降低趋势轮动仓位"
    elif sectors[0].rating >= 4:
        action = f"围绕{sectors[0].name}主线轮动，优先趋势确认标的"
    else:
        action = "主线仍在观察，等待连续性和涨停扩散确认"

    return {
        "main_sectors": [sector.to_dict() for sector in sectors[:5]],
        "sector_candidates": grouped,
        "action": action,
        "summary": f"有效主线{len(sectors)}个，趋势候选{len(candidates)}只",
    }
