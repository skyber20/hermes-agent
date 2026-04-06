import json
import os
from urllib import error, request
from tools.registry import registry


def run_browser_task(task):
    if not task or not str(task).strip():
        return json.dumps({"success": False, "error": "Task is required"}, ensure_ascii=False)

    rpc_url = os.getenv("BROWSER_USE_RPC_URL", "http://browser:8787/run")
    timeout_sec = int(os.getenv("BROWSER_USE_RPC_TIMEOUT", "900"))
    payload = json.dumps({"task": task}).encode("utf-8")
    req = request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read().decode("utf-8")
            return body
    except error.HTTPError as http_err:
        body = http_err.read().decode("utf-8", errors="replace")
        return json.dumps(
            {
                "success": False,
                "error": f"browser-use RPC returned HTTP {http_err.code}",
                "details": body,
            },
            ensure_ascii=False,
        )
    except Exception as err:
        return json.dumps(
            {
                "success": False,
                "error": f"browser-use RPC request failed: {err}",
            },
            ensure_ascii=False,
        )


registry.register(
    name="internet_browser",
    toolset="browse_cmd", 
    schema={
        "name": "internet_browser",
        "description": (
            "ГЛАВНЫЙ ИНСТРУМЕНТ ДЛЯ ВЕБ-СЕРФИНГА. Вызывай этот инструмент НАПРЯМУЮ (через стандартный tool call/function call). "
            "КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать `execute_code` или `delegate_task` для работы с браузером. "
            "Не пиши Python-скрипты! Просто передай в этот инструмент параметр `task`. "
            "Используй для любых задач в интернете: поиск товаров (Wildberries, Ozon), чтение статей, клики, навигация."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string", 
                    "description": "Подробная задача на естественном языке. Например: 'Зайди на wildberries.ru, найди черную футболку и верни цену'."
                }
            },
            "required": ["task"]
        }
    },
 
    handler=lambda args, **kw: run_browser_task(args.get("task")),
    emoji="🌐",
)