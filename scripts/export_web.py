"""Write every file the dashboard reads into web/data. See docs/DATA_CONTRACT.md."""
import json

import geopandas as gpd
import numpy as np
import pandas as pd

from sajag import alerts as A
from sajag import dataset, frozen
from sajag import river_model as R
from sajag.config import ARTIFACTS, PROCESSED, ROOT, WEB
from sajag.jsonsafe import dumps

OUT = WEB / "data"
REASONS = {
    "river_now": {"en": "River already high", "hi": "नदी पहले से ऊँची"},
    "upstream_rain": {"en": "Heavy rain upstream", "hi": "ऊपरी इलाके में भारी बारिश"},
    "local_rain": {"en": "Heavy rain in the district", "hi": "जिले में भारी बारिश"},
    "soil": {"en": "Ground already wet", "hi": "जमीन पहले से गीली"},
    "statewide": {"en": "Rivers high across Bihar", "hi": "पूरे बिहार में नदियाँ ऊँची"},
    "rain_forecast": {"en": "Extreme rain forecast", "hi": "भारी बारिश का पूर्वानुमान"},
}
STORIES = [
    {"id": "sep2024", "title": "Kosi and Nepal rivers, September 2024", "year": 2024,
     "start": "2024-09-16", "end": "2024-10-04", "focus": "darbhanga", "held_out": True},
    {"id": "sep2026", "title": "Ganga, September 2026", "year": 2026,
     "start": "2026-08-24", "end": "2026-09-14", "focus": "patna", "held_out": True},
    {"id": "aug2017", "title": "North Bihar, August 2017", "year": 2017,
     "start": "2017-08-03", "end": "2017-08-20", "focus": "araria", "held_out": False},
    {"id": "jul2019", "title": "Bagmati and Kamla, July 2019", "year": 2019,
     "start": "2019-07-04", "end": "2019-07-22", "focus": "sitamarhi", "held_out": False},
]


def write(name: str, payload) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(payload, separators=(",", ":")))


def load(name: str):
    return json.loads((ARTIFACTS / name).read_text())


def top_reasons(row: pd.Series, groups: list[str]) -> list[str]:
    ranked = row[groups].astype(float).sort_values(ascending=False)
    return [g for g, v in ranked.items() if v > 0][:3]


def export_year(year, hind, flows, peak, sites, p99, keys, records, held_out, thresholds_level):
    groups = [g for g in REASONS if g in hind.columns]
    block = hind[hind.index.get_level_values("date").year == year]
    dates = sorted(block.index.get_level_values("date").unique())
    pivot = {k: block[f"risk{k}"].unstack("district").reindex(columns=keys) for k in R.LEADS}
    level = thresholds_level(block).unstack("district").reindex(columns=keys).fillna(0).astype(int)

    reasons = {}
    extra = block["rain_level"].unstack("district") if "rain_level" in block else None
    for i, d in enumerate(dates):
        for j, key in enumerate(keys):
            if level.iat[i, j] >= 1:
                codes = top_reasons(block.loc[(d, key)], groups)
                if extra is not None and extra.at[d, key] >= 1:
                    codes = ["rain_forecast", *codes][:3]
                reasons[f"{i}:{j}"] = codes

    q = flows.reindex(dates)[sites]
    pk = peak.reindex(dates)[sites]
    forecast = {}
    if extra is not None:
        rain = block["fc5"].unstack("district").reindex(columns=keys)
        observed = block["obs_level"].unstack("district").reindex(columns=keys)
        forecast = {
            "rain_mm": np.rint(rain.fillna(0).values).astype(int).tolist(),
            "raised": (level.values > observed.values).astype(int).tolist(),
        }
    write(f"hindcast/{year}.json", {
        "year": int(year), "held_out": held_out,
        "rain_forecast_used": extra is not None,
        **forecast,
        "dates": [str(d.date()) for d in dates],
        "districts": keys,
        "risk": {
            str(k): np.rint(100 * pivot[k].fillna(0).values).astype(int).tolist() for k in R.LEADS
        },
        "level": level.values.tolist(),
        "reasons": reasons,
        "statewide": [round(float(v), 3) for v in (level >= 2).mean(axis=1)],
        "sites": sites,
        "q": np.round(q.values, 1).tolist(),
        "peak7": np.round((pk * p99).values, 1).tolist(),
        "records": records.get(int(year), []),
    })


