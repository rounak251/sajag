"""Draw Bihar's main rivers for the map, from OpenStreetMap."""
import json

import geopandas as gpd
import requests
from shapely.geometry import LineString
from shapely.ops import linemerge, unary_union

from sajag.config import PROCESSED, RAW

URL = "https://overpass-api.de/api/interpreter"
NAMES = {
    "Ganga": "Ganga|Ganges|गंगा", "Kosi": "Kosi|Koshi|Sapta Koshi|कोसी", "Gandak": "Gandak|Narayani",
    "Burhi Gandak": "Burhi Gandak|Budhi Gandak|Sikrahna", "Bagmati": "Bagmati", "Kamla": "Kamla|Kamala",
    "Mahananda": "Mahananda", "Ghaghara": "Ghaghara|Ghaghra|Sarju|Saryu", "Sone": "^Son$|^Sone$|Son River",
    "Punpun": "Punpun",
}


def main() -> None:
    path = RAW / "geo" / "osm_rivers.json"
    if not path.exists():
        pattern = "|".join(NAMES.values())
        query = (
            f'[out:json][timeout:170];way["waterway"="river"]["name"~"{pattern}",i]'
            "(24.2,83.2,27.6,88.4);out geom;"
        )
        r = requests.post(URL, data={"data": query}, timeout=200,
                          headers={"User-Agent": "sajag-research/0.1"})
        r.raise_for_status()
        path.write_bytes(r.content)
    ways = json.loads(path.read_text())["elements"]
    rows = []
    import re
    for name, pattern in NAMES.items():
        lines = [
            LineString([(p["lon"], p["lat"]) for p in w["geometry"]]) for w in ways
            if re.search(pattern, w["tags"].get("name", ""), re.IGNORECASE) and len(w["geometry"]) > 1
        ]
        if lines:
            rows.append({"name": name, "geometry": linemerge(unary_union(lines)).simplify(0.004)})
    gdf = gpd.GeoDataFrame(rows, crs=4326)
    print(gdf.assign(n=gdf.geometry.length.round(2))[["name", "n"]].to_string())
    gdf.to_file(PROCESSED / "rivers.geojson", driver="GeoJSON", COORDINATE_PRECISION=4)


if __name__ == "__main__":
    main()
