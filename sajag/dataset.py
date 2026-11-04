"""Load downloaded files into the tables the models use."""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from sajag import features as F
from sajag import river_model as R
from sajag.config import PROCESSED, RAW, SITES
from sajag.geo import bihar_districts
from sajag.sources import ifi

RIVER_START = 1997  # GloFAS history through the API starts here
LABEL_START = 2006  # the flood record is event by event from here
LABEL_END = 2023  # the flood record stops here
MONSOON = (6, 7, 8, 9, 10)


@dataclass
class World:
    districts: pd.DataFrame
    sites: pd.DataFrame
    near: dict
    ref: dict
    q: pd.DataFrame
    site_table: pd.DataFrame
    district_table: pd.DataFrame


def load_sites() -> pd.DataFrame:
    """Snapped sites in config order, which runs top to bottom along each river."""
    sites = pd.read_csv(PROCESSED / "sites.csv").set_index("site_id")
    order = [s[0] for s in SITES if s[0] in sites.index]
    return sites.reindex(order).reset_index()


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
    cols = {p.stem: pd.read_parquet(p)["q"] for p in sorted((RAW / "glofas").glob("*.parquet"))}
    return pd.DataFrame(cols).sort_index()


def _monsoon(table: pd.DataFrame, first_year: int) -> pd.DataFrame:
    dates = table.index.get_level_values("date")
    return table[(dates.year >= first_year) & dates.month.isin(MONSOON)]


def load_world() -> World:
    districts = bihar_districts()
    sites = load_sites()
    points = load_points()
    q = load_discharge()[sites["site_id"].tolist()]
    last = min(q.dropna(how="all").index.max(), points["rain"].dropna(how="all").index.max())
    q = q.loc[:last]
    points = {k: v.loc[:last] for k, v in points.items()}
    ref = F.river_reference(q)
    district_table = F.build(
        points["rain"], points["soil_top"], points["soil_root"], points["upstream"], q,
        districts, sites, ref,
    )
    site_table = R.site_table(
        q, ref, points["upstream"], points["rain"], points["soil_root"], sites, districts,
    )
    return World(
        districts=districts, sites=sites, near=F.river_groups(districts, sites), ref=ref, q=q,
        site_table=_monsoon(site_table, RIVER_START),
        district_table=_monsoon(district_table, LABEL_START),
    )


def flood_labels(world: World, leads: tuple[int, ...]):
    """Clean river-flood events, the flooded table, and per-day targets for the labelled years."""
    keys = sorted(world.districts["key"])
    events = ifi.load_river_floods(RAW / "ifi_v3.csv", set(keys), first_year=LABEL_START)
    days = pd.date_range(f"{LABEL_START}-01-01", f"{LABEL_END}-12-31")
    flooded = ifi.flood_days(events, days, keys)
    return events, flooded, F.targets(flooded, leads)


def years_of(table: pd.DataFrame) -> np.ndarray:
    return table.index.get_level_values("date").year.values
