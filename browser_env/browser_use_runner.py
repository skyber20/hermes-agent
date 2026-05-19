import asyncio
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, parse, request

from browser_use import Agent, Browser, ChatOpenAI

logger = logging.getLogger(__name__)

_EVENT_LIMIT = int(os.getenv("BROWSER_USE_EVENT_LIMIT", "300"))
_EVENT_TTL_SEC = int(os.getenv("BROWSER_USE_EVENT_TTL_SEC", "3600"))
_STATE_POLL_INTERVAL = float(os.getenv("BROWSER_USE_STATE_POLL_INTERVAL", "3.0"))

_RUNS = {}
_RUNS_LOCK = threading.RLock()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_SPACE_RE = re.compile(r"\s+")
_URL_RE = re.compile(r"https?://[^\s\"'<>),]+")
_CAPTCHA_RE = re.compile(
    r"(captcha|cloudflare|verify you are human|human verification|checking your browser|"
    r"anti[- ]?bot|challenge|blocked)",
    re.IGNORECASE,
)


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_text(value, limit=220):
    text = _ANSI_RE.sub("", str(value or ""))
    text = _SPACE_RE.sub(" ", text).strip()
    if len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def _short_url(url):
    if not url:
        return ""
    parsed = parse.urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        path = parsed.path or "/"
        if len(path) > 64:
            path = path[:61] + "..."
        return f"{parsed.netloc}{path}"
    return _clean_text(url, limit=100)


def _extract_url(text):
    match = _URL_RE.search(text or "")
    return match.group(0) if match else ""


def _public_data(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(exclude_none=True)
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    if hasattr(value, "dict"):
        try:
            dumped = value.dict(exclude_none=True)
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}
    return {}


def _compact_value(value, limit=120):
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value if item is not None)
    if isinstance(value, dict):
        return ""
    return _clean_text(value, limit=limit)


def _first_param(params, *names):
    if not isinstance(params, dict):
        return ""
    for name in names:
        if name in params:
            value = _compact_value(params.get(name))
            if value:
                return value
    return ""


def _strip_browser_use_hint(text):
    return re.sub(r"\s*💡\s*This is an autocomplete field\..*$", "", text, flags=re.IGNORECASE).strip()


def _strip_browser_use_prefix(text):
    return re.sub(r"^\s*[🔗🔍✅❌⚠️🖱️⌨️📖📍➡️🌐]+\s*", "", text or "").strip()


def _extract_quoted_label(text):
    match = re.search(r'"([^"]{1,90})"', text or "")
    if match:
        return _clean_text(match.group(1), limit=80)
    match = re.search(r"'([^']{1,90})'", text or "")
    if match:
        return _clean_text(match.group(1), limit=80)
    return ""


