import numpy as np
import pandas as pd
import pytest

from sajag import features as F
from sajag.config import UPSTREAM


@pytest.fixture
def world():
    rng = np.random.default_rng(0)
    idx = pd.date_range("1997-01-01", "2012-12-31")
    districts = pd.DataFrame({"key": ["a", "b"], "lat": [26.0, 25.5], "lon": [86.0, 85.0]})
    sites = pd.DataFrame({
        "site_id": ["s1", "s2", "s3"], "river": ["Kosi", "Gandak", "Ganga"],
        "lat": [26.1, 25.9, 25.6], "lon": [86.1, 85.5, 85.1],
    })

    def frame(cols, hi):
        return pd.DataFrame(rng.uniform(0, hi, (len(idx), len(cols))), idx, cols)

    return {
        "rain": frame(["a", "b"], 40), "soil_top": frame(["a", "b"], 1),
        "soil_root": frame(["a", "b"], 1), "upstream": frame([u[0] for u in UPSTREAM], 40),
        "q": frame(["s1", "s2", "s3"], 5000) + 1, "districts": districts, "sites": sites,
    }


def _build(w):
    return F.build(ref=F.river_reference(w["q"]), **w)


def test_features_never_look_ahead(world):
    cut = pd.Timestamp("2012-07-15")
    before = _build(world).xs(cut, level="date")[F.FEATURES]
    for name in ("rain", "soil_top", "soil_root", "upstream"):
        world[name].loc[world[name].index > cut] = 999.0
    # Reference years end in 2010, so changing later flow cannot change percentiles.
    world["q"].loc[world["q"].index > cut] = 1e7
    after = _build(world).xs(cut, level="date")[F.FEATURES]
    pd.testing.assert_frame_equal(before, after)


def test_every_feature_exists_in_the_table(world):
    table = _build(world)
    assert set(F.FEATURES) <= set(table.columns)


def test_target_counts_the_next_days_but_not_today():
    idx = pd.date_range("2020-07-01", "2020-07-10")
    flooded = pd.DataFrame(False, idx, ["a"])
    flooded.loc["2020-07-05", "a"] = True
    t = F.targets(flooded, (3,)).xs("a", level="district")
    assert t.loc["2020-07-01", "y3"] == 0
    assert t.loc["2020-07-02", "y3"] == 1  # 5 July is 3 days ahead
    assert t.loc["2020-07-04", "y3"] == 1
    assert t.loc["2020-07-05", "y3"] == 0  # today does not count


def test_percentile_is_empirical_and_keeps_gaps():
    ref = np.array([1.0, 2.0, 3.0, 4.0])
    s = pd.Series([0.5, 2.0, 9.0, np.nan])
    out = F.percentile_of(s, ref)
    assert out.tolist()[:3] == [0.0, 0.5, 1.0]
    assert np.isnan(out.iloc[3])


def test_nearest_sites_are_ordered_by_distance():
    districts = pd.DataFrame({"key": ["a"], "lat": [26.0], "lon": [86.0]})
    sites = pd.DataFrame({
        "site_id": ["far", "near", "mid"],
        "lat": [29.0, 26.01, 26.5], "lon": [90.0, 86.0, 86.5],
    })
    assert F.nearest_sites(districts, sites, 2)["a"] == ["near", "mid"]


def test_river_fetch_retries_after_a_timeout(monkeypatch):
    import requests

    from sajag.sources import glofas

    calls = {"n": 0}

    class Ok:
        status_code = 200
        ok = True

        def json(self):
            return {"daily": {"time": ["2026-11-05"], "river_discharge": [1.0]}}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.exceptions.ReadTimeout("slow")
        return Ok()

    monkeypatch.setattr(glofas.requests, "get", flaky)
    monkeypatch.setattr(glofas.time, "sleep", lambda s: None)
    assert glofas.history(26.5, 86.9, "2026-11-05", "2026-11-05").iloc[0] == 1.0
    assert calls["n"] == 2
