"""Manual intake: links you were sent (Lobbie pages, agent sites, anything).

Lobbie (app.lobbieapp.com/inmueble/<id>) is an agent marketing tool with no
public index, so its pages can't be crawled — but each one parses cleanly.
Other URLs get a best-effort read of og:title / og:description / og:image.
Anything in the entry's `set:` block overrides what was parsed.

data/manual.yaml:
  - url: https://app.lobbieapp.com/inmueble/1hGm
    label: "Cra 47B #17A Sur"
    benchmark: true            # optional — pins it as the yardstick
    note: "free text shown on the card"
    set: {area_m2: 740, lat: 6.19, lng: -75.57}
"""
from __future__ import annotations

import hashlib
import html as htmllib
import os
import re

import yaml

from core.models import Listing, parse_int, parse_area, normalize_type, wa_number, clean_phone
from .http import get, polite_sleep

ROOT = os.path.dirname(os.path.dirname(__file__))
MANUAL_PATH = os.path.join(ROOT, "data", "manual.yaml")


def _text(html: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = htmllib.unescape(re.sub(r"<[^>]+>", " | ", t))
    return re.sub(r"(\s*\|\s*)+", " | ", t)


def _meta(html: str, prop: str) -> str:
    m = re.search(rf'(?:property|name)="{prop}"\s+content="([^"]*)"', html)
    return htmllib.unescape(m.group(1)) if m else ""


def _parse_lobbie(url: str, html: str) -> Listing:
    text = _text(html)
    sid = url.rstrip("/").split("/")[-1].split("?")[0]
    title = _meta(html, "og:title") or "Lobbie listing"

    price = parse_int((re.search(r"COP\s*([\d.]+)", text) or [None, None])[1])
    m2 = parse_area((re.search(r"([\d.,]+)\s*m²", text) or [None, None])[1])
    stratum = parse_int((re.search(r"Estrato\s*\|\s*(\d)", text) or [None, None])[1])
    loc = re.search(r"Lobbie \| ([^|]+?), (Medell[ií]n|Envigado)", text)
    desc = re.search(r"Descripción \|(.*?)\| (?:A \| )?[A-ZÁÉÍÓÚ][^|]{2,60} \| \+?\d", text, re.S)
    phone = re.search(r"\+57\s?3\d{9}", text)
    agent = re.search(r"\| ([A-ZÁÉÍÓÚ][\wáéíóúñ]+(?: [A-ZÁÉÍÓÚ][\wáéíóúñ]+){1,3}) \| \+57", text)

    photos = []
    for u in re.findall(r'(?:src|href)="(https://[a-z0-9]+\.cloudfront\.net/properties/[^"]+\.jpe?g)"', html):
        full = u.replace("/preview_", "/")
        if full not in photos:
            photos.append(full)

    deal = "venta" if "venta" in title.lower() else "arriendo"
    return Listing(
        source="manual", source_id="lobbie-" + sid, url=url, title=title, deal=deal,
        property_type=normalize_type(title),
        neighborhood=loc.group(1).strip() if loc else "",
        city=loc.group(2) if loc else "",        # never default: Lobbie is multi-country
        price_rent=(price or 0) if deal == "arriendo" else 0,
        price_sale=(price or 0) if deal == "venta" else 0,
        area_m2=m2, stratum=stratum,
        description=desc.group(1).strip(" |") if desc else "",
        image=photos[0] if photos else "", images=photos[:12],
        contact_name=agent.group(1) if agent else "",
        contact_phone=clean_phone(phone.group()) if phone else "",
        contact_whatsapp=wa_number(phone.group()) if phone else "",
    )


def _parse_generic(url: str, html: str) -> Listing:
    title = _meta(html, "og:title") or (re.search(r"<title>([^<]*)", html) or [None, url])[1]
    desc = _meta(html, "og:description") or _meta(html, "description")
    img = _meta(html, "og:image")
    hay = f"{title} {desc}"
    return Listing(
        source="manual", source_id="url-" + hashlib.md5(url.encode()).hexdigest()[:10],
        url=url, title=title.strip(), description=desc,
        deal="venta" if re.search(r"\bventa\b", hay, re.I) else "arriendo",
        property_type=normalize_type(title),
        area_m2=parse_area((re.search(r"([\d.,]+)\s*m(?:²|2)\b", hay) or [None, None])[1]),
        image=img, images=[img] if img else [],
    )


def scrape(cfg: dict) -> list[Listing]:
    if not os.path.exists(MANUAL_PATH):
        return []
    with open(MANUAL_PATH, encoding="utf-8") as f:
        entries = yaml.safe_load(f) or []

    out: list[Listing] = []
    for e in entries:
        url = (e or {}).get("url")
        if not url:
            continue
        html = get(url) or ""
        lst = _parse_lobbie(url, html) if "lobbieapp.com/inmueble" in url else _parse_generic(url, html)
        if not html:
            lst.notes.append("page could not be fetched — showing manual fields only")
        lst.label = e.get("label", "")
        lst.benchmark = bool(e.get("benchmark"))
        lst.user_note = e.get("note", "")
        for k, v in (e.get("set") or {}).items():
            if hasattr(lst, k):
                setattr(lst, k, v)
        print(f"    manual: {lst.label or lst.title[:50]} ({lst.area_m2 or '?'} m²)")
        out.append(lst)
        polite_sleep()
    return out
