"""Score how exposed every named village in Bihar is to flooding.

Exposure uses two open sources: how often satellites have seen water near the village since 1984
(JRC Global Surface Water, which ends in 2021) and how low it sits compared with the land around
it (Copernicus GLO-90). Neither knows about any 2024 flood, so the flood map below is a fair test.
"""
import json
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.merge import merge
from rasterio.transform import rowcol
from rasterio.windows import from_bounds
from scipy import ndimage

from sajag.config import ARTIFACTS, PROCESSED, RAW, ROOT
from sajag.geo import bihar_districts

GEO = RAW / "geo"
BOUNDS = (83.2, 24.2, 88.4, 27.6)
BLOCK = 30  # 30 JRC pixels: about 900 m
WATER_WEIGHT = 0.65
HIGH, MEDIUM = 80, 50
# A Sentinel-1 flood map of the Kosi plain for 9 October 2024, from the author's earlier SARITA
# project. Only used to test the score, and optional, so the pipeline runs without it.
FLOOD_MAP = ROOT.parents[2] / "nitp_6th_sem_project/sarita/data/bihar/kosi_2024-10-09_floodclass.tif"


def load_places(districts: gpd.GeoDataFrame) -> pd.DataFrame:
    """GeoNames villages, with OSM filling districts GeoNames covers thinly."""
    names = ["gid", "name", "ascii", "alt", "lat", "lon", "fclass", "fcode", "cc", "cc2", "a1", "a2", "a3", "a4", "pop", "elev", "dem", "tz", "mod"]
    with zipfile.ZipFile(GEO / "IN.zip") as z:
        df = pd.read_csv(z.open("IN.txt"), sep="\t", names=names, low_memory=False)
    geo = df[df["fclass"] == "P"][["name", "lat", "lon"]].assign(src="geonames")
    osm = json.loads((GEO / "osm_places.json").read_text())["elements"]
    extra = pd.DataFrame([
        {"name": e["tags"].get("name"), "lat": e["lat"], "lon": e["lon"], "src": "osm"}
        for e in osm if e["tags"].get("name")
    ])
    both = pd.concat([geo, extra], ignore_index=True)
    points = gpd.GeoDataFrame(
        both, geometry=gpd.points_from_xy(both["lon"], both["lat"]), crs=4326,
    )
    joined = gpd.sjoin(points, districts[["key", "geometry"]], predicate="within")
    joined["cell"] = (joined["lat"].round(3).astype(str) + joined["lon"].round(3).astype(str))
    out = joined.drop_duplicates(["cell"]).drop_duplicates(["name", "key"])
    return pd.DataFrame(out[["name", "lat", "lon", "key", "src"]]).reset_index(drop=True)


def water_share() -> tuple[np.ndarray, rasterio.Affine]:
    """Share of each 900 m block where satellites have seen water at least 5% of the time."""
    with rasterio.open(GEO / "jrc_occurrence.tif") as src:
        window = from_bounds(*BOUNDS, src.transform)
        occ = src.read(1, window=window)
        transform = src.window_transform(window)
    h, w = (occ.shape[0] // BLOCK) * BLOCK, (occ.shape[1] // BLOCK) * BLOCK
    wet = ((occ[:h, :w] >= 5) & (occ[:h, :w] <= 100)).astype("float32")
    share = wet.reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).mean(axis=(1, 3))
    # Widen to about 2.7 km, so a village beside a channel counts as beside it.
    return ndimage.uniform_filter(share, 3), transform * transform.scale(BLOCK, BLOCK)


def relative_height() -> tuple[np.ndarray, rasterio.Affine]:
    """Height above the lowest ground within about 5 km, after smoothing out DEM noise."""
    sources = [rasterio.open(p) for p in sorted(GEO.glob("dem_N*.tif"))]
    dem, transform = merge(sources, bounds=BOUNDS)
    for s in sources:
        s.close()
    dem = ndimage.median_filter(dem[0].astype("float32"), 5)
    return dem - ndimage.minimum_filter(dem, 55), transform


