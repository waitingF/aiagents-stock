"""Local cache helpers for market data providers."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

import pandas as pd

from src.aiagents_stock.core.paths import data_path


class LocalDataCache:
    """Disk-backed daily cache for pandas DataFrames.

    Cache files are refreshed once per local calendar day. When a stale cache
    cannot be refreshed, callers may still fall back to the previous cached
    value so the application remains usable during transient data-source
    outages.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        today_provider: Optional[Callable[[], str]] = None,
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else data_path("market_data_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / "index.json"
        self.today_provider = today_provider or (lambda: datetime.now().strftime("%Y-%m-%d"))
        self._callbacks: Dict[str, Callable[[], pd.DataFrame]] = {}
        self._lock = threading.RLock()
        self._scheduler_started = False
        self._scheduler_thread: Optional[threading.Thread] = None

    def get_or_fetch(
        self,
        namespace: str,
        params: dict,
        fetcher: Callable[[], pd.DataFrame],
        force_refresh: bool = False,
        allow_stale_on_error: bool = True,
    ) -> pd.DataFrame:
        """Return a cached DataFrame, refreshing it when today's cache is absent."""
        key = self._cache_key(namespace, params)
        self._callbacks[key] = fetcher

        if not force_refresh and self.is_fresh(key):
            cached = self.read(key)
            if cached is not None:
                return cached

        try:
            df = fetcher()
            if df is not None and not df.empty:
                self.write(key, df, namespace, params)
            return df
        except Exception:
            if allow_stale_on_error:
                cached = self.read(key)
                if cached is not None and not cached.empty:
                    return cached
            raise

    def start_daily_auto_update(self, update_time: str = "18:30") -> None:
        """Start a daemon thread that refreshes registered stale cache entries daily."""
        with self._lock:
            if self._scheduler_started:
                return
            self._scheduler_started = True
            self._scheduler_thread = threading.Thread(
                target=self._run_update_loop,
                args=(update_time,),
                name="market-data-cache-updater",
                daemon=True,
            )
            self._scheduler_thread.start()

    def refresh_registered(self) -> dict:
        """Refresh all callbacks registered in the current process."""
        result = {"checked": 0, "updated": 0, "failed": 0}
        for key, fetcher in list(self._callbacks.items()):
            result["checked"] += 1
            metadata = self._index().get(key, {})
            try:
                df = fetcher()
                if df is not None and not df.empty:
                    self.write(key, df, metadata.get("namespace", "unknown"), metadata.get("params", {}))
                    result["updated"] += 1
            except Exception:
                result["failed"] += 1
        return result

    def is_fresh(self, key: str) -> bool:
        metadata = self._index().get(key)
        return bool(metadata and metadata.get("cache_date") == self.today_provider())

    def read(self, key: str) -> Optional[pd.DataFrame]:
        metadata = self._index().get(key)
        if not metadata:
            return None
        path = self.cache_dir / metadata.get("filename", "")
        if not path.exists():
            return None
        try:
            return pd.read_pickle(path)
        except Exception:
            return None

    def write(self, key: str, df: pd.DataFrame, namespace: str, params: dict) -> None:
        filename = f"{key}.pkl"
        path = self.cache_dir / filename
        with self._lock:
            df.to_pickle(path)
            index = self._index()
            index[key] = {
                "namespace": namespace,
                "params": params,
                "filename": filename,
                "cache_date": self.today_provider(),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "rows": int(len(df)),
            }
            self._write_index(index)

    def _run_update_loop(self, update_time: str) -> None:
        last_run_date: Optional[str] = None
        while True:
            now = datetime.now()
            today = self.today_provider()
            if now.strftime("%H:%M") >= update_time and last_run_date != today:
                self.refresh_registered()
                last_run_date = today
            time.sleep(60)

    def _cache_key(self, namespace: str, params: dict) -> str:
        payload = json.dumps({"namespace": namespace, "params": params}, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        safe_namespace = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in namespace)
        return f"{safe_namespace}_{digest}"

    def _index(self) -> dict:
        if not self.index_path.exists():
            return {}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_index(self, index: dict) -> None:
        self.index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
