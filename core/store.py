"""Persistence: current matches + a 'seen' ledger for dedup across daily runs."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
SEEN_PATH = os.path.join(DATA_DIR, "seen.json")
LISTINGS_PATH = os.path.join(DATA_DIR, "listings.json")
REJECTED_PATH = os.path.join(DATA_DIR, "rejected.json")


def load_rejected() -> set:
    """uids the user rejected on the dashboard (exported → committed). These are
    excluded from matches, the dashboard, and the push. Missing file == none."""
    if not os.path.exists(REJECTED_PATH):
        return set()
    try:
        with open(REJECTED_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, ValueError):
        return set()


def _ensure():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_seen() -> dict:
    """uid -> {first_seen, last_seen} for every listing ever surfaced."""
    if not os.path.exists(SEEN_PATH):
        return {}
    with open(SEEN_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_seen(seen: dict):
    _ensure()
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def mark_seen(seen: dict, uids: list) -> list:
    """Update the ledger; return the uids that are brand new this run."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new = []
    for uid in uids:
        if uid not in seen:
            seen[uid] = {"first_seen": now, "last_seen": now}
            new.append(uid)
        else:
            seen[uid]["last_seen"] = now
    return new


def save_listings(listings: list):
    """Persist the current matched set (dicts) for the dashboard build step."""
    _ensure()
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(listings),
        "listings": listings,
    }
    with open(LISTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_listings() -> dict:
    if not os.path.exists(LISTINGS_PATH):
        return {"listings": [], "generated_at": "", "count": 0}
    with open(LISTINGS_PATH, encoding="utf-8") as f:
        return json.load(f)
