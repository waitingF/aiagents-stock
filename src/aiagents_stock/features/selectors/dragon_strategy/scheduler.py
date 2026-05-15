"""Local scheduler for dragon strategy daily reports."""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

import schedule

from src.aiagents_stock.features.selectors.dragon_strategy.engine import DragonStrategyEngine


class DragonStrategyScheduler:
    """Run daily report jobs locally; it only stores reports in SQLite."""

    def __init__(self, engine: Optional[DragonStrategyEngine] = None) -> None:
        self.engine = engine or DragonStrategyEngine()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_result: Optional[dict[str, Any]] = None
        self._last_error: str = ""

    def start(self, schedule_time: str = "20:00") -> None:
        if self._thread and self._thread.is_alive():
            return
        schedule.clear("dragon_strategy_daily")
        schedule.every().day.at(schedule_time).do(self._run_daily_report).tag("dragon_strategy_daily")
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        schedule.clear("dragon_strategy_daily")

    def manual_run(self, date: str | None = None) -> dict[str, Any]:
        report = self.engine.generate_daily_report(date=date, persist=True)
        self._last_result = report.to_dict()
        self._last_error = ""
        return self._last_result

    def status(self) -> dict[str, Any]:
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "last_result": self._last_result,
            "last_error": self._last_error,
        }

    def _loop(self) -> None:
        while not self._stop.is_set():
            schedule.run_pending()
            time.sleep(1)

    def _run_daily_report(self) -> None:
        try:
            self.manual_run()
        except Exception as exc:
            self._last_error = str(exc)
