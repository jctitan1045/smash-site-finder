# Architecture — Smash Site Finder

Forked from `medellin-apartment-finder` (same engine, commercial rules).

```
run.py
  scrapers/fincaraiz.py      __NEXT_DATA__ JSON; size filter in URL (/m2-desde-450)
  scrapers/metrocuadrado.py  RSC flight payload; no size filter → crawl all pages
  scrapers/ciencuadras.py    Angular state JSON; list m² pre-filter, detail enrich survivors
  scrapers/lobbie.py         walks NEW Lobbie ids daily (short code = base62 of a sequential id,
                             1hGm = 404660); cursor in data/lobbie_cursor.json, kept commercial
                             hits in data/lobbie_found.json (re-checked daily, delisted dropped)
  scrapers/manual.py         data/manual.yaml links (Lobbie parser + generic og: fallback)
  → pipeline.match_area      barrio tokens (config.areas), exclude_tokens drop Las Palmas
  → pipeline.process         IVA detect → all-in → hard filter (+near-miss) → score
  → store                    data/seen.json ledger (is_new), data/listings.json
  → dashboard/build.py       docs/index.html (self-contained, localStorage triage)
```

Key rules
- **All-in rent** = canon × 1.19 (unless "IVA incluido") + administración (admin not IVA-able).
- **Near-miss** = 90–100% of min m²; on the board but hidden behind a toggle.
- **Benchmark** (Cra 47B, from manual.yaml `benchmark: true`) bypasses filters, pinned first,
  and is the yardstick for COP/m² (59.5M / 740 m² = 80,405).
- Manual entries always show, even if they fail filters.

Grok companion: `GROK_TASK.md`. A scheduled Grok task runs the same searches plus the
open web/X (Lobbie pages, brokers, ex-restaurants) and messages Jordan daily.
Links it finds go into data/manual.yaml.
