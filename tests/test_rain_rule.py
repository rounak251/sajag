import numpy as np
import pandas as pd

from sajag import rain_rule as RR
from sajag.config import UPSTREAM


def test_levels_step_up_with_forecast_rain():
    idx = pd.MultiIndex.from_tuples(
        [(pd.Timestamp("2024-09-01"), d) for d in "abcd"], names=["date", "district"],
    )
    stat = pd.Series([10.0, 60.0, 110.0, 210.0], index=idx)
    out = RR.level(stat, {"watch": 50, "warning": 100, "severe": 200})
    assert out.tolist() == [0, 1, 2, 3]


def test_a_missing_forecast_never_raises_the_alert():
    idx = pd.MultiIndex.from_tuples([(pd.Timestamp("2024-09-01"), "a")], names=["date", "district"])
    assert RR.level(pd.Series([np.nan], index=idx), {"watch": 1, "warning": 2, "severe": 3}).iloc[0] == 0


def test_thresholds_ignore_years_outside_the_reference_window():
    days = pd.date_range("2023-07-01", periods=90).append(pd.date_range("2024-07-01", periods=90))
    idx = pd.MultiIndex.from_product([days, ["a"]], names=["date", "district"])
    stat = pd.Series(np.r_[np.arange(90.0), np.full(90, 1e6)], index=idx)
    assert RR.thresholds(stat)["warning"] < 100


def _points(kosi_rain):
    idx = pd.to_datetime(["2024-09-25"])
    cols = {f"upstream_{u[0]}": [kosi_rain if u[1] == "Kosi" else 0.0] for u in UPSTREAM}
    cols["district_banka"] = [10.0]
    cols["district_supaul"] = [10.0]
    return pd.DataFrame(cols, index=idx)


def test_rain_in_the_kosi_basin_never_reaches_south_of_the_ganga():
    sites = pd.DataFrame({"site_id": ["k"], "river": ["Kosi"]})
    groups = {"trib": {"banka": ["k"], "supaul": ["k"]}}
    out = RR.district_statistic(_points(300.0), groups, sites).droplevel("date")
    assert out["supaul"] == 300
    assert out["banka"] == 10
