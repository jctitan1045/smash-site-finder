#!/usr/bin/env python3
"""Smash Wellness Club — Site Finder. Daily orchestrator.

  scrape portals + manual links -> area-match -> IVA all-in + hard-filter + score
  -> dedup ledger -> dashboard (docs/index.html)

Usage:
  python run.py            full run
  python run.py --dry      quick run: 1 page per search (local testing)
  python run.py --rescore  re-apply config.yaml to the last scrape (no network)
"""
from __future__ import annotations

import argparse
import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import pipeline, store
import dataclasses

from core.models import Listing
from scrapers import fincaraiz, ciencuadras, metrocuadrado, manual, lobbie
from dashboard import build as dashboard

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _area_match(listings: list[Listing], cfg: dict, name: str) -> list[Listing]:
    """Portals pad results with nearby barrios; keep only our target areas."""
    kept = []
    for l in listings:
        area = l.area_key or pipeline.match_area(l.neighborhood, l.city, cfg["areas"],
                                                    cfg.get("exclude_tokens"))
        if area:
            l.area_key = area
            kept.append(l)
    print(f"  {name}: {len(kept)}/{len(listings)} in target areas")
    return kept


def collect(cfg: dict) -> list[Listing]:
    src = cfg["sources"]
    out: list[Listing] = []
    if src["fincaraiz"].get("enabled"):
        print("→ Fincaraíz")
        out += _area_match(fincaraiz.scrape(cfg), cfg, "fincaraiz")
    if src["metrocuadrado"].get("enabled"):
        print("→ Metrocuadrado")
        out += _area_match(metrocuadrado.scrape(cfg), cfg, "metrocuadrado")
    if src["ciencuadras"].get("enabled"):
        print("→ Ciencuadras")
        out += ciencuadras.scrape(
            cfg, lambda n, c, a: pipeline.match_area(n, c, a, cfg.get("exclude_tokens")))
    manual_urls: set[str] = set()
    if src["manual"].get("enabled"):
        print("→ Manual links")
        for l in manual.scrape(cfg):          # manual entries are always kept
            l.area_key = l.area_key or pipeline.match_area(
                l.neighborhood, l.city, cfg["areas"], cfg.get("exclude_tokens")) or "other"
            manual_urls.add(l.url.split("?")[0])
            out.append(l)
    if src.get("lobbie", {}).get("enabled"):
        print("→ Lobbie (new ids)")
        lb = [l for l in lobbie.scrape(cfg) if l.url.split("?")[0] not in manual_urls]
        out += _area_match(lb, cfg, "lobbie")

    unique: dict[str, Listing] = {}
    for l in out:
        unique.setdefault(l.uid, l)
    return list(unique.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="fast local run, 1 page per search")
    ap.add_argument("--rescore", action="store_true", help="re-apply config to last scrape")
    args = ap.parse_args()

    cfg = load_config()
    if args.rescore:
        return rescore(cfg)
    if args.dry:
        for s in ("fincaraiz", "metrocuadrado", "ciencuadras"):
            cfg["sources"][s]["max_pages"] = 1

    listings = collect(cfg)
    print(f"\nCollected {len(listings)} in-area listings. Processing...")
    for l in listings:
        pipeline.process(l, cfg)

    rejected = store.load_rejected()
    matches = [l for l in listings
               if (l.benchmark or l.source == "manual" or not l.hard_fails)
               and l.uid not in rejected]
    matches.sort(key=lambda x: (not x.benchmark, -x.score))
    print(f"{len(matches)} on the board "
          f"({sum(1 for l in matches if getattr(l, '_near_miss', False))} near-miss).")

    seen = store.load_seen()
    new_uids = set(store.mark_seen(seen, [l.uid for l in matches]))
    for l in matches:
        l.is_new = l.uid in new_uids and not l.benchmark
    store.save_seen(seen)
    print(f"{len(new_uids)} new since last run.")

    dicts = [l.to_dict() for l in matches]
    store.save_listings(dicts)
    print(f"Dashboard written: {dashboard.build(dicts, cfg)}")


def rescore(cfg: dict):
    """Rebuild scores/filters/dashboard from data/listings.json after a config tweak.
    Only re-filters what was already on the board — loosening a filter needs a scrape."""
    fields = {f.name for f in dataclasses.fields(Listing)}
    listings = []
    for d in store.load_listings()["listings"]:
        l = Listing(**{k: v for k, v in d.items() if k in fields})
        l.notes, l.hard_fails, l.score_flags = [], [], []
        if l.source != "manual":
            l.iva_included = None
            l.area_key = pipeline.match_area(l.neighborhood, l.city, cfg["areas"],
                                             cfg.get("exclude_tokens")) or ""
            if not l.area_key:
                continue                          # area now excluded by config
        pipeline.process(l, cfg)
        listings.append(l)
    keep = [l for l in listings if l.benchmark or l.source == "manual" or not l.hard_fails]
    keep.sort(key=lambda x: (not x.benchmark, -x.score))
    dicts = [l.to_dict() for l in keep]
    store.save_listings(dicts)
    print(f"Rescored {len(keep)} listings. Dashboard: {dashboard.build(dicts, cfg)}")


if __name__ == "__main__":
    main()
