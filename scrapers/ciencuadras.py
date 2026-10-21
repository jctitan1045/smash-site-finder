"""Ciencuadras scraper (commercial).

Angular Universal: server state sits in one <script type="application/json">
block, HTML-entity-encoded (&q; == "). The list payload already carries m²,
price, barrio, coords and contact, so we pre-filter on size + area from the list
and only fetch detail pages (description, admin, amenities, gallery) for the
survivors. No size filter in the URL, so the list crawl is the long part.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from core.models import Listing, parse_int, parse_area, normalize_type, wa_number, clean_phone
from .http import get, polite_sleep

BASE = "https://www.ciencuadras.com"
_JSON_RE = re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S)


def _decode_state(html: str) -> dict | None:
    m = _JSON_RE.search(html)
    if not m:
        return None
    dec = (m.group(1).replace("&q;", '"').replace("&a;", "&")
           .replace("&l;", "<").replace("&g;", ">")
           .replace("&s;", "'").replace("&b;", "\\"))
    try:
        return json.loads(dec)
    except json.JSONDecodeError:
        return None


def _list_to_listing(raw: dict, deal: str) -> Listing | None:
    sid = str(raw.get("code") or raw.get("id") or "")
    if not sid:
        return None
    url = raw.get("url") or ""
    if url and not url.startswith("http"):
        url = BASE + ("" if url.startswith("/") else "/") + url
    coord = raw.get("coordinates") or {}
    admin = parse_int(raw.get("adminValue")) or 0
    return Listing(
        source="ciencuadras",
        source_id=sid,
        url=url,
        title=f"{raw.get('realEstateType','Inmueble')} en {raw.get('neighborhood','')}, {raw.get('city','')}",
        deal=deal,
        property_type=normalize_type(raw.get("realEstateType")),
        neighborhood=raw.get("neighborhood", "") or "",
        city=raw.get("city", "") or "",
        address=raw.get("address", "") or "",
        price_rent=(parse_int(raw.get("rentPrice")) or 0) if deal == "arriendo" else 0,
        price_sale=(parse_int(raw.get("salePrice")) or 0) if deal == "venta" else 0,
        price_admin=admin,
        admin_known=admin > 0,
        area_m2=parse_area(raw.get("privateArea") or raw.get("area")),
        stratum=parse_int(raw.get("stratum")),
        garages=parse_int(raw.get("garages")),
        lat=coord.get("latitude"),
        lng=coord.get("longitude"),
        image=raw.get("image", "") or "",
        images=[raw["image"]] if raw.get("image") else [],
        contact_name=raw.get("userName", "") or "",
        contact_phone=clean_phone(raw.get("contactPhone")),
        contact_whatsapp=wa_number(raw.get("contactPhone")),
        contact_email=raw.get("realStateEmail", "") or "",
        created_at=str(raw.get("createdAt", "") or ""),
    )


def _enrich(listing: Listing) -> None:
    """Detail page: description, admin, amenities, gallery, advisor contact."""
    html = get(listing.url)
    if not html:
        return
    state = _decode_state(html)
    if not state:
        return
    detail = state.get(f"detail-property-{urlparse(listing.url).path}") or {}
    g = detail.get("generalData") or {}
    if not g:
        return

    admin = parse_int(g.get("adminValue")) or 0
    if admin:
        listing.price_admin, listing.admin_known = admin, True
    if listing.deal == "arriendo":
        listing.price_rent = parse_int(g.get("leaseFee")) or listing.price_rent
    listing.description = g.get("description", "") or ""
    listing.area_m2 = parse_area(g.get("builtArea")) or listing.area_m2
    listing.floor = parse_int(g.get("floor")) or listing.floor
    listing.bathrooms = parse_int(g.get("bathRoomNum")) or listing.bathrooms

    amen = [z.get("label", "") for z in (detail.get("commonZonesProperty") or []) if z.get("label")]
    if parse_int(g.get("numTerrace")):
        amen.append("Terraza")
    if parse_int(g.get("numElevators")):
        amen.append("Ascensor")
    listing.amenities = amen

    gallery = [p.get("url") for p in ((detail.get("galleryData") or {}).get("flatPhotos") or [])
               if p.get("url")]
    if gallery:
        listing.images = gallery[:12]
        listing.image = listing.image or gallery[0]

    listing.contact_name = g.get("advisoryName") or listing.contact_name
    listing.contact_phone = clean_phone(g.get("advisoryPhone")) or listing.contact_phone
    listing.contact_whatsapp = (wa_number(g.get("whatsAppContact") or g.get("advisorWhatsapp"))
                                or listing.contact_whatsapp)
    listing.contact_email = g.get("advisorMail") or listing.contact_email


def scrape(cfg: dict, match_area) -> list[Listing]:
    """match_area is injected to avoid a circular import with core.pipeline."""
    conf = cfg["sources"]["ciencuadras"]
    max_pages = conf.get("max_pages", 50)
    floor = cfg["hard"]["min_area_m2"] * 0.9          # keep near-misses for the board
    out: list[Listing] = []
    seen: set[str] = set()

    for path in conf["searches"]:
        deal = path.split("/", 1)[0]
        for page in range(1, max_pages + 1):
            url = f"{BASE}/{path}" + (f"?page={page}" if page > 1 else "")
            html = get(url)
            if not html:
                break
            state = _decode_state(html)
            if not state:
                print(f"    ! ciencuadras: no state at {url}")
                break
            block = (state.get(f"results-/{path}") or {}).get("data") or {}
            rows = (block.get("results") or []) + (block.get("highlights") or [])
            if not rows:
                break
            fresh = kept = 0
            for raw in rows:
                lst = _list_to_listing(raw, deal)
                if not lst or lst.uid in seen:
                    continue
                seen.add(lst.uid)
                fresh += 1
                if lst.area_m2 is not None and lst.area_m2 < floor:
                    continue
                area = match_area(lst.neighborhood, lst.city, cfg["areas"])
                if not area:
                    continue
                lst.area_key = area
                out.append(lst)
                kept += 1
            print(f"    ciencuadras/{path} p{page}: kept {kept}/{len(rows)}")
            if fresh == 0:
                break
            polite_sleep()

    print(f"    ciencuadras: enriching {len(out)} survivors...")
    for lst in out:
        _enrich(lst)
        polite_sleep()
    return out
