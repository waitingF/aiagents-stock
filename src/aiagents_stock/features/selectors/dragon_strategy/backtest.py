"""Backtesting helpers for dragon strategy research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from src.aiagents_stock.features.selectors.dragon_strategy.data import normalize_daily_frame, normalize_stock_code


def _signal_value(signal: Any, key: str, default: Any = None) -> Any:
    if isinstance(signal, dict):
        return signal.get(key, default)
    return getattr(signal, key, default)


@dataclass
class BacktestResult:
    trades: List[dict[str, Any]]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"trades": self.trades, "summary": self.summary}


class BacktestEngine:
    """Simple next-day-entry fixed-holding backtest; no trading integration."""

    def run_fixed_holding(
        self,
        signals: Iterable[Any],
        daily_by_code: Dict[str, pd.DataFrame],
        holding_days: int = 5,
        stop_loss_pct: float = 0.05,
        take_profit_pct: Optional[float] = None,
    ) -> BacktestResult:
        trades: list[dict[str, Any]] = []
        for signal in signals:
            code = normalize_stock_code(_signal_value(signal, "code", ""))
            if not code or code not in daily_by_code:
                continue
            signal_date = str(_signal_value(signal, "signal_date", _signal_value(signal, "date", ""))).replace("-", "")
            name = _signal_value(signal, "name", code)
            frame = normalize_daily_frame(daily_by_code[code])
            if frame.empty or "date" not in frame:
                continue
            frame = frame.copy()
            frame["trade_date_text"] = frame["date"].dt.strftime("%Y%m%d")
            if signal_date:
                eligible = frame[frame["trade_date_text"] > signal_date]
            else:
                eligible = frame
            if eligible.empty:
                continue
            entry_idx = int(eligible.index[0])
            exit_idx = min(entry_idx + max(holding_days, 1) - 1, len(frame) - 1)
            entry_row = frame.loc[entry_idx]
            entry_price = float(entry_row["open"] if "open" in frame and pd.notna(entry_row["open"]) else entry_row["close"])
            stop_price = entry_price * (1 - stop_loss_pct)
            take_price = entry_price * (1 + take_profit_pct) if take_profit_pct else None
            exit_reason = "到期"
            exit_price = float(frame.loc[exit_idx, "close"])
            actual_exit_idx = exit_idx

            for idx in range(entry_idx, exit_idx + 1):
                row = frame.loc[idx]
                low = float(row["low"] if "low" in frame and pd.notna(row["low"]) else row["close"])
                high = float(row["high"] if "high" in frame and pd.notna(row["high"]) else row["close"])
                if low <= stop_price:
                    exit_price = stop_price
                    actual_exit_idx = idx
                    exit_reason = "止损"
                    break
                if take_price is not None and high >= take_price:
                    exit_price = take_price
                    actual_exit_idx = idx
                    exit_reason = "止盈"
                    break

            ret = (exit_price - entry_price) / entry_price * 100 if entry_price else 0.0
            trades.append(
                {
                    "code": code,
                    "name": name,
                    "signal_date": signal_date,
                    "entry_date": frame.loc[entry_idx, "trade_date_text"],
                    "exit_date": frame.loc[actual_exit_idx, "trade_date_text"],
                    "entry_price": round(entry_price, 2),
                    "exit_price": round(exit_price, 2),
                    "return_pct": round(ret, 2),
                    "holding_days": actual_exit_idx - entry_idx + 1,
                    "exit_reason": exit_reason,
                }
            )

        return BacktestResult(trades=trades, summary=self._summarize(trades))

    def _summarize(self, trades: list[dict[str, Any]]) -> dict[str, Any]:
        if not trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_return": 0.0,
                "total_return": 0.0,
                "max_drawdown": 0.0,
                "profit_factor": 0.0,
            }
        returns = [float(item["return_pct"]) for item in trades]
        wins = [item for item in returns if item > 0]
        losses = [item for item in returns if item < 0]
        equity = 1.0
        peak = 1.0
        max_drawdown = 0.0
        for ret in returns:
            equity *= 1 + ret / 100
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, (equity - peak) / peak * 100)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        return {
            "total_trades": len(trades),
            "win_rate": round(len(wins) / len(trades) * 100, 2),
            "avg_return": round(sum(returns) / len(returns), 2),
            "total_return": round((equity - 1) * 100, 2),
            "max_drawdown": round(max_drawdown, 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else 0.0,
        }
