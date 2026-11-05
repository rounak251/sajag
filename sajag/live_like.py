"""Rebuild past inputs as the morning run would really have seen them.

NASA POWER runs about four days behind, so the live job fills the newest days with Open-Meteo
rain and uses soil moisture four days old. Scoring on complete POWER data would test a system
that cannot exist, so the headline score uses this table instead.
"""
import pandas as pd

from sajag.config import RAW, UPSTREAM

POWER_LAG = 4  # newest days missing from POWER on a morning run


def recent_rain() -> pd.DataFrame:
    """Best-match archived rain per point, as used to fill the newest days."""
    frames = [pd.read_parquet(p) for p in sorted((RAW / "recent_rain").glob("*.parquet"))]
    return pd.concat(frames).sort_index()


def stitched(power: pd.DataFrame, recent: pd.DataFrame, days: int) -> pd.DataFrame:
    """`days`-day rain ending each date: POWER where it exists by then, recent rain after."""
    recent = recent.reindex(columns=power.columns)
    if days <= POWER_LAG:
        return recent.rolling(days, min_periods=days).sum()
    old = power.rolling(days - POWER_LAG, min_periods=days - POWER_LAG).sum().shift(POWER_LAG)
    return old + recent.rolling(POWER_LAG, min_periods=POWER_LAG).sum()


def rebuild(blind: pd.DataFrame, points: dict, sites: pd.DataFrame, groups: dict) -> pd.DataFrame:
    """A copy of the district table with rain and soil replaced by what a morning run had."""
    recent = recent_rain()
    power = pd.concat(
        [points["rain"].add_prefix("district_"), points["upstream"].add_prefix("upstream_")],
        axis=1,
    )
    sums = {n: stitched(power, recent, n) for n in (3, 7, 15, 30)}
    basin_points: dict[str, list[str]] = {}
    for uid, basin, _lat, _lon in UPSTREAM:
        basin_points.setdefault(basin, []).append(f"upstream_{uid}")
    basins = {
        n: pd.DataFrame({b: s[c].mean(axis=1) for b, c in basin_points.items()})
        for n, s in sums.items()
    }
    river_of = dict(zip(sites["site_id"], sites["river"]))
    keys = sorted(groups["trib"])
    local3 = sums[3][[f"district_{k}" for k in keys]]

    out = blind.copy()
    dates = out.index.get_level_values("date")
    names = out.index.get_level_values("district")
    soil = points["soil_root"].shift(POWER_LAG)
    state_r3 = local3.mean(axis=1)
    state_wet = (local3 > 50).mean(axis=1)
    for key in keys:
        here = names == key
        day = dates[here]
        for n in (3, 7, 15, 30):
            out.loc[here, f"r{n}"] = sums[n][f"district_{key}"].reindex(day).values
        rivers = sorted({river_of[s] for s in groups["trib"][key]} & set(basin_points))
        for n in (3, 7, 15):
            out.loc[here, f"up_r{n}"] = basins[n][rivers].max(axis=1).reindex(day).values
        out.loc[here, "g_up_r7"] = basins[7]["Ganga"].reindex(day).values
        out.loc[here, "soil_root"] = soil[key].reindex(day).values
        out.loc[here, "state_r3"] = state_r3.reindex(day).values
        out.loc[here, "state_wet"] = state_wet.reindex(day).values
    return out


