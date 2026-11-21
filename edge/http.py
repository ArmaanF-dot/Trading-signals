"""Polite HTTP GET: rate limiting plus retries with exponential backoff."""
import time

import requests

import config

_last_request = 0.0


def get(url: str, headers: dict | None = None, min_interval: float = 0.0) -> requests.Response:
    global _last_request
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(config.HTTP_RETRIES):
        wait = min_interval - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()
        try:
            resp = requests.get(url, headers=headers, timeout=config.HTTP_TIMEOUT)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < config.HTTP_RETRIES - 1:
                time.sleep(delay)
                delay *= 2
    raise last_exc  # type: ignore[misc]
