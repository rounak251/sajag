"""Turn raw rain, soil and river series into one row per district per day.

Every feature for date t uses data up to and including t, never later. The test
`test_features_never_look_ahead` changes the future and checks nothing moves.
"""
import numpy as np
import pandas as pd

from sajag.config import UPSTREAM

RIVER_REF_YEARS = (1997, 2010)  # percentiles come from here, before any test year
NEAREST_SITES = 3

RAIN_FEATURES = ["r1", "r3", "r7", "r15", "r30", "rmax3", "api", "soil_top", "soil_root"]
BASIN_FEATURES = ["up_r1", "up_r3", "up_r7", "up_r15"]
RIVER_FEATURES = [
    "q_near", "q_max", "q_mean", "q_log_p99", "q_rise1", "q_rise3", "q_rise7", "q_days_high",
]
GANGA_FEATURES = ["g_pct", "g_over", "g_rise3", "g_up_r7"]
STATE_FEATURES = ["state_r3", "state_wet", "state_sites_high", "state_ganga_high"]
PLACE_FEATURES = ["lat", "lon", "doy"]
FEATURES = (
    RAIN_FEATURES + BASIN_FEATURES + RIVER_FEATURES + GANGA_FEATURES + STATE_FEATURES
    + PLACE_FEATURES
)


def nearest_sites(districts: pd.DataFrame, sites: pd.DataFrame, k: int = NEAREST_SITES) -> dict:
    """The k closest river sites to each district, closest first."""
    out = {}
    for d in districts.itertuples():
        dist = np.hypot((sites["lat"] - d.lat), (sites["lon"] - d.lon) * np.cos(np.radians(d.lat)))
        out[d.key] = sites.iloc[np.argsort(dist.values)[:k]]["site_id"].tolist()
    return out


def river_groups(districts: pd.DataFrame, sites: pd.DataFrame) -> dict[str, dict]:
    """Nearest tributary sites and nearest Ganga site for each district, kept apart.

    The fast Nepal-fed tributaries and the huge, slow Ganga are different hazards. Taking the
    worst of both lets the Ganga drown out the tributary signal for most of the state.
    """
    return {
        "trib": nearest_sites(districts, sites[sites["river"] != "Ganga"]),
        "ganga": nearest_sites(districts, sites[sites["river"] == "Ganga"], 1),
    }


def river_reference(q: pd.DataFrame) -> dict[str, np.ndarray]:
    """Sorted reference flows per site, from the reference years only."""
    lo, hi = RIVER_REF_YEARS
    ref = q[(q.index.year >= lo) & (q.index.year <= hi)]
    return {c: np.sort(ref[c].dropna().values) for c in q.columns}


def percentile_of(series: pd.Series, ref: np.ndarray) -> pd.Series:
    """Share of reference days at or below each flow."""
    pct = np.searchsorted(ref, series.values, side="right") / len(ref)
    return pd.Series(pct, index=series.index).where(series.notna())


def _rain_block(r: pd.Series) -> pd.DataFrame:
    decay = r.ewm(alpha=0.1, adjust=False).mean() * 10  # 0.9 per-day antecedent rain index
    return pd.DataFrame({
        "r1": r,
        "r3": r.rolling(3, min_periods=1).sum(),
        "r7": r.rolling(7, min_periods=1).sum(),
        "r15": r.rolling(15, min_periods=1).sum(),
        "r30": r.rolling(30, min_periods=1).sum(),
        "rmax3": r.rolling(3, min_periods=1).max(),
        "api": decay,
    })


def basin_rain(upstream: pd.DataFrame) -> pd.DataFrame:
    """Mean daily rain over each basin's upstream points. Columns are basin names."""
    groups: dict[str, list[str]] = {}
    for uid, basin, _lat, _lon in UPSTREAM:
        groups.setdefault(basin, []).append(uid)
    return pd.DataFrame({b: upstream[c].mean(axis=1) for b, c in groups.items()})


