from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Any

try:
    from curl_cffi import requests as cffi_requests

    HAS_CURL_CFFI = True
except ImportError:
    cffi_requests = None
    HAS_CURL_CFFI = False

import httpx

CHROME_PROFILES = ["chrome", "chrome136", "chrome131", "chrome124"]
SAFARI_PROFILES = ["safari_ios", "safari", "chrome"]

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['fr-FR', 'fr', 'en-US', 'en'] });
window.chrome = window.chrome || { runtime: {} };
"""


def jitter_sleep(min_seconds: float = 3.5, max_seconds: float = 7.5) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def launch_stealth_context(
    playwright_obj: Any,
    profile_dir: Path,
    *,
    headless: bool = True,
    use_system_channel: bool = False,
) -> Any:
    """Lance un contexte Playwright persistant (Chromium Playwright par défaut)."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    common_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    base_kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "locale": "fr-FR",
        "timezone_id": "Europe/Paris",
        "viewport": {"width": 1366, "height": 860},
        "args": common_args,
        "ignore_default_args": ["--enable-automation"],
    }
    channels = ("chrome", "msedge", None) if use_system_channel else (None,)
    for channel in channels:
        try:
            kw = dict(base_kwargs)
            if channel:
                kw["channel"] = channel
            ctx = playwright_obj.chromium.launch_persistent_context(**kw)
            ctx.add_init_script(STEALTH_JS)
            return ctx
        except Exception:
            continue
    raise RuntimeError("Impossible de lancer Chromium via Playwright.")


class StealthSession:
    """Session HTTP imitant l'empreinte TLS d'un vrai navigateur (Chrome ou Safari iOS)."""

    def __init__(self, timeout: float = 20.0, mobile: bool = False) -> None:
        self.timeout = timeout
        self._session: Any = None
        profiles = SAFARI_PROFILES if mobile else CHROME_PROFILES
        if HAS_CURL_CFFI:
            for profile in profiles:
                try:
                    self._session = cffi_requests.Session(impersonate=profile)
                    break
                except Exception:
                    continue
        if self._session is None:
            self._session = httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36"
                    )
                },
            )

    def get(self, url: str, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", self.timeout)
        return self._session.get(url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", self.timeout)
        return self._session.post(url, **kwargs)

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass
