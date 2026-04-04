import json
import os
import asyncio
import socket
import logging
from telegram import Bot
from telegram.constants import ParseMode
from browser_use import Agent, Browser, ChatOpenAI
from tools.registry import registry


logger = logging.getLogger("hermes.browser_use_tool")


def get_chat_id(honcho_session_key: str) -> str:
    if not honcho_session_key or not isinstance(honcho_session_key, str):
        logger.warning("нет honcho_session_key")
        return None
    
    if ':' in honcho_session_key:
        logger.info("получен honcho_session_key")
        return honcho_session_key.split(':')[-1]
    
    logger.warning("нет honcho_session_key")
    return None


async def notify_user_vnc(honcho_session_key: str, vnc_url: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = get_chat_id(honcho_session_key)
    
    if not token or not chat_id:
        logger.warning("Сообщение не отправлено: отсутствует токен или chat_id")
        return

    try:
        bot = Bot(token=token)
        text = (
            f"🌐 *Запуск браузера*\n\n"
            f"Ты можешь наблюдать за моими действиями здесь:\n"
            f"🔗 [ОТКРЫТЬ ТРАНСЛЯЦИЮ]({vnc_url})"
        )
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

        logger.info(f"Уведомление отправлено в Telegram для chat_id: {chat_id}")
    except Exception as e:
        logger.warning(f"Ошибка при отправке уведомления в Telegram: {str(e)}")


async def run_browser_task(task: str, honcho_session_key: str):
    browser_host = "browser"
    browser_port = 9222
    vnc_url = os.getenv("BROWSER_VIEW_URL", "")

    if honcho_session_key:
        asyncio.create_task(notify_user_vnc(honcho_session_key, vnc_url))
    
    try:
        browser_ip = socket.gethostbyname(browser_host)
        cdp_url = f"http://{browser_ip}:{browser_port}"
    except Exception:
        cdp_url = f"http://{browser_host}:{browser_port}"

    browser = Browser(cdp_url=cdp_url)

    # Для подключения к Chrome на виртуальной машине раскомментируй
    # browser = Browser(
    #     executable_path="/usr/bin/google-chrome",  # Linux
    #     # Windows: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    #     # macOS: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    # )
    # или
    # browser = Browser.from_system_chrome() для автоопределения

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

        return json.dumps({
            "success": True,
            "result": final_result,
            "vnc_url": vnc_url
        }, ensure_ascii=False)
        
    except Exception as e:
        return json.dumps({
            "success": False, 
            "error": f"Browser automation failed: {str(e)}"
        }, ensure_ascii=False)
        
    finally:
        if browser:
            await browser.stop()


registry.register(
    name="internet_browser",
    toolset="browse_cmd", 
    schema={
        "name": "internet_browser",
        "description": "ГЛАВНЫЙ ИНСТРУМЕНТ ДЛЯ ВЕБ-СЕРФИНГА. Вызывай напрямую.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "Задача для браузера"}
            },
            "required": ["task"]
        }
    },
    handler=lambda args, **kw: asyncio.run(run_browser_task(args.get("task", ""), kw.get("honcho_session_key", ""))),
    emoji="🌐",
)
