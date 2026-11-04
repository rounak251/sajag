"""Extend the downloaded rain and river series up to the latest available day."""
from datetime import date, timedelta

import pandas as pd

from sajag.config import PROCESSED, RAW, UPSTREAM
from sajag.geo import bihar_districts
from sajag.sources import glofas, power


def main() -> None:
    today = date.today()
    points = {f"district_{d.key}": (round(d.lat, 3), round(d.lon, 3))
              for d in bihar_districts().itertuples()}
    points.update({f"upstream_{u[0]}": (u[2], u[3]) for u in UPSTREAM})
    for name, (lat, lon) in points.items():
        path = RAW / "power" / f"{name}.parquet"
        old = pd.read_parquet(path)
        old = old[old["rain"].notna()]
        start = old.index.max() + pd.Timedelta(days=1)
        new = power.fetch_point(lat, lon, str(start.date()), str(today - timedelta(days=1)))
        pd.concat([old, new[new["rain"].notna()]]).to_parquet(path)
        print("power", name, new["rain"].notna().sum(), flush=True)
    sites = pd.read_csv(PROCESSED / "sites.csv")
    for row in sites.itertuples():
        path = RAW / "glofas" / f"{row.site_id}.parquet"
        old = pd.read_parquet(path).dropna()
        start = old.index.max() + pd.Timedelta(days=1)
        new = glofas.history(row.lat, row.lon, str(start.date()), str(today - timedelta(days=1)))
        pd.concat([old, new.dropna().to_frame("q")]).to_parquet(path)
        print("glofas", row.site_id, new.notna().sum(), flush=True)


if __name__ == "__main__":
    main()