def _extract_attribute_label(text):
    for attr in ("aria-label", "name", "title", "id"):
        match = re.search(rf"\b{attr}=([^\s]+)", text or "", flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip("\"'")
            if value:
                return _clean_text(value.replace("_", " "), limit=80)
    return ""


def _normalize_model_action(action):
    data = _public_data(action)
    if not data:
        name = action.__class__.__name__ if action is not None else "action"
        return name, {}

    container = data.get("action") or data.get("actions")
    if isinstance(container, list) and container:
        return _normalize_model_action(container[0])
    if isinstance(container, dict):
        return _normalize_model_action(container)
    if isinstance(container, str) and container.strip():
        explicit_params = data.get("parameters") or data.get("params") or data.get("input") or data.get("args") or data
        return container, _public_data(explicit_params) or data

    explicit_name = data.get("name") or data.get("type")
    explicit_params = data.get("parameters") or data.get("params") or data.get("input") or data.get("args")
    if explicit_name:
        return str(explicit_name), _public_data(explicit_params) or data

    action_items = [(key, value) for key, value in data.items() if value not in (None, {}, [])]
    if len(action_items) == 1:
        name, params = action_items[0]
        return str(name), _public_data(params)

    if len(data) == 1:
        name, params = next(iter(data.items()))
        return str(name), _public_data(params)

    return "action", data


def _format_model_action(action):
    name, params = _normalize_model_action(action)
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    label = _first_param(params, "label", "text", "title", "element", "button", "aria_label", "selector")
    index = _first_param(params, "index", "element_index", "idx")

    if normalized in {"go_to_url", "open_url", "navigate", "navigate_to", "open"} or "url" in normalized:
        url = _first_param(params, "url", "href")
        target = _short_url(url) if url else "новую страницу"
        return "navigation", f"Перехожу на {target}."

    if normalized in {"search", "search_google", "search_browser"} or "search" in normalized:
        query = _first_param(params, "query", "text", "search_query", "value")
        if query:
            return "search", f"Ищу: {query}."
        return "search", "Ищу информацию на странице."

    if normalized in {"input_text", "type", "fill", "fill_form", "set_value"} or any(
        token in normalized for token in ("input", "type", "fill")
    ):
        value = _first_param(params, "text", "value", "query", "content")
        if value:
            return "input", f"Ввожу в поле: {value}."
        return "input", "Ввожу данные в поле."

    if normalized in {"click", "click_element", "click_element_by_index"} or "click" in normalized:
        if label and not label.isdigit():
            return "action", f"Нажимаю: {label}."
        return None

    if "scroll" in normalized:
        direction = _first_param(params, "direction")
        if direction:
            return "action", f"Прокручиваю страницу: {direction}."
        if "up" in normalized:
            return "action", "Прокручиваю страницу вверх."
        return "action", "Прокручиваю страницу вниз."

    if normalized in {"send_keys", "press_key", "keyboard"} or any(token in normalized for token in ("key", "press")):
        keys = _first_param(params, "keys", "key", "text")
        if keys:
            return "action", f"Нажимаю клавиши: {keys}."
        return "action", "Нажимаю клавиши."

    if "extract" in normalized:
        query = _first_param(params, "query", "goal", "instruction")
        if query:
            return "read", f"Извлекаю данные: {query}."
        return "read", "Извлекаю данные со страницы."

    if normalized in {"find_elements", "find_element", "locate_element"} or "find_element" in normalized:
        return None

    if "wait" in normalized:
        return "action", "Жду загрузку страницы."

    if normalized in {"evaluate", "execute_script", "run_javascript"} or "javascript" in normalized:
        return "action", "Проверяю страницу скриптом."

    if "done" in normalized or "finish" in normalized:
        return "done", "Завершаю браузерную задачу."

    return None


def _format_action_result_content(content):
    content = _strip_browser_use_prefix(_strip_browser_use_hint(_clean_text(content, limit=320)))
    if not content:
        return None

    lower = content.lower()

    if lower.startswith("navigated to "):
        url = content[len("Navigated to ") :].strip()
        return "navigation", f"Открыл страницу: {_short_url(url) or url}."

    if lower.startswith("opened new tab with url "):
        url = content[len("Opened new tab with url ") :].strip()
        return "navigation", f"Открыл новую вкладку: {_short_url(url) or url}."

    if lower.startswith(("http://", "https://")):
        return "navigation", f"Открыл страницу: {_short_url(content) or content}."

    if lower.startswith("clicked "):
        label = _extract_quoted_label(content) or _extract_attribute_label(content)
        if label:
            return "action", f"Нажал: {label}."

        target = content[len("Clicked ") :].strip()
        target = re.sub(r"\s+(aria-label|id|role|name|type)=.*$", "", target, flags=re.IGNORECASE).strip()
        target = target.replace("button", "кнопку").replace("input", "поле ввода").replace("span", "элемент")
        if target in {"кнопку", "поле ввода", "элемент"}:
            return "action", f"Нажал {target}."
        return "action", f"Нажал: {target or 'элемент'}."

    if lower.startswith("typed "):
        value = _extract_quoted_label(content)
        if value:
            return "input", f"Ввёл в поиск: {value}."
        typed = content[len("Typed ") :].strip()
        return "input", f"Ввёл текст: {_clean_text(typed, 80)}."

    wait_match = re.match(r"waited for\s+(.+)", content, flags=re.IGNORECASE)
    if wait_match:
        duration = wait_match.group(1).replace("seconds", "сек.").replace("second", "сек.")
        return "action", f"Жду загрузку: {duration.rstrip('.')}."

    if lower.startswith("scrolled"):
        direction = "вверх" if "up" in lower else "вниз"
        amount_match = re.search(r"scrolled\s+(?:up|down)\s+(.+)", content, flags=re.IGNORECASE)
        amount = _clean_text(amount_match.group(1), 40) if amount_match else ""
        return "action", f"Прокрутил страницу {direction}{f' на {amount}' if amount else ''}."

    if lower.startswith("no elements found matching"):
        return "read", "Не нашёл подходящее поле или кнопку на странице."

    if lower.startswith("task completed successfully"):
        return "done", "Browser-use сообщил, что задача выполнена."

    return "read", f"Получил данные со страницы: {_clean_text(content, 180)}"


def _call_history(history, method_name):
    method = getattr(history, method_name, None)
    if not callable(method):
        return []
    try:
        value = method()
    except Exception:
        return []
    return list(value) if isinstance(value, (list, tuple)) else []


def _prune_runs_locked(now=None):
    now = now or time.time()
    for run_id, run in list(_RUNS.items()):
        if run.get("done") and now - run.get("updated_at", now) > _EVENT_TTL_SEC:
            _RUNS.pop(run_id, None)


def _ensure_run(run_id):
    if not run_id:
        return None
    with _RUNS_LOCK:
        _prune_runs_locked()
        run = _RUNS.get(run_id)
        if run is None:
            now = time.time()
            run = {
                "run_id": run_id,
                "seq": 0,
                "events": [],
                "done": False,
                "started_at": now,
                "updated_at": now,
            }
            _RUNS[run_id] = run
        return run


def _append_event(run_id, phase, message, level="info", **data):
    if not run_id or not message:
        return None

    message = _clean_text(message)
    if not message:
        return None

    with _RUNS_LOCK:
        run = _ensure_run(run_id)
        if run is None:
            return None

        if run["events"]:
            last = run["events"][-1]
            if last.get("phase") == phase and last.get("message") == message:
                return last

        run["seq"] += 1
        event = {
            "seq": run["seq"],
            "ts": _utc_now_iso(),
            "phase": phase,
            "level": level,
            "message": message,
        }
        for key, value in data.items():
            if value is not None:
                event[key] = value

        run["events"].append(event)
        if len(run["events"]) > _EVENT_LIMIT:
            run["events"] = run["events"][-_EVENT_LIMIT:]
        run["updated_at"] = time.time()
        return event


def _finish_run(run_id):
    if not run_id:
        return
    with _RUNS_LOCK:
        run = _ensure_run(run_id)
        if run is not None:
            run["done"] = True
            run["updated_at"] = time.time()


def _get_events(run_id, after=0):
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
        if run is None:
            return None
        events = [event for event in run["events"] if int(event.get("seq", 0)) > after]
        return {
            "success": True,
            "run_id": run_id,
            "events": events,
            "done": bool(run.get("done")),
        }


def _browser_log_to_event(raw_message, levelno):
    msg = _clean_text(raw_message, limit=320)
    if not msg:
        return None

    lower = msg.lower()

    if _CAPTCHA_RE.search(lower):
        return (
            "human_help",
            "Похоже, на странице проверка или капча. Откройте экран браузера и помогите пройти её.",
            "help",
        )

    if levelno >= logging.ERROR:
        return ("error", f"Browser-use сообщил об ошибке: {_clean_text(msg, 180)}", "error")

    if levelno >= logging.WARNING and any(token in lower for token in ("failed", "error", "timeout")):
        return ("warning", f"Возникла проблема в браузере: {_clean_text(msg, 180)}", "warning")

    step_match = re.search(r"\bstep\s+(\d+)\b", lower)
    if step_match:
        return (
            "step",
            f"Шаг {step_match.group(1)}: анализирую страницу и выбираю следующее действие.",
            "info",
        )

    if "go_to_url" in lower or "navigate" in lower or "open url" in lower:
        url = _extract_url(msg)
        target = _short_url(url) if url else "новую страницу"
        return ("navigation", f"Перехожу на {target}.", "info")

    if "click" in lower or "press" in lower or "button" in lower:
        return ("action", "Кликаю по элементу на странице.", "info")

    if any(token in lower for token in ("input_text", "type", "typing", "fill", "insert text")):
        return ("input", "Ввожу данные в поле на странице.", "info")

    if "scroll" in lower:
        return ("action", "Прокручиваю страницу.", "info")

    if any(token in lower for token in ("extract", "read", "content")):
        return ("read", "Читаю содержимое страницы.", "info")

    if "done" in lower or "final result" in lower or "finished" in lower:
        return ("done", "Browser-use закончил выполнение задачи.", "done")

    return None


class BrowserUseLiveLogHandler(logging.Handler):
    def __init__(self, run_id):
        super().__init__(level=logging.INFO)
        self.run_id = run_id
        self._last_emit_by_message = {}

    def emit(self, record):
        if not record.name.startswith("browser_use"):
            return
        try:
            converted = _browser_log_to_event(record.getMessage(), record.levelno)
            if not converted:
                return
            phase, message, level = converted
            now = time.monotonic()
            last_at = self._last_emit_by_message.get(message)
            if last_at is not None and now - last_at < 8:
                return
            self._last_emit_by_message[message] = now
            _append_event(self.run_id, phase, message, level=level)
        except Exception:
            logger.debug("Failed to convert browser-use log record", exc_info=True)


def _fetch_json(url):
    with request.urlopen(url, timeout=2) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _watch_browser_state(run_id, cdp_url, stop_event):
    if not run_id or not cdp_url:
        return

    json_url = f"{cdp_url.rstrip('/')}/json"
    last_url = None
    human_help_sent = False

    while not stop_event.is_set():
        try:
            pages = await asyncio.to_thread(_fetch_json, json_url)
            if isinstance(pages, list):
                page = next(
                    (
                        item
                        for item in pages
                        if item.get("type") == "page"
                        and item.get("url")
                        and not item.get("url", "").startswith(("devtools://", "chrome://"))
                    ),
                    None,
                )
                if page:
                    url = page.get("url", "")
                    title = _clean_text(page.get("title", ""), limit=90)
                    if url and url != last_url:
                        short = _short_url(url)
                        if title:
                            message = f"Я на странице: {title} — {short}"
                        else:
                            message = f"Я на странице: {short}"
                        _append_event(run_id, "page", message, url=url, title=title)
                        last_url = url

                    if not human_help_sent and _CAPTCHA_RE.search(f"{title} {url}"):
                        _append_event(
                            run_id,
                            "human_help",
                            "Похоже, на странице антибот-проверка. Откройте экран браузера и помогите пройти её.",
                            level="help",
                            url=url,
                            title=title,
                        )
                        human_help_sent = True
        except Exception:
            pass

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_STATE_POLL_INTERVAL)
        except asyncio.TimeoutError:
            continue