def river_tables(q: pd.DataFrame, ref: dict[str, np.ndarray]) -> dict[str, pd.DataFrame]:
    pct = pd.DataFrame({c: percentile_of(q[c], ref[c]) for c in q.columns})
    p99 = pd.Series({c: np.quantile(ref[c], 0.99) for c in q.columns})
    logq = np.log(q.clip(lower=0.1))
    return {
        "pct": pct,
        "over": np.log(q.clip(lower=0.1) / p99),
        "rise1": logq.diff(1),
        "rise3": logq.diff(3),
        "rise7": logq.diff(7),
        "high": (pct >= 0.95).astype(float).where(q.notna()).rolling(7, min_periods=1).sum(),
    }


def build(
    rain: pd.DataFrame,
    soil_top: pd.DataFrame,
    soil_root: pd.DataFrame,
    upstream: pd.DataFrame,
    q: pd.DataFrame,
    districts: pd.DataFrame,
    sites: pd.DataFrame,
    ref: dict[str, np.ndarray],
) -> pd.DataFrame:
    """Long table of features indexed by (date, district)."""
    groups = river_groups(districts, sites)
    river_of = dict(zip(sites["site_id"], sites["river"]))
    ganga_ids = sites.loc[sites["river"] == "Ganga", "site_id"].tolist()
    trib_ids = sites.loc[sites["river"] != "Ganga", "site_id"].tolist()
    tables = river_tables(q, ref)
    basins = basin_rain(upstream)
    basin_sums = {n: basins.rolling(n, min_periods=1).sum() for n in (1, 3, 7, 15)}

    r3_all = rain.rolling(3, min_periods=1).sum()
    state = pd.DataFrame({
        "state_r3": r3_all.mean(axis=1),
        "state_wet": (r3_all > 50).mean(axis=1),
    })
    state["state_sites_high"] = (tables["pct"][trib_ids] >= 0.95).sum(axis=1).reindex(state.index)
    state["state_ganga_high"] = (tables["pct"][ganga_ids] >= 0.95).sum(axis=1).reindex(state.index)

    frames = []
    for d in districts.itertuples():
        f = _rain_block(rain[d.key])
        f["soil_top"] = soil_top[d.key]
        f["soil_root"] = soil_root[d.key]

        site_ids = groups["trib"][d.key]
        rivers = sorted({river_of[s] for s in site_ids} & set(basins.columns))
        for n in (1, 3, 7, 15):
            f[f"up_r{n}"] = basin_sums[n][rivers].max(axis=1).reindex(f.index)

        pct = tables["pct"][site_ids].reindex(f.index)
        f["q_near"] = pct[site_ids[0]]
        f["q_max"] = pct.max(axis=1)
        f["q_mean"] = pct.mean(axis=1)
        f["q_log_p99"] = tables["over"][site_ids].max(axis=1).reindex(f.index)
        f["q_rise1"] = tables["rise1"][site_ids].max(axis=1).reindex(f.index)
        f["q_rise3"] = tables["rise3"][site_ids].max(axis=1).reindex(f.index)
        f["q_rise7"] = tables["rise7"][site_ids].max(axis=1).reindex(f.index)
        f["q_days_high"] = tables["high"][site_ids].max(axis=1).reindex(f.index)

        ganga = groups["ganga"][d.key][0]
        f["g_pct"] = tables["pct"][ganga].reindex(f.index)
        f["g_over"] = tables["over"][ganga].reindex(f.index)
        f["g_rise3"] = tables["rise3"][ganga].reindex(f.index)
        f["g_up_r7"] = basin_sums[7]["Ganga"].reindex(f.index)

        f = f.join(state)
        f["lat"], f["lon"] = d.lat, d.lon
        f["doy"] = f.index.day_of_year
        f["district"] = d.key
        frames.append(f)
    out = pd.concat(frames)
    out.index.name = "date"
    return out.reset_index().set_index(["date", "district"]).sort_index()


def targets(flooded: pd.DataFrame, leads: tuple[int, ...]) -> pd.DataFrame:
    """y{L}: a flood is on record in the L days after t, excluding t itself."""
    cols = {}
    for lead in leads:
        ahead = flooded.astype(float).iloc[::-1].rolling(lead, min_periods=1).max().iloc[::-1]
        cols[f"y{lead}"] = ahead.shift(-1).fillna(0).stack()
    past = flooded.astype(float).rolling(8, min_periods=1).max().stack()
    cols["active"] = past
    out = pd.DataFrame(cols)
    out.index.names = ["date", "district"]
    return out
