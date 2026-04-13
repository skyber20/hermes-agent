from typing import Any, Protocol


class BrowserRpcError(RuntimeError): ...


class BrowserRpcRunner(Protocol):
    async def run(self, task: str, timeout_sec: float) -> dict[str, Any]: ...
