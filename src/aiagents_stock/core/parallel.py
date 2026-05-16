"""Shared helpers for thread-backed parallel task execution."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Hashable, Iterable, Iterator, Mapping, Optional, Tuple


ErrorHandler = Callable[[Exception], Any]


@dataclass(frozen=True)
class ParallelTask:
    """A keyed callable that can be run in a thread pool."""

    key: Hashable
    func: Callable[..., Any]
    args: Tuple[Any, ...] = ()
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    on_error: Optional[ErrorHandler] = None


@dataclass(frozen=True)
class ParallelTaskResult:
    """Result for one completed parallel task."""

    key: Hashable
    value: Any = None
    error: Optional[Exception] = None
    completed: int = 0
    total: int = 0


def iter_parallel_results(
    tasks: Iterable[ParallelTask],
    max_workers: int,
) -> Iterator[ParallelTaskResult]:
    """Yield task results as they complete.

    Exceptions are captured in ``ParallelTaskResult.error`` unless the task has
    an ``on_error`` handler, in which case the handler's return value is used.
    """

    task_list = list(tasks)
    if not task_list:
        return

    worker_count = max(1, min(int(max_workers), len(task_list)))
    completed = 0
    total = len(task_list)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_task = {
            executor.submit(task.func, *task.args, **dict(task.kwargs)): task
            for task in task_list
        }

        for future in as_completed(future_to_task):
            task = future_to_task[future]
            completed += 1
            try:
                value = future.result()
            except Exception as exc:
                if task.on_error is None:
                    yield ParallelTaskResult(
                        key=task.key,
                        error=exc,
                        completed=completed,
                        total=total,
                    )
                    continue
                try:
                    value = task.on_error(exc)
                except Exception as handler_exc:
                    yield ParallelTaskResult(
                        key=task.key,
                        error=handler_exc,
                        completed=completed,
                        total=total,
                    )
                    continue

            yield ParallelTaskResult(
                key=task.key,
                value=value,
                completed=completed,
                total=total,
            )


def run_parallel_tasks(
    tasks: Iterable[ParallelTask],
    max_workers: int,
    preserve_order: bool = True,
) -> Dict[Hashable, Any]:
    """Run keyed tasks and return a key-to-result mapping.

    When ``preserve_order`` is true, the returned dict follows the input task
    order. Unhandled task exceptions are re-raised in the caller.
    """

    task_list = list(tasks)
    completed_results: Dict[Hashable, Any] = {}

    for result in iter_parallel_results(task_list, max_workers=max_workers):
        if result.error is not None:
            raise result.error
        completed_results[result.key] = result.value

    if not preserve_order:
        return completed_results

    return {
        task.key: completed_results[task.key]
        for task in task_list
        if task.key in completed_results
    }
