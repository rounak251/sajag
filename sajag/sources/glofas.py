"""GloFAS river discharge through the Open-Meteo Flood API. No API key, 1984 to +7 months."""
import time

import pandas as pd
import requests

URL = "https://flood-api.open-meteo.com/v1/flood"
CELL = 0.05


class RateLimited(RuntimeError):
    pass


def _get(params: dict, retries: int = 5) -> dict | list:
    for attempt in range(retries):
        try:
            r = requests.get(URL, params=params, timeout=120)
        except requests.RequestException:
            # A timeout on one site once failed the whole daily run on GitHub's servers.
            if attempt == retries - 1:
                raise
            time.sleep(15 * (attempt + 1))
            continue
        if r.status_code == 429:
            reason = r.text[:200]
            if "Hourly" in reason or "Daily" in reason:
                raise RateLimited(reason)
            time.sleep(65)
            continue
        if r.ok:
            return r.json()
        time.sleep(3 * (attempt + 1))
    r.raise_for_status()
    raise RuntimeError("unreachable")


def window_cells(lat: float, lon: float, radius: int = 3) -> list[tuple[float, float]]:
    """Cell centres in a square of (2*radius+1)^2 around a point."""
    return [
        (round(lat + i * CELL, 3), round(lon + j * CELL, 3))
        for i in range(-radius, radius + 1)
        for j in range(-radius, radius + 1)
    ]


def mean_flow(cells: list[tuple[float, float]], start: str, end: str) -> list[dict]:
    """Mean discharge for many cells in one request."""
    data = _get({
        "latitude": ",".join(str(c[0]) for c in cells),
        "longitude": ",".join(str(c[1]) for c in cells),
        "daily": "river_discharge",
        "start_date": start,
        "end_date": end,
    })
    data = data if isinstance(data, list) else [data]
    out = []
    for req, item in zip(cells, data):
        q = [v for v in item["daily"]["river_discharge"] if v is not None]
        out.append({
            "req_lat": req[0], "req_lon": req[1],
            "lat": item["latitude"], "lon": item["longitude"],
            "q": sum(q) / len(q) if q else float("nan"),
        })
    return out


def pick_cell(candidates: list[dict], lat: float, lon: float, low: float, high: float) -> dict:
    """Nearest cell whose flow fits the river, so a tributary never snaps onto the Ganga."""
    fits = [c for c in candidates if low <= c["q"] <= high]
    if not fits:
        raise ValueError(f"no cell in {low}-{high} m3/s near {lat},{lon}")
    return min(fits, key=lambda c: (c["lat"] - lat) ** 2 + (c["lon"] - lon) ** 2)


def history(lat: float, lon: float, start: str, end: str) -> pd.Series:
    data = _get({
        "latitude": lat, "longitude": lon, "daily": "river_discharge",
        "start_date": start, "end_date": end,
    })
    d = data["daily"]
    s = pd.Series(d["river_discharge"], index=pd.to_datetime(d["time"]), dtype="float64")
    s.index.name = "date"
    return s


def forecast(lat: float, lon: float, days: int = 16) -> pd.DataFrame:
    """Ensemble forecast: control run plus the ensemble spread."""
    variables = ["river_discharge", "river_discharge_mean", "river_discharge_max",
                 "river_discharge_min", "river_discharge_p25", "river_discharge_p75"]
    data = _get({
        "latitude": lat, "longitude": lon, "daily": ",".join(variables),
        "forecast_days": days, "past_days": 3,
    })
    df = pd.DataFrame(data["daily"])
    df["time"] = pd.to_datetime(df["time"])
    return df.set_index("time")
