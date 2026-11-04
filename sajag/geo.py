"""Bihar's 38 districts, with name matching for the flood inventory."""
import re

import geopandas as gpd

from sajag.config import PROCESSED, RAW

# The inventory and the boundary file spell these differently.
ALIASES = {
    "purbi champaran": "east champaran",
    "purba champaran": "east champaran",
    "pashchim champaran": "west champaran",
    "paschim champaran": "west champaran",
    "kaimur (bhabua)": "kaimur",
    "bhabua": "kaimur",
    "monghyr": "munger",
    "sheikhpura": "sheikhpura",
    "sheikpura": "sheikhpura",
    "shekhpura": "sheikhpura",
    "purnea": "purnia",
    "purniya": "purnia",
    "jahanabad": "jehanabad",
    "jamuei": "jamui",
    "aurangabad (bh)": "aurangabad",
    "samstipur": "samastipur",
    "gopalgunj": "gopalganj",
    "kishangunj": "kishanganj",
    "muzzaffarpur": "muzaffarpur",
    "mazaffarpur": "muzaffarpur",
    "muzafarpur": "muzaffarpur",
}


def key(name: str) -> str:
    """Normalise a district name to a lowercase key with spelling variants folded in."""
    clean = re.sub(r"\s+", " ", str(name).strip().lower())
    return ALIASES.get(clean, clean).replace(" ", "_")


def bihar_districts() -> gpd.GeoDataFrame:
    """Districts inside the Bihar outline, with a key, a centroid and an area."""
    path = PROCESSED / "districts.geojson"
    if path.exists():
        gdf = gpd.read_file(path)
    else:
        gdf = _extract()
        gdf.to_file(path, driver="GeoJSON")
    pts = gdf.geometry.representative_point()
    gdf["lat"], gdf["lon"] = pts.y, pts.x
    return gdf


def _extract() -> gpd.GeoDataFrame:
    india = gpd.read_file(RAW / "india_adm2.geojson")
    col = "shapeName"
    names = {
        "araria", "arwal", "aurangabad", "banka", "begusarai", "bhagalpur", "bhojpur", "buxar",
        "darbhanga", "east champaran", "gaya", "gopalganj", "jamui", "jehanabad", "kaimur",
        "katihar", "khagaria", "kishanganj", "lakhisarai", "madhepura", "madhubani", "munger",
        "muzaffarpur", "nalanda", "nawada", "patna", "purnia", "rohtas", "saharsa", "samastipur",
        "saran", "sheikhpura", "sheohar", "sitamarhi", "siwan", "supaul", "vaishali",
        "west champaran",
    }
    india["key"] = india[col].map(key)
    box = india.cx[83.2:88.4, 24.2:27.6]
    out = box[box["key"].str.replace("_", " ").isin(names)].copy()
    # Aurangabad also exists in Maharashtra; the box above keeps only Bihar's.
    out = out.drop_duplicates("key")[["key", col, "geometry"]].rename(columns={col: "name"})
    return out.sort_values("key").reset_index(drop=True)
