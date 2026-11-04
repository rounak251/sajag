"""Train both stages, score them on years they never saw, and save the frozen models.

Run after scripts/fetch_history.py and scripts/fetch_recent.py. Nothing here reads a label
after 2023, and blind-test years are scored separately by scripts/blind_test.py.
"""
import json

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import average_precision_score

from sajag import dataset
from sajag import flood_model as M
from sajag import impact_model as I
from sajag import river_model as R
from sajag import scoring
from sajag.config import ARTIFACTS, PROCESSED, RAW
from sajag.features import PLACE_FEATURES
from sajag.sources import ifi

LEADS = R.LEADS
BUDGETS = (0.02, 0.05, 0.10)
LEVEL_BUDGETS = {"watch": 0.10, "warning": 0.05, "severe": 0.02}
REASON_GROUPS = {
    "river_now": ["q_max", "q_log_p99", "q_days_high", "g_pct", "g_over"],
    "upstream_rain": ["up_r3", "up_r7", "up_r15", "g_up_r7"],
    "local_rain": ["r3", "r7", "r15", "r30"],
    "soil": ["soil_root"],
    "statewide": ["state_r3", "state_wet", "state_sites_high", "state_ganga_high"],
    "season": ["doy"],
}


def stage_one(world) -> tuple[pd.DataFrame, dict]:
    """Out-of-fold river forecasts for the labelled years, then the final river models."""
    table = world.site_table
    years = dataset.years_of(table)
    dev = table[years <= dataset.LABEL_END]
    dev_years = dataset.years_of(dev)
    preds = []
    for block in M.year_blocks(list(range(dataset.LABEL_START, dataset.LABEL_END + 1))):
        held = np.isin(dev_years, block)
        preds.append(R.predict_block(R.fit_all(dev[~held]), dev[held]))
        print("stage 1 held out", block, flush=True)
    return pd.concat(preds).sort_index(), R.fit_all(dev)


def river_skill(world, oof: pd.DataFrame) -> list[dict]:
    """River forecast against persistence, on out-of-fold years."""
    t = world.site_table.reindex(oof.index)
    rows = []
    for lead in LEADS:
        keep = t[f"peak{lead}"].notna()
        obs, pers = t.loc[keep, f"peak{lead}"], t.loc[keep, "q_over"]
        pk, ex = oof.loc[keep, f"pk{lead}"], oof.loc[keep, f"ex{lead}"]
        hit = (obs >= 0).astype(int)
        new = pers < 0  # river not yet in flood: the only case a forecast adds anything

        def nse(sim):
            return float(1 - ((sim - obs) ** 2).sum() / ((obs - obs.mean()) ** 2).sum())

        def csi(flag):
            tp = int((flag & (hit == 1)).sum())
            return tp / max(tp + int((flag & (hit == 0)).sum()) + int((~flag & (hit == 1)).sum()), 1)

        rows.append({
            "lead": lead,
            "ap_new_model": float(average_precision_score(hit[new], ex[new])),
            "ap_new_persistence": float(average_precision_score(hit[new], pers[new])),
            "nse_model": nse(pk), "nse_persistence": nse(pers),
            "csi_model": csi(ex >= 0.5), "csi_persistence": csi(pers >= 0),
        })
    return rows


def out_of_fold(
    table: pd.DataFrame, target: str, features: list[str], reasons: bool = False, **kw,
):
    """A score for every row from models that never saw that row's years."""
    years = dataset.years_of(table)
    pred = pd.Series(np.nan, index=table.index)
    contrib = []
    for block in M.year_blocks(sorted(set(years))):
        held = np.isin(years, block)
        models = I.fit_bag(table[~held], target, features=features, **kw)
        pred[held] = I.predict_bag(models, table[held], features)
        if reasons:
            contrib.append(I.contributions(models, table[held], features))
    return (pred, pd.concat(contrib).sort_index()) if reasons else pred


def group_reasons(contrib: pd.DataFrame) -> pd.DataFrame:
    """Sum SHAP values into the groups a person can read."""
    return pd.DataFrame({
        g: contrib[[c for c in cols if c in contrib.columns]].sum(axis=1)
        for g, cols in REASON_GROUPS.items()
    })


