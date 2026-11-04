# Data contract between the Python pipeline and the web dashboard

The dashboard is static. Python writes these files into `web/data/`, and the page only reads
them. All dates are `YYYY-MM-DD`. District keys are lowercase with underscores, such as
`west_champaran`. Risk values are whole percentages from 0 to 100.

Flood levels: `0` Normal, `1` Watch, `2` Warning, `3` Severe.

Reason codes: `river_now`, `river_forecast`, `upstream_rain`, `local_rain`, `soil`, `statewide`,
`season`.

## `meta.json`

```json
{
  "issued": "2026-11-05",
  "season_active": false,
  "levels": [{"id": 0, "en": "Normal", "hi": "सामान्य"}, {"id": 1, "en": "Watch", "hi": "सतर्क"},
             {"id": 2, "en": "Warning", "hi": "चेतावनी"}, {"id": 3, "en": "Severe", "hi": "गंभीर"}],
  "reasons": {"river_now": {"en": "River already high", "hi": "नदी पहले से ऊँची"}},
  "years": [2006, 2007],
  "blind_years": [2024, 2025, 2026],
  "stories": [{
    "id": "sep2026", "title": "Ganga, September 2026", "year": 2026,
    "start": "2026-08-22", "end": "2026-09-14", "focus": "patna",
    "caption": "One or two plain sentences about what happened.",
    "blind": true
  }]
}
```

## `districts.geojson`

FeatureCollection of 38 polygons with properties `key`, `name`, `name_hi`.

## `rivers.geojson`

FeatureCollection of LineStrings with property `name`.

## `sites.json`

```json
[{"id": "kosi_birpur", "river": "Kosi", "site": "Birpur", "lat": 26.52, "lon": 86.92,
  "p95": 3100.0, "p99": 5200.0}]
```

## `hindcast/<year>.json`

One file per year from 2006, covering 1 June to 31 October. Index order is `dates[i]`,
`districts[j]`, `sites[k]`.

```json
{
  "year": 2024,
  "blind": true,
  "dates": ["2024-06-01"],
  "districts": ["araria"],
  "risk": {"1": [[3]], "3": [[4]], "5": [[5]], "7": [[7]]},
  "level": [[0]],
  "reasons": {"120:7": ["river_forecast", "upstream_rain", "soil"]},
  "statewide": [0.08],
  "sites": ["kosi_birpur"],
  "q": [[1420.5]],
  "peak7": [[1880.0]],
  "records": [{"start": "2024-09-28", "end": "2024-09-28", "district": "supaul",
               "label": "2024 Nepal rivers flood", "source": "press", "url": "https://..."}]
}
```

- `reasons` is keyed by `"<date index>:<district index>"`, and only present when level is 1 or more.
- `statewide[i]` is the share of districts at Warning or above on that date.
- `peak7[i][k]` is the forecast peak flow at the site over the next 7 days, in m3/s.
- `records` holds floods that really happened: `source` is `inventory` for the IIT Delhi and IMD
  record, or `press` for the blind test list. In every `blind` year the model never saw them.

## `live.json`

```json
{
  "issued": "2026-11-05",
  "season_active": false,
  "note": "Plain sentence on why the flood model is resting, if it is.",
  "districts": {"patna": {"risk": {"1": 1, "3": 1, "5": 2, "7": 2}, "level": 0, "reasons": []}},
  "sites": [{
    "id": "kosi_birpur", "q": 1420.5, "pct": 62.0, "status": "normal",
    "forecast": {"dates": ["2026-11-05"], "q": [1400], "p25": [1300], "p75": [1500],
                 "min": [1200], "max": [1700]}
  }]
}
```

Site `status` is one of `normal`, `high` (above p95), `extreme` (above p99).

## `drought.json`

Monthly, 1997 onward. Index order is `months[i]`, `districts[j]`.

```json
{
  "months": ["2022-07"],
  "districts": ["araria"],
  "spi3": [[-1.42]],
  "chance": [[38]],
  "state_share": [0.42],
  "declared": [{"year": 2022, "scope": "96 blocks in 11 districts", "url": "https://..."}]
}
```

- `spi3` is the 3-month Standardised Precipitation Index. At or below -1 means drought.
- `chance[i][j]` is the percentage chance of drought one month after `months[i]`.
- `state_share[i]` is the share of districts with `spi3` at or below -1.

## `villages/<district>.json`

```json
{"district": "darbhanga", "villages": [["Bhubhaul", 26.03, 86.21, 91, 2]]}
```

Row order: name, lat, lon, exposure from 0 to 100, class (`0` low, `1` medium, `2` high).

## `alerts.json`

```json
{
  "languages": [{"id": "hi", "name": "हिन्दी"}, {"id": "mai", "name": "मैथिली"},
                {"id": "bho", "name": "भोजपुरी"}, {"id": "en", "name": "English"}],
  "templates": {"hi": {"1": {"sms": "...{district}...", "voice": "..."}}},
  "audio": {"hi": {"1": "audio/hi_1.m4a"}}
}
```

Placeholders: `{district}`, `{river}`, `{days}`. Levels `1`, `2`, `3` have templates. A Devanagari
SMS must stay within 70 characters so that it fits one message.

## `metrics.json`

Everything shown on the Evidence page. The page must render whatever is present here, and never
hard-code a number.

```json
{
  "headline": {"caught_3d": 0.64, "caught_3d_ci": [0.5, 0.75], "budget": 0.05,
               "events": 24, "onsets": 130},
  "river": [{"lead": 3, "ap_new_model": 0.47, "ap_new_persistence": 0.17, "nse_model": 0.96,
             "nse_persistence": 0.93, "csi_model": 0.66, "csi_persistence": 0.57}],
  "impact": [{"lead": 7, "model": "Sajag", "pr_auc": 0.15}],
  "budget": [{"budget": 0.05, "method": "Sajag", "caught_1d": 0.66, "caught_3d": 0.64,
              "caught_5d": 0.45, "precision": 0.16}],
  "reliability": [{"predicted": 0.1, "observed": 0.08, "n": 1200}],
  "ablation": [{"variant": "No river stage", "pr_auc": 0.12}],
  "blind": {"events": [{"event": "2024 Nepal rivers flood", "first_report": "2024-09-28",
                        "districts": 14, "warned_1d": 12, "warned_3d": 9, "median_lead": 4}],
            "total": {"district_events": 46, "warned_3d": 30}},
  "drought": {"auc": 0.9, "rows": [{"year": 2022, "declared": true, "share": 0.6}]},
  "exposure": {"high_flooded": 0.3, "low_flooded": 0.05, "ratio": 6.0, "villages": 800},
  "data_story": ["Plain sentences on the data problems found and how they were fixed."],
  "limits": ["Plain sentences on what the system cannot do."]
}
```
