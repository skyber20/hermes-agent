import asyncio

from api.clients.browser_rpc_contracts import BrowserRpcError, BrowserRpcRunner
from api.repositories.task_store import TaskRecord, TaskStore


class TaskService:
    def __init__(
            self,
            store: TaskStore,
            rpc_client: BrowserRpcRunner,
            max_concurrency: int,
            rpc_timeout_cap: float | None = None,
    ) -> None:
        self._store = store
        self._rpc_client = rpc_client
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._rpc_timeout_cap = rpc_timeout_cap
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def submit_task(self, task: str, timeout: int, metadata: dict | None) -> TaskRecord:
        record = await self._store.create(task=task, timeout=timeout, metadata=metadata)
        background_task = asyncio.create_task(self._worker(record.task_id))
        self._background_tasks.add(background_task)
        background_task.add_done_callback(self._background_tasks.discard)
        return record

    async def get_task(self, task_id: str) -> TaskRecord | None:
        return await self._store.get(task_id)

    async def close(self) -> None:
        if not self._background_tasks:
            return

        for task in list(self._background_tasks):
            task.cancel()
        await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._background_tasks.clear()

    async def _worker(self, task_id: str) -> None:
        rec = await self._store.set_running(task_id)
        if rec is None:
            return

        async with self._semaphore:
            try:
                rpc_timeout = float(rec.timeout)
                if self._rpc_timeout_cap is not None:
                    rpc_timeout = min(rpc_timeout, self._rpc_timeout_cap)

                raw = await asyncio.wait_for(
                    self._rpc_client.run(task=rec.task, timeout_sec=rpc_timeout),
                    timeout=float(rec.timeout) + 5,
                )
                success = bool(raw.get("success"))
                await self._store.set_done(
                    task_id=task_id,
                    success=success,
                    raw_response=raw,
                    error=None,
                    result=raw.get("result") if isinstance(raw, dict) else None,
                )
            except asyncio.TimeoutError:
                await self._store.set_done(
                    task_id=task_id,
                    success=False,
                    raw_response=None,
                    error="Timeout exceeded",
                )
            except BrowserRpcError as exc:
                await self._store.set_done(
                    task_id=task_id,
                    success=False,
                    raw_response=None,
                    error=str(exc),
                )
            except Exception as exc:
                await self._store.set_done(
                    task_id=task_id,
                    success=False,
                    raw_response=None,
                    error=f"Internal error: {exc}",
                )
