"""Score version 2 on 2024 onward. This is not a blind test.

Version 1's blind result stays in artifacts/metrics_blind.json. Version 2 was designed after seeing
version 1 fail on these same floods, and was corrected again after an independent review.

The headline rule uses inputs as a morning run would have had them: NASA POWER four days behind,
recent rain from Open-Meteo, and rain forecasts public by 08:00 IST. Complete POWER data is scored
too, only to show what that shortcut was worth.

Rain-rule alerts add to the model's, so the system alerts more often than either alone. Every
baseline is scored at the same alert rate, with its threshold set on these same years. That gives
baselines hindsight. Two baselines also get the rain forecast, since a fair test of the model has
to ask what it adds to a forecast, not just what the forecast adds to nothing.
"""
import json

import numpy as np
import pandas as pd

from sajag import dataset, frozen, live_like, rain_rule
from sajag import river_model as R
from sajag.config import ARTIFACTS, PROCESSED, ROOT

WINDOW = 7
PLACEBO_MONTHS = (7, 8, 9)  # the months these floods came in, so chance is judged fairly


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


def union_at_rate(flag: pd.Series, other: pd.Series, rate: float) -> pd.Series:
    """`flag` or `other` above a cut, with the cut chosen so the union fires at `rate`."""
    lo, hi = 0.0, 1.0
    best = flag
    for _ in range(30):
        q = (lo + hi) / 2
        best = flag | (other >= other.quantile(q))
        if best.mean() > rate:
            lo = q
        else:
            hi = q
    return best


def placebo(events: pd.DataFrame, rules: dict[str, pd.Series], runs: int = 2000) -> dict:
    """How many floods would each rule 'warn' if the floods had come on other days?

    Alerts come in clumps, so a rule that alerts often can catch floods by luck. Each report moves
    to a random day in July to September of its year, its districts moving together, and is scored
    again. Drawing from all of June to October would flatter the system, because alerts are rare
    in June and October and these floods came in August and September.
    """
    rng = np.random.default_rng(5)
    groups = [
        (pd.Timestamp(day), g["district"].tolist())
        for (_, day), g in events.groupby(["event", "first_report"])
    ]
    out = {}
    for name, flag in rules.items():
        table = flag.unstack("district").reindex(
            columns=sorted(events["district"].unique()),
        ).fillna(False).astype(bool)
        dates = table.index
        position = {d: i for i, d in enumerate(dates)}
        values = table.values
        column = {c: i for i, c in enumerate(table.columns)}

        def hits(day_of: list[int], values=values, column=column) -> int:
            total = 0
            for (_, districts), i in zip(groups, day_of):
                lo, hi = max(i - WINDOW, 0), max(i - 2, 0)  # 7 to 3 days before
                for d in districts:
                    total += int(values[lo:hi, column[d]].any())
            return total

        actual = hits([position[g[0]] for g in groups])
        pool = {
            y: np.flatnonzero((dates.year == y) & dates.month.isin(PLACEBO_MONTHS))
            for y in sorted(set(dates.year))
        }
        draws = np.array([
            hits([int(rng.choice(pool[g[0].year])) for g in groups]) for _ in range(runs)
        ])
        out[name] = {
            "actual": actual, "chance_mean": float(draws.mean()),
            "chance_p95": float(np.quantile(draws, 0.95)),
            "p": float(((draws >= actual).sum() + 1) / (runs + 1)),
        }
    return out


def spatial_check(events: pd.DataFrame, flag: pd.Series) -> list[dict]:
    """Was the warning about the right place, or did it cover everywhere?

    Each report date is judged on its own 7-to-3-day window. Other districts are counted as warned
    in any of the event's windows. Press lists are incomplete, so some 'other' districts may really
    have flooded, which makes this a rough, harsh test.
    """
    wide = flag.unstack("district").fillna(False).astype(bool)
    rows = []
    for name, g in events.groupby("event", sort=False):
        named_hit, days_all = 0, []
        for day, part in g.groupby("first_report"):
            report = pd.Timestamp(day)
            days = pd.date_range(report - pd.Timedelta(days=WINDOW), report - pd.Timedelta(days=3))
            days_all.extend(days)
            window = wide.reindex(days).fillna(False).any()
            named_hit += int(window[part["district"].tolist()].sum())
        anywhere = wide.reindex(pd.DatetimeIndex(sorted(set(days_all)))).fillna(False).any()
        other = anywhere[~anywhere.index.isin(g["district"])]
        rows.append({
            "event": name, "named": int(len(g)), "named_warned": named_hit,
            "other": int(len(other)), "other_warned": int(other.sum()),
        })
    return rows


def already_on(events: pd.DataFrame, flag: pd.Series) -> int:
    """Floods where an alert was already running 8 days before the report, outside the window."""
    count = 0
    for e in events.itertuples():
        day = pd.Timestamp(e.first_report) - pd.Timedelta(days=WINDOW + 1)
        series = flag.xs(e.district, level="district")
        count += int(bool(series.get(day, False)))
    return count


def burden(flag: pd.Series) -> dict:
    """How many Warning days a district gets in a season, since the load is uneven."""
    years = flag.index.get_level_values("date").year.nunique()
    days = (flag.groupby(level="district").sum() / years).sort_values()
    return {
        "mean": float(days.mean()), "median": float(days.median()),
        "most": [[k, round(float(v), 1)] for k, v in days.tail(3).iloc[::-1].items()],
        "least": [[k, round(float(v), 1)] for k, v in days.head(3).items()],
    }


