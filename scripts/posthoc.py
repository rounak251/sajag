"""Score version 2 (observed-data model plus rain-forecast rule) on 2024 onward. Not blind.

Version 1's blind result stays in artifacts/metrics_blind.json. The forecasts used here are the
ones really issued at the time, so nothing from the future leaks in, but the design of version 2
was shaped by seeing version 1 fail on these same years.

Rain-rule alerts add to the model's, so the combined system alerts more often. Each baseline is
therefore also scored at the combined system's alert rate, with its threshold set on these same
years. That hands the baseline hindsight, which keeps the comparison from flattering Sajag.
"""
import json

import numpy as np
import pandas as pd

from sajag import dataset, frozen, rain_rule
from sajag.config import ARTIFACTS, PROCESSED, ROOT

WINDOW = 7


def lead_of(flag: pd.Series, district: str, report: pd.Timestamp) -> int:
    days = pd.date_range(report - pd.Timedelta(days=WINDOW), report - pd.Timedelta(days=1))
    hits = flag.xs(district, level="district").reindex(days).fillna(False).astype(bool)
    early = hits[hits].index
    return (report - early[0]).days if len(early) else 0


def score(events: pd.DataFrame, rules: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for e in events.itertuples():
        report = pd.Timestamp(e.first_report)
        row = {"event": e.event, "first_report": e.first_report, "district": e.district}
        for name, flag in rules.items():
            row[name] = lead_of(flag, e.district, report)
        rows.append(row)
    return pd.DataFrame(rows)


def matched(score_series: pd.Series, rate: float) -> pd.Series:
    return score_series >= score_series.quantile(1 - rate)


def placebo(events: pd.DataFrame, rules: dict[str, pd.Series], runs: int = 2000) -> dict:
    """How many floods would each rule 'warn' if the floods had come on other days?

    Alerts come in clumps, so a rule that alerts often can catch floods by luck. Each event moves
    to a random day of the same monsoon, its districts moving together, and is scored again.
    """
    rng = np.random.default_rng(5)
    wide = {
        name: flag.unstack("district").reindex(
            columns=sorted(events["district"].unique()),
        ).fillna(False).astype(bool)
        for name, flag in rules.items()
    }
    groups = []
    for _, g in events.groupby(["event", "first_report"]):
        groups.append((pd.Timestamp(g["first_report"].iloc[0]), g["district"].tolist()))
    out = {}
    for name, table in wide.items():
        dates = table.index
        position = {d: i for i, d in enumerate(dates)}
        values = table.values
        column = {c: i for i, c in enumerate(table.columns)}

        def hits(day_of: list[int]) -> int:
            total = 0
            for (_, districts), i in zip(groups, day_of):
                lo, hi = max(i - WINDOW, 0), max(i - 2, 0)  # 7 to 3 days before
                for d in districts:
                    total += int(values[lo:hi, column[d]].any())
            return total

        actual = hits([position.get(g[0], 0) for g in groups])
        by_year = {y: np.flatnonzero(dates.year == y) for y in sorted(set(dates.year))}
        draws = [
            hits([int(rng.choice(by_year[g[0].year])) for g in groups]) for _ in range(runs)
        ]
        out[name] = {
            "actual": actual, "chance_mean": float(np.mean(draws)),
            "chance_p95": float(np.quantile(draws, 0.95)),
            "p": float((np.sum(np.array(draws) >= actual) + 1) / (runs + 1)),
        }
    return out


def spatial_check(events: pd.DataFrame, flag: pd.Series) -> list[dict]:
    """Was the warning about the right place, or did it cover everywhere?

    Compares named districts with all others over the same days. Press lists are incomplete, so
    some 'other' districts may really have flooded, which makes this a rough, harsh test.
    """
    wide = flag.unstack("district").fillna(False).astype(bool)
    rows = []
    for name, g in events.groupby("event", sort=False):
        report = pd.Timestamp(g["first_report"].min())
        days = pd.date_range(report - pd.Timedelta(days=WINDOW), report - pd.Timedelta(days=3))
        window = wide.reindex(days).fillna(False).any()
        named = window[window.index.isin(g["district"])]
        other = window[~window.index.isin(g["district"])]
        rows.append({
            "event": name, "named": int(len(named)), "named_warned": int(named.sum()),
            "other": int(len(other)), "other_warned": int(other.sum()),
        })
    return rows


def main() -> None:
    world = dataset.load_world()
    model = frozen.load()
    table = world.district_table
    blind = table[dataset.years_of(table) >= 2024]

    points = rain_rule.load_point_forecasts()
    stat = rain_rule.district_statistic(points, world.near, world.sites)
    observed = dataset.load_points()
    limits = rain_rule.thresholds(rain_rule.observed_statistic(
        observed["rain"], observed["upstream"], world.near, world.sites,
    ))
    print("rain thresholds, mm in 5 days", {k: round(v) for k, v in limits.items()}, flush=True)
    rain_level = rain_rule.level(stat, limits).reindex(blind.index).fillna(0).astype(int)
    covered = float(stat.reindex(blind.index).notna().mean())

    obs_level = model.level(model.score(blind, 7))
    level = pd.concat([obs_level, rain_level], axis=1).max(axis=1)
    alert = level >= 2
    rate = float(alert.mean())

    river = blind["q_log_p99"].fillna(-9)
    rain_now = blind["r3"]
    ref = model.reference["baseline_thresholds"]
    rules = {
        "sajag": alert,
        "sajag_watch": level >= 1,
        "model_only": obs_level >= 2,
        "forecast_only": rain_level >= 2,
        "river_fixed": river >= ref["river"],
        "rain_fixed": rain_now >= ref["rain"],
        "river_matched": matched(river, rate),
        "rain_matched": matched(rain_now, rate),
    }
    events = pd.read_csv(ROOT / "data" / "reference" / "blind_test_events.csv")
    leads = score(events, rules)

    per_event = []
    for name, g in leads.groupby("event", sort=False):
        got = g.loc[g["sajag"] > 0, "sajag"]
        per_event.append({
            "event": name, "first_report": g["first_report"].min(), "districts": len(g),
            "warned_1d": int((g["sajag"] >= 1).sum()), "warned_3d": int((g["sajag"] >= 3).sum()),
            "river_3d": int((g["river_matched"] >= 3).sum()),
            "rain_3d": int((g["rain_matched"] >= 3).sum()),
            "median_lead": float(got.median()) if len(got) else 0.0,
        })
    years = dataset.years_of(blind)
    out = {
        "rain_thresholds_mm": limits,
        "forecast_coverage": covered,
        "alert_rate": rate,
        "alert_rate_by_year": {
            int(y): float(alert[years == y].mean()) for y in sorted(set(years))
        },
        "totals": {
            name: {"warned_1d": int((leads[name] >= 1).sum()),
                   "warned_3d": int((leads[name] >= 3).sum()),
                   "alert_rate": float(flag.mean())}
            for name, flag in rules.items()
        },
        "district_events": len(leads),
        "events": per_event,
    }
    out["spatial"] = spatial_check(events, alert)
    out["placebo"] = placebo(events, {k: rules[k] for k in (
        "sajag", "model_only", "forecast_only", "rain_matched", "river_matched",
    )})
    (ARTIFACTS / "metrics_posthoc.json").write_text(json.dumps(out, indent=1))

    hind = pd.read_parquet(PROCESSED / "hindcast_blind.parquet")
    hind["obs_level"] = obs_level
    hind["rain_level"] = rain_level
    hind["level"] = level
    hind["fc5"] = stat.reindex(hind.index)
    hind.to_parquet(PROCESSED / "hindcast_blind.parquet")
    (ARTIFACTS / "rain_thresholds.json").write_text(json.dumps(limits))

    pd.set_option("display.width", 170)
    print(pd.DataFrame(per_event).to_string())
    print(pd.DataFrame(out["totals"]).T.round(3).to_string())
    print(pd.DataFrame(out["placebo"]).T.round(3).to_string())
    print(pd.DataFrame(out["spatial"]).to_string())
    print("coverage", round(covered, 3), "by year", out["alert_rate_by_year"], flush=True)
    print(np.round(leads["sajag"].describe().values, 2))


if __name__ == "__main__":
    main()
