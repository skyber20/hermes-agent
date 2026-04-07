from contextlib import asynccontextmanager

import aiohttp
from fastapi import FastAPI

from api.clients.browser_rpc_client import BrowserRpcClient
from api.core.settings import settings
from api.repositories.task_store import TaskStore
from api.routes.tasks import router as tasks_router
from api.services.task_service import TaskService


@asynccontextmanager
async def lifespan(app: FastAPI):
    session = aiohttp.ClientSession()
    task_service = TaskService(
        store=TaskStore(),
        rpc_client=BrowserRpcClient(settings.browser_rpc_url, session=session),
        max_concurrency=settings.max_concurrency,
        rpc_timeout_cap=settings.browser_rpc_timeout,
    )
    app.state.task_service = task_service
    try:
        yield
    finally:
        await task_service.close()
        await session.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Browser API",
        version="1.0.0",
        description="REST API for submitting tasks to browser-use and retrieving their status/results.",
        lifespan=lifespan,
    )
    app.include_router(tasks_router)

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
