"""Assemble the model table from downloaded files."""
import pandas as pd

from sajag import features as F
from sajag.config import PROCESSED, RAW
from sajag.geo import bihar_districts
from sajag.sources import ifi

START_YEAR = 1997  # first year of GloFAS history available through the API
LAST_LABEL_YEAR = 2023  # the inventory stops here
LEADS = (1, 3, 5, 7)


def load_points() -> dict[str, pd.DataFrame]:
    """Rain and soil per district, plus rain at upstream points."""
    series: dict[str, dict[str, pd.Series]] = {
        "rain": {}, "soil_top": {}, "soil_root": {}, "upstream": {},
    }
    for path in sorted((RAW / "power").glob("*.parquet")):
        df = pd.read_parquet(path)
        if path.stem.startswith("district_"):
            name = path.stem.removeprefix("district_")
            for col in ("rain", "soil_top", "soil_root"):
                series[col][name] = df[col]
        else:
            series["upstream"][path.stem.removeprefix("upstream_")] = df["rain"]
    return {k: pd.DataFrame(v).sort_index().interpolate(limit=3) for k, v in series.items()}


def load_discharge() -> pd.DataFrame:
    cols = {
        p.stem: pd.read_parquet(p)["q"] for p in sorted((RAW / "glofas").glob("*.parquet"))
    }
    return pd.DataFrame(cols).sort_index()


def model_table() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Features with labels for June to October, and the raw flood events."""
    districts = bihar_districts()
    sites = pd.read_csv(PROCESSED / "sites.csv")
    points = load_points()
    q = load_discharge()
    ref = F.river_reference(q)
    table = F.build(
        points["rain"], points["soil_top"], points["soil_root"], points["upstream"], q,
        districts, sites[sites.site_id.isin(q.columns)], ref,
    )
    events = ifi.load_events(RAW / "ifi_v3.csv", set(districts.key))
    days = pd.date_range(f"{START_YEAR}-01-01", table.index.get_level_values("date").max())
    flooded = ifi.flood_days(events, days, sorted(districts.key))
    labels = F.targets(flooded, LEADS)
    table = table.join(labels, how="inner")

    dates = table.index.get_level_values("date")
    keep = (dates.year >= START_YEAR) & dates.month.isin([6, 7, 8, 9, 10])
    return table[keep], events
