"""Download everything the model learns from. Safe to re-run: finished files are skipped."""
import json
import sys
import time

import pandas as pd
import requests

from sajag.config import HISTORY_START, PROCESSED, RAW, SITES, UPSTREAM
from sajag.sources import glofas, power

END = "2025-12-31"
BOUNDARIES = (
    "https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/IND/ADM2/"
    "geoBoundaries-IND-ADM2_simplified.geojson"
)
IFI = (
    "https://raw.githubusercontent.com/hydrosenselab/India-Flood-Inventory/main/"
    "v3.0/India_Flood_Inventory_v3.csv"
)


def download(url: str, path) -> None:
    if path.exists():
        return
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    path.write_bytes(r.content)
    print("downloaded", path.name, len(r.content), flush=True)


def fetch_power(points: list[tuple[str, float, float]]) -> None:
    folder = RAW / "power"
    folder.mkdir(parents=True, exist_ok=True)
    for name, lat, lon in points:
        path = folder / f"{name}.parquet"
        if path.exists():
            continue
        df = power.fetch_point(lat, lon, HISTORY_START, END)
        df.to_parquet(path)
        print("power", name, len(df), flush=True)


def snap_sites() -> pd.DataFrame:
    path = PROCESSED / "sites.csv"
    if path.exists():
        return pd.read_csv(path)
    rows = []
    for sid, river, site, lat, lon, low, high in SITES:
        # Two monsoon fortnights, so one dry spell cannot push a cell below its range.
        cells = glofas.window_cells(lat, lon)
        found = glofas.mean_flow(cells, "2020-08-01", "2020-08-14")
        try:
            cell = glofas.pick_cell(found, lat, lon, low, high)
        except ValueError as err:
            print("SKIP", sid, err, max(c["q"] for c in found), flush=True)
            continue
        rows.append({
            "site_id": sid, "river": river, "site": site, "lat": cell["lat"],
            "lon": cell["lon"], "asked_lat": lat, "asked_lon": lon, "aug2020_q": cell["q"],
        })
        print("snap", sid, round(cell["q"]), cell["lat"], cell["lon"], flush=True)
        time.sleep(6)
    out = pd.DataFrame(rows)
    out.to_csv(path, index=False)
    return out


def fetch_discharge(sites: pd.DataFrame) -> None:
    folder = RAW / "glofas"
    folder.mkdir(parents=True, exist_ok=True)
    for row in sites.itertuples():
        path = folder / f"{row.site_id}.parquet"
        if path.exists():
            continue
        s = glofas.history(row.lat, row.lon, HISTORY_START, END)
        s.to_frame("q").to_parquet(path)
        print("glofas", row.site_id, s.notna().sum(), flush=True)
        time.sleep(4)


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    download(IFI, RAW / "ifi_v3.csv")
    download(BOUNDARIES, RAW / "india_adm2.geojson")

    from sajag.geo import bihar_districts  # needs the boundary file above

    districts = bihar_districts()
    points = [(f"district_{d.key}", round(d.lat, 3), round(d.lon, 3)) for d in districts.itertuples()]
    points += [(f"upstream_{u[0]}", u[2], u[3]) for u in UPSTREAM]
    print(len(points), "rain points", flush=True)

    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("all", "power"):
        fetch_power(points)
    if what in ("all", "glofas"):
        sites = snap_sites()
        fetch_discharge(sites)
    (PROCESSED / "fetch_done.json").write_text(json.dumps({"end": END}))


if __name__ == "__main__":
    main()
