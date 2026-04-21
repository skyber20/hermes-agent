import json
import os
from urllib import error, request
from tools.registry import registry

logger = logging.getLogger("hermes.browser_use_tool")


def get_chat_id(honcho_session_key: str) -> str:
    if not honcho_session_key or not isinstance(honcho_session_key, str):
        logger.warning("нет honcho_session_key")
        return None
    
    if ":" in honcho_session_key:
        logger.info("получен honcho_session_key")
        return honcho_session_key.split(":")[-1]
    
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


async def run_browser_task(task: str, honcho_session_key: str = None):
    if not task or not str(task).strip():
        return json.dumps({"success": False, "error": "Task is required"}, ensure_ascii=False)

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

    rpc_url = os.getenv("BROWSER_USE_RPC_URL", "http://browser:8787/run")
    timeout_sec = int(os.getenv("BROWSER_USE_RPC_TIMEOUT", "900"))
    payload = json.dumps({"task": task}).encode("utf-8")
    req = request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    try:
        def _do_rpc():
            with request.urlopen(req, timeout=timeout_sec) as resp:
                return resp.read().decode("utf-8")
        
        body = await asyncio.to_thread(_do_rpc)
        
        try:
            resp_json = json.loads(body)
            if isinstance(resp_json, dict):
                if "vnc_url" not in resp_json:
                    resp_json["vnc_url"] = vnc_url
                return json.dumps(resp_json, ensure_ascii=False)
        except:
            pass
            
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
