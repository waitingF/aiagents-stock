"""Scheduler for stock pool analysis."""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime
from typing import Iterable, List, Optional

import schedule

from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager


class StockPoolScheduler:
    """In-process scheduler for stock pool analysis."""

    def __init__(self):
        self.schedule_times = ["15:05"]
        self.analysis_mode = "sequential"
        self.max_workers = 3
        self.auto_monitor_sync = True
        self.notification_enabled = True
        self.selected_agents = None
        self.scope = "today_unanalysed"
        self.pool_ids: Optional[List[int]] = None
        self._is_running = False
        self.thread = None
        self.last_run_time = None
        self.next_run_time = None

    @property
    def schedule_time(self) -> str:
        return self.schedule_times[0] if self.schedule_times else "15:05"

    def is_running(self) -> bool:
        return self._is_running

    def set_pool_ids(self, pool_ids: Optional[Iterable[int]]) -> None:
        self.pool_ids = [int(pool_id) for pool_id in pool_ids] if pool_ids else None

    def get_effective_pool_ids(self) -> List[int]:
        if self.pool_ids:
            return self.pool_ids
        return [stock_pool_manager.get_holding_pool()["id"]]

    def get_schedule_times(self) -> List[str]:
        return self.schedule_times.copy()

    def add_schedule_time(self, time_str: str) -> bool:
        datetime.strptime(time_str, "%H:%M")
        if time_str in self.schedule_times:
            return False
        self.schedule_times.append(time_str)
        self.schedule_times.sort()
        if self._is_running:
            self._reschedule()
        return True

    def remove_schedule_time(self, time_str: str) -> bool:
        if time_str not in self.schedule_times:
            return False
        self.schedule_times.remove(time_str)
        if self._is_running:
            self._reschedule()
        return True

    def set_schedule_times(self, times: List[str]) -> None:
        valid_times = []
        for time_str in times:
            datetime.strptime(time_str, "%H:%M")
            valid_times.append(time_str)
        if not valid_times:
            raise ValueError("至少需要一个有效时间")
        self.schedule_times = sorted(set(valid_times))
        if self._is_running:
            self._reschedule()

    def update_config(
        self,
        analysis_mode: str,
        max_workers: int,
        auto_sync_monitor: bool,
        send_notification: bool,
        scope: str = "today_unanalysed",
        pool_ids: Optional[Iterable[int]] = None,
    ) -> None:
        self.analysis_mode = analysis_mode if analysis_mode in {"sequential", "parallel"} else "sequential"
        self.max_workers = int(max_workers)
        self.auto_monitor_sync = bool(auto_sync_monitor)
        self.notification_enabled = bool(send_notification)
        self.scope = scope
        if pool_ids is not None:
            self.set_pool_ids(pool_ids)

    def get_next_run_time(self):
        jobs = [job for job in schedule.jobs if "stock_pool_analysis" in job.tags]
        if not jobs:
            return None
        next_run = min(job.next_run for job in jobs if job.next_run)
        self.next_run_time = next_run
        return next_run.strftime("%Y-%m-%d %H:%M:%S")

    def _scheduled_job(self):
        try:
            result = self.run_analysis_now()
            return result
        except Exception:
            traceback.print_exc()
            self.last_run_time = datetime.now()
            return None

    def _reschedule(self) -> None:
        self._clear_jobs()
        for time_str in self.schedule_times:
            schedule.every().day.at(time_str).do(self._scheduled_job).tag("stock_pool_analysis")

    def _clear_jobs(self) -> None:
        jobs_to_remove = [job for job in schedule.jobs if "stock_pool_analysis" in job.tags]
        for job in jobs_to_remove:
            schedule.cancel_job(job)

    def start_scheduler(self) -> bool:
        if self._is_running:
            return True
        self._reschedule()
        self._is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        return True

    def stop_scheduler(self) -> bool:
        if not self._is_running:
            return True
        self._is_running = False
        self._clear_jobs()
        return True

    def _run_loop(self) -> None:
        while self._is_running:
            schedule.run_pending()
            time.sleep(30)

    def run_analysis_now(self) -> dict:
        pool_ids = self.get_effective_pool_ids()
        result = stock_pool_manager.batch_analyze_pools(
            pool_ids=pool_ids,
            scope=self.scope,
            mode=self.analysis_mode,
            max_workers=self.max_workers,
            selected_agents=self.selected_agents,
        )
        sync_result = None
        if result.get("success") and self.auto_monitor_sync:
            sync_result = stock_pool_manager.sync_results_to_monitor(result)
            result["sync_result"] = sync_result
        if result.get("success") and self.notification_enabled:
            from src.aiagents_stock.integrations.notification.service import notification_service

            notification_service.send_portfolio_analysis_notification(result, sync_result)
        self.last_run_time = datetime.now()
        return result


stock_pool_scheduler = StockPoolScheduler()

