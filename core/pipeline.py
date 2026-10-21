"""Filter + score + detect logic for commercial sites. Portal-agnostic."""
from __future__ import annotations

import re
from typing import Optional

from .models import Listing, strip_accents

_IVA_INCLUDED = ["iva incluido", "incluye iva", "incluido iva", "con iva incluido", "valor con iva"]
_IVA_EXTRA = ["+ iva", "+iva", "mas iva", "más iva", "no incluye iva", "sin iva", "iva no incluido", "antes de iva"]
_COMMERCIAL_USE = ["uso comercial", "uso mixto", "comercial", "local", "oficinas", "consultorio"]
# Commercial spaces only. A house must SAY it's commercial/mixed use; a building
# with residential markers needs a commercial marker to stay.
# A house passes only on a real USE statement, never on surroundings
# ("cerca a hoteles", amenity "Locales comerciales" = nearby, a home's "2 oficinas").
_CASA_COMMERCIAL = [r"\bcasa comercial", r"\busos? comercial", r"\buso mixto", r"alta mixtura",
                    r"uso de suelo comercial", r"ideal para (tu |su )?negocio", r"destinacion comercial",
                    r"se arrienda comercial", r"para empresa"]
# Buildings: commercial markers (singular "hotel" = the building is one, "hoteles" = nearby)
_BUILDING_COMMERCIAL = _CASA_COMMERCIAL + [r"\bhotel\b", r"licencia hotelera", r"edificio comercial",
                                           r"espacio comercial", r"\boficinas\b", r"\blocales\b"]
_RESIDENTIAL = ["apartamentos", "apartaestudios", "airbnb", "renta turistica",
                "conjunto de 2 casas", "vivienda", "unifamiliar", "residencial"]
_MULTI_LEVEL = ["niveles", "pisos", "segundo piso", "2 pisos", "3 pisos", "mezzanine", "mezanine", "rooftop", "azotea"]


def match_area(neighborhood: str, city: str, areas_cfg: dict,
               exclude: list | None = None) -> Optional[str]:
    """Map a listing to a target-area key by neighborhood/city tokens (first match wins).
    Barrios matching an exclude token never match."""
    hay = strip_accents(f"{neighborhood} {city}")
    if any(re.search(r"\b" + re.escape(strip_accents(t)) + r"\b", hay) for t in exclude or []):
        return None
    for key, cfg in areas_cfg.items():
        for tok in cfg.get("tokens", []):
            if re.search(r"\b" + re.escape(strip_accents(tok)) + r"\b", hay):
                return key
    return None


def detect_iva(listing: Listing) -> Optional[bool]:
    """True = listed price includes IVA, False = IVA on top, None = not stated."""
    if listing.iva_included is not None:
        return listing.iva_included
    hay = listing.haystack()
    if any(h in hay for h in _IVA_INCLUDED):
        return True
    if any(strip_accents(h) in hay for h in _IVA_EXTRA):
        return False
    return None


def price_all_in(listing: Listing, iva_rate: float) -> int:
    """Monthly cost: canon + IVA (unless included) + administración.
    Administración in propiedad horizontal is not IVA-able, so it's added flat."""
    if not listing.price_rent:
        return 0
    canon = listing.price_rent if listing.iva_included is True \
        else round(listing.price_rent * (1 + iva_rate))
    return canon + (listing.price_admin or 0)


def apply_hard_filter(listing: Listing, hard: dict) -> tuple[list, bool]:
    """Return (deal-breaker reasons, near_miss). Empty list == passes."""
    fails, near = [], False

    if listing.property_type not in hard["include_types"]:
        fails.append(f"type '{listing.property_type}' excluded")
    hay = listing.haystack()
    if listing.property_type == "casa" and not any(re.search(k, hay) for k in _CASA_COMMERCIAL):
        fails.append("residential house (no commercial use stated)")
    if (listing.property_type == "edificio"
            and not any(re.search(k, hay) for k in _BUILDING_COMMERCIAL)
            and any(k in hay for k in _RESIDENTIAL)):
        fails.append("residential building")
    if listing.deal not in hard["include_deals"]:
        fails.append(f"deal '{listing.deal}' excluded")

    city = strip_accents(listing.city)
    if city and not any(c in city for c in hard["allowed_cities"]):
        fails.append(f"city '{listing.city}' not in target")

    a, lo, hi = listing.area_m2, hard["min_area_m2"], hard["max_area_m2"]
    if a is not None:
        if a > 20000:
            fails.append(f"{int(a)} m² (bad data)")
        elif a > hi:
            fails.append(f"{int(a)} m² (> {hi})")
        elif a < lo * 0.9:
            fails.append(f"{int(a)} m² (< {lo})")
        elif a < lo:
            near = True

    if listing.deal == "arriendo" and listing.price_all_in > hard["max_all_in_cop"]:
        fails.append(f"{listing.price_all_in:,} COP all-in (> {hard['max_all_in_cop']:,})")
    cap = hard.get("max_sale_cop")
    if listing.deal == "venta" and cap and listing.price_sale > cap:
        fails.append(f"sale {listing.price_sale:,} COP (> {cap:,})")

    return fails, near


