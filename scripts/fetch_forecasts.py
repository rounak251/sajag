"""Download archived rain forecasts. The archive starts in January 2024."""
import sys
import time

from sajag.config import RAW, UPSTREAM
from sajag.geo import bihar_districts
from sajag.sources import nwp

SEASONS = (2024, 2025, 2026)


def main() -> None:
    folder = RAW / "nwp"
    folder.mkdir(parents=True, exist_ok=True)
    points = [(f"district_{d.key}", round(d.lat, 3), round(d.lon, 3))
              for d in bihar_districts().itertuples()]
    points += [(f"upstream_{u[0]}", u[2], u[3]) for u in UPSTREAM]
    done = 0
    for year in SEASONS:
        for model in nwp.MODELS:
            for name, lat, lon in points:
                path = folder / f"{model}__{name}__{year}.parquet"
                if path.exists():
                    continue
                try:
                    df = nwp.archived(lat, lon, f"{year}-05-25", f"{year}-10-31", model)
                except nwp.RateLimited as err:
                    print("limit, waiting", err, flush=True)
                    time.sleep(900)
                    df = nwp.archived(lat, lon, f"{year}-05-25", f"{year}-10-31", model)
                df.to_parquet(path)
                done += 1
                if done % 25 == 0:
                    print(year, model, name, done, int(df.notna().sum().min()), flush=True)
                time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 3)
    print("finished", done, flush=True)


if __name__ == "__main__":
    main()
