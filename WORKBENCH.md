# Workbench log

## 2026-10-21 — initial build
- Forked the apartment-finder engine. Probed commercial URLs on all 3 portals (all parse).
- Found: Lobbie link Jordan sent = Cra 47B itself. Its 59.5M "canon" was 50M + 19% IVA.
  So the all-in cap applies IVA by default.
- Jordan's choices: benchmark vs Cra 47B · 500–1,200 m² · ≤45M all-in · Poblado, Manila/
  Provenza, Ciudad del Río, Envigado (no Laureles) · include buildings for sale.
- Fix carried over: http.py now retries IncompleteRead/RemoteDisconnected (the apartment
  finder has the same gap).
- Wrote GROK_TASK.md, a daily Grok scout prompt.
- First full run: 705 in-area → 259 matches + 82 near-misses (Poblado 141, Envigado 104,
  Manila/Provenza 14; 15 for sale). Ciudad del Río listings land under Poblado (barrio = "El Poblado").
- Scoring tuned: whole-word keyword matching (`*` stem, `re:` regex); dropped noisy portal
  amenity tags ("Restaurantes" = nearby, "Colegios", "Jardín", "spa"⊂"espacio",
  "parque"⊂"parqueaderos"). Portal "Zona Residencial" tag → warning + −15.
  Value flag = ≥25% cheaper/m² than Cra 47B (still 251/259: Cra 47B is pricey per m²).
- Out-of-metro geotags (one in Bogotá) are nulled. Added `run.py --rescore` (no network).
- Jordan: COMMERCIAL ONLY, never residential. Casas now pass only on an explicit use
  statement (casa comercial / uso comercial / uso mixto / alta mixtura / para empresa); surroundings
  ("cerca a hoteles", "Locales comerciales" amenity, "2 oficinas") don't count. Residential edificios
  (apartments/Airbnb) fail unless a commercial marker is present. 259 → 140 matches.
