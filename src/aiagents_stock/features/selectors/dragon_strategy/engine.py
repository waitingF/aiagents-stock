"""Orchestration engine for dragon strategy workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

import pandas as pd

from src.aiagents_stock.features.selectors.dragon_strategy.backtest import BacktestEngine, BacktestResult
from src.aiagents_stock.features.selectors.dragon_strategy.data import (
    AkshareDragonDataProvider,
    normalize_limit_up_pool,
    normalize_stock_code,
)
from src.aiagents_stock.features.selectors.dragon_strategy.leader import screen_limit_up_candidates
from src.aiagents_stock.features.selectors.dragon_strategy.models import (
    DragonStrategyConfig,
    DragonStrategyReport,
    LeaderCandidate,
    MarketEnvironment,
    SectorSignal,
    TrendCandidate,
)
from src.aiagents_stock.features.selectors.dragon_strategy.position import calculate_dragon_position
from src.aiagents_stock.features.selectors.dragon_strategy.report import format_markdown_report
from src.aiagents_stock.features.selectors.dragon_strategy.repository import DragonStrategyRepository
from src.aiagents_stock.features.selectors.dragon_strategy.sector import compute_sector_signals, normalize_industry_ranking
from src.aiagents_stock.features.selectors.dragon_strategy.sentiment import MarketEnvironmentService
from src.aiagents_stock.features.selectors.dragon_strategy.trend import (
    generate_rotation_signals,
    normalize_realtime_quotes,
    scan_trend_tracking,
)


def _trade_date(date: str | None = None) -> str:
    return (date or datetime.now().strftime("%Y%m%d")).replace("-", "")


class DragonStrategyEngine:
    """High-level runner for the ordered dragon strategy roadmap."""

    def __init__(
        self,
        provider: Any | None = None,
        repository: DragonStrategyRepository | None = None,
        config: DragonStrategyConfig | None = None,
    ) -> None:
        self.provider = provider or AkshareDragonDataProvider()
        self.repository = repository or DragonStrategyRepository()
        self.config = config or DragonStrategyConfig()
        self.market_service = MarketEnvironmentService(self.provider, self.config)
        self.backtest_engine = BacktestEngine()
        self.last_sector_diagnostics: dict[str, Any] = {}

    def run_dragon_mvp(self, date: str | None = None, persist: bool = True) -> DragonStrategyReport:
        """Step 1: market gate plus strict dragon candidate screening."""
        trade_date = _trade_date(date)
        run_id = self.repository.create_run("dragon_mvp", {"date": trade_date}) if persist else None
        try:
            market = self.market_service.evaluate(trade_date)
            limit_up_df = self._safe_provider_call("get_limit_up_pool", trade_date, default=pd.DataFrame())
            leaders = self._build_leaders(trade_date, market, limit_up_df)
            report = DragonStrategyReport(
                report_date=trade_date,
                report_type="dragon_mvp",
                market=market,
                leaders=leaders,
                metadata={"workflow_step": 1},
            )
            position = calculate_dragon_position(market.score, config=self.config)
            report.markdown = format_markdown_report(report, position)
            report_id = self.repository.save_report(report) if persist else None
            if run_id:
                self.repository.finish_run(run_id, "success", report_id)
            return report
        except Exception as exc:
            if run_id:
                self.repository.finish_run(run_id, "failed", error_message=str(exc))
            raise

    def track_main_sectors(
        self,
        date: str | None = None,
        industry_rank_df: pd.DataFrame | None = None,
        limit_up_df: pd.DataFrame | None = None,
        persist: bool = True,
        top_n: int = 20,
    ) -> list[SectorSignal]:
        """Step 2: track mainline sectors and their historical state."""
        trade_date = _trade_date(date)
        if industry_rank_df is None:
            industry_rank_df = self._safe_provider_call("get_industry_ranking", trade_date, default=pd.DataFrame())
        if limit_up_df is None:
            limit_up_df = self._safe_provider_call("get_limit_up_pool", trade_date, default=pd.DataFrame())
        normalized_rank = normalize_industry_ranking(industry_rank_df)
        history = self.repository.get_recent_sector_history(limit_days=60)
        signals = compute_sector_signals(
            industry_rank_df=industry_rank_df,
            limit_up_df=limit_up_df,
            history=history,
            config=self.config,
            date=trade_date,
            top_n=top_n,
        )
        source = ""
        if industry_rank_df is not None and not industry_rank_df.empty and "source" in industry_rank_df.columns:
            source = str(industry_rank_df["source"].iloc[0])
        self.last_sector_diagnostics = {
            "trade_date": trade_date,
            "raw_rank_rows": 0 if industry_rank_df is None else int(len(industry_rank_df)),
            "normalized_rank_rows": int(len(normalized_rank)),
            "limit_up_rows": 0 if limit_up_df is None else int(len(limit_up_df)),
            "output_rows": int(len(signals)),
            "missing_rank_rows": int(sum(1 for item in signals if item.rank is None)),
            "source": source,
            "top_n": top_n,
        }
        if persist:
            self.repository.save_sector_signals(trade_date, signals)
        return signals

    def scan_trends(
        self,
        date: str | None = None,
        quotes_df: pd.DataFrame | None = None,
        daily_by_code: Optional[Dict[str, pd.DataFrame]] = None,
        top_n: int = 20,
    ) -> list[TrendCandidate]:
        """Step 3: trend tracking from daily frames and optional live quotes."""
        trade_date = _trade_date(date)
        if quotes_df is None:
            quotes_df = self._safe_provider_call("get_realtime_quotes", default=pd.DataFrame())
        quote_frame = normalize_realtime_quotes(quotes_df)
        if daily_by_code is None:
            daily_by_code = self._fetch_daily_for_quotes(quote_frame, trade_date)
        meta_by_code = {
            normalize_stock_code(row["code"]): {"name": row.get("name", ""), "sector": row.get("sector", "")}
            for row in quote_frame.to_dict("records")
        }
        return scan_trend_tracking(
            daily_by_code=daily_by_code,
            quotes_df=quote_frame,
            stock_meta_by_code=meta_by_code,
            config=self.config,
            top_n=top_n,
        )

    def generate_daily_report(self, date: str | None = None, persist: bool = True) -> DragonStrategyReport:
        """Step 4 daily report: market, dragon MVP, sectors, trend rotation, tracking."""
        trade_date = _trade_date(date)
        run_id = self.repository.create_run("daily_report", {"date": trade_date}) if persist else None
        try:
            market = self.market_service.evaluate(trade_date)
            limit_up_df = self._safe_provider_call("get_limit_up_pool", trade_date, default=pd.DataFrame())
            leaders = self._build_leaders(trade_date, market, limit_up_df)
            sectors = self.track_main_sectors(
                date=trade_date,
                limit_up_df=limit_up_df,
                persist=persist,
            )
            trend_candidates = self.scan_trends(date=trade_date, top_n=20)
            rotation = generate_rotation_signals(sectors, trend_candidates)
            report = DragonStrategyReport(
                report_date=trade_date,
                report_type="daily_report",
                market=market,
                leaders=leaders,
                sectors=sectors,
                trend_rotation=rotation,
                trend_tracking=trend_candidates,
                metadata={"workflow_step": 4},
            )
            position = calculate_dragon_position(market.score, leader_counts=self._leader_counts(leaders), config=self.config)
            report.markdown = format_markdown_report(report, position)
            report_id = self.repository.save_report(report) if persist else None
            if run_id:
                self.repository.finish_run(run_id, "success", report_id)
            return report
        except Exception as exc:
            if run_id:
                self.repository.finish_run(run_id, "failed", error_message=str(exc))
            raise

    def run_backtest(
        self,
        signals: Iterable[Any],
        daily_by_code: Dict[str, pd.DataFrame],
        holding_days: int = 5,
        stop_loss_pct: float = 0.05,
        take_profit_pct: Optional[float] = None,
    ) -> BacktestResult:
        """Step 4 backtest; research-only and detached from trading systems."""
        return self.backtest_engine.run_fixed_holding(
            signals=signals,
            daily_by_code=daily_by_code,
            holding_days=holding_days,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
        )

    def _build_leaders(
        self,
        trade_date: str,
        market: MarketEnvironment,
        limit_up_df: pd.DataFrame | None,
    ) -> list[LeaderCandidate]:
        if not market.passed:
            return []
        frame = normalize_limit_up_pool(limit_up_df) if limit_up_df is not None and "code" not in limit_up_df.columns else limit_up_df
        if frame is None or frame.empty:
            return []
        stock_info_by_code: dict[str, dict[str, Any]] = {}
        daily_by_code: dict[str, pd.DataFrame] = {}
        for row in frame.head(self.config.max_fetch_candidates).to_dict("records"):
            code = normalize_stock_code(row.get("code", ""))
            if not code:
                continue
            stock_info_by_code[code] = self._safe_provider_call("get_stock_info", code, default={})
            daily_by_code[code] = self._safe_provider_call("get_stock_daily", code, trade_date, default=pd.DataFrame())
        return screen_limit_up_candidates(
            limit_up_df=frame,
            stock_info_by_code=stock_info_by_code,
            daily_by_code=daily_by_code,
            config=self.config,
            date=trade_date,
        )

    def _fetch_daily_for_quotes(self, quote_frame: pd.DataFrame, trade_date: str) -> dict[str, pd.DataFrame]:
        daily_by_code: dict[str, pd.DataFrame] = {}
        if quote_frame.empty:
            return daily_by_code
        candidates = quote_frame.copy()
        if "amount" in candidates:
            candidates = candidates.sort_values("amount", ascending=False, na_position="last")
        for row in candidates.head(self.config.max_fetch_candidates).to_dict("records"):
            code = normalize_stock_code(row.get("code", ""))
            if not code:
                continue
            daily_by_code[code] = self._safe_provider_call("get_stock_daily", code, trade_date, default=pd.DataFrame())
        return daily_by_code

    def _leader_counts(self, leaders: list[LeaderCandidate]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for leader in leaders:
            counts[leader.level] = counts.get(leader.level, 0) + 1
        return counts

    def _safe_provider_call(self, method_name: str, *args: Any, default: Any = None) -> Any:
        method = getattr(self.provider, method_name, None)
        if method is None:
            return default
        try:
            return method(*args)
        except Exception:
            return default
