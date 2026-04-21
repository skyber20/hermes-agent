from typing import Any

import aiohttp

from api.clients.browser_rpc_contracts import BrowserRpcError


class BrowserRpcClient:
    def __init__(self, rpc_url: str, session: aiohttp.ClientSession) -> None:
        self._rpc_url = rpc_url
        self._session = session

    async def run(self, task: str, timeout_sec: float) -> dict[str, Any]:
        payload = {"task": task}
        timeout = aiohttp.ClientTimeout(total=timeout_sec)

        try:
            async with self._session.post(self._rpc_url, json=payload, timeout=timeout) as response:
                if response.status >= 400:
                    body = await response.text()
                    raise BrowserRpcError(f"RPC HTTP: {response.status}: {body}")

                try:
                    data = await response.json(content_type=None)
                except aiohttp.ContentTypeError as exc:
                    raise BrowserRpcError("RPC returned non-JSON response") from exc
        except aiohttp.ClientError as exc:
            raise BrowserRpcError(f"Transport error: {exc}") from exc

        if not isinstance(data, dict):
            raise BrowserRpcError("RPC returned invalid payload type")

        return data


async def run_browser_task(rpc_url: str, task: str, timeout_sec: float) -> dict[str, Any]:
    async with aiohttp.ClientSession() as session:
        return await BrowserRpcClient(rpc_url, session=session).run(task=task, timeout_sec=timeout_sec)
