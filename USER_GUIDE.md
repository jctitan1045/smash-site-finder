# User guide — Smash Site Finder

**Run locally:** `python run.py` (full, ~10 min) or `python run.py --dry` (1 page per search).
Uses PyYAML only.

**Preview:** launch.json entry `smash-site-finder` (port 8941).

**Add a link someone sent you** (Lobbie, agent site): append to `data/manual.yaml`:
```yaml
- url: https://app.lobbieapp.com/inmueble/XXXX
  label: "Optional name"
  note: "Optional free text"
  set: {area_m2: 600}      # override anything the parser missed
```

**Tune:** everything is in `config.yaml`: size range, rent cap, IVA rate, areas, scoring
weights, search URLs.

**Hide listings for good server-side:** "Hidden" export → save as `data/rejected.json`.

**Grok daily scout:** paste `GROK_TASK.md` (below the line) into Grok → Tasks, daily 7:00.

**Lobbie:** found automatically. The daily run walks new listing numbers since the last run and
keeps only locales/bodegas/edificios in Medellín/Envigado. Re-backfill from an id:
`python -m scrapers.lobbie 401000`. Pasting a Lobbie link in manual.yaml still works.
