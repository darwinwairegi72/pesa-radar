"""One place for web requests, so we are polite: identify ourselves and pause between requests."""
import time

import requests

_last_request = 0.0


def get(url: str, cfg: dict, binary: bool = False):
    global _last_request
    pause = cfg.get("request_delay_seconds", 3) - (time.time() - _last_request)
    if pause > 0:
        time.sleep(pause)
    response = requests.get(url, headers={"User-Agent": cfg["user_agent"]}, timeout=30)
    _last_request = time.time()
    response.raise_for_status()
    return response.content if binary else response.text


def safe_url(url: str) -> str:
    """Spaces in a link break it when it is pasted into an email or an issue. Encode them (as %20)."""
    import urllib.parse
    return urllib.parse.quote(url, safe=":/?&=#%@+,;~")