def _make_step_end_hook(run_id, cursor):
    async def _on_step_end(agent):
        history = getattr(agent, "history", None)
        if history is None:
            return

        actions = _call_history(history, "model_actions")
        start = int(cursor.get("actions", 0))
        for action in actions[start:]:
            formatted_action = _format_model_action(action)
            if not formatted_action:
                continue
            phase, message = formatted_action
            _append_event(
                run_id,
                phase,
                message,
                action_name=_normalize_model_action(action)[0],
            )
        cursor["actions"] = len(actions)

        results = _call_history(history, "action_results")
        result_start = int(cursor.get("results", 0))
        for result in results[result_start:]:
            data = _public_data(result)
            error_text = _compact_value(data.get("error") or data.get("exception"), limit=180)
            if error_text:
                _append_event(run_id, "error", f"Ошибка действия: {error_text}", level="error")
                continue

            content = _compact_value(data.get("extracted_content") or data.get("content"), limit=320)
            if content and not _CAPTCHA_RE.search(content):
                formatted = _format_action_result_content(content)
                if formatted:
                    phase, message = formatted
                    _append_event(run_id, phase, message)
            elif content:
                _append_event(
                    run_id,
                    "human_help",
                    "Похоже, страница просит проверку человека. Откройте экран браузера и помогите пройти её.",
                    level="help",
                )
        cursor["results"] = len(results)

    return _on_step_end


