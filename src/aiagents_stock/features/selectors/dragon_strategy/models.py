"""Typed models for the dragon leader strategy."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _clean_dict(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, list):
        return [_clean_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_dict(item) for key, item in value.items()}
    return value


@dataclass
class DragonStrategyConfig:
    """Config shared by dragon, sector, trend, report, and backtest logic."""

    min_circ_market_cap: float = 10.0
    max_circ_market_cap: float = 300.0
    min_price: float = 5.0
    max_price: float = 30.0
    max_stock_count: int = 5
    max_fetch_candidates: int = 200
    limit_up_min_count: int = 35
    limit_down_max_count: int = 8
    max_lianban_min_height: int = 4
    explode_rate_max: float = 35.0
    index_day_change_min: float = -1.0
    index_5day_gain_min: float = 0.0
    theme_ratio_min: float = 60.0
    limit_up_ring_min: float = 0.9
    north_money_min: float = -30.0
    up_down_ratio_min: float = 1.2
    turnover_min: float = 8.0
    turnover_max: float = 18.0
    volume_ratio_min: float = 1.5
    volume_growth_min: float = 1.3
    min_list_days: int = 60
    min_first_limit_time: str = "13:30:00"
    seal_amount_to_float_cap_min: float = 0.01
    dragon_position_cap: float = 20.0
    trend_rotation_cap: float = 45.0
    trend_tracking_cap: float = 35.0


@dataclass
class MarketEnvironment:
    date: str
    is_trade_day: bool
    passed: bool
    message: str
    score: float
    stage: str
    limit_up_count: int = 0
    limit_down_count: int = 0
    max_lianban: int = 0
    explode_rate: float = 0.0
    index_day_change: Optional[float] = None
    index_5day_gain: Optional[float] = None
    assist_pass_count: int = 0
    core_conditions: Dict[str, bool] = field(default_factory=dict)
    assist_conditions: Dict[str, bool] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TradePlan:
    current_price: float
    stop_loss: float
    targets: List[float]
    support_levels: List[float]
    risk_reward: Optional[float] = None
    position_advice: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LeaderCandidate:
    code: str
    name: str
    sector: str
    lianban_count: int
    board_type: str
    first_limit_time: str
    seal_amount: float
    circ_market_cap: Optional[float]
    price: Optional[float]
    score: float
    level: str
    score_detail: Dict[str, float] = field(default_factory=dict)
    trade_plan: Optional[TradePlan] = None
    reasons: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _clean_dict(asdict(self))


@dataclass
class SectorSignal:
    name: str
    rank: Optional[int]
    pct_chg: Optional[float]
    limit_up_count: int
    consecutive_days: int
    stage: str
    rating: int
    action: str
    status: str = "active"
    amount: Optional[float] = None
    stock_count: Optional[int] = None
    up_stocks: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TrendCandidate:
    code: str
    name: str
    close: float
    pct_chg: float
    amount: float
    trend_score: float
    ma_aligned: bool
    ma20_slope: float
    rsi_zone: str
    volume_ratio: float
    support: Optional[float] = None
    resistance: Optional[float] = None
    details: List[str] = field(default_factory=list)
    sector: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DragonStrategyReport:
    report_date: str
    report_type: str
    market: MarketEnvironment
    leaders: List[LeaderCandidate]
    sectors: List[SectorSignal] = field(default_factory=list)
    trend_rotation: Dict[str, Any] = field(default_factory=dict)
    trend_tracking: List[TrendCandidate] = field(default_factory=list)
    markdown: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _clean_dict(asdict(self))
