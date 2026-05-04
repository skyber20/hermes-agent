import asyncio
import json
import logging
import os
import socket
import uuid
from urllib import error, request
from urllib import parse as urlparse

from tools.registry import registry

logger = logging.getLogger("hermes.browser_use_tool")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float, minimum: float = 0.1) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _build_events_url(rpc_url: str) -> str:
    override = os.getenv("BROWSER_USE_EVENTS_URL", "").strip()
    if override:
        return override

    parsed = urlparse.urlparse(rpc_url)
    path = parsed.path or "/run"
    if path.endswith("/run"):
        path = path[: -len("/run")] + "/events"
    else:
        path = path.rstrip("/") + "/events"
    return urlparse.urlunparse(parsed._replace(path=path, query="", fragment=""))


def _fetch_browser_events(events_url: str, run_id: str, after: int) -> dict:
    query = urlparse.urlencode({"run_id": run_id, "after": str(after)})
    separator = "&" if urlparse.urlparse(events_url).query else "?"
    url = f"{events_url}{separator}{query}"
    with request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _emit_browser_progress(progress_callback, text: str, **metadata) -> None:
    if not progress_callback or not text:
        return
    try:
        progress_callback(
            "internet_browser",
            text,
            {"_browser_live": True, **metadata},
        )
    except Exception as exc:
        logger.debug("Browser progress callback failed: %s", exc)


def _format_event_for_progress(event: dict, vnc_url: str = "") -> str:
    if not isinstance(event, dict):
        return ""

    message = str(event.get("message") or "").strip()
    if not message:
        return ""

    phase = str(event.get("phase") or "")
    level = str(event.get("level") or "info")

    if level == "help":
        suffix = f" Экран: {vnc_url}" if vnc_url else ""
        return f"🧑‍💻 Нужна помощь: {message}{suffix}"
    if level == "error":
        return f"⚠️ {message}"
    if level == "done" or phase == "done":
        return f"✅ {message}"
    if phase == "view":
        return f"🌐 {message}"
    if phase == "page":
        return f"📍 {message}"
    if phase == "navigation":
        return f"➡️ {message}"
    if phase == "action":
        return f"🖱️ {message}"
    if phase == "input":
        return f"⌨️ {message}"
    if phase == "read":
        return f"📖 {message}"
    return f"🌐 {message}"


def _emit_unseen_events(
    events,
    last_seq: dict,
    progress_callback,
    vnc_url: str,
    *,
    max_events: int,
) -> int:
    if not isinstance(events, list):
        return 0

    emitted = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        seq = int(event.get("seq") or 0)
        if seq and seq <= int(last_seq.get("value", 0)):
            continue

        level = str(event.get("level") or "info")
        high_priority = level in {"help", "error", "done"} or event.get("phase") in {"start", "view"}
        if emitted >= max_events and not high_priority:
            if seq:
                last_seq["value"] = max(int(last_seq.get("value", 0)), seq)
            continue

        text = _format_event_for_progress(event, vnc_url=vnc_url)
        if text:
            _emit_browser_progress(progress_callback, text, browser_event=event)
            emitted += 1
        if seq:
            last_seq["value"] = max(int(last_seq.get("value", 0)), seq)
    return emitted


async def _poll_live_events(
    events_url: str,
    run_id: str,
    progress_callback,
    stop_event: asyncio.Event,
    vnc_url: str,
    last_seq: dict,
) -> None:
    if not progress_callback or not events_url or not run_id:
        return

    interval = _env_float("BROWSER_LIVE_LOG_POLL_INTERVAL", 1.5)
    max_events = _env_int("BROWSER_LIVE_LOG_MAX_EVENTS", 40)
    failures = 0
    misses = 0

    while not stop_event.is_set():
        try:
            data = await asyncio.to_thread(
                _fetch_browser_events,
                events_url,
                run_id,
                int(last_seq.get("value", 0)),
            )
        except error.HTTPError as exc:
            if exc.code == 404:
                misses += 1
                if misses >= 4:
                    return
            else:
                failures += 1
                if failures >= 4:
                    return
        except Exception as exc:
            failures += 1
            if failures >= 4:
                logger.debug("Stopping browser live event polling after repeated failures: %s", exc)
                return
        else:
            failures = 0
            misses = 0
            _emit_unseen_events(
                data.get("events", []),
                last_seq,
                progress_callback,
                vnc_url,
                max_events=max_events,
            )
            if data.get("done"):
                return

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue


