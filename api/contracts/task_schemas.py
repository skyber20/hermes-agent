from typing import Any

from pydantic import BaseModel, Field

from api.domain.task_status import TaskStatus


class BrowserTaskRequest(BaseModel):
    """Запрос на запуск задачи в browser-use агенте."""

    task: str = Field(..., description="Текстовая задача для browser-use агента")
    timeout: int = Field(300, description="Максимальное время выполнения задачи в секундах")
    metadata: dict[str, Any] | None = Field(default=None, description="Дополнительные метаданные клиента")


class BrowserTaskAcceptedResponse(BaseModel):
    """Ответ о том, что задача принята в обработку."""

    task_id: str
    status: TaskStatus


class BrowserTaskStatusResponse(BaseModel):
    """Текущий статус задачи и временные отметки ее выполнения."""

    task_id: str
    status: TaskStatus
    create_at: float = Field(..., description="Время создания задачи в Unix timestamp")
    started_at: float | None = Field(default=None, description="Время начала выполнения в Unix timestamp")
    finished_at: float | None = Field(default=None, description="Время завершения выполнения в Unix timestamp")
    error: str | None = Field(default=None, description="Текст ошибки, если задача завершилась с ошибкой")


class BrowserTaskResultResponse(BaseModel):
    """Финальный результат выполнения задачи в browser-use."""

    task_id: str
    status: TaskStatus
    success: bool = Field(..., description="Успешно ли выполнена задача")
    execution_time: float = Field(..., description="Фактическое время выполнения в секундах")
    result: str | None = Field(default=None, description="Итоговый текстовый результат")
    error: str | None = Field(default=None, description="Текст ошибки, если выполнение не удалось")
    raw_response: dict[str, Any] | None = Field(default=None, description="Сырой ответ от browser-use RPC")
