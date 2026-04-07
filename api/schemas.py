from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class BrowserTaskRequest(BaseModel):
    task: str = Field(..., description="Задача для браузера")
    timeout: int = Field(300, description="Максимальное время выполнения задачи в секундах")
    metadata: dict[str, Any] | None = Field(default=None, description="Метаданные клиента")


class BrowserTaskAcceptedResponse(BaseModel):
    task_id: str
    status: TaskStatus


class BrowserTaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    create_at: float
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None


class BrowserTaskResultResponse(BaseModel):
    task_id: str
    status: TaskStatus
    success: bool
    execution_time: float
    result: str | None = None
    error: str | None = None
    raw_response: dict[str, Any] | None = None