def sample(grid: np.ndarray, transform, lat: pd.Series, lon: pd.Series) -> np.ndarray:
    rows, cols = rowcol(transform, lon.values, lat.values)
    rows = np.clip(rows, 0, grid.shape[0] - 1)
    cols = np.clip(cols, 0, grid.shape[1] - 1)
    return grid[rows, cols]


def flooded_share(places: pd.DataFrame) -> pd.Series | None:
    """Share of a 500 m box around each village mapped as flood, where the map covers it."""
    if not FLOOD_MAP.exists():
        return None
    with rasterio.open(FLOOD_MAP) as src:
        cls = src.read(1)
        pts = gpd.GeoSeries(
            gpd.points_from_xy(places["lon"], places["lat"]), crs=4326,
        ).to_crs(src.crs)
        rows, cols = rowcol(src.transform, pts.x.values, pts.y.values)
    rows, cols = np.array(rows), np.array(cols)
    pad = 25  # 25 pixels of 10 m each way
    inside = (rows > pad) & (rows < cls.shape[0] - pad) & (cols > pad) & (cols < cls.shape[1] - pad)
    out = pd.Series(np.nan, index=places.index)
    for i in np.flatnonzero(inside):
        box = cls[rows[i] - pad : rows[i] + pad, cols[i] - pad : cols[i] + pad]
        out.iloc[i] = float((box == FLOOD_CLASS).mean())
    return out


FLOOD_CLASS = 2


def validate(places: pd.DataFrame) -> dict | None:
    """Did villages scored as exposed really see more flood water in October 2024?"""
    share = flooded_share(places)
    if share is None:
        return None
    test = places.assign(share=share).dropna(subset=["share"])
    rate = test.groupby("cls")["share"].agg(
        any_water=lambda s: float((s > 0).mean()),
        over_5pct=lambda s: float((s >= 0.05).mean()),
        mean_share="mean",
        n="size",
    )
    return {
        "villages": len(test),
        "date": "2024-10-09",
        "rule": "any mapped flood water in the 500 m box around the village",
        "high_flooded": rate.loc[2, "any_water"], "medium_flooded": rate.loc[1, "any_water"],
        "low_flooded": rate.loc[0, "any_water"],
        "ratio": rate.loc[2, "any_water"] / rate.loc[0, "any_water"],
        "high_over_5pct": rate.loc[2, "over_5pct"], "medium_over_5pct": rate.loc[1, "over_5pct"],
        "low_over_5pct": rate.loc[0, "over_5pct"],
        "high_n": int(rate.loc[2, "n"]), "medium_n": int(rate.loc[1, "n"]),
        "low_n": int(rate.loc[0, "n"]),
    }


def main() -> None:
    districts = bihar_districts()
    places = load_places(districts)
    print("places", len(places), places["src"].value_counts().to_dict(), flush=True)

    share, t1 = water_share()
    height, t2 = relative_height()
    places["water"] = sample(share, t1, places["lat"], places["lon"])
    places["height"] = sample(height, t2, places["lat"], places["lon"])
    wet_rank = places["water"].rank(pct=True)
    low_rank = 1 - places["height"].rank(pct=True)
    score = WATER_WEIGHT * wet_rank + (1 - WATER_WEIGHT) * low_rank
    places["exposure"] = (score.rank(pct=True) * 100).round().astype(int)
    places["cls"] = np.select(
        [places["exposure"] >= HIGH, places["exposure"] >= MEDIUM], [2, 1], default=0,
    )

    result = validate(places)
    print(json.dumps(result, indent=1), flush=True)
    (ARTIFACTS / "metrics_exposure.json").write_text(json.dumps(result, indent=1))

    counts = places.groupby("key").size()
    print("per district min", counts.nsmallest(5).to_dict(), flush=True)
    places.to_parquet(PROCESSED / "villages.parquet")


if __name__ == "__main__":
    main()