def main() -> None:
    world = dataset.load_world()
    model = frozen.load()
    table = world.district_table
    blind = table[dataset.years_of(table) >= 2024]
    observed = dataset.load_points()

    points = rain_rule.load_point_forecasts()
    stat = rain_rule.district_statistic(points, world.near, world.sites)
    limits = rain_rule.thresholds(rain_rule.observed_statistic(
        observed["rain"], observed["upstream"], world.near, world.sites,
    ))
    before_fix = rain_rule.thresholds(rain_rule.observed_statistic(
        observed["rain"], observed["upstream"], world.near, world.sites, south_fix=False,
    ))
    print("rain thresholds, mm in 5 days", {k: round(v) for k, v in limits.items()}, flush=True)
    fc5 = stat.reindex(blind.index)
    coverage = float(fc5.notna().mean())
    if coverage < 0.9:
        # A broken download once produced a score from a third of the forecasts. Never again.
        raise SystemExit(f"only {coverage:.0%} of forecasts present: finish fetch_forecasts.py first")
    rain_level = rain_rule.level(stat, limits).reindex(blind.index).fillna(0).astype(int)
    rain_level_old = rain_rule.level(stat, before_fix).reindex(blind.index).fillna(0).astype(int)

    live = live_like.rebuild(blind, observed, world.sites, world.near)
    scores = {lead: model.score(live, lead) for lead in R.LEADS}
    obs_level = model.level(scores[7])
    obs_ideal = model.level(model.score(blind, 7))
    level = pd.concat([obs_level, rain_level], axis=1).max(axis=1)
    alert = level >= 2
    rate = float(alert.mean())

    river = blind["q_log_p99"].fillna(-9)
    river_any = pd.concat([river, blind["g_over"].fillna(-9)], axis=1).max(axis=1)
    rain_now = live["r3"].fillna(0)
    ref = model.reference["baseline_thresholds"]
    rules = {
        "sajag": alert,
        "sajag_watch": level >= 1,
        "complete_data": pd.concat([obs_ideal, rain_level], axis=1).max(axis=1) >= 2,
        "higher_threshold": pd.concat([obs_level, rain_level_old], axis=1).max(axis=1) >= 2,
        "model_only": obs_level >= 2,
        "forecast_only": rain_level >= 2,
        "river_fixed": river >= ref["river"],
        "rain_fixed": rain_now >= ref["rain"],
        "forecast_matched": matched(fc5.fillna(0), rate),
        "forecast_or_river": union_at_rate(rain_level >= 2, river_any, rate),
        "river_matched": matched(river, rate),
        "rain_matched": matched(rain_now, rate),
    }
    events = pd.read_csv(ROOT / "data" / "reference" / "blind_test_events.csv")
    leads = score(events, rules)

    per_event = []
    for name, g in leads.groupby("event", sort=False):
        got = g.loc[g["sajag"] > 0, "sajag"]
        per_event.append({
            "event": name, "first_report": g["first_report"].min(), "districts": int(len(g)),
            "warned_1d": int((g["sajag"] >= 1).sum()), "warned_3d": int((g["sajag"] >= 3).sum()),
            "forecast_3d": int((g["forecast_matched"] >= 3).sum()),
            "combo_3d": int((g["forecast_or_river"] >= 3).sum()),
            "river_3d": int((g["river_matched"] >= 3).sum()),
            "rain_3d": int((g["rain_matched"] >= 3).sum()),
            "median_lead": float(got.median()) if len(got) else 0.0,
        })
    first = leads["first_report"] == leads.groupby("event")["first_report"].transform("min")
    years = dataset.years_of(blind)
    out = {
        "rain_thresholds_mm": limits,
        "thresholds_before_fix_mm": before_fix,
        "forecast_coverage": coverage,
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
        "district_events": int(len(leads)),
        "first_listed": {"districts": int(first.sum()),
                         "warned_3d": int((leads.loc[first, "sajag"] >= 3).sum())},
        "already_on_8_days_before": already_on(events, alert),
        "burden": burden(alert),
        "events": per_event,
        "spatial": spatial_check(events, alert),
        "placebo": placebo(events, {k: rules[k] for k in (
            "sajag", "model_only", "forecast_only", "forecast_matched", "forecast_or_river",
            "rain_matched", "river_matched",
        )}),
    }
    (ARTIFACTS / "metrics_posthoc.json").write_text(json.dumps(out, indent=1))
    (ARTIFACTS / "rain_thresholds.json").write_text(json.dumps(limits))

    hind = pd.DataFrame({f"risk{k}": model.calibrate(v, k) for k, v in scores.items()})
    hind["score7"] = scores[7]
    hind = hind.join(model.reasons(live))
    hind["obs_level"] = obs_level
    hind["rain_level"] = rain_level
    hind["level"] = level
    hind["fc5"] = fc5
    hind.to_parquet(PROCESSED / "hindcast_blind.parquet")

    pd.set_option("display.width", 170)
    print(pd.DataFrame(per_event).to_string())
    print(pd.DataFrame(out["totals"]).T.round(3).to_string())
    print(pd.DataFrame(out["placebo"]).T.round(3).to_string())
    print(pd.DataFrame(out["spatial"]).to_string())
    for k in ("first_listed", "already_on_8_days_before", "burden", "alert_rate_by_year",
              "thresholds_before_fix_mm", "forecast_coverage"):
        print(k, out[k])


if __name__ == "__main__":
    main()
