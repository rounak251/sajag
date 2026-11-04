import numpy as np
import pandas as pd

from sajag import drought as D


def _rain(seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1985-01-01", "2020-12-01", freq="MS")
    season = 60 + 200 * np.exp(-((idx.month - 7.5) ** 2) / 4)
    return pd.Series(rng.gamma(4, season / 4), index=idx)


def test_spi_is_near_standard_normal_over_the_reference_years():
    s = D.spi(_rain(), 3).loc["1985":"2014"].dropna()
    assert abs(s.mean()) < 0.2
    assert 0.8 < s.std() < 1.2


def test_a_failed_monsoon_scores_as_drought():
    r = _rain()
    r.loc["2018-06":"2018-08"] *= 0.2
    assert D.spi(r, 3).loc["2018-08-01"] < -1.5


def test_future_years_cannot_change_past_scores():
    r = _rain()
    before = D.spi(r, 3).loc["2010-08-01"]
    r.loc["2016":] *= 5
    assert D.spi(r, 3).loc["2010-08-01"] == before


def test_target_is_next_month_drought():
    idx = pd.date_range("1985-01-01", "2020-12-31")
    rain = pd.DataFrame({"a": np.full(len(idx), 3.0)}, index=idx)
    rng = np.random.default_rng(3)
    rain["a"] = rng.gamma(2, 2, len(idx))
    rain.loc["2019-06":"2019-08", "a"] = 0.0
    soil = pd.DataFrame({"a": np.full(len(idx), 0.5)}, index=idx)
    districts = pd.DataFrame({"key": ["a"], "lat": [26.0], "lon": [86.0]})
    t = D.monthly_table(rain, soil, districts).xs("a", level="district")
    assert t.loc["2019-07-01", "target"] == 1.0
    assert t.loc["2018-07-01", "target"] == 0.0
