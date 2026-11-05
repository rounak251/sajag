"""Rain forecasts from the Open-Meteo Previous Runs archive.

`precipitation_previous_dayK` at an hour is the forecast for that hour from about K days earlier.
It is a sliding window, not one model run: for one valid day it stitches runs started across a
whole day. So a forecast for t+k uses column k+1, not k. That draws only on runs started by 18Z on
t-1, which were published by about 07:00 IST on t, ahead of the 08:00 IST issue time. Column k would
use runs from later on day t, which nobody could have seen that morning.

Two independent global models are averaged. That choice was fixed on principle before scoring.
"""
import time

import pandas as pd
import requests

ARCHIVE = "https://previous-runs-api.open-meteo.com/v1/forecast"
LIVE = "https://api.open-meteo.com/v1/forecast"
MODELS = ("ecmwf_ifs025", "gfs_global")
LEADS = (1, 2, 3, 4, 5, 6)


class RateLimited(RuntimeError):
    pass


def _get(url: str, params: dict, retries: int = 5) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=120)
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code == 429:
            if "Hourly" in r.text or "Daily" in r.text:
                raise RateLimited(r.text[:160])
            time.sleep(65)
            continue
        if r.ok:
            return r.json()
        time.sleep(3 * (attempt + 1))
    r.raise_for_status()
    raise RuntimeError("unreachable")


def archived(lat: float, lon: float, start: str, end: str, model: str) -> pd.DataFrame:
    """Daily forecast rain by valid date. Column k holds the forecast made k days before."""
    data = _get(ARCHIVE, {
        "latitude": lat, "longitude": lon, "start_date": start, "end_date": end,
        "hourly": ",".join(f"precipitation_previous_day{k}" for k in LEADS),
        "models": model, "timezone": "Asia/Kolkata",
    })
    hourly = pd.DataFrame(data["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"])
    hourly = hourly.set_index("time")
    daily = hourly.resample("D").sum(min_count=20)
    daily.columns = [int(c.rsplit("day", 1)[1]) for c in daily.columns]
    daily.index.name = "valid"
    return daily


def issued_sums(valid: pd.DataFrame, days: int) -> pd.Series:
    """Rain forecast for the next `days` days, as public at 08:00 IST on each issue date."""
    parts = [valid[k + 1].shift(-k) for k in range(1, days + 1)]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=days)