async def run_browser_task(
    task: str,
    honcho_session_key: str = None,
    progress_callback=None,
):
    if not task or not str(task).strip():
        return json.dumps({"success": False, "error": "Task is required"}, ensure_ascii=False)

    browser_host = "browser"
    browser_port = 9222
    vnc_url = os.getenv("BROWSER_VIEW_URL", "")

    try:
        browser_ip = socket.gethostbyname(browser_host)
        cdp_url = f"http://{browser_ip}:{browser_port}"
    except Exception:
        cdp_url = f"http://{browser_host}:{browser_port}"

    rpc_url = os.getenv("BROWSER_USE_RPC_URL", "http://browser:8787/run")
    events_url = _build_events_url(rpc_url)
    timeout_sec = int(os.getenv("BROWSER_USE_RPC_TIMEOUT", "900"))
    run_id = uuid.uuid4().hex
    payload = json.dumps({"task": task.strip(), "run_id": run_id}).encode("utf-8")
    req = request.Request(rpc_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    live_logs_enabled = _env_bool("BROWSER_LIVE_LOGS", True) and bool(progress_callback)
    stop_event = asyncio.Event()
    last_seq = {"value": 0}
    poll_task = None

    if live_logs_enabled:
        if vnc_url:
            _emit_browser_progress(
                progress_callback,
                f"Открыл браузерный экран: {vnc_url}",
                run_id=run_id,
                cdp_url=cdp_url,
            )
        else:
            _emit_browser_progress(
                progress_callback,
                "Запускаю browser-use. Экран noVNC не настроен: задайте BROWSER_VIEW_URL.",
                run_id=run_id,
                cdp_url=cdp_url,
            )
        poll_task = asyncio.create_task(
            _poll_live_events(
                events_url,
                run_id,
                progress_callback,
                stop_event,
                vnc_url,
                last_seq,
            )
        )

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
                resp_json.setdefault("run_id", run_id)

                if live_logs_enabled:
                    _emit_unseen_events(
                        resp_json.get("events", []),
                        last_seq,
                        progress_callback,
                        vnc_url,
                        max_events=_env_int("BROWSER_LIVE_LOG_MAX_EVENTS", 40),
                    )
                    if resp_json.get("success"):
                        _emit_browser_progress(progress_callback, "✅ Browser-use завершил задачу.", run_id=run_id)
                    else:
                        _emit_browser_progress(
                            progress_callback,
                            f"⚠️ Browser-use завершился с ошибкой: {resp_json.get('error', 'unknown error')}",
                            run_id=run_id,
                        )

                return json.dumps(resp_json, ensure_ascii=False)
        except Exception:
            pass
            
        return body

    except error.HTTPError as http_err:
        body = http_err.read().decode("utf-8", errors="replace")
        if live_logs_enabled:
            _emit_browser_progress(progress_callback, f"⚠️ Ошибка browser-use RPC: HTTP {http_err.code}", run_id=run_id)
        return json.dumps(
            {
                "success": False,
                "error": f"browser-use RPC returned HTTP {http_err.code}",
                "details": body,
            },
            ensure_ascii=False,
        )
    except Exception as err:
        if live_logs_enabled:
            _emit_browser_progress(progress_callback, f"⚠️ Ошибка browser-use RPC: {err}", run_id=run_id)
        return json.dumps(
            {
                "success": False,
                "error": f"browser-use RPC request failed: {err}",
            },
            ensure_ascii=False,
        )
    finally:
        stop_event.set()
        if poll_task:
            try:
                await asyncio.wait_for(poll_task, timeout=3)
            except asyncio.TimeoutError:
                poll_task.cancel()
            except Exception as exc:
                logger.debug("Browser live polling finished with error: %s", exc)


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
    handler=lambda args, **kw: asyncio.run(
        run_browser_task(
            args.get("task", ""),
            kw.get("honcho_session_key", ""),
            kw.get("tool_progress_callback"),
        )
    ),
    emoji="🌐",
)
