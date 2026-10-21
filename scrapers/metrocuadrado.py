"""Metrocuadrado scraper (commercial).

Next.js App-Router site: results stream as RSC "flight" chunks
(self.__next_f.push([1,"..."])); we reassemble them and brace-match the
"results" array — 50 listings/page. No working size filter in the URL, so we
crawl every page and let the pipeline drop anything under the m² floor.
"""
from __future__ import annotations

import json
import re

from core.models import Listing, parse_int, parse_area, normalize_type, wa_number, clean_phone
from .http import get, polite_sleep

BASE = "https://www.metrocuadrado.com"
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[\d+,\s*"((?:[^"\\]|\\.)*)"\]\)')


def _flight_blob(html: str) -> str:
    out = []
    for chunk in _PUSH_RE.findall(html):
        try:
            out.append(json.loads('"' + chunk + '"'))
        except json.JSONDecodeError:
            out.append(chunk)
    return "".join(out)


def _extract_results(blob: str) -> list:
    i = blob.find('"results":[')
    if i < 0:
        return []
    start = blob.find("[", i + len('"results":') - 1)
    depth = 0
    for k in range(start, len(blob)):
        c = blob[k]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(blob[start:k + 1])
                except json.JSONDecodeError:
                    return []
    return []


def _name(v):
    if isinstance(v, dict):
        return v.get("nombre", "") or ""
    return v or ""


def _to_listing(raw: dict, deal: str) -> Listing | None:
    sid = str(raw.get("midinmueble") or "")
    if not sid:
        return None
    link = raw.get("link") or ""

    rent = parse_int(raw.get("mvalorarriendo")) or 0
    sale = parse_int(raw.get("mvalorventa")) or 0
    admin = parse_int(raw.get("mvaloradministracion")) or 0

    photo_ids = raw.get("mgaleriainmueble") or []
    gallery = [f"https://multimedia.metrocuadrado.com/{sid}/{pid}_p.jpg"
               for pid in photo_ids if pid][:12]
    primary = raw.get("imageLink", "") or (gallery[0] if gallery else "")
    if primary and primary not in gallery:
        gallery = [primary] + gallery

    lat = lng = None
    gp = raw.get("geopoints") or []
    if gp:
        try:
            lat, lng = float(gp[0].get("latitude")), float(gp[0].get("longitude"))
        except (TypeError, ValueError):
            pass

    return Listing(
        source="metrocuadrado",
        source_id=sid,
        url=link if link.startswith("http") else BASE + link,
        title=raw.get("title", "") or "",
        deal=deal,
        property_type=normalize_type(_name(raw.get("mtipoinmueble"))),
        neighborhood=_name(raw.get("mnombrecomunbarrio")) or _name(raw.get("mbarrio")),
        city=_name(raw.get("mciudad")),
        price_rent=rent if deal == "arriendo" else 0,
        price_sale=sale if deal == "venta" else 0,
        price_admin=admin,
        admin_known=admin > 0,
        area_m2=parse_area(raw.get("mareac") or raw.get("marea")),
        stratum=parse_int(raw.get("estrato")),
        garages=parse_int(raw.get("mnrogarajes")),
        bathrooms=parse_int(raw.get("mnrobanos")),
        description=raw.get("comment", "") or "",
        lat=lat, lng=lng,
        image=primary,
        images=gallery[:12],
        contact_name=_name(raw.get("moferente")) if raw.get("moferente") not in ("RealEstate", None) else "",
        contact_phone=clean_phone(raw.get("contactPhone") or raw.get("mcontactoinmobiliaria_fijo1")),
        contact_whatsapp=wa_number(raw.get("whatsapp")),
    )


def scrape(cfg: dict) -> list[Listing]:
    conf = cfg["sources"]["metrocuadrado"]
    max_pages = conf.get("max_pages", 20)
    out: list[Listing] = []
    seen: set[str] = set()

    for path in conf["searches"]:
        deal = "venta" if "/venta/" in path else "arriendo"
        for page in range(1, max_pages + 1):
            url = f"{BASE}/{path}" + (f"{page}/" if page > 1 else "")
            html = get(url)
            if not html:
                break
            rows = _extract_results(_flight_blob(html))
            if not rows:
                if page == 1:
                    print(f"    ! metrocuadrado: no results at {url}")
                break
            fresh = 0
            for raw in rows:
                lst = _to_listing(raw, deal)
                if not lst or lst.uid in seen:
                    continue
                seen.add(lst.uid)
                out.append(lst)
                fresh += 1
            print(f"    metrocuadrado/{path} p{page}: +{fresh}/{len(rows)}")
            if fresh == 0:
                break
            polite_sleep()

    return out
