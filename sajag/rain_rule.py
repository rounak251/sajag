"""Raise the alert when extreme rain is forecast over a district or its upstream basin.

A model that sees only rain already fallen cannot warn of a flood before the rain starts. On
26-28 September 2024 rain fell in Nepal and the flood reached Bihar by the 28th, so three days of
warning needed a forecast. This is a plain rule rather than a model input, because archived
forecasts only reach back to January 2024, too short to train on.

Thresholds come from rain that really fell in 2006-2023, so a forecast counts as extreme when it
exceeds what five wet days usually bring. No forecast or outcome from 2024 onward sets them.
"""
import pandas as pd

from sajag.config import RAW, UPSTREAM
from sajag.sources import nwp

WINDOW_DAYS = 5
THRESHOLD_YEARS = (2006, 2023)
QUANTILES = {"watch": 0.90, "warning": 0.95, "severe": 0.98}

# Water from Nepal cannot cross the Ganga to reach these districts, so they use their own rain,
# plus the Sone basin where that river runs. The first version took the nearest river site for
# every district, which tied Banka and Nawada to the Kosi and warned all of Bihar at once.
SOUTH_OF_GANGA = {
    "arwal", "aurangabad", "banka", "bhagalpur", "bhojpur", "buxar", "gaya", "jamui", "jehanabad",
    "kaimur", "lakhisarai", "munger", "nalanda", "nawada", "patna", "rohtas", "sheikhpura",
}
SONE_DISTRICTS = {"arwal", "aurangabad", "bhojpur", "kaimur", "patna", "rohtas"}


def load_point_forecasts() -> pd.DataFrame:
    """Forecast rain for the next five days per point and issue date, as the mean of two models."""
    parts: dict[str, dict[str, list[pd.Series]]] = {}
    for path in sorted((RAW / "nwp").glob("*.parquet")):
        model, point, _year = path.stem.split("__")
        sums = nwp.issued_sums(pd.read_parquet(path), WINDOW_DAYS)
        parts.setdefault(point, {}).setdefault(model, []).append(sums)
    columns = {}
    for point, models in parts.items():
        runs = [pd.concat(v).sort_index() for v in models.values()]
        columns[point] = pd.concat(runs, axis=1).mean(axis=1, skipna=False)
    return pd.DataFrame(columns).sort_index()


def _combine(
    points: pd.DataFrame, groups: dict, sites: pd.DataFrame, south_fix: bool = True,
) -> pd.Series:
    """The wetter of the district's own rain and its worst upstream tributary basin."""
    river_of = dict(zip(sites["site_id"], sites["river"]))
    basin_points: dict[str, list[str]] = {}
    for uid, basin, _lat, _lon in UPSTREAM:
        basin_points.setdefault(basin, []).append(f"upstream_{uid}")
    out = {}
    for district, ids in groups["trib"].items():
        local = points[f"district_{district}"]
        rivers = {river_of[s] for s in ids} & set(basin_points)
        if south_fix and district in SOUTH_OF_GANGA:
            rivers = {"Sone"} if district in SONE_DISTRICTS else set()
        basins = [points[basin_points[r]].mean(axis=1, skipna=False) for r in sorted(rivers)]
        out[district] = pd.concat([local, *basins], axis=1).max(axis=1, skipna=False)
    table = pd.DataFrame(out)
    table.index.name = "date"
    stacked = table.stack(future_stack=True)
    stacked.index.names = ["date", "district"]
    return stacked


def district_statistic(points: pd.DataFrame, groups: dict, sites: pd.DataFrame) -> pd.Series:
    """Forecast rain per district, from point forecasts already summed over the window."""
    return _combine(points, groups, sites)


def observed_statistic(
    rain: pd.DataFrame, upstream: pd.DataFrame, groups: dict, sites: pd.DataFrame,
    south_fix: bool = True,
) -> pd.Series:
    """The same statistic on rain that really fell, as five-day sums."""
    points = pd.concat([rain.add_prefix("district_"), upstream.add_prefix("upstream_")], axis=1)
    return _combine(points.rolling(WINDOW_DAYS).sum(), groups, sites, south_fix)


def thresholds(stat: pd.Series) -> dict[str, float]:
    dates = stat.index.get_level_values("date")
    first, last = THRESHOLD_YEARS
    keep = (dates.year >= first) & (dates.year <= last) & dates.month.isin([6, 7, 8, 9, 10])
    return {k: float(stat[keep].quantile(v)) for k, v in QUANTILES.items()}


def level(stat: pd.Series, limits: dict[str, float]) -> pd.Series:
    out = pd.Series(0, index=stat.index, dtype="int64")
    for i, name in enumerate(("watch", "warning", "severe"), start=1):
        out[stat >= limits[name]] = i
    return out
