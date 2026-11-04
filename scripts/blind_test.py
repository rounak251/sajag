"""Score the frozen models on 2024 onward, against a list locked before any prediction existed.

The list is data/reference/blind_test_events.csv. Its commit precedes the first run of this
script, so the events could not have been chosen to suit the model. Alert thresholds come from
2006-2023 only. A first-report date is when the press first named a district, which can be
later than the water arrived, so an alert before it is not always an alert before the flood.
"""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from sajag import dataset, frozen
from sajag import river_model as R
from sajag.config import ARTIFACTS, PROCESSED, ROOT

WINDOW = 7
FIRST_BLIND_YEAR = 2024


def alert_days(flag: pd.Series, district: str, report: pd.Timestamp) -> pd.Series:
    """Alert flags for one district over the week before its first report."""
    days = pd.date_range(report - pd.Timedelta(days=WINDOW), report - pd.Timedelta(days=1))
    return flag.xs(district, level="district").reindex(days).fillna(False).astype(bool)


def score_events(events: pd.DataFrame, rules: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for e in events.itertuples():
        report = pd.Timestamp(e.first_report)
        row = {"event": e.event, "first_report": e.first_report, "district": e.district}
        for name, flag in rules.items():
            hits = alert_days(flag, e.district, report)
            early = hits[hits].index
            lead = (report - early[0]).days if len(early) else 0
            row[f"{name}_1d"] = bool(lead >= 1)
            row[f"{name}_3d"] = bool(lead >= 3)
            row[f"{name}_lead"] = lead
        rows.append(row)
    return pd.DataFrame(rows)


def river_skill(table: pd.DataFrame, pred: pd.DataFrame) -> list[dict]:
    rows = []
    for lead in R.LEADS:
        keep = table[f"peak{lead}"].notna()
        obs, pers = table.loc[keep, f"peak{lead}"], table.loc[keep, "q_over"]
        new = pers < 0
        hit = (obs >= 0).astype(int)
        sim = pred.loc[keep, f"pk{lead}"]
        rows.append({
            "lead": lead,
            "ap_new_model": float(average_precision_score(hit[new], pred.loc[keep, f"ex{lead}"][new])),
            "ap_new_persistence": float(average_precision_score(hit[new], pers[new])),
            "nse_model": float(1 - ((sim - obs) ** 2).sum() / ((obs - obs.mean()) ** 2).sum()),
            "nse_persistence": float(1 - ((pers - obs) ** 2).sum() / ((obs - obs.mean()) ** 2).sum()),
            "new_events": int(hit[new].sum()),
        })
    return rows


def main() -> None:
    world = dataset.load_world()
    model = frozen.load()
    ref = model.reference

    table = world.district_table
    blind = table[dataset.years_of(table) >= FIRST_BLIND_YEAR]
    print("blind rows", blind.shape, blind.index.get_level_values("date").max(), flush=True)

    scores = {lead: model.score(blind, lead) for lead in R.LEADS}
    level = model.level(scores[7])
    rules = {
        "sajag": level >= 2,
        "sajag_watch": level >= 1,
        "river": blind["q_log_p99"].fillna(-9) >= ref["baseline_thresholds"]["river"],
        "rain": blind["r3"] >= ref["baseline_thresholds"]["rain"],
    }

    events = pd.read_csv(ROOT / "data" / "reference" / "blind_test_events.csv")
    scored = score_events(events, rules)

    per_event = []
    for name, g in scored.groupby("event", sort=False):
        leads = g.loc[g["sajag_lead"] > 0, "sajag_lead"]
        per_event.append({
            "event": name, "first_report": g["first_report"].min(), "districts": int(len(g)),
            "warned_1d": int(g["sajag_1d"].sum()), "warned_3d": int(g["sajag_3d"].sum()),
            "watch_3d": int(g["sajag_watch_3d"].sum()),
            "river_3d": int(g["river_3d"].sum()), "rain_3d": int(g["rain_3d"].sum()),
            "median_lead": float(leads.median()) if len(leads) else 0.0,
        })

    years = dataset.years_of(blind)
    alert_rate = [
        {
            "year": int(y),
            **{name: float(flag[years == y].mean()) for name, flag in rules.items()},
        }
        for y in sorted(set(years))
    ]

    site = world.site_table
    site = site[dataset.years_of(site) >= FIRST_BLIND_YEAR]
    river_pred = model.river_forecast(site)

    total = {
        "district_events": int(len(scored)),
        "events": int(scored["event"].nunique()),
        **{
            f"{name}_{k}": int(scored[f"{name}_{k}"].sum())
            for name in rules for k in ("1d", "3d")
        },
    }
    out = {
        "events": per_event, "total": total, "alert_rate": alert_rate,
        "river": river_skill(site, river_pred), "rows": scored.to_dict("records"),
    }
    (ARTIFACTS / "metrics_blind.json").write_text(json.dumps(out, indent=1))

    hind = pd.DataFrame({f"risk{k}": model.calibrate(v, k) for k, v in scores.items()})
    hind["score7"] = scores[7]
    hind = hind.join(model.reasons(blind))
    hind.to_parquet(PROCESSED / "hindcast_blind.parquet")
    river_pred.to_parquet(PROCESSED / "river_blind.parquet")

    pd.set_option("display.width", 160)
    print(pd.DataFrame(per_event).to_string())
    print(json.dumps(total, indent=1))
    print(pd.DataFrame(alert_rate).round(3).to_string())
    print(pd.DataFrame(out["river"]).round(3).to_string())
    print(np.round(scored["sajag_lead"].describe().values, 2))


if __name__ == "__main__":
    main()
