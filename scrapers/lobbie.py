"""Lobbie watcher.

Lobbie (app.lobbieapp.com) is an agent ad tool: every property gets a public
landing page, but there is no search or index. The short code in the URL is just
the property's sequential id in base62 (1hGm = 404660), so new listings can be
found by walking ids forward from where the last run stopped.

Politeness: robots.txt allows all. We only walk NEW ids each day (~1 req/s),
stop after a run of misses (deleted/unpublished ids leave gaps), and re-check
previously found listings so delisted ones drop off.

State:
  data/lobbie_cursor.json  {"max_id": highest id seen live}
  data/lobbie_found.json   {id: {"url":..., "first_seen":...}} commercial hits we keep
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

from core.models import Listing, strip_accents
from .http import get
from .manual import _parse_lobbie

ROOT = os.path.dirname(os.path.dirname(__file__))
CURSOR_PATH = os.path.join(ROOT, "data", "lobbie_cursor.json")
FOUND_PATH = os.path.join(ROOT, "data", "lobbie_found.json")
BASE = "https://app.lobbieapp.com/inmueble/"
_A = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_COMMERCIAL = re.compile(r"\b(local|bodega|edificio)\b")      # matches include_types


def enc(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n, 62)
        s = _A[r] + s
    return s or "0"


def _load(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _fetch(n: int) -> Listing | None:
    url = BASE + enc(n)
    html = get(url, retries=2)                 # 404 -> None immediately
    if not html:
        return None
    lst = _parse_lobbie(url, html)
    lst.source, lst.source_id = "lobbie", str(n)
    return lst


def _wanted(lst: Listing, cities: list[str]) -> bool:
    """Commercial type, priced in COP, in one of our cities. Area match happens later."""
    hay = strip_accents(f"{lst.title} {lst.neighborhood} {lst.city}")
    if not _COMMERCIAL.search(strip_accents(lst.title)):
        return False
    if not (lst.price_rent or lst.price_sale):
        return False
    return any(c in hay for c in cities)


def scan(cfg: dict, start: int | None = None, stop_after_misses: int | None = None,
         pace: float | None = None) -> list[Listing]:
    conf = cfg["sources"]["lobbie"]
    cities = cfg["hard"]["allowed_cities"]
    misses_cap = stop_after_misses or conf.get("stop_after_misses", 200)
    pace = conf.get("pace_seconds", 0.8) if pace is None else pace
    cursor = _load(CURSOR_PATH, {"max_id": conf.get("seed_id", 406000)})
    found = _load(FOUND_PATH, {})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1) walk new ids
    n = start if start is not None else cursor["max_id"] + 1
    misses = scanned = live = 0
    while misses < misses_cap:
        lst = _fetch(n)
        scanned += 1
        if lst is None:
            misses += 1
        else:
            misses, live = 0, live + 1
            cursor["max_id"] = max(cursor["max_id"], n)
            if _wanted(lst, cities) and str(n) not in found:
                found[str(n)] = {"url": lst.url, "first_seen": today, "title": lst.title}
                print(f"    lobbie #{n}: {lst.title} · {lst.neighborhood}, {lst.city}")
        n += 1
        if scanned % 500 == 0:
            print(f"    lobbie: scanned {scanned} (at #{n}, {live} live, {len(found)} kept)")
            _save(CURSOR_PATH, cursor)
            _save(FOUND_PATH, found)
        time.sleep(pace)
    _save(CURSOR_PATH, cursor)
    print(f"    lobbie: walked {scanned} ids, {live} live, frontier #{cursor['max_id']}")

    # 2) re-check everything we've kept; drop delisted
    out: list[Listing] = []
    for sid in list(found):
        lst = _fetch(int(sid))
        if lst is None:
            print(f"    lobbie #{sid}: delisted, dropping")
            del found[sid]
            continue
        out.append(lst)
        time.sleep(pace)
    _save(FOUND_PATH, found)
    print(f"    lobbie: {len(out)} commercial listings in our cities")
    return out


def scrape(cfg: dict) -> list[Listing]:
    return scan(cfg)


if __name__ == "__main__":
    # one-off backfill:  python -m scrapers.lobbie 400000
    import sys
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        _cfg = yaml.safe_load(f)
    _start = int(sys.argv[1]) if len(sys.argv) > 1 else None
    scan(_cfg, start=_start, pace=0.35)
