import asyncio

from tools import browser_use_tool


def test_build_events_url_replaces_run_endpoint(monkeypatch):
    monkeypatch.delenv("BROWSER_USE_EVENTS_URL", raising=False)

    assert (
        browser_use_tool._build_events_url("http://browser:8787/run")
        == "http://browser:8787/events"
    )
    assert (
        browser_use_tool._build_events_url("http://browser:8787/api/run?x=1")
        == "http://browser:8787/api/events"
    )


def test_build_events_url_uses_override(monkeypatch):
    monkeypatch.setenv("BROWSER_USE_EVENTS_URL", "http://agent/events")

    assert browser_use_tool._build_events_url("http://browser:8787/run") == "http://agent/events"


def test_format_event_for_progress_adds_human_help_link():
    text = browser_use_tool._format_event_for_progress(
        {
            "phase": "human_help",
            "level": "help",
            "message": "Похоже, нужна капча.",
        },
        vnc_url="https://vnc.example",
    )

    assert text == "🧑‍💻 Нужна помощь: Похоже, нужна капча. Экран: https://vnc.example"


def test_emit_unseen_events_keeps_high_priority_after_limit():
    calls = []

    def progress_callback(name, preview, args):
        calls.append((name, preview, args))

    last_seq = {"value": 0}
    emitted = browser_use_tool._emit_unseen_events(
        [
            {"seq": 1, "phase": "page", "message": "Я на странице: example.com"},
            {"seq": 2, "phase": "page", "message": "Я на странице: example.org"},
            {
                "seq": 3,
                "phase": "human_help",
                "level": "help",
                "message": "Нужна капча.",
            },
        ],
        last_seq,
        progress_callback,
        "https://vnc.example",
        max_events=1,
    )

    assert emitted == 2
    assert last_seq["value"] == 3
    assert [call[1] for call in calls] == [
        "📍 Я на странице: example.com",
        "🧑‍💻 Нужна помощь: Нужна капча. Экран: https://vnc.example",
    ]
    assert all(call[0] == "internet_browser" for call in calls)
    assert all(call[2]["_browser_live"] is True for call in calls)


def test_poll_live_events_emits_until_done(monkeypatch):
    responses = [
        {
            "success": True,
            "events": [{"seq": 1, "phase": "start", "message": "Запускаю."}],
            "done": False,
        },
        {
            "success": True,
            "events": [{"seq": 2, "phase": "done", "level": "done", "message": "Готово."}],
            "done": True,
        },
    ]

    def fake_fetch(events_url, run_id, after):
        return responses.pop(0)

    calls = []

    def progress_callback(name, preview, args):
        calls.append((name, preview, args))

    monkeypatch.setattr(browser_use_tool, "_fetch_browser_events", fake_fetch)
    monkeypatch.setenv("BROWSER_LIVE_LOG_POLL_INTERVAL", "0.1")

    async def run_poll():
        stop_event = asyncio.Event()
        last_seq = {"value": 0}
        await browser_use_tool._poll_live_events(
            "http://browser:8787/events",
            "run-1",
            progress_callback,
            stop_event,
            "",
            last_seq,
        )
        return last_seq

    last_seq = asyncio.run(run_poll())

    assert last_seq["value"] == 2
    assert [call[1] for call in calls] == ["🌐 Запускаю.", "✅ Готово."]


def test_poll_live_events_applies_event_limit_per_poll(monkeypatch):
    responses = [
        {
            "success": True,
            "events": [{"seq": 1, "phase": "page", "message": "Первая страница."}],
            "done": False,
        },
        {
            "success": True,
            "events": [{"seq": 2, "phase": "action", "message": "Нажимаю play."}],
            "done": True,
        },
    ]

    def fake_fetch(events_url, run_id, after):
        return responses.pop(0)

    calls = []

    def progress_callback(name, preview, args):
        calls.append(preview)

    monkeypatch.setattr(browser_use_tool, "_fetch_browser_events", fake_fetch)
    monkeypatch.setenv("BROWSER_LIVE_LOG_POLL_INTERVAL", "0.1")
    monkeypatch.setenv("BROWSER_LIVE_LOG_MAX_EVENTS", "1")

    async def run_poll():
        await browser_use_tool._poll_live_events(
            "http://browser:8787/events",
            "run-1",
            progress_callback,
            asyncio.Event(),
            "",
            {"value": 0},
        )

    asyncio.run(run_poll())

    assert calls == ["📍 Первая страница.", "🖱️ Нажимаю play."]
