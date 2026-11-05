import numpy as np
import pandas as pd

from sajag.live_like import POWER_LAG, stitched


def test_newest_days_come_from_recent_rain_and_older_days_from_power():
    idx = pd.date_range("2024-07-01", periods=20)
    power = pd.DataFrame({"a": np.ones(20)}, index=idx)
    recent = pd.DataFrame({"a": np.full(20, 10.0)}, index=idx)
    s = stitched(power, recent, 7)["a"]
    # 7 days ending today: 3 old days of POWER at 1, then the 4 newest at 10.
    assert s.iloc[-1] == 3 * 1 + POWER_LAG * 10


def test_short_windows_use_only_recent_rain():
    idx = pd.date_range("2024-07-01", periods=10)
    power = pd.DataFrame({"a": np.ones(10)}, index=idx)
    recent = pd.DataFrame({"a": np.full(10, 10.0)}, index=idx)
    assert stitched(power, recent, 3)["a"].iloc[-1] == 30


def test_a_later_value_cannot_reach_an_earlier_date():
    idx = pd.date_range("2024-07-01", periods=20)
    power = pd.DataFrame({"a": np.ones(20)}, index=idx)
    recent = pd.DataFrame({"a": np.full(20, 10.0)}, index=idx)
    before = stitched(power, recent, 7)["a"].iloc[10]
    power.iloc[11:] = 999.0
    recent.iloc[11:] = 999.0
    assert stitched(power, recent, 7)["a"].iloc[10] == before
