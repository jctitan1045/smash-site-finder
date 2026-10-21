"""Common listing schema shared across all portal scrapers.

Every scraper normalizes its portal-specific data into a Listing so the
filter / score / dedup / dashboard layers never see portal quirks.
Forked from medellin-apartment-finder; reshaped for commercial space
(no bedrooms, rent vs sale, IVA on commercial rent).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Optional


def strip_accents(text: str) -> str:
    """Lowercase + remove accents so 'Ascensor' matches token 'ascensor'."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


@dataclass
class Listing:
    source: str                       # fincaraiz | metrocuadrado | ciencuadras | manual
    source_id: str                    # portal's own id
    url: str
    title: str = ""
    deal: str = "arriendo"            # arriendo | venta
    area_key: str = ""                # our target-area key (poblado, manila_provenza, ...)
    neighborhood: str = ""
    city: str = ""
    address: str = ""

    price_rent: int = 0               # COP/month, canon as listed (usually before IVA)
    price_admin: int = 0              # COP/month, administración, 0 if unknown/none
    admin_known: bool = False
    iva_included: Optional[bool] = None   # True = listed price already has IVA
    price_all_in: int = 0             # COP/month: canon + IVA (if not included) + admin
    price_sale: int = 0               # COP, sale price (venta only)
    cop_per_m2: int = 0               # all-in monthly rent / m² (or sale / m² for venta)

    area_m2: Optional[float] = None
    stratum: Optional[int] = None
    floor: Optional[int] = None
    garages: Optional[int] = None
    bathrooms: Optional[int] = None

    property_type: str = "local"      # local | bodega | casa | edificio | oficina
    amenities: list = field(default_factory=list)
    description: str = ""
    lat: Optional[float] = None
    lng: Optional[float] = None
    image: str = ""
    images: list = field(default_factory=list)

    contact_name: str = ""
    contact_phone: str = ""
    contact_whatsapp: str = ""
    contact_email: str = ""
    created_at: str = ""

    benchmark: bool = False           # pinned reference site (Cra 47B), bypasses filters
    label: str = ""                   # human name for manual/benchmark entries
    user_note: str = ""               # free note from data/manual.yaml

    # populated downstream
    score: int = 0
    score_flags: list = field(default_factory=list)
    hard_fails: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    is_new: bool = False

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.source_id}"

    def haystack(self) -> str:
        """All free text a scorer/detector should scan, accent-stripped."""
        parts = [self.title, self.description, self.neighborhood,
                 " ".join(self.amenities)]
        return strip_accents(" ".join(p for p in parts if p))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        d["usd_month"] = getattr(self, "_usd_month", 0)
        d["usd_sale"] = getattr(self, "_usd_sale", 0)
        d["near_miss"] = getattr(self, "_near_miss", False)
        return d


def wa_number(raw) -> str:
    """Normalize a Colombian phone to WhatsApp digits (57 + 10-digit mobile).
    Returns '' for landlines/unusable values — only mobiles (start 3) get a link."""
    if not raw:
        return ""
    d = re.sub(r"\D", "", str(raw))
    if d.startswith("57"):
        d = d[2:]
    return "57" + d if len(d) == 10 and d.startswith("3") else ""


def clean_phone(raw) -> str:
    """Human-readable call number: digits only (keeps landlines like 604…)."""
    if not raw:
        return ""
    d = re.sub(r"\D", "", str(raw))
    if d.startswith("57") and len(d) > 10:
        d = d[2:]
    return d


def normalize_type(name: str) -> str:
    """Map a portal's property-type label to our canonical commercial set."""
    n = strip_accents(name or "")
    if "edificio" in n:
        return "edificio"
    if "bodega" in n or "nave" in n or "galpon" in n:
        return "bodega"
    if "local" in n:
        return "local"
    if "oficina" in n or "consultorio" in n:
        return "oficina"
    if "casa" in n or "casalote" in n:
        return "casa"
    if "lote" in n:
        return "lote"
    if "apartamento" in n or "apartaestudio" in n:
        return "apartamento"
    return n or "local"


def parse_int(value) -> Optional[int]:
    """Integer from money/count strings where '.' is a thousands separator.
    '5.300.000' -> 5300000, '104 m2' -> 104. Wrong for decimals — use parse_area."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"\d[\d.\s]*", str(value))
    if not m:
        return None
    digits = re.sub(r"[.\s]", "", m.group())
    return int(digits) if digits else None


def parse_area(value) -> Optional[float]:
    """Square-metre value where '.' is a DECIMAL point: '122.0'->122, '104 m2'->104.
    Handles ',' decimals ('122,5'->122.5) and thousands-dot areas ('1.200'->1200)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value)
    m = re.search(r"\d[\d.,]*", s)
    if not m:
        return None
    tok = m.group()
    if "," in tok:
        tok = tok.replace(".", "").replace(",", ".")
    elif tok.count(".") > 1:
        head, _, tail = tok.rpartition(".")
        tok = head.replace(".", "") + "." + tail
    elif re.fullmatch(r"\d{1,2}\.\d{3}", tok):   # '1.200' = 1200 m², not 1.2
        tok = tok.replace(".", "")
    try:
        return float(tok)
    except ValueError:
        return None
