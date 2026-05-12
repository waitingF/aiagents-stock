"""Local full-market data-store adapter.

This module keeps aiagents-stock insulated from the stock-data-store
submodule's internal layout while exposing a small API for update jobs and
selector-friendly local reads.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd

from src.aiagents_stock.core.paths import data_path
from src.aiagents_stock.integrations.stock_data_store.loader import ensure_stock_data_store_loaded


class StockDataStoreService:
    """Facade around the stock-data-store submodule."""

    def __init__(self, data_root: str | Path | None = None) -> None:
        self.data_root = Path(data_root) if data_root else data_path("stock_data")
        self.daily_dir = self.data_root / "daily"
        self.meta_dir = self.data_root / "meta"

    def build_config(self, overrides: Optional[dict] = None) -> dict:
        """Build a stock-data-store config rooted under this project."""
        config = {
            "data": {
                "data_root": str(self.data_root),
                "daily_dir": str(self.daily_dir),
                "meta_dir": str(self.meta_dir),
                "adj": os.getenv("STOCK_DATA_ADJ", "qfq"),
                "refresh": False,
                "batch_size": int(os.getenv("STOCK_DATA_BATCH_SIZE", "50")),
                "max_workers": int(os.getenv("STOCK_DATA_MAX_WORKERS", "4")),
                "requests_per_second": float(os.getenv("STOCK_DATA_REQUESTS_PER_SECOND", "4.0")),
                "retry": int(os.getenv("STOCK_DATA_RETRY", "3")),
                "retry_interval": float(os.getenv("STOCK_DATA_RETRY_INTERVAL", "1.0")),
                "adjustment_detect": {
                    "enabled": os.getenv("STOCK_DATA_ADJUSTMENT_DETECT_ENABLED", "true").lower() == "true",
                    "price_tolerance": float(os.getenv("STOCK_DATA_ADJUSTMENT_PRICE_TOLERANCE", "0.001")),
                },
                "fundamental": {
                    "enabled": True,
                    "datasets": ["daily_basic", "fina_indicator", "income"],
                    "incremental_lookback_days": int(
                        os.getenv("STOCK_DATA_FUNDAMENTAL_INCREMENTAL_LOOKBACK_DAYS", "5")
                    ),
                },
                "universe": {
                    "list_status": ["L"],
                    "exchanges": ["SSE", "SZSE"],
                    "include_st": os.getenv("STOCK_DATA_UNIVERSE_INCLUDE_ST", "false").lower() == "true",
                    "min_list_days": int(os.getenv("STOCK_DATA_UNIVERSE_MIN_LIST_DAYS", "120")),
                },
            }
        }
        if overrides:
            self._deep_update(config, overrides)
        return config

    def get_manager(self, config_overrides: Optional[dict] = None):
        """Create a stock-data-store DataManager for remote update operations."""
        module = ensure_stock_data_store_loaded()
        return module.DataManager.from_tushare(config=self.build_config(config_overrides))

    def read_daily(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """Read locally cached daily bars without touching remote APIs."""
        ensure_stock_data_store_loaded()
        from stock_data_store.stores.csv_store import CsvStore

        ts_code = self.to_ts_code(symbol)
        store = CsvStore(
            data_root=str(self.data_root),
            daily_dir=str(self.daily_dir),
            meta_dir=str(self.meta_dir),
        )
        frame = store.slice_daily(ts_code, start_date=start_date, end_date=end_date)
        return self._to_provider_daily_frame(frame, symbol)

    def has_daily(self, symbol: str) -> bool:
        return (self.daily_dir / f"{self.to_ts_code(symbol)}.csv").exists()

    def update_symbol_daily(
        self,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
        force: bool = False,
        adj: str | None = None,
    ) -> pd.DataFrame:
        manager = self.get_manager()
        frame = manager.update_symbol_daily(
            symbol=self.to_ts_code(symbol),
            start_date=start_date,
            end_date=end_date,
            force=force,
            adj=adj,
        )
        return self._to_provider_daily_frame(frame, symbol)

    def update_daily_all(
        self,
        symbols: Optional[Iterable[str]] = None,
        start_date: str | None = None,
        end_date: str | None = None,
        force: bool = False,
        refresh_stock_basic: bool = False,
        limit: int | None = None,
    ) -> dict:
        manager = self.get_manager()
        normalized = [self.to_ts_code(symbol) for symbol in symbols] if symbols else None
        return manager.update_daily_data(
            symbols=normalized,
            start_date=start_date,
            end_date=end_date,
            force=force,
            refresh_stock_basic=refresh_stock_basic,
            limit=limit,
        )

    def update_fundamental_all(
        self,
        symbols: Optional[Iterable[str]] = None,
        datasets: Optional[list[str]] = None,
        force: bool = False,
        refresh_stock_basic: bool = False,
        limit: int | None = None,
        end_date: str | None = None,
    ) -> dict:
        manager = self.get_manager()
        normalized = [self.to_ts_code(symbol) for symbol in symbols] if symbols else None
        return manager.update_fundamental_data(
            symbols=normalized,
            datasets=datasets,
            force=force,
            refresh_stock_basic=refresh_stock_basic,
            limit=limit,
            end_date=end_date,
        )

    @contextmanager
    def stock_data_environment(self):
        """Temporarily set STOCK_DATA_* env vars for submodule CLI entrypoints."""
        updates = {
            "STOCK_DATA_ROOT": str(self.data_root),
            "STOCK_DATA_DAILY_DIR": str(self.daily_dir),
            "STOCK_DATA_META_DIR": str(self.meta_dir),
            "STOCK_DATA_ADJ": os.getenv("STOCK_DATA_ADJ", "qfq"),
        }
        old_values = {key: os.environ.get(key) for key in updates}
        os.environ.update(updates)
        try:
            yield
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def to_ts_code(self, symbol: str) -> str:
        symbol = str(symbol).strip().upper()
        if "." in symbol:
            return symbol
        if len(symbol) != 6:
            return symbol
        if symbol.startswith("6"):
            return f"{symbol}.SH"
        if symbol.startswith(("0", "3")):
            return f"{symbol}.SZ"
        if symbol.startswith(("4", "8")):
            return f"{symbol}.BJ"
        return f"{symbol}.SZ"

    def from_ts_code(self, ts_code: str) -> str:
        return str(ts_code).split(".")[0]

    def _to_provider_daily_frame(self, frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        result = frame.copy()
        result = result.rename(columns={"ts": "date"})
        result["date"] = pd.to_datetime(result["date"])
        result["symbol"] = self.from_ts_code(self.to_ts_code(symbol))
        columns = [col for col in ["symbol", "date", "open", "high", "low", "close", "volume"] if col in result]
        return result[columns].sort_values("date").reset_index(drop=True)

    def _deep_update(self, target: dict, source: dict) -> dict:
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._deep_update(target[key], value)
            else:
                target[key] = value
        return target


stock_data_store_service = StockDataStoreService()
