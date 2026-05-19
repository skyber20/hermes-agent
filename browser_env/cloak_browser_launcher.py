import asyncio
import os
import shlex
import signal

from cloakbrowser import launch_async


def _env_bool(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


async def main():
    debug_port = os.getenv("CHROME_LOCAL_DEBUG_PORT", "9223")
    args = [
        f"--remote-debugging-port={debug_port}",
        "--remote-debugging-address=127.0.0.1",
        "--remote-allow-origins=*",
        "--window-size=1280,720",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--ozone-platform=x11",
    ]
    extra_args = os.getenv("CLOAK_ARGS", "").strip()
    if extra_args:
        args.extend(shlex.split(extra_args))

    launch_kwargs = {
        "headless": _env_bool("CLOAK_HEADLESS", False),
        "humanize": _env_bool("CLOAK_HUMANIZE", True),
        "args": args,
    }

    if launch_kwargs["humanize"]:
        launch_kwargs["human_preset"] = os.getenv("CLOAK_HUMAN_PRESET", "default")

    proxy = os.getenv("CLOAK_PROXY", "").strip()
    if proxy:
        launch_kwargs["proxy"] = proxy

    if _env_bool("CLOAK_GEOIP", False):
        launch_kwargs["geoip"] = True

    browser = await launch_async(**launch_kwargs)
    print(f"CloakBrowser started on 127.0.0.1:{debug_port}", flush=True)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    try:
        await stop_event.wait()
    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
