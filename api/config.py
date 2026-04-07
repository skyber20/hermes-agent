import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("BROWSER_API_HOST", "0.0.0.0")
    app_port: int = os.getenv("BROWSER_API_PORT", "8080")

    browser_rpc_url: str = os.getenv("BROWSER_USE_RPC_URL", "http://browser:8787/run")
    browser_rpc_timeout: float = float(os.getenv("BROWSER_USE_RPC_TIMEOUT", "900"))

    max_concurrency = int(os.getenv("BROWSER_API_MAX_CONCURRENCY", "2"))


settings = Settings()
