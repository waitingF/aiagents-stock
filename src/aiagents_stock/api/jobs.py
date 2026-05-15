"""In-memory background job manager used by API endpoints."""

from __future__ import annotations

import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, Callable, Dict, Optional

from src.aiagents_stock.api.serialization import to_jsonable


@dataclass
class Job:
    id: str
    name: str
    status: str = "queued"
    progress: int = 0
    message: str = "Queued"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    result: Any = None
    error: Optional[str] = None
    traceback: Optional[str] = None

    def snapshot(self) -> Dict[str, Any]:
        return to_jsonable(self.__dict__)


class JobManager:
    """Small thread-backed job manager for long stock analysis calls."""

    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._jobs: Dict[str, Job] = {}
        self._lock = Lock()

    def submit(self, name: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Job:
        job = Job(id=uuid.uuid4().hex, name=name)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job.id, fn, args, kwargs)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda item: item.created_at, reverse=True)
        return [job.snapshot() for job in jobs]

    def update(self, job_id: str, progress: int, message: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.progress = max(0, min(100, int(progress)))
            job.message = message
            job.updated_at = datetime.now().isoformat()

    def progress_callback(self, job_id: str) -> Callable[..., None]:
        def callback(*args: Any) -> None:
            if len(args) >= 2 and isinstance(args[0], (int, float)):
                self.update(job_id, int(args[0]), str(args[1]))
            elif len(args) >= 4:
                current, total, code, status = args[:4]
                progress = int((float(current) / max(float(total), 1.0)) * 100)
                self.update(job_id, progress, f"{code}: {status}")
            elif args:
                self.update(job_id, 0, " ".join(str(item) for item in args))

        return callback

    def _run(self, job_id: str, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.progress = max(job.progress, 1)
            job.message = "Running"
            job.updated_at = datetime.now().isoformat()

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                job = self._jobs[job_id]
                job.status = "completed"
                job.progress = 100
                job.message = "Completed"
                job.result = to_jsonable(result)
                job.updated_at = datetime.now().isoformat()
        except Exception as exc:
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.error = str(exc)
                job.traceback = traceback.format_exc()
                job.message = "Failed"
                job.updated_at = datetime.now().isoformat()


job_manager = JobManager()