def _json_response(handler, status_code, payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


async def run_browser_task(task, run_id=None):
    _ensure_run(run_id)
    _append_event(run_id, "start", "Запускаю browser-use задачу.")
    logger.info(f"run_browser_task started with task: {task[:200]}...")
    cdp_url = os.getenv("BROWSER_CDP_URL", "http://127.0.0.1:9222")
    browser_view_url = os.getenv("BROWSER_VIEW_URL", "")
    logger.info(f"CDP URL: {cdp_url}")
    if browser_view_url:
        _append_event(run_id, "view", f"Экран браузера доступен здесь: {browser_view_url}", view_url=browser_view_url)

    browser = None
    state_stop = asyncio.Event()
    state_task = asyncio.create_task(_watch_browser_state(run_id, cdp_url, state_stop)) if run_id else None
    live_log_handler = BrowserUseLiveLogHandler(run_id) if run_id else None
    browser_use_logger = logging.getLogger("browser_use")
    old_browser_use_level = browser_use_logger.level
    if live_log_handler:
        browser_use_logger.addHandler(live_log_handler)
        if browser_use_logger.getEffectiveLevel() > logging.INFO:
            browser_use_logger.setLevel(logging.INFO)

    async def _cleanup():
        state_stop.set()
        if state_task:
            try:
                await asyncio.wait_for(state_task, timeout=1)
            except Exception:
                state_task.cancel()
        if live_log_handler:
            browser_use_logger.removeHandler(live_log_handler)
            browser_use_logger.setLevel(old_browser_use_level)
        try:
            if browser is not None:
                logger.info("Closing browser...")
                await browser.close()
                logger.info("Browser closed")
        except Exception as close_err:
            logger.warning(f"Browser close failed: {close_err}")
        _finish_run(run_id)

    try:
        logger.info("Creating Browser...")
        _append_event(run_id, "setup", "Подключаюсь к браузеру через CDP.")
        browser = Browser(cdp_url=cdp_url)
        logger.info("Browser created")
    except Exception as err:
        logger.error(f"Browser creation failed: {err}", exc_info=True)
        _append_event(run_id, "error", f"Не удалось создать браузер: {_clean_text(err, 180)}", level="error")
        await _cleanup()
        return {"success": False, "run_id": run_id, "error": f"Browser creation failed: {err}"}

    try:
        logger.info("Creating LLM...")
        model = os.getenv("MODEL_DEFAULT", "qwen3.5-122b")
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        logger.info(
            "LLM params: model=%s, base_url=%s, api_key=%s",
            model,
            (base_url[:80] + "...") if base_url and len(base_url) > 80 else base_url,
            "set" if api_key else "missing",
        )
        _append_event(run_id, "setup", f"Готовлю модель управления браузером: {model}.")
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.0,
        )
        logger.info("LLM created")
    except Exception as err:
        logger.error(f"LLM creation failed: {err}", exc_info=True)
        _append_event(run_id, "error", f"Не удалось создать модель для browser-use: {_clean_text(err, 180)}", level="error")
        await _cleanup()
        return {"success": False, "run_id": run_id, "error": f"LLM creation failed: {err}"}

    try:
        logger.info("Creating Agent...")
        agent = Agent(task=task, llm=llm, browser=browser)
        logger.info("Agent created")
        _append_event(run_id, "setup", "Агент browser-use готов, начинаю действия на странице.")
    except Exception as err:
        logger.error(f"Agent creation failed: {err}", exc_info=True)
        _append_event(run_id, "error", f"Не удалось создать browser-use агента: {_clean_text(err, 180)}", level="error")
        await _cleanup()
        return {"success": False, "run_id": run_id, "error": f"Agent creation failed: {err}"}

    try:
        logger.info("Running agent...")
        _append_event(run_id, "running", "Выполняю задачу в браузере.")
        step_cursor = {"actions": 0, "results": 0}
        try:
            history = await agent.run(on_step_end=_make_step_end_hook(run_id, step_cursor))
        except TypeError as hook_err:
            if "on_step_end" not in str(hook_err):
                raise
            logger.warning("browser-use does not support on_step_end hooks; falling back to plain run()")
            history = await agent.run()
        logger.info("Agent run completed")
        for action in _call_history(history, "model_actions")[int(step_cursor.get("actions", 0)):]:
            formatted_action = _format_model_action(action)
            if not formatted_action:
                continue
            phase, message = formatted_action
            _append_event(run_id, phase, message, action_name=_normalize_model_action(action)[0])
        _append_event(run_id, "done", "Браузерная задача завершена.", level="done")
        return {
            "success": True,
            "run_id": run_id,
            "result": history.final_result(),
            "browser_view": browser_view_url,
            "events": (_get_events(run_id, after=0) or {}).get("events", [])[-50:],
        }
    except Exception as err:
        logger.error(f"Agent run failed: {err}", exc_info=True)
        _append_event(
            run_id,
            "error",
            f"Браузерная автоматизация завершилась с ошибкой: {_clean_text(err, 180)}",
            level="error",
        )
        return {"success": False, "run_id": run_id, "error": f"Browser automation failed: {err}"}
    finally:
        await _cleanup()