def _kw_hit(kw: str, hay: str) -> bool:
    """Whole-word keyword match. 're:...' = regex, trailing '*' = stem/prefix."""
    if kw.startswith("re:"):
        return bool(re.search(kw[3:], hay))
    k = strip_accents(kw)
    if k.endswith("*"):
        return bool(re.search(r"\b" + re.escape(k[:-1]), hay))
    return bool(re.search(r"\b" + re.escape(k) + r"\b", hay))


def score_listing(listing: Listing, cfg: dict) -> tuple[int, list]:
    hay = listing.haystack()
    bench = cfg["benchmark"]
    bench_m2 = round(bench["all_in_cop"] / bench["total_m2"])
    total, flags = 0, []
    for name, rule in cfg["scoring"].items():
        if name == "parking":
            hit = (listing.garages or 0) >= 4 or bool(
                re.search(r"\b([4-9]|\d{2,})\s*(parqueaderos|parqueadero|garajes|celdas)", hay))
        elif name == "value_vs_benchmark":
            # meaningful only if clearly cheaper: ≥25% under the benchmark's COP/m²
            hit = listing.deal == "arriendo" and 0 < listing.cop_per_m2 <= bench_m2 * 0.75
        else:
            hit = any(_kw_hit(k, hay) for k in rule.get("any", []))
        if hit:
            total += rule.get("points", 0)
            flags.append(rule.get("flag", name))
    return min(total, 100), flags


def process(listing: Listing, cfg: dict) -> Listing:
    hard = cfg["hard"]
    hay = listing.haystack()

    listing.iva_included = detect_iva(listing)
    listing.price_all_in = price_all_in(listing, hard.get("iva_rate", 0.19))
    if listing.area_m2:
        base = listing.price_all_in if listing.deal == "arriendo" else listing.price_sale
        listing.cop_per_m2 = round(base / listing.area_m2) if base else 0

    if listing.deal == "arriendo":
        if not listing.price_rent:
            listing.notes.append("price not listed")
        elif listing.iva_included is None:
            listing.notes.append("IVA not stated — assumed +19%")
        if not listing.admin_known:
            listing.notes.append("administración unknown")
    if listing.area_m2 is None:
        listing.notes.append("m² not listed")
    if listing.lat is not None and not (6.05 <= listing.lat <= 6.40 and -75.70 <= listing.lng <= -75.45):
        listing.lat = listing.lng = None          # agent geotag outside the metro area
        listing.notes.append("map pin was outside Medellín — not mapped")
    if "zona residencial" in hay and "zona comercial" not in hay:
        listing.notes.append("portal tags it Zona Residencial — zoning risk")
    if ("ascensor" not in hay and "elevador" not in hay
            and (listing.property_type in ("edificio", "casa") or any(k in hay for k in _MULTI_LEVEL))):
        listing.notes.append("multi-level, no elevator mentioned (Ley 361)")

    listing.hard_fails, near = apply_hard_filter(listing, hard)
    listing._near_miss = near
    if near:
        listing.notes.insert(0, f"near-miss: {int(listing.area_m2)} m² (< {hard['min_area_m2']})")
    listing.score, listing.score_flags = score_listing(listing, cfg)
    if any(n.startswith("portal tags it Zona Residencial") for n in listing.notes):
        listing.score = max(0, listing.score - 15)    # uso de suelo is a kill criterion

    fx = cfg.get("fx_cop_per_usd", 3900)
    listing._usd_month = round(listing.price_all_in / fx) if listing.price_all_in else 0
    listing._usd_sale = round(listing.price_sale / fx) if listing.price_sale else 0
    return listing
