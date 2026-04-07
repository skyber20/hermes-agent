import time
import uuid
from asyncio import Lock
from dataclasses import dataclass, field
from typing import Any

from api.domain.task_status import TaskStatus


@dataclass
class TaskRecord:
    task_id: str
    task: str
    timeout: int
    metadata: dict[str, Any] | None
    status: TaskStatus = TaskStatus.queued
    create_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: str | None = None
    error: str | None = None
    raw_response: dict[str, Any] | None = None

    @property
    def execution_time(self) -> float:
        if self.started_at is None:
            return 0
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0, end - self.started_at)


class TaskStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._tasks: dict[str, TaskRecord] = {}

    async def create(self, task: str, timeout: int, metadata: dict[str, Any] | None) -> TaskRecord:
        task_id = uuid.uuid4().hex
        rec = TaskRecord(task_id=task_id, task=task, timeout=timeout, metadata=metadata)
        async with self._lock:
            self._tasks[task_id] = rec
        return rec

    async def get(self, task_id: str) -> TaskRecord | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def set_running(self, task_id: str) -> TaskRecord | None:
        async with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                return None
            rec.status = TaskStatus.running
            rec.started_at = time.time()
            return rec

    async def set_done(
            self,
            task_id: str,
            success: bool,
            raw_response: dict[str, Any] | None,
            error: str | None,
            result: str | None = None,
    ) -> TaskRecord | None:
        async with self._lock:
            rec = self._tasks.get(task_id)
            if rec is None:
                return None
            rec.finished_at = time.time()
            rec.raw_response = raw_response
            rec.error = error if error is not None else (
                raw_response.get("error") if isinstance(raw_response, dict) else None)
            rec.result = result if result is not None else (
                raw_response.get("result") if isinstance(raw_response, dict) else None)
            rec.status = TaskStatus.succeeded if success else TaskStatus.failed
            return rec
