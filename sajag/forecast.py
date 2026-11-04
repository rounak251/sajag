"""Today's forecast, from the frozen models. GitHub Actions runs this on a schedule.

Each run also writes forecast_log/<date>.json. Those files are committed as they are made, so
next monsoon can be scored against a record that could not have been edited afterwards.
"""
import json
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from sajag import features as F
from sajag import frozen, rain_rule
from sajag import river_model as R
from sajag.config import ARTIFACTS, MONSOON_MONTHS, PROCESSED, ROOT, UPSTREAM, WEB
from sajag.jsonsafe import dumps
from sajag.sources import glofas, nwp, power

HISTORY_DAYS = 50
RECENT_RAIN_DAYS = 7


def _points(districts: pd.DataFrame) -> dict[str, tuple[float, float]]:
    out = {f"district_{d.key}": (round(d.lat, 3), round(d.lon, 3)) for d in districts.itertuples()}
    out.update({f"upstream_{u[0]}": (u[2], u[3]) for u in UPSTREAM})
    return out


def recent_rain(points: dict) -> pd.DataFrame:
    """Rain for the last few days, which NASA POWER has not published yet."""
    names = list(points)
    r = requests.get(nwp.LIVE, params={
        "latitude": ",".join(str(points[n][0]) for n in names),
        "longitude": ",".join(str(points[n][1]) for n in names),
        "daily": "precipitation_sum", "past_days": RECENT_RAIN_DAYS, "forecast_days": 1,
        "timezone": "Asia/Kolkata",
    }, timeout=120)
    r.raise_for_status()
    data = r.json()
    data = data if isinstance(data, list) else [data]
    cols = {
        n: pd.Series(d["daily"]["precipitation_sum"], index=pd.to_datetime(d["daily"]["time"]))
        for n, d in zip(names, data)
    }
    return pd.DataFrame(cols)


def forecast_rain(points: dict) -> pd.Series:
    """Rain forecast for the next five days per point: the mean of the two models."""
    names = list(points)
    runs = []
    for model in nwp.MODELS:
        r = requests.get(nwp.LIVE, params={
            "latitude": ",".join(str(points[n][0]) for n in names),
            "longitude": ",".join(str(points[n][1]) for n in names),
            "daily": "precipitation_sum", "forecast_days": rain_rule.WINDOW_DAYS + 1,
            "models": model, "timezone": "Asia/Kolkata",
        }, timeout=120)
        r.raise_for_status()
        data = r.json()
        data = data if isinstance(data, list) else [data]
        runs.append(pd.Series({
            n: float(np.nansum(np.array(d["daily"]["precipitation_sum"][1:], dtype=float)))
            for n, d in zip(names, data)
        }))
        time.sleep(1)
    return pd.concat(runs, axis=1).mean(axis=1)


def gather(today: date, districts: pd.DataFrame, sites: pd.DataFrame) -> dict:
    points = _points(districts)
    start = str(today - timedelta(days=HISTORY_DAYS))
    end = str(today - timedelta(days=1))
    series = {}
    for name, (lat, lon) in points.items():
        series[name] = power.fetch_point(lat, lon, start, end)
    index = pd.date_range(start, today)
    fill = recent_rain(points)

    def column(col: str, prefix: str) -> pd.DataFrame:
        cols = {
            n.removeprefix(prefix): s[col].reindex(index)
            for n, s in series.items() if n.startswith(prefix)
        }
        return pd.DataFrame(cols)

    rain = column("rain", "district_")
    upstream = column("rain", "upstream_")
    for table, prefix in ((rain, "district_"), (upstream, "upstream_")):
        for col in table.columns:
            table[col] = table[col].fillna(fill[prefix + col].reindex(index))
    soil_top = column("soil_top", "district_").ffill()
    soil_root = column("soil_root", "district_").ffill()

    flows, outlook = {}, {}
    for s in sites.itertuples():
        history = glofas.history(s.lat, s.lon, start, str(today))
        flows[s.site_id] = history.reindex(index).interpolate(limit=3)
        outlook[s.site_id] = glofas.forecast(s.lat, s.lon)
        time.sleep(0.3)
    return {
        "rain": rain.fillna(0), "upstream": upstream.fillna(0), "soil_top": soil_top,
        "soil_root": soil_root, "q": pd.DataFrame(flows), "outlook": outlook,
        "fc5": forecast_rain(points),
    }


