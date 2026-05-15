"""Mainline sector tracking for dragon strategy."""

from __future__ import annotations

from typing import Any, Iterable, List, Optional

import pandas as pd

from src.aiagents_stock.features.selectors.dragon_strategy.data import normalize_limit_up_pool
from src.aiagents_stock.features.selectors.dragon_strategy.models import DragonStrategyConfig, SectorSignal


def _first_matching_column(frame: pd.DataFrame, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        for col in frame.columns:
            if pattern in str(col):
                return col
    return None


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    text = str(value).replace(",", "").replace("%", "").strip()
    if text.endswith("亿"):
        text = text[:-1]
        multiplier = 100000000.0
    elif text.endswith("万"):
        text = text[:-1]
        multiplier = 10000.0
    else:
        multiplier = 1.0
    try:
        return float(text) * multiplier
    except ValueError:
        return default


def normalize_industry_ranking(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize sector/industry ranking data to stable English columns."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["name", "rank", "pct_chg", "amount", "stock_count", "up_stocks", "source", "raw"])
    source = frame.copy()
    col_map = {
        "name": _first_matching_column(source, ["板块名称", "行业名称", "名称", "板块"]),
        "rank": _first_matching_column(source, ["排名", "排行", "序号"]),
        "pct_chg": _first_matching_column(source, ["涨跌幅", "涨幅"]),
        "amount": _first_matching_column(source, ["总成交额", "成交额", "成交金额", "资金"]),
        "stock_count": _first_matching_column(source, ["股票家数", "成分股", "家数"]),
        "up_stocks": _first_matching_column(source, ["上涨家数", "上涨数"]),
    }
    normalized = pd.DataFrame(index=source.index)
    for target, column in col_map.items():
        normalized[target] = source[column] if column else None
    normalized["name"] = normalized["name"].fillna("").astype(str)
    normalized["pct_chg"] = normalized["pct_chg"].apply(_to_float)
    normalized["amount"] = normalized["amount"].apply(_to_float)
    normalized["stock_count"] = pd.to_numeric(normalized["stock_count"], errors="coerce")
    normalized["up_stocks"] = pd.to_numeric(normalized["up_stocks"], errors="coerce")
    normalized["rank"] = pd.to_numeric(normalized["rank"], errors="coerce")
    if normalized["rank"].isna().all():
        normalized = normalized.sort_values("pct_chg", ascending=False, na_position="last")
        normalized["rank"] = range(1, len(normalized) + 1)
    normalized["rank"] = normalized["rank"].fillna(9999).astype(int)
    normalized["source"] = source["source"] if "source" in source.columns else source.get("source_type", "unknown")
    normalized["raw"] = source.to_dict("records")
    return normalized[normalized["name"] != ""].reset_index(drop=True)


def count_sector_limit_ups(limit_up_df: pd.DataFrame | None) -> dict[str, int]:
    frame = normalize_limit_up_pool(limit_up_df) if limit_up_df is not None and "code" not in limit_up_df.columns else limit_up_df
    if frame is None or frame.empty or "sector" not in frame:
        return {}
    return frame.groupby("sector", dropna=False)["code"].count().astype(int).to_dict()


def _sector_history_records(history: Iterable[dict[str, Any]], sector_name: str, current_date: str) -> list[dict[str, Any]]:
    records = [
        item
        for item in history
        if item.get("name") == sector_name and str(item.get("trade_date", "")) != str(current_date)
    ]
    return sorted(records, key=lambda item: str(item.get("trade_date", "")), reverse=True)


def consecutive_mainline_days(
    sector_name: str,
    current_date: str,
    current_rank: Optional[int],
    history: Iterable[dict[str, Any]],
    rank_threshold: int = 10,
) -> int:
    if current_rank is None or current_rank > rank_threshold:
        return 0
    count = 1
    for record in _sector_history_records(history, sector_name, current_date):
        rank = record.get("rank")
        if rank is not None and int(rank) <= rank_threshold and record.get("status") != "fading":
            count += 1
            continue
        break
    return count


def classify_sector_stage(rank: Optional[int], limit_up_count: int, consecutive_days: int) -> tuple[str, int, str, str]:
    if rank is None or rank > 20 or limit_up_count <= 0:
        return "退潮期", 1, "回避", "fading"
    if consecutive_days >= 5 and limit_up_count >= 10:
        return "高潮期", 5, "持股待涨", "active"
    if consecutive_days >= 3 and limit_up_count >= 5 and rank <= 8:
        return "发酵期", 4, "加仓主线", "active"
    if rank <= 10 and limit_up_count >= 2:
        return "启动期", 3, "轻仓试错", "active"
    if rank <= 10:
        return "观察期", 2, "观察持续性", "watch"
    return "退潮期", 1, "降仓或回避", "fading"


def compute_sector_signals(
    industry_rank_df: pd.DataFrame | None,
    limit_up_df: pd.DataFrame | None,
    history: Iterable[dict[str, Any]] | None = None,
    config: DragonStrategyConfig | None = None,
    date: str = "",
    top_n: int = 20,
) -> List[SectorSignal]:
    """Build sector state signals from ranking, limit-up breadth, and history."""
    _ = config or DragonStrategyConfig()
    rank_frame = normalize_industry_ranking(industry_rank_df)
    limit_counts = count_sector_limit_ups(limit_up_df)
    history = history or []
    signals: list[SectorSignal] = []

    for row in rank_frame.to_dict("records"):
        name = str(row.get("name", ""))
        rank = int(row.get("rank")) if row.get("rank") is not None else None
        limit_count = int(limit_counts.get(name, 0))
        consecutive = consecutive_mainline_days(name, date, rank, history)
        stage, rating, action, status = classify_sector_stage(rank, limit_count, consecutive)
        signals.append(
            SectorSignal(
                name=name,
                rank=rank,
                pct_chg=row.get("pct_chg"),
                limit_up_count=limit_count,
                consecutive_days=consecutive,
                stage=stage,
                rating=rating,
                action=action,
                status=status,
                amount=row.get("amount"),
                stock_count=int(row["stock_count"]) if pd.notna(row.get("stock_count")) else None,
                up_stocks=int(row["up_stocks"]) if pd.notna(row.get("up_stocks")) else None,
                raw=row.get("raw", {}),
            )
        )

    for sector_name, count in limit_counts.items():
        if any(signal.name == sector_name for signal in signals):
            continue
        stage, rating, action, status = classify_sector_stage(None, count, 0)
        signals.append(
            SectorSignal(
                name=sector_name,
                rank=None,
                pct_chg=None,
                limit_up_count=count,
                consecutive_days=0,
                stage=stage,
                rating=rating,
                action=action,
                status=status,
            )
        )

    signals.sort(key=lambda item: (-(item.rating or 0), item.rank if item.rank is not None else 9999, -item.limit_up_count))
    return signals[:top_n]
