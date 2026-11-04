"""Rain forecasts as they were really issued, from the Open-Meteo Previous Runs archive.

`precipitation_previous_dayK` on a date is the forecast for that date made K days earlier, so a
past warning can be tested using only what forecasters had at the time. Two independent global
models are averaged. The choice was fixed on principle, before scoring, not picked per event.
"""
import time

import pandas as pd
import requests

ARCHIVE = "https://previous-runs-api.open-meteo.com/v1/forecast"
LIVE = "https://api.open-meteo.com/v1/forecast"
MODELS = ("ecmwf_ifs025", "gfs_global")
LEADS = (1, 2, 3, 4, 5)


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
    """Rain forecast for the next `days` days, as known on each issue date.

    Issued on t, the forecast for t+k is column k at valid date t+k.
    """
    parts = [valid[k].shift(-k) for k in range(1, days + 1)]
    return pd.concat(parts, axis=1).sum(axis=1, min_count=days)
