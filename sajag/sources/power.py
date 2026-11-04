"""Daily rainfall and soil wetness from NASA POWER (MERRA-2). No API key, 1981 to about 3 days ago."""
import io
import time

import pandas as pd
import requests

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "PRECTOTCORR,GWETTOP,GWETROOT"
RENAME = {"PRECTOTCORR": "rain", "GWETTOP": "soil_top", "GWETROOT": "soil_root"}


def parse_power_csv(text: str) -> pd.DataFrame:
    """Turn a POWER CSV response into a date-indexed frame with -999/-99 fills as missing."""
    body = text.split("-END HEADER-", 1)[1].lstrip()
    df = pd.read_csv(io.StringIO(body))
    date = pd.to_datetime(
        df["YEAR"].astype(str) + df["DOY"].astype(str).str.zfill(3), format="%Y%j"
    )
    out = df.rename(columns=RENAME)[list(RENAME.values())].set_index(date)
    out.index.name = "date"
    return out.mask(out <= -99)


def fetch_point(lat: float, lon: float, start: str, end: str, retries: int = 4) -> pd.DataFrame:
    params = {
        "parameters": PARAMS,
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": start.replace("-", ""),
        "end": end.replace("-", ""),
        "format": "CSV",
    }
    for attempt in range(retries):
        try:
            r = requests.get(URL, params=params, timeout=90)
            r.raise_for_status()
            return parse_power_csv(r.text)
        except (requests.RequestException, IndexError):
            if attempt == retries - 1:
                raise
            time.sleep(4 * (attempt + 1))
    raise RuntimeError("unreachable")
