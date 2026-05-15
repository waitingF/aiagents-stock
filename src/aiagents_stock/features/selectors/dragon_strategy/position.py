"""Position sizing rules for dragon and trend strategy outputs."""

from __future__ import annotations

from typing import Dict

from src.aiagents_stock.features.selectors.dragon_strategy.models import DragonStrategyConfig
from src.aiagents_stock.features.selectors.dragon_strategy.sentiment import position_usage_for_score


def calculate_dragon_position(score: float, leader_counts: Dict[str, int] | None = None, config: DragonStrategyConfig | None = None) -> Dict:
    cfg = config or DragonStrategyConfig()
    usage_rate, actual_position = position_usage_for_score(score)
    leader_counts = leader_counts or {}
    allocation = {}
    if not leader_counts or sum(leader_counts.values()) == 0:
        allocation = {
            "主线龙头": actual_position * 0.5,
            "板块龙头": actual_position * 0.3,
            "补涨龙": actual_position * 0.1,
            "现金": actual_position * 0.1,
        }
    else:
        if leader_counts.get("总龙头", 0):
            allocation["总龙头"] = min(actual_position * 0.5, 10.0)
        if leader_counts.get("主线龙头", 0):
            allocation["主线龙头"] = min(actual_position * 0.3, 8.0)
        if leader_counts.get("板块龙头", 0):
            allocation["板块龙头"] = min(actual_position * 0.15, 6.0)
        if leader_counts.get("补涨龙", 0):
            allocation["补涨龙"] = min(actual_position * 0.05, 4.0)
        allocation["现金"] = max(0.0, actual_position - sum(allocation.values()))
    return {
        "usage_rate": usage_rate,
        "total_position": round(actual_position, 1),
        "allocation": {key: round(value, 1) for key, value in allocation.items()},
        "single_stock_limits": {
            "总龙头": 10,
            "主线龙头": 8,
            "板块龙头": 6,
            "补涨龙": 4,
        },
        "strategy_caps": {
            "龙头战法": cfg.dragon_position_cap,
            "趋势轮动": cfg.trend_rotation_cap,
            "趋势跟踪": cfg.trend_tracking_cap,
            "总仓位上限": 95,
        },
    }

