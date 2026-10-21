"""Shared HTTP fetch with browser-like headers, retries, and polite pacing."""
from __future__ import annotations

import http.client
import socket
import time
import random
import urllib.request
import urllib.error

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Connection": "close",
}


def get(url: str, retries: int = 3, timeout: int = 30) -> str | None:
    """Fetch a URL as text, following redirects. Returns None on hard failure."""
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="ignore")
        except (urllib.error.HTTPError, urllib.error.URLError,
                TimeoutError, socket.timeout, ConnectionError,
                http.client.IncompleteRead, http.client.RemoteDisconnected) as e:
            last_err = e
            # 404 on a pagination page just means we've run out — don't retry hard
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                return None
            time.sleep(1.5 * (attempt + 1) + random.random())
    print(f"    ! fetch failed: {url} ({last_err})")
    return None


def polite_sleep():
    time.sleep(0.8 + random.random() * 0.7)
