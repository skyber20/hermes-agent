from typing import Optional

from pydantic import BaseModel, Field


class BrowserTaskRequest(BaseModel):
    task: str = Field(..., description="Задача для браузера")
    timeout: int = Field(300, description="Максимальное время выполнения задачи в секундах")


class BrowserTaskResponse(BaseModel):
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    execution_time: float
