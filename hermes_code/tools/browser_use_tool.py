import json
import os
import asyncio
import socket
from browser_use import Agent, Browser, ChatOpenAI
from tools.registry import registry


async def run_browser_task(task):
    browser_host = "browser"
    browser_port = 9222
    BROWSER_VIEW_URL = os.getenv("BROWSER_VIEW_URL", "")
    
    try:
        browser_ip = socket.gethostbyname(browser_host)
        cdp_url = f"http://{browser_ip}:{browser_port}"
    except Exception:
        cdp_url = f"http://{browser_host}:{browser_port}"

    browser = Browser(cdp_url=cdp_url)
    # browser = Browser(
    #     config=BrowserConfig(
    #         chrome_instance_path="/usr/bin/google-chrome",  # путь к Chrome на ВМ
    #         # Для Windows: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    #         # Для macOS: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    #     )
    # )
    # для хрома на вирутальной машине

    llm = ChatOpenAI(
        model=os.getenv("MODEL_DEFAULT", "qwen3.5-122b"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.0,
    )

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        use_vision=False
    )

    try:
        history = await agent.run()
        final_result = history.final_result()

        response = {
            "success": True,
            "result": final_result,
            "browser_view": BROWSER_VIEW_URL
        }
        return json.dumps(response, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "success": False, 
            "error": f"Browser automation failed: {str(e)}"
        }, ensure_ascii=False)
        
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass


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
 
    handler=lambda args, **kw: asyncio.run(run_browser_task(args.get("task"))),
    emoji="🌐",
)