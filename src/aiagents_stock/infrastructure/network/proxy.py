"""Proxy handling for external data and API calls.

The desktop/runtime environment can inject proxy variables such as
HTTP_PROXY=http://127.0.0.1:9. Many market-data SDKs use requests and inherit
those variables automatically, which breaks data fetches. The project default
is therefore to disable proxy environment variables for the app process.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "GIT_HTTP_PROXY",
    "GIT_HTTPS_PROXY",
)


def proxy_bypass_enabled() -> bool:
    """Return whether external interfaces should ignore process proxies."""
    value = os.getenv("AIAGENTS_STOCK_DISABLE_PROXY", "true").strip().lower()
    return value not in {"0", "false", "no", "off"}


def disable_proxy_env() -> dict[str, str | None]:
    """Remove proxy env vars process-wide and bypass any remaining proxies."""
    saved = {key: os.environ.get(key) for key in (*PROXY_ENV_KEYS, "NO_PROXY", "no_proxy")}
    if not proxy_bypass_enabled():
        return saved
    for key in PROXY_ENV_KEYS:
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"
    return saved


@contextmanager
def without_proxy_env() -> Iterator[None]:
    """Temporarily disable proxy env vars, then restore them."""
    saved = disable_proxy_env()
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
