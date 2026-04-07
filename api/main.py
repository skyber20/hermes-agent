import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from api.browser_rpc_client import BrowserRpcError
from api.config import settings
from api.schemas import BrowserTaskRequest, BrowserTaskAcceptedResponse, BrowserTaskStatusResponse, \
    BrowserTaskResultResponse, TaskStatus
from api.task_store import TaskStore
from api.browser_rpc_client import run_browser_task

store = TaskStore()
_semaphore = asyncio.Semaphore(settings.max_concurrency)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="Browser API", version="1.0.0", lifespan=lifespan)


async def _worker(task_id: str) -> None:
    rec = await store.set_running(task_id)
    if rec is None:
        return None

    async with _semaphore:
        try:
            raw = await asyncio.wait_for(
                run_browser_task(
                    rpc_url=settings.browser_rpc_url,
                    task=rec.task,
                    timeout_sec=float(rec.timeout),
                ),
                timeout=float(rec.timeout) + 5,
            )
            success = bool(raw.get("success"))
            await store.set_done(task_id=task_id, success=success, raw_response=raw, error=None)
        except asyncio.TimeoutError:
            await store.set_done(
                task_id=task_id,
                success=False,
                raw_response=None,
                error="Timeout exceeded",
            )
        except BrowserRpcError as exc:
            await store.set_done(
                task_id=task_id,
                success=False,
                raw_response=None,
                error=str(exc),
            )
        except Exception as exc:
            await store.set_done(
                task_id=task_id,
                success=False,
                raw_response=None,
                error=f"Internal error: {exc}",
            )


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/api/browser/tasks", response_model=BrowserTaskAcceptedResponse, status_code=202)
async def create_task(payload: BrowserTaskRequest) -> BrowserTaskAcceptedResponse:
    rec = await store.create(task=payload.task.strip(), timeout=payload.timeout, metadata=payload.metadata)
    asyncio.create_task(_worker(rec.task_id))
    return BrowserTaskAcceptedResponse(task_id=rec.task_id, status=rec.status)


@app.get("/api/browser/tasks/{task_id}", response_model=BrowserTaskStatusResponse)
async def get_task_status(task_id: str) -> BrowserTaskStatusResponse:
    rec = await store.get(task_id=task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return BrowserTaskStatusResponse(task_id=rec.task_id, status=rec.status, create_at=rec.create_at,
                                     started_at=rec.started_at, finished_at=rec.finished_at, error=rec.error)


@app.get("/api/browser/tasks/{task_id}/result", response_model=BrowserTaskResultResponse)
async def get_task_result(task_id: str) -> BrowserTaskResultResponse:
    rec = await store.get(task_id=task_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if rec.status in (TaskStatus.queued, TaskStatus.running):
        return JSONResponse(status_code=202, content={
            "task_id": rec.task_id,
            "status": rec.status,
            "success": False,
            "execution_time": rec.execution_time,
            "result": None,
            "error": None,
            "raw_response": None,
        })

    return BrowserTaskResultResponse(
        task_id=rec.task_id,
        status=rec.status,
        success=(rec.status == "succeeded"),
        execution_time=rec.execution_time,
        result=rec.result,
        error=rec.error,
        raw_response=rec.raw_response,
    )