class BrowserUseRPCHandler(BaseHTTPRequestHandler):
    def log_message(self, format_str, *args):
        logger.info(f"HTTP {self.address_string()}: {format_str % args}")

    def do_GET(self):
        logger.info(f"GET {self.path}")
        parsed = parse.urlparse(self.path)
        if parsed.path == "/events":
            params = parse.parse_qs(parsed.query)
            run_id = (params.get("run_id") or [""])[0]
            try:
                after = int((params.get("after") or ["0"])[0])
            except ValueError:
                after = 0
            payload = _get_events(run_id, after=after)
            if payload is None:
                _json_response(self, 404, {"success": False, "error": "Run not found"})
            else:
                _json_response(self, 200, payload)
            return

        if parsed.path != "/health":
            _json_response(self, 404, {"success": False, "error": "Not found"})
            return

        try:
            debug_url = os.getenv("BROWSER_HEALTH_URL", "http://127.0.0.1:9222/json/version")
            with request.urlopen(debug_url, timeout=2):
                pass
            _json_response(self, 200, {"success": True})
        except Exception as err:
            logger.error(f"Health check failed: {err}")
            _json_response(self, 503, {"success": False, "error": f"Browser is not ready: {err}"})

    def do_POST(self):
        logger.info(f"POST {self.path}")
        if self.path != "/run":
            _json_response(self, 404, {"success": False, "error": "Not found"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length)
            payload = json.loads(raw.decode("utf-8") if raw else "{}")
            task = payload.get("task", "")
            run_id = payload.get("run_id") or uuid.uuid4().hex
            _ensure_run(run_id)
            logger.info(f"RPC task received, run_id: {run_id}, task preview: {task[:200]}...")
            if not isinstance(task, str) or not task.strip():
                _json_response(self, 400, {"success": False, "error": "Field 'task' is required"})
                return

            logger.info("Starting browser task...")
            result = asyncio.run(run_browser_task(task.strip(), run_id=run_id))
            if isinstance(result, dict):
                result.setdefault("run_id", run_id)
            logger.info(f"Task completed: {result}")
            code = 200 if result.get("success") else 500
            _json_response(self, code, result)
        except json.JSONDecodeError as err:
            logger.error(f"JSON decode error: {err}")
            _json_response(self, 400, {"success": False, "error": "Invalid JSON payload"})
        except error.URLError as err:
            logger.error(f"URLError: {err}")
            _json_response(self, 503, {"success": False, "error": f"Transport error: {err}"})
        except Exception as err:
            logger.error(f"do_POST exception: {err}", exc_info=True)
            _json_response(self, 500, {"success": False, "error": f"Internal error: {err}"})


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    host = os.getenv("BROWSER_USE_RPC_HOST", "0.0.0.0")
    port = int(os.getenv("BROWSER_USE_RPC_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), BrowserUseRPCHandler)
    logger.info(f"browser-use RPC listening on {host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
