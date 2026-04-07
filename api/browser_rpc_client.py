from typing import Any

import httpx


class BrowserRpcError(RuntimeError): ...


async def run_browser_task(rpc_url: str, task: str, timeout_sec: float) -> dict[str, Any]:
    payload = {"task": task}

    timeout = httpx.Timeout(timeout_sec)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(rpc_url, json=payload)
        except httpx.HTTPError as exc:
            raise BrowserRpcError(f"Transport error: {exc}")

    if response.status_code >= 400:
        body = response.text
        raise BrowserRpcError(f"RPC HTTP: {response.status_code}: {body}")

    try:
        data = response.json()
    except ValueError as exc:
        raise BrowserRpcError("RPC returned non-JSON response")

    if not isinstance(data, dict):
        raise BrowserRpcError("RPC returned invalid payload type")

    return data