def site_summary(sites, q, outlook, ref, peak7, today) -> list[dict]:
    rows = []
    for s in sites.itertuples():
        now = q[s.site_id].dropna()
        value = float(now.iloc[-1])
        pct = float(F.percentile_of(pd.Series([value]), ref[s.site_id]).iloc[0])
        p95, p99 = float(np.quantile(ref[s.site_id], 0.95)), float(np.quantile(ref[s.site_id], 0.99))
        ahead = outlook[s.site_id]
        ahead = ahead[ahead.index >= pd.Timestamp(today)]
        rows.append({
            "id": s.site_id, "q": round(value, 1), "pct": round(pct * 100, 1),
            "status": "extreme" if value >= p99 else "high" if value >= p95 else "normal",
            "peak7": round(float(peak7.get(s.site_id, np.nan)), 1),
            "forecast": {
                "dates": [str(d.date()) for d in ahead.index],
                "q": ahead["river_discharge"].round(1).tolist(),
                "p25": ahead["river_discharge_p25"].round(1).tolist(),
                "p75": ahead["river_discharge_p75"].round(1).tolist(),
                "min": ahead["river_discharge_min"].round(1).tolist(),
                "max": ahead["river_discharge_max"].round(1).tolist(),
            },
        })
    return rows


def run(today: date | None = None) -> dict:
    today = today or date.today()
    model = frozen.load()
    ref = {k: np.array(v) for k, v in model.reference["ref"].items()}
    districts = pd.read_csv(PROCESSED / "district_points.csv")
    sites = pd.read_csv(PROCESSED / "sites.csv")
    order = list(ref)
    sites = sites.set_index("site_id").reindex(order).reset_index()
    data = gather(today, districts, sites)

    table = F.build(
        data["rain"], data["soil_top"], data["soil_root"], data["upstream"], data["q"],
        districts, sites, ref,
    )
    latest = table.index.get_level_values("date").max()
    now = table.xs(latest, level="date", drop_level=False)

    site_table = R.site_table(
        data["q"], ref, data["upstream"], data["rain"], data["soil_root"], sites, districts,
    )
    site_now = site_table.xs(latest, level="date", drop_level=False)
    river = model.river_forecast(site_now)
    p99 = {k: float(np.quantile(v, 0.99)) for k, v in ref.items()}
    peak7 = {
        site: p99[site] * float(np.exp(river.xs(site, level="site")["pk7"].iloc[0]))
        for site in order
    }

    scores = {lead: model.score(now, lead) for lead in R.LEADS}
    level = model.level(scores[7])

    fc = data["fc5"].to_frame(pd.Timestamp(latest)).T
    fc.index.name = "date"
    stat = rain_rule.district_statistic(fc, model.reference["near"], sites)
    limits = json.loads((ARTIFACTS / "rain_thresholds.json").read_text())
    level = pd.concat([level, rain_rule.level(stat, limits).reindex(level.index)], axis=1).max(axis=1)

    season = today.month in MONSOON_MONTHS
    reasons = model.reasons(now)
    out_districts = {}
    for key in districts["key"]:
        i = (latest, key)
        ranked = reasons.loc[i].sort_values(ascending=False)
        out_districts[key] = {
            "risk": {
                str(k): int(round(100 * model.calibrate(scores[k], k).loc[i])) for k in R.LEADS
            } if season else {str(k): 0 for k in R.LEADS},
            "level": int(level.loc[i]) if season else 0,
            "reasons": [g for g, v in ranked.items() if v > 0][:3] if season else [],
            "rain_forecast_mm": round(float(stat.loc[i]), 1),
        }
    out = {
        "issued": str(today),
        "season_active": season,
        "note": "" if season else (
            "The flood model runs from 1 June to 31 October, the months it was trained on. "
            "River flows below are still live."
        ),
        "districts": out_districts,
        "sites": site_summary(sites, data["q"], data["outlook"], ref, peak7, today),
    }
    (WEB / "data").mkdir(parents=True, exist_ok=True)
    (WEB / "data" / "live.json").write_text(dumps(out))
    log = ROOT / "forecast_log"
    log.mkdir(exist_ok=True)
    summary = {k: {"level": v["level"], "risk": v["risk"]} for k, v in out_districts.items()}
    (log / f"{today}.json").write_text(dumps(
        {"issued": str(today), "season_active": season, "districts": summary}, indent=0,
    ))
    return out


if __name__ == "__main__":
    result = run()
    print(result["issued"], "season", result["season_active"], len(result["sites"]), "sites")
