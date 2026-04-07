from enum import Enum


class TaskStatus(str, Enum):
    """Состояние задачи браузерного агента."""
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
