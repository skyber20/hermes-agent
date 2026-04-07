from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.contracts.task_schemas import (
    BrowserTaskAcceptedResponse,
    BrowserTaskRequest,
    BrowserTaskResultResponse,
    BrowserTaskStatusResponse,
)
from api.domain.task_status import TaskStatus
from api.repositories.task_store import TaskRecord
from api.services.task_service import TaskService

router = APIRouter(prefix="/api/browser", tags=["browser-tasks"])


def get_task_service(request: Request) -> TaskService:
    return request.app.state.task_service


@router.post("/tasks", response_model=BrowserTaskAcceptedResponse, status_code=202)
async def create_task(
        payload: BrowserTaskRequest,
        service: TaskService = Depends(get_task_service),
) -> BrowserTaskAcceptedResponse:
    rec = await service.submit_task(task=payload.task.strip(), timeout=payload.timeout, metadata=payload.metadata)
    return BrowserTaskAcceptedResponse(task_id=rec.task_id, status=rec.status)


@router.get("/tasks/{task_id}", response_model=BrowserTaskStatusResponse)
async def get_task_status(task_id: str, service: TaskService = Depends(get_task_service)) -> BrowserTaskStatusResponse:
    rec = await service.get_task(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_status_response(rec)


@router.get("/tasks/{task_id}/result", response_model=BrowserTaskResultResponse)
async def get_task_result(
        task_id: str,
        service: TaskService = Depends(get_task_service),
) -> JSONResponse | BrowserTaskResultResponse:
    rec = await service.get_task(task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if rec.status in (TaskStatus.queued, TaskStatus.running):
        return JSONResponse(
            status_code=202,
            content={
                "task_id": rec.task_id,
                "status": rec.status.value,
                "success": False,
                "execution_time": rec.execution_time,
                "result": None,
                "error": None,
                "raw_response": None,
            },
        )

    return BrowserTaskResultResponse(
        task_id=rec.task_id,
        status=rec.status,
        success=(rec.status == TaskStatus.succeeded),
        execution_time=rec.execution_time,
        result=rec.result,
        error=rec.error,
        raw_response=rec.raw_response,
    )


def _to_status_response(rec: TaskRecord) -> BrowserTaskStatusResponse:
    return BrowserTaskStatusResponse(
        task_id=rec.task_id,
        status=rec.status,
        create_at=rec.create_at,
        started_at=rec.started_at,
        finished_at=rec.finished_at,
        error=rec.error,
    )
