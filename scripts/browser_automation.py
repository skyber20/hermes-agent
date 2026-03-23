

## 🐍 Файл: scripts/browser_automation.py


# !/usr/bin/env python3
"""
Browser automation core module for Hermes Agent Skill
Автоматизация браузера с использованием Playwright
"""

import asyncio
import json
import sys
import os
from typing import Dict, Any, Optional, List
from playwright.async_api import async_playwright, Page, Browser, Playwright


class BrowserAutomation:
    """Основной класс для автоматизации браузера"""

    def __init__(self, headless: bool = True, timeout: int = 30000):
        self.headless = headless
        self.timeout = timeout
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        """Запуск браузера"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu'
            ]
        )
        self.page = await self.browser.new_page()
        self.page.set_default_timeout(self.timeout)

    async def close(self):
        """Закрытие браузера"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def goto(self, url: str) -> Dict[str, Any]:
        """Переход по URL"""
        try:
            response = await self.page.goto(url, wait_until='networkidle')
            status = response.status if response else None

            return {
                "success": True,
                "url": self.page.url,
                "status": status
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to navigate to {url}: {str(e)}"
            }

    async def click(self, selector: str) -> Dict[str, Any]:
        """Клик по элементу"""
        try:
            await self.page.wait_for_selector(selector, timeout=self.timeout)
            await self.page.click(selector)
            return {
                "success": True,
                "selector": selector,
                "message": f"Clicked on {selector}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to click on {selector}: {str(e)}"
            }

    async def fill(self, selector: str, value: str) -> Dict[str, Any]:
        """Заполнение поля"""
        try:
            await self.page.wait_for_selector(selector, timeout=self.timeout)
            await self.page.fill(selector, value)
            return {
                "success": True,
                "selector": selector,
                "value": value,
                "message": f"Filled {selector} with '{value}'"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fill {selector}: {str(e)}"
            }

    async def screenshot(self, path: str = "/tmp/screenshot.png") -> Dict[str, Any]:
        """Скриншот страницы"""
        try:
            # Убедимся, что директория существует
            os.makedirs(os.path.dirname(path), exist_ok=True)

            await self.page.screenshot(path=path, full_page=True)
            return {
                "success": True,
                "path": path,
                "message": f"Screenshot saved to {path}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to take screenshot: {str(e)}"
            }

    async def get_text(self, selector: str) -> Dict[str, Any]:
        """Получение текста элемента"""
        try:
            await self.page.wait_for_selector(selector, timeout=self.timeout)
            text = await self.page.text_content(selector)
            return {
                "success": True,
                "text": text.strip() if text else "",
                "selector": selector
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get text from {selector}: {str(e)}"
            }

    async def get_text_all(self, selector: str) -> Dict[str, Any]:
        """Получение текста всех элементов"""
        try:
            await self.page.wait_for_selector(selector, timeout=self.timeout)
            elements = await self.page.query_selector_all(selector)
            texts = []
            for el in elements:
                text = await el.text_content()
                if text:
                    texts.append(text.strip())

            return {
                "success": True,
                "texts": texts,
                "count": len(texts),
                "selector": selector
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get texts from {selector}: {str(e)}"
            }

    async def evaluate(self, js_code: str) -> Dict[str, Any]:
        """Выполнение JavaScript"""
        try:
            result = await self.page.evaluate(js_code)
            return {
                "success": True,
                "result": result,
                "code": js_code[:100]  # Обрезаем для вывода
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to evaluate JavaScript: {str(e)}"
            }

    async def select(self, selector: str, value: str) -> Dict[str, Any]:
        """Выбор из выпадающего списка"""
        try:
            await self.page.wait_for_selector(selector, timeout=self.timeout)
            await self.page.select_option(selector, value)
            return {
                "success": True,
                "selector": selector,
                "value": value,
                "message": f"Selected '{value}' from {selector}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to select from {selector}: {str(e)}"
            }

    async def wait_for_selector(self, selector: str, timeout: int = None) -> Dict[str, Any]:
        """Ожидание появления элемента"""
        timeout_ms = timeout or self.timeout
        try:
            await self.page.wait_for_selector(selector, timeout=timeout_ms)
            return {
                "success": True,
                "selector": selector,
                "timeout": timeout_ms,
                "message": f"Element {selector} appeared"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Timeout waiting for {selector}: {str(e)}"
            }

    async def get_html(self) -> Dict[str, Any]:
        """Получение HTML страницы"""
        try:
            html = await self.page.content()
            return {
                "success": True,
                "html": html,
                "size": len(html)
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get HTML: {str(e)}"
            }

    async def get_title(self) -> Dict[str, Any]:
        """Получение заголовка страницы"""
        try:
            title = await self.page.title()
            return {
                "success": True,
                "title": title
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get title: {str(e)}"
            }

    async def get_url(self) -> Dict[str, Any]:
        """Получение текущего URL"""
        try:
            url = self.page.url
            return {
                "success": True,
                "url": url
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get URL: {str(e)}"
            }

    async def execute_sequence(self, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Выполнение последовательности действий"""
        results = []

        for i, step in enumerate(steps):
            result = await self.execute_task(step)
            results.append({
                "step": i + 1,
                "action": step.get("action"),
                "result": result
            })

            # Если шаг не удался, прекращаем выполнение
            if not result.get("success"):
                return {
                    "success": False,
                    "error": f"Sequence failed at step {i + 1}",
                    "results": results
                }

        return {
            "success": True,
            "results": results,
            "total_steps": len(steps)
        }

    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнение задачи по описанию"""
        action = task.get("action")

        actions_map = {
            "goto": lambda: self.goto(task.get("url")),
            "click": lambda: self.click(task.get("selector")),
            "fill": lambda: self.fill(task.get("selector"), task.get("value")),
            "screenshot": lambda: self.screenshot(task.get("path", "/tmp/screenshot.png")),
            "get_text": lambda: self.get_text(task.get("selector")),
            "get_text_all": lambda: self.get_text_all(task.get("selector")),
            "evaluate": lambda: self.evaluate(task.get("code")),
            "select": lambda: self.select(task.get("selector"), task.get("value")),
            "wait": lambda: self.wait_for_selector(task.get("selector"), task.get("timeout")),
            "get_html": lambda: self.get_html(),
            "get_title": lambda: self.get_title(),
            "get_url": lambda: self.get_url(),
            "sequence": lambda: self.execute_sequence(task.get("steps", []))
        }

        if action not in actions_map:
            return {
                "success": False,
                "error": f"Unknown action: {action}. Available: {', '.join(actions_map.keys())}"
            }

        return await actions_map[action]()


async def run_from_args():
    """Запуск из аргументов командной строки"""
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "No task provided. Usage: python3 browser_automation.py '<JSON_TASK>'"
        }))
        return

    try:
        task = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        # Если не JSON, пробуем как goto команду
        task = {"action": "goto", "url": sys.argv[1]}

    # Определяем режим headless (можно переопределить через переменную окружения)
    headless = os.environ.get("BROWSER_HEADLESS", "true").lower() == "true"

    async with BrowserAutomation(headless=headless) as browser:
        result = await browser.execute_task(task)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run_from_args())