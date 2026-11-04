"""Scores that answer what a disaster officer would ask, with honest uncertainty."""
import numpy as np
import pandas as pd

from sajag import impact_model as I


def onset_events(flooded: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Flood onsets tagged with the event they belong to, for bootstrapping by event."""
    on = I.onsets(flooded)
    on = on[on["date"].dt.month.between(6, 10)].reset_index(drop=True)
    uei = []
    for r in on.itertuples():
        match = events[
            (events["district"] == r.district)
            & (events["start"] <= r.date)
            & (events["end"] >= r.date)
        ]
        uei.append(match["uei"].iloc[0] if len(match) else None)
    on["event"] = uei
    return on


def bootstrap_by_event(
    values: dict[str, np.ndarray], event: pd.Series, n: int = 2000, seed: int = 11,
) -> dict[str, tuple[float, float]]:
    """Confidence intervals that resample whole events.

    Districts in one flood are not independent, so resampling rows would overstate certainty.
    Each entry of `values` is a 0/1 array over onsets. Also returns the difference between the
    first two entries, the comparison that matters.
    """
    rng = np.random.default_rng(seed)
    groups = [np.flatnonzero((event == e).values) for e in event.unique()]
    names = list(values)
    draws: dict[str, list[float]] = {k: [] for k in names}
    diffs: list[float] = []
    for _ in range(n):
        pick = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        for k in names:
            draws[k].append(float(values[k][pick].mean()))
        if len(names) >= 2:
            diffs.append(float(values[names[0]][pick].mean() - values[names[1]][pick].mean()))
    out = {k: tuple(np.quantile(draws[k], [0.025, 0.975])) for k in names}
    if diffs:
        out["difference"] = tuple(np.quantile(diffs, [0.025, 0.975]))
    return out


def reliability(y: pd.Series, p: pd.Series, bins: int = 8) -> list[dict]:
    """Predicted against observed rate, in bins of equal size among the higher scores."""
    edges = np.unique(np.quantile(p, np.linspace(0.5, 1, bins + 1)))
    which = np.digitize(p, edges[1:-1])
    rows = []
    for b in range(len(edges) - 1):
        sel = (which == b) & (p >= edges[0])
        if sel.sum():
            rows.append({
                "predicted": float(p[sel].mean()), "observed": float(y[sel].mean()),
                "n": int(sel.sum()),
            })
    return rows