def budget_table(table, flooded, on, methods) -> tuple[list[dict], dict]:
    rows, headline = [], {}
    for budget in BUDGETS:
        hit3 = {}
        for name, score in methods.items():
            alerts = I.alerts_at_budget(score, budget)
            c = {k: I.caught(alerts, on, k) for k in (1, 3, 5)}
            lead = I.lead_times(alerts, on)
            rows.append({
                "budget": budget, "method": name,
                "caught_1d": float(c[1].mean()), "caught_3d": float(c[3].mean()),
                "caught_5d": float(c[5].mean()),
                "precision": I.precision_of_alerts(alerts, flooded),
                "median_lead": float(np.median(lead[lead > 0])) if (lead > 0).any() else 0.0,
            })
            hit3[name] = c[3].astype(float)
        if budget == 0.05:
            headline = hit3
    return rows, headline


def main() -> None:
    ARTIFACTS.mkdir(exist_ok=True)
    world = dataset.load_world()
    events, flooded, labels = dataset.flood_labels(world, LEADS)
    print("labelled events", events["uei"].nunique(), "district events", len(events), flush=True)

    oof_river, river_models = stage_one(world)
    site_rows = river_skill(world, oof_river)
    print(pd.DataFrame(site_rows).round(3).to_string(), flush=True)

    d = world.district_table
    labelled = d[dataset.years_of(d) <= dataset.LABEL_END]
    table = labelled.join(labels, how="inner").join(
        R.district_forecast(oof_river, world.near), how="left",
    )
    on = scoring.onset_events(flooded, events)

    # Stage 2, out of fold, per lead.
    oof = {}
    contrib = None
    for lead in LEADS:
        if lead == 7:
            oof[lead], contrib = out_of_fold(table, f"y{lead}", I.FEATURES, reasons=True)
        else:
            oof[lead] = out_of_fold(table, f"y{lead}", I.FEATURES)
        print("stage 2 lead", lead, flush=True)

    # Baselines, scored on the same rows.
    years = dataset.years_of(table)
    clim = {}
    for lead in LEADS:
        c = pd.Series(np.nan, index=table.index)
        for block in M.year_blocks(sorted(set(years))):
            held = np.isin(years, block)
            c[held] = M.climatology(table[~held], table[held], f"y{lead}")
        clim[lead] = c
    river_only = table["q_log_p99"].fillna(-9)
    rain_only = table["r3"]

    impact = []
    for lead in LEADS:
        y = table[f"y{lead}"]
        for name, s in (("Sajag", oof[lead]), ("River level only", river_only),
                        ("3-day rain only", rain_only), ("Climatology", clim[lead])):
            impact.append({
                "lead": lead, "model": name,
                "pr_auc": float(average_precision_score(y, s)), "base_rate": float(y.mean()),
            })

    methods = {"Sajag": oof[7], "River level only": river_only, "3-day rain only": rain_only,
               "Climatology": clim[7]}
    budget_rows, hit3 = budget_table(table, flooded, on, methods)
    ci = scoring.bootstrap_by_event(
        {"Sajag": hit3["Sajag"], "River level only": hit3["River level only"]}, on["event"],
    )
    ci_rain = scoring.bootstrap_by_event(
        {"Sajag": hit3["Sajag"], "3-day rain only": hit3["3-day rain only"]}, on["event"],
    )

    # Ablations: remove one idea at a time, keep everything else fixed.
    y7 = "y7"
    variants = {
        "Full model": (I.FEATURES, {}),
        "Adding the river forecast": (I.FEATURES + I.RIVER_FORECAST, {}),
        "No physics constraints": (I.FEATURES, {"constrained": False}),
        "No upstream rain": (
            [f for f in I.FEATURES if f not in ("up_r3", "up_r7", "up_r15", "g_up_r7")], {},
        ),
        "Tributaries and Ganga merged": ([f for f in I.FEATURES if not f.startswith("g_")], {}),
        "No river data at all": ([
            f for f in I.FEATURES
            if f not in ("q_max", "q_log_p99", "q_days_high", "g_pct", "g_over",
                         "state_sites_high", "state_ganga_high")
        ], {}),
        "No season feature": ([f for f in I.FEATURES if f != "doy"], {}),
    }
    ablation = []
    for name, (feats, kw) in variants.items():
        p = oof[7] if name == "Full model" else out_of_fold(table, y7, feats, **kw)
        a = I.alerts_at_budget(p, 0.05)
        ablation.append({
            "variant": name, "pr_auc": float(average_precision_score(table[y7], p)),
            "caught_3d": float(I.caught(a, on, 3).mean()),
        })
        print("ablation", name, flush=True)
    # The cost of skipping the data cleaning: train on every record, score on real river floods.
    all_rows = ifi.load_events(RAW / "ifi_v3.csv", set(world.districts["key"]))
    keys = sorted(world.districts["key"])
    days = pd.date_range(f"{dataset.LABEL_START}-01-01", f"{dataset.LABEL_END}-12-31")
    from sajag.features import targets

    messy = targets(ifi.flood_days(all_rows, days, keys), (7,))["y7"].rename("y7_messy")
    tm = table.join(messy, how="left")
    p = out_of_fold(tm.assign(y7_messy=tm["y7_messy"].fillna(0)), "y7_messy", I.FEATURES)
    a = I.alerts_at_budget(p, 0.05)
    ablation.append({
        "variant": "No label cleaning", "pr_auc": float(average_precision_score(table[y7], p)),
        "caught_3d": float(I.caught(a, on, 3).mean()),
    })

    # Freeze: thresholds and calibration come from out-of-fold scores only.
    thresholds = {k: float(oof[7].quantile(1 - v)) for k, v in LEVEL_BUDGETS.items()}
    calibration = {}
    calibrated = {}
    for lead in LEADS:
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        calibrated[lead] = pd.Series(iso.fit_transform(oof[lead], table[f"y{lead}"]), table.index)
        calibration[str(lead)] = {
            "x": [float(v) for v in iso.X_thresholds_], "y": [float(v) for v in iso.y_thresholds_],
        }

    # Reliability must not be read off the curve fitted to the same rows, so each year block is
    # calibrated by a curve fitted on the other blocks.
    crossfit = pd.Series(np.nan, index=table.index)
    for block in M.year_blocks(sorted(set(years))):
        held = np.isin(years, block)
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(oof[7][~held], table.loc[~held, "y7"])
        crossfit[held] = iso.predict(oof[7][held])

    final = {lead: I.fit_bag(table, f"y{lead}") for lead in LEADS}
    for lead, models in final.items():
        for i, model in enumerate(models):
            model.booster_.save_model(str(ARTIFACTS / f"impact_{lead}_{i}.txt"))
    for (kind, lead), model in river_models.items():
        model.booster_.save_model(str(ARTIFACTS / f"river_{kind}_{lead}.txt"))
    reference = {
        "ref": {k: [float(x) for x in np.quantile(v, np.linspace(0, 1, 2001))]
                for k, v in world.ref.items()},
        "near": world.near,
        "thresholds": thresholds,
        "baseline_thresholds": {
            "river": float(river_only.quantile(0.95)), "rain": float(rain_only.quantile(0.95)),
        },
        "calibration": calibration,
        "reason_groups": REASON_GROUPS,
        "features": I.FEATURES,
        "river_features": R.SITE_FEATURES,
        "place_features": PLACE_FEATURES,
    }
    (ARTIFACTS / "reference.json").write_text(json.dumps(reference))

    # Out-of-fold hindcast for the dashboard: every labelled day comes from a model that never
    # saw that day's years.
    hind = pd.DataFrame({f"risk{lead}": calibrated[lead] for lead in LEADS})
    hind["score7"] = oof[7]
    hind = hind.join(group_reasons(contrib))
    hind.to_parquet(PROCESSED / "hindcast_labelled.parquet")
    oof_river.to_parquet(PROCESSED / "river_labelled.parquet")
    events.to_parquet(PROCESSED / "events_clean.parquet")

    y = table[y7]
    metrics = {
        "headline": {
            "caught_3d": float(hit3["Sajag"].mean()), "caught_3d_ci": list(ci["Sajag"]),
            "river_only_3d": float(hit3["River level only"].mean()),
            "river_only_3d_ci": list(ci["River level only"]),
            "difference_ci": list(ci["difference"]),
            "rain_only_3d": float(hit3["3-day rain only"].mean()),
            "rain_difference_ci": list(ci_rain["difference"]),
            "budget": 0.05, "events": int(on["event"].nunique()), "onsets": int(len(on)),
            "years": f"{dataset.LABEL_START}-{dataset.LABEL_END}",
        },
        "river": site_rows,
        "impact": impact,
        "budget": budget_rows,
        "reliability": scoring.reliability(y, crossfit),
        "ablation": ablation,
        "thresholds": thresholds,
    }
    (ARTIFACTS / "metrics_cv.json").write_text(json.dumps(metrics, indent=1))
    print(json.dumps(metrics["headline"], indent=1))
    print(pd.DataFrame(budget_rows).round(3).to_string())
    print(pd.DataFrame(ablation).round(3).to_string())
    print(pd.DataFrame(metrics["reliability"]).round(3).to_string())


if __name__ == "__main__":
    main()
