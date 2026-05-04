import importlib.util
import asyncio
import logging
import sys
import types
from pathlib import Path


def _load_runner(monkeypatch):
    fake_browser_use = types.ModuleType("browser_use")
    fake_browser_use.Agent = object
    fake_browser_use.Browser = object
    fake_browser_use.ChatOpenAI = object
    monkeypatch.setitem(sys.modules, "browser_use", fake_browser_use)

    path = Path(__file__).resolve().parents[3] / "browser_env" / "browser_use_runner.py"
    spec = importlib.util.spec_from_file_location("test_browser_use_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_event_store_returns_incremental_events(monkeypatch):
    runner = _load_runner(monkeypatch)
    runner._RUNS.clear()

    runner._append_event("run-1", "start", "Запускаю.")
    runner._append_event("run-1", "page", "Я на странице: example.com")
    runner._finish_run("run-1")

    payload = runner._get_events("run-1", after=1)

    assert payload["success"] is True
    assert payload["done"] is True
    assert [event["message"] for event in payload["events"]] == ["Я на странице: example.com"]


def test_browser_use_log_translation_detects_actions_and_captcha(monkeypatch):
    runner = _load_runner(monkeypatch)

    assert runner._browser_log_to_event("Step 3: deciding next action", logging.INFO) == (
        "step",
        "Шаг 3: анализирую страницу и выбираю следующее действие.",
        "info",
    )
    assert runner._browser_log_to_event("Action: click button Sign in", logging.INFO) == (
        "action",
        "Кликаю по элементу на странице.",
        "info",
    )
    assert runner._browser_log_to_event("Cloudflare captcha detected", logging.INFO) == (
        "human_help",
        "Похоже, на странице проверка или капча. Откройте экран браузера и помогите пройти её.",
        "help",
    )


def test_model_action_formatter_reports_specific_actions(monkeypatch):
    runner = _load_runner(monkeypatch)

    assert runner._format_model_action({"go_to_url": {"url": "https://music.yandex.ru/search?text=Дора"}}) == (
        "navigation",
        "Перехожу на music.yandex.ru/search.",
    )
    assert runner._format_model_action({"input_text": {"text": "Дора", "index": 4}}) == (
        "input",
        "Ввожу в поле: Дора.",
    )
    assert runner._format_model_action({"click_element_by_index": {"index": 12}}) is None
    assert runner._format_model_action({"click": {"label": "Playback"}}) == (
        "action",
        "Нажимаю: Playback.",
    )
    assert runner._format_model_action({"send_keys": {"keys": "Enter"}}) == (
        "action",
        "Нажимаю клавиши: Enter.",
    )
    assert runner._format_model_action({"scroll_down": {"amount": 614}}) == (
        "action",
        "Прокручиваю страницу вниз.",
    )
    assert runner._format_model_action({"action": [{"click_element_by_index": {"index": 5}}]}) is None
    assert runner._format_model_action({"action": "evaluate", "code": "document.querySelector('#q')"}) == (
        "action",
        "Проверяю страницу скриптом.",
    )


def test_action_result_formatter_humanizes_browser_use_content(monkeypatch):
    runner = _load_runner(monkeypatch)

    assert runner._format_action_result_content("Navigated to https://youtube.com") == (
        "navigation",
        "Открыл страницу: youtube.com/.",
    )
    assert runner._format_action_result_content("🔗 Navigated to https://music.vk.com") == (
        "navigation",
        "Открыл страницу: music.vk.com/.",
    )
    assert runner._format_action_result_content(
        "🔗 Opened new tab with url https://yandex.ru/search/?text=ВК+Музыка+Дора"
    ) == (
        "navigation",
        "Открыл новую вкладку: yandex.ru/search/.",
    )
    assert runner._format_action_result_content("https://music.yandex.ru/search?text=Дора") == (
        "navigation",
        "Открыл страницу: music.yandex.ru/search.",
    )
    assert runner._format_action_result_content('Clicked button "Accept all" aria-label=Accept the use') == (
        "action",
        "Нажал: Accept all.",
    )
    assert runner._format_action_result_content('Clicked div "Меню" id=header__burger_menu') == (
        "action",
        "Нажал: Меню.",
    )
    assert runner._format_action_result_content("Clicked a aria-label=Home") == (
        "action",
        "Нажал: Home.",
    )
    assert runner._format_action_result_content("Clicked button aria-label=Playback") == (
        "action",
        "Нажал: Playback.",
    )
    assert runner._format_action_result_content("Clicked button") == (
        "action",
        "Нажал кнопку.",
    )
    assert runner._format_action_result_content(
        "Typed 'Дора' 💡 This is an autocomplete field. Wait for suggestions to appear"
    ) == (
        "input",
        "Ввёл в поиск: Дора.",
    )
    assert runner._format_action_result_content("Waited for 3 seconds") == (
        "action",
        "Жду загрузку: 3 сек.",
    )
    assert runner._format_action_result_content("🔍 Scrolled up 1.5 pages") == (
        "action",
        "Прокрутил страницу вверх на 1.5 pages.",
    )
    assert runner._format_action_result_content("🔍 Scrolled down 613px") == (
        "action",
        "Прокрутил страницу вниз на 613px.",
    )
    assert runner._format_action_result_content(
        "No elements found matching \"input[type='text'], [role='searchbox']\"."
    ) == (
        "read",
        "Не нашёл подходящее поле или кнопку на странице.",
    )
    assert runner._format_action_result_content("Task Completed Successfully! I found band 'Дора'") == (
        "done",
        "Browser-use сообщил, что задача выполнена.",
    )


def test_step_end_hook_emits_history_actions(monkeypatch):
    runner = _load_runner(monkeypatch)
    runner._RUNS.clear()

    class FakeHistory:
        def model_actions(self):
            return [
                {"go_to_url": {"url": "https://music.yandex.ru"}},
                {"input_text": {"text": "Дора", "index": 3}},
                {"click_element_by_index": {"index": 7}},
            ]

        def action_results(self):
            return []

    agent = types.SimpleNamespace(history=FakeHistory())
    hook = runner._make_step_end_hook("run-2", {"actions": 0, "results": 0})

    asyncio.run(hook(agent))
    payload = runner._get_events("run-2", after=0)

    assert [event["message"] for event in payload["events"]] == [
        "Перехожу на music.yandex.ru/.",
        "Ввожу в поле: Дора.",
    ]

    asyncio.run(hook(agent))
    assert runner._get_events("run-2", after=2)["events"] == []


def test_step_end_hook_emits_action_results(monkeypatch):
    runner = _load_runner(monkeypatch)
    runner._RUNS.clear()

    class FakeHistory:
        def model_actions(self):
            return ()

        def action_results(self):
            return (
                {"extracted_content": "Clicked button \"Play (k)\" aria-label=Play (k)"},
                {"error": "Element not found"},
                {"extracted_content": "Cloudflare captcha"},
            )

    agent = types.SimpleNamespace(history=FakeHistory())
    hook = runner._make_step_end_hook("run-3", {"actions": 0, "results": 0})

    asyncio.run(hook(agent))
    payload = runner._get_events("run-3", after=0)

    assert [event["phase"] for event in payload["events"]] == ["action", "error", "human_help"]
    assert [event["message"] for event in payload["events"]] == [
        "Нажал: Play (k).",
        "Ошибка действия: Element not found",
        "Похоже, страница просит проверку человека. Откройте экран браузера и помогите пройти её.",
    ]