def main() -> None:
    world = dataset.load_world()
    model = frozen.load()
    keys = sorted(world.districts["key"])
    site_ids = world.sites["site_id"].tolist()
    ref = world.ref
    p95 = {k: float(np.quantile(v, 0.95)) for k, v in ref.items()}
    p99 = pd.Series({k: float(np.quantile(v, 0.99)) for k, v in ref.items()})

    gdf = world.districts[["key", "name", "geometry"]].copy()
    gdf["name_hi"] = gdf["key"].map(A.DISTRICT_HI)
    gdf["geometry"] = gdf.geometry.simplify(0.002)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "districts.geojson").write_text(gdf.to_json(drop_id=True, ensure_ascii=False))
    rivers = gpd.read_file(PROCESSED / "rivers.geojson")
    (OUT / "rivers.geojson").write_text(rivers.to_json(drop_id=True))

    write("sites.json", [
        {"id": s.site_id, "river": s.river, "site": s.site, "lat": round(s.lat, 3),
         "lon": round(s.lon, 3), "p95": round(p95[s.site_id], 1), "p99": round(p99[s.site_id], 1)}
        for s in world.sites.itertuples()
    ])

    # What really happened, by year.
    records: dict[int, list] = {}
    clean = pd.read_parquet(PROCESSED / "events_clean.parquet")
    for r in clean.itertuples():
        records.setdefault(int(r.start.year), []).append({
            "start": str(r.start.date()), "end": str(r.end.date()), "district": r.district,
            "label": "Recorded flood", "source": "inventory", "url": "",
        })
    blind_events = pd.read_csv(ROOT / "data" / "reference" / "blind_test_events.csv")
    for r in blind_events.itertuples():
        records.setdefault(int(r.first_report[:4]), []).append({
            "start": r.first_report, "end": r.first_report, "district": r.district,
            "label": r.event, "source": "press", "url": r.source,
        })

    labelled = pd.read_parquet(PROCESSED / "hindcast_labelled.parquet")
    blind = pd.read_parquet(PROCESSED / "hindcast_blind.parquet")
    flows = world.q
    site_wide = {}
    for name in ("river_labelled.parquet", "river_blind.parquet"):
        site_wide[name] = np.exp(pd.read_parquet(PROCESSED / name)["pk7"].unstack("site"))
    peak = pd.concat(site_wide.values()).sort_index()

    def model_level(block):
        return model.level(block["score7"])

    def combined_level(block):
        return block["level"]

    for year in sorted(set(labelled.index.get_level_values("date").year)):
        export_year(year, labelled, flows, peak, site_ids, p99[site_ids], keys, records,
                    False, model_level)
    for year in sorted(set(blind.index.get_level_values("date").year)):
        export_year(year, blind, flows, peak, site_ids, p99[site_ids], keys, records,
                    True, combined_level)

    d = pd.read_parquet(PROCESSED / "drought.parquet")
    d = d[d.index.get_level_values("month_start").year >= 1997]
    spi = d["spi3"].unstack("district").reindex(columns=keys)
    chance = d["chance"].unstack("district").reindex(columns=keys)
    declared = pd.read_csv(ROOT / "data" / "reference" / "declared_droughts.csv")
    write("drought.json", {
        "months": [m.strftime("%Y-%m") for m in spi.index],
        "districts": keys,
        "spi3": np.round(spi.values, 2).tolist(),
        "chance": np.rint(100 * chance.fillna(0).values).astype(int).tolist(),
        "state_share": [round(float(v), 3) for v in (spi <= -1).mean(axis=1)],
        "declared": [
            {"year": int(r.year), "scope": r.scope, "url": r.source}
            for r in declared.itertuples()
        ],
    })

    villages = pd.read_parquet(PROCESSED / "villages.parquet")
    for key, g in villages.groupby("key"):
        g = g.sort_values("exposure", ascending=False)
        rows = [
            [r.name, round(r.lat, 4), round(r.lon, 4), int(r.exposure), int(r.cls)]
            for r in g.itertuples()
        ]
        write(f"villages/{key}.json", {"district": key, "villages": rows})

    write("alerts.json", {
        "languages": A.LANGUAGES,
        "templates": A.TEMPLATES,
        "sms_limit": A.SMS_LIMIT,
        "district_hi": A.DISTRICT_HI,
        "audio": {
            lang["id"]: {str(i): f"audio/{lang['id']}_{i}.m4a" for i in (1, 2, 3)}
            for lang in A.LANGUAGES
        },
        "note": (
            "Maithili and Bhojpuri text was drafted by an AI tool and has not been reviewed by a "
            "native speaker. Their audio uses a Hindi voice as a stand-in."
        ),
    })

    write("meta.json", {
        "issued": str(pd.Timestamp.now().date()),
        "levels": [
            {"id": 0, "en": "Normal", "hi": "सामान्य"}, {"id": 1, "en": "Watch", "hi": "सतर्क"},
            {"id": 2, "en": "Warning", "hi": "चेतावनी"}, {"id": 3, "en": "Severe", "hi": "गंभीर"},
        ],
        "reasons": REASONS,
        "years": sorted({*labelled.index.get_level_values("date").year,
                         *blind.index.get_level_values("date").year}),
        "held_out_years": sorted(set(blind.index.get_level_values("date").year)),
        "stories": json.loads((ROOT / "data" / "reference" / "stories.json").read_text())
        if (ROOT / "data" / "reference" / "stories.json").exists() else STORIES,
    })

    cv = load("metrics_cv.json")
    write("metrics.json", {
        "headline": cv["headline"],
        "river": cv["river"],
        "river_held_out": load("metrics_blind.json")["river"],
        "impact": cv["impact"],
        "budget": cv["budget"],
        "reliability": cv["reliability"],
        "ablation": cv["ablation"],
        "version1": {
            "cv": load("metrics_cv_v1.json")["headline"],
            "blind": {k: load("metrics_blind.json")[k] for k in ("events", "total", "alert_rate")},
        },
        "version2": load("metrics_posthoc.json"),
        "drought": load("metrics_drought.json"),
        "exposure": load("metrics_exposure.json"),
        "data_story": json.loads((ROOT / "data" / "reference" / "evidence_text.json").read_text())[
            "data_story"
        ],
        "limits": json.loads((ROOT / "data" / "reference" / "evidence_text.json").read_text())[
            "limits"
        ],
    })
    sizes = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print("web/data", round(sizes / 1e6, 1), "MB", len(list(OUT.rglob("*.json"))), "json files")


if __name__ == "__main__":
    main()
