"""Market environment and sentiment scoring for dragon strategy."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd

from src.aiagents_stock.features.selectors.dragon_strategy.data import normalize_limit_up_pool
from src.aiagents_stock.features.selectors.dragon_strategy.models import DragonStrategyConfig, MarketEnvironment


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return min(upper, max(lower, value))


def judge_sentiment_stage(score: float) -> str:
    if score >= 80:
        return "高潮期"
    if score >= 60:
        return "发酵期"
    if score >= 40:
        return "启动期/分歧期"
    return "退潮期"


def stage_advice(stage: str) -> str:
    return {
        "高潮期": "持股待涨，不追高，准备兑现",
        "发酵期": "加仓主线，积极参与",
        "启动期/分歧期": "轻仓试错，等待确认",
        "退潮期": "空仓或轻仓防守，等待信号",
    }.get(stage, "谨慎观望")


def position_usage_for_score(score: float) -> tuple[int, float]:
    if score >= 80:
        return 60, 12.0
    if score >= 60:
        return 80, 16.0
    if score >= 40:
        return 50, 10.0
    return 20, 4.0


def calculate_sentiment_score(limit_up_count: int, limit_down_count: int, max_lianban: int) -> float:
    return round(clamp(50 + (limit_up_count - limit_down_count) * 2 + max_lianban * 5), 1)


def _count_non_st(frame: pd.DataFrame | None) -> int:
    if frame is None or frame.empty:
        return 0
    if "name" in frame.columns:
        names = frame["name"].astype(str)
    elif "名称" in frame.columns:
        names = frame["名称"].astype(str)
    else:
        return int(len(frame))
    return int((~names.str.contains("ST|退", na=False)).sum())


def _max_lianban(limit_up_df: pd.DataFrame, strong_df: pd.DataFrame | None = None) -> int:
    candidates = []
    if limit_up_df is not None and not limit_up_df.empty and "lianban_count" in limit_up_df:
        candidates.append(int(pd.to_numeric(limit_up_df["lianban_count"], errors="coerce").fillna(0).max()))
    if strong_df is not None and not strong_df.empty:
        col = next((col for col in strong_df.columns if "连板" in str(col)), None)
        if col:
            candidates.append(int(pd.to_numeric(strong_df[col], errors="coerce").fillna(0).max()))
    return max(candidates or [0])


def _index_changes(index_df: pd.DataFrame | None) -> tuple[Optional[float], Optional[float]]:
    if index_df is None or index_df.empty or "close" not in index_df:
        return None, None
    latest = index_df.iloc[-1]
    if "open" in index_df:
        day_change = (float(latest["close"]) - float(latest["open"])) / float(latest["open"]) * 100
    else:
        day_change = None
    if len(index_df) >= 2:
        five_gain = (float(index_df["close"].iloc[-1]) - float(index_df["close"].iloc[0])) / float(index_df["close"].iloc[0]) * 100
    else:
        five_gain = None
    return (round(day_change, 2) if day_change is not None else None, round(five_gain, 2) if five_gain is not None else None)


def evaluate_market_environment(
    *,
    date: str,
    is_trade_day: bool,
    limit_up_df: pd.DataFrame | None,
    limit_down_df: pd.DataFrame | None,
    strong_df: pd.DataFrame | None = None,
    explode_df: pd.DataFrame | None = None,
    board_df: pd.DataFrame | None = None,
    index_df: pd.DataFrame | None = None,
    yesterday_limit_up_count: int = 0,
    north_money: float = -100.0,
    up_count: int = 0,
    down_count: int = 1,
    data_errors: Dict[str, str] | None = None,
    config: DragonStrategyConfig | None = None,
) -> MarketEnvironment:
    """Evaluate market environment with the stockchoosedragon gate rules."""
    cfg = config or DragonStrategyConfig()
    if limit_up_df is None:
        normalized_limit_up = pd.DataFrame()
    elif "code" in limit_up_df.columns:
        normalized_limit_up = limit_up_df.copy()
    else:
        normalized_limit_up = normalize_limit_up_pool(limit_up_df)
    limit_up_count = _count_non_st(normalized_limit_up)
    limit_down_count = _count_non_st(limit_down_df)
    max_lianban = _max_lianban(normalized_limit_up, strong_df)
    explode_count = 0 if explode_df is None else len(explode_df)
    total_try_limit = limit_up_count + explode_count
    explode_rate = round(explode_count / total_try_limit * 100, 1) if total_try_limit else 100.0
    index_day_change, index_5day_gain = _index_changes(index_df)

    top3_theme_limit = 0
    if board_df is not None and not board_df.empty:
        col = next((col for col in board_df.columns if "涨停" in str(col) and "家" in str(col)), None)
        if col:
            top3_theme_limit = int(pd.to_numeric(board_df[col], errors="coerce").fillna(0).head(3).sum())
    theme_ratio = round(top3_theme_limit / limit_up_count * 100, 1) if limit_up_count else 0.0
    limit_up_ring = round(limit_up_count / yesterday_limit_up_count, 2) if yesterday_limit_up_count else 0.0
    up_down_ratio = round(up_count / down_count, 2) if down_count else 0.0

    core_conditions = {
        "limit_up_count": limit_up_count >= cfg.limit_up_min_count,
        "limit_down_count": limit_down_count <= cfg.limit_down_max_count,
        "max_lianban": max_lianban >= cfg.max_lianban_min_height,
        "index_day_change": index_day_change is not None and index_day_change >= cfg.index_day_change_min,
        "index_5day_gain": index_5day_gain is not None and index_5day_gain >= cfg.index_5day_gain_min,
        "explode_rate": explode_rate <= cfg.explode_rate_max,
    }
    assist_conditions = {
        "theme_ratio": theme_ratio >= cfg.theme_ratio_min,
        "limit_up_ring": limit_up_ring >= cfg.limit_up_ring_min,
        "north_money": north_money >= cfg.north_money_min,
        "up_down_ratio": up_down_ratio >= cfg.up_down_ratio_min,
    }
    assist_pass_count = sum(assist_conditions.values())
    score = calculate_sentiment_score(limit_up_count, limit_down_count, max_lianban)
    stage = judge_sentiment_stage(score)

    data_errors = data_errors or {}
    data_error_message = ""
    if data_errors:
        data_error_message = "；数据源异常：" + "、".join(sorted(data_errors.keys()))

    if not is_trade_day:
        passed = False
        message = f"[{date}] 非A股交易日，不执行选股"
    elif not all(core_conditions.values()):
        passed = False
        message = (
            "市场核心条件不达标："
            f"涨停数{limit_up_count}, 跌停数{limit_down_count}, "
            f"最高连板{max_lianban}, 炸板率{explode_rate:.1f}%"
        )
    elif assist_pass_count < 3:
        passed = False
        message = f"市场辅助条件不达标：4项中仅{assist_pass_count}项通过"
    else:
        passed = True
        message = "市场环境达标，启动龙头战法选股"
    message += data_error_message

    return MarketEnvironment(
        date=date,
        is_trade_day=is_trade_day,
        passed=passed,
        message=message,
        score=score,
        stage=stage,
        limit_up_count=limit_up_count,
        limit_down_count=limit_down_count,
        max_lianban=max_lianban,
        explode_rate=explode_rate,
        index_day_change=index_day_change,
        index_5day_gain=index_5day_gain,
        assist_pass_count=assist_pass_count,
        core_conditions=core_conditions,
        assist_conditions=assist_conditions,
        metrics={
            "theme_ratio": theme_ratio,
            "limit_up_ring": limit_up_ring,
            "north_money": north_money,
            "up_down_ratio": up_down_ratio,
            "stage_advice": stage_advice(stage),
            "position_usage": position_usage_for_score(score)[0],
            "actual_position": position_usage_for_score(score)[1],
            "data_errors": data_errors,
        },
    )


class MarketEnvironmentService:
    """Build market environment from a provider."""

    def __init__(self, provider: Any, config: DragonStrategyConfig | None = None) -> None:
        self.provider = provider
        self.config = config or DragonStrategyConfig()

    def evaluate(self, date: str | None = None) -> MarketEnvironment:
        trade_date = (date or datetime.now().strftime("%Y%m%d")).replace("-", "")
        start_5day = (datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=7)).strftime("%Y%m%d")
        data_errors: Dict[str, str] = {}
        up_count, down_count = self._provider_call(
            "get_market_activity",
            default=(0, 1),
            data_errors=data_errors,
        )
        return evaluate_market_environment(
            date=trade_date,
            is_trade_day=self._provider_call("is_trade_day", trade_date, default=False, data_errors=data_errors),
            limit_up_df=self._provider_call("get_limit_up_pool", trade_date, default=pd.DataFrame(), data_errors=data_errors),
            limit_down_df=self._provider_call("get_limit_down_pool", trade_date, default=pd.DataFrame(), data_errors=data_errors),
            strong_df=self._provider_call("get_strong_pool", trade_date, default=pd.DataFrame(), data_errors=data_errors),
            explode_df=self._provider_call("get_explode_pool", trade_date, default=pd.DataFrame(), data_errors=data_errors),
            board_df=self._provider_call("get_board_pool", trade_date, default=pd.DataFrame(), data_errors=data_errors),
            index_df=self._provider_call("get_index_daily", start_5day, trade_date, default=pd.DataFrame(), data_errors=data_errors),
            yesterday_limit_up_count=self._provider_call(
                "get_yesterday_limit_up_count",
                trade_date,
                default=0,
                data_errors=data_errors,
            ),
            north_money=self._provider_call("get_north_money", default=-100.0, data_errors=data_errors),
            up_count=up_count,
            down_count=down_count,
            data_errors=data_errors,
            config=self.config,
        )

    def _provider_call(
        self,
        method_name: str,
        *args: Any,
        default: Any = None,
        data_errors: Dict[str, str] | None = None,
    ) -> Any:
        method = getattr(self.provider, method_name, None)
        if method is None:
            if data_errors is not None:
                data_errors[method_name] = "provider method missing"
            return default
        try:
            return method(*args)
        except Exception as exc:
            if data_errors is not None:
                data_errors[method_name] = str(exc)
            return default
