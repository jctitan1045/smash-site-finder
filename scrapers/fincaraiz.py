"""Fincaraíz scraper (commercial).

Same engine as the apartment finder: Next.js server-renders the result set into
__NEXT_DATA__ (props.pageProps.fetchResult.searchFast.data). Commercial search
paths accept a size filter as a path segment (`/m2-desde-450`), which keeps the
crawl small. Area is re-derived from the listing's own barrio in run.py.
"""
from __future__ import annotations

import json
import re

from core.models import Listing, parse_int, parse_area, normalize_type
from .http import get, polite_sleep

BASE = "https://www.fincaraiz.com.co"
_NEXT_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>', re.S)


def _extract_next_data(html: str) -> dict | None:
    m = _NEXT_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _tech(sheet: list, field: str):
    for row in sheet or []:
        if row.get("field") == field:
            return row.get("value")
    return None


def _to_listing(raw: dict, deal: str) -> Listing | None:
    try:
        sid = str(raw.get("id"))
        if not sid or sid == "None":
            return None

        amount = parse_int((raw.get("price") or {}).get("amount")) or 0
        common = raw.get("commonExpenses") or {}
        admin = parse_int(common.get("amount")) or 0
        include_admin = bool(raw.get("include_administration"))

        loc = raw.get("locations") or {}
        main = loc.get("location_main") or {}
        city_list = loc.get("city") or []
        sheet = raw.get("technicalSheet") or []

        link = raw.get("link") or ""
        img = raw.get("img", "") or ""
        gallery = [i.get("image") for i in (raw.get("images") or []) if i.get("image")]
        if not gallery and img:
            gallery = [img]

        built = parse_area(_tech(sheet, "m2Built"))
        area = built or parse_area(raw.get("m2"))

        return Listing(
            source="fincaraiz",
            source_id=sid,
            url=link if link.startswith("http") else BASE + link,
            title=raw.get("title", "") or "",
            deal=deal,
            neighborhood=main.get("name") or "",
            city=city_list[0]["name"] if city_list else "",
            address=raw.get("address", "") or "",
            price_rent=amount if deal == "arriendo" else 0,
            price_sale=amount if deal == "venta" else 0,
            price_admin=0 if include_admin else admin,
            admin_known=include_admin or admin > 0,
            area_m2=area,
            stratum=raw.get("stratum") or parse_int(_tech(sheet, "stratum")),
            floor=raw.get("floor") or parse_int(_tech(sheet, "floor")),
            garages=raw.get("garage"),
            bathrooms=raw.get("bathrooms"),
            property_type=normalize_type((raw.get("property_type") or {}).get("name")),
            amenities=[f.get("name", "") for f in (raw.get("facilities") or [])],
            description=raw.get("description", "") or "",
            lat=raw.get("latitude"),
            lng=raw.get("longitude"),
            image=img,
            images=gallery[:12],
            contact_name=((raw.get("owner") or {}).get("name") or "").strip(),
            created_at=raw.get("created_at", "") or "",
        )
    except (KeyError, TypeError, ValueError) as e:
        print(f"    ! fincaraiz parse skip: {e}")
        return None


def scrape(cfg: dict) -> list[Listing]:
    conf = cfg["sources"]["fincaraiz"]
    max_pages = conf.get("max_pages", 8)
    out: list[Listing] = []
    seen: set[str] = set()

    for path in conf["searches"]:
        deal = path.split("/", 1)[0]
        for page in range(1, max_pages + 1):
            url = f"{BASE}/{path}" + (f"/pagina{page}" if page > 1 else "")
            html = get(url)
            if not html:
                break
            data = _extract_next_data(html)
            if not data:
                print(f"    ! fincaraiz: no __NEXT_DATA__ at {url}")
                break
            try:
                sf = data["props"]["pageProps"]["fetchResult"]["searchFast"]
                rows = sf["data"]
            except (KeyError, TypeError):
                break
            if not rows:
                break

            page_new = 0
            for raw in rows:
                lst = _to_listing(raw, deal)
                if lst and lst.source_id not in seen:
                    seen.add(lst.source_id)
                    out.append(lst)
                    page_new += 1
            print(f"    fincaraiz/{path.replace('/suroriente/medellin','')} p{page}: +{page_new}")
            more = (sf.get("paginatorInfo") or {}).get("hasMorePages")
            if page_new == 0 or more is False:
                break
            polite_sleep()

    return out
