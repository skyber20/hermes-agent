import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request

from browser_use import Agent, Browser, ChatOpenAI


def _json_response(handler, status_code, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


async def run_browser_task(task):
    cdp_url = os.getenv("BROWSER_CDP_URL", "http://127.0.0.1:9222")
    browser_view_url = os.getenv("BROWSER_VIEW_URL", "")

    browser = Browser(cdp_url=cdp_url)

    llm = ChatOpenAI(
        model=os.getenv("MODEL_DEFAULT", "qwen3.5-122b"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        temperature=0.0,
    )

    agent = Agent(task=task, llm=llm, browser=browser, use_vision=False)

    try:
        history = await agent.run()
        return {
            "success": True,
            "result": history.final_result(),
            "browser_view": browser_view_url,
        }
    except Exception as err:
        return {"success": False, "error": f"Browser automation failed: {err}"}
    finally:
        try:
            await browser.close()
        except Exception:
            pass


class BrowserUseRPCHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            _json_response(self, 404, {"success": False, "error": "Not found"})
            return

        try:
            debug_url = os.getenv("BROWSER_HEALTH_URL", "http://127.0.0.1:9222/json/version")
            with request.urlopen(debug_url, timeout=2):
                pass
            _json_response(self, 200, {"success": True})
        except Exception as err:
            _json_response(self, 503, {"success": False, "error": f"Browser is not ready: {err}"})

    def do_POST(self):
        if self.path != "/run":
            _json_response(self, 404, {"success": False, "error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode("utf-8") if raw else "{}")
            task = payload.get("task", "")
            if not isinstance(task, str) or not task.strip():
                _json_response(self, 400, {"success": False, "error": "Field 'task' is required"})
                return

            result = asyncio.run(run_browser_task(task.strip()))
            code = 200 if result.get("success") else 500
            _json_response(self, code, result)
        except json.JSONDecodeError:
            _json_response(self, 400, {"success": False, "error": "Invalid JSON payload"})
        except error.URLError as err:
            _json_response(self, 503, {"success": False, "error": f"Transport error: {err}"})
        except Exception as err:
            _json_response(self, 500, {"success": False, "error": f"Internal error: {err}"})

    def log_message(self, format_str, *args):
        return


def main():
    host = os.getenv("BROWSER_USE_RPC_HOST", "0.0.0.0")
    port = int(os.getenv("BROWSER_USE_RPC_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), BrowserUseRPCHandler)
    print(f"browser-use RPC listening on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()

