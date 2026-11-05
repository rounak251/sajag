"""Download the best-match rain the live job uses to fill days NASA POWER has not published."""
import time

import pandas as pd
import requests

from sajag.config import PROCESSED, RAW, UPSTREAM

URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"


def main() -> None:
    folder = RAW / "recent_rain"
    folder.mkdir(parents=True, exist_ok=True)
    districts = pd.read_csv(PROCESSED / "district_points.csv")
    points = {f"district_{d.key}": (d.lat, d.lon) for d in districts.itertuples()}
    points.update({f"upstream_{u[0]}": (u[2], u[3]) for u in UPSTREAM})
    names = list(points)
    for year in (2024, 2025, 2026):
        path = folder / f"{year}.parquet"
        if path.exists():
            continue
        r = requests.get(URL, params={
            "latitude": ",".join(str(points[n][0]) for n in names),
            "longitude": ",".join(str(points[n][1]) for n in names),
            "start_date": f"{year}-04-20", "end_date": f"{year}-10-31",
            "daily": "precipitation_sum", "timezone": "Asia/Kolkata",
        }, timeout=240)
        r.raise_for_status()
        cols = {
            n: pd.Series(d["daily"]["precipitation_sum"], index=pd.to_datetime(d["daily"]["time"]))
            for n, d in zip(names, r.json())
        }
        table = pd.DataFrame(cols)
        table.index.name = "date"
        table.to_parquet(path)
        print(year, table.shape, round(float(table.isna().mean().mean()), 4), flush=True)
        time.sleep(5)


if __name__ == "__main__":
    main()
