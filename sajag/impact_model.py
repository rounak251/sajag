"""Stage 2: turn a forecast river state into the chance a district floods.

Trained on recorded floods only. Rain and river inputs are constrained to push risk up, which
keeps a small, noisy label set from teaching the model anything physically backwards.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from sajag import river_model as R
from sajag.features import PLACE_FEATURES, STATE_FEATURES

LOCAL = ["r3", "r7", "r15", "r30", "soil_root", "up_r3", "up_r7", "up_r15",
         "q_max", "q_log_p99", "q_days_high"]
RIVER_FORECAST = [f"{kind}{lead}" for lead in R.LEADS for kind in ("pk", "ex")]
FEATURES = LOCAL + RIVER_FORECAST + STATE_FEATURES + PLACE_FEATURES
RISING = set(LOCAL) | set(RIVER_FORECAST) | set(STATE_FEATURES)
PARAMS = dict(
    n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=300, subsample=0.7,
    subsample_freq=1, colsample_bytree=0.6, reg_lambda=10.0, verbose=-1, n_jobs=4,
    monotone_constraints_method="intermediate",
)


def fit(train: pd.DataFrame, target: str, seed: int = 7, features: list[str] = FEATURES):
    constraints = [1 if f in RISING else 0 for f in features]
    model = lgb.LGBMClassifier(**PARAMS, random_state=seed, monotone_constraints=constraints)
    model.fit(train[features], train[target])
    return model


def onsets(flooded: pd.DataFrame, quiet_days: int = 7) -> pd.DataFrame:
    """First day of each flood per district, after at least `quiet_days` without one."""
    prior = flooded.astype(float).shift(1).rolling(quiet_days, min_periods=1).max().fillna(0)
    table = flooded & (prior == 0)
    stacked = table.stack()
    out = stacked[stacked].reset_index()
    out.columns = ["date", "district", "x"]
    return out[["date", "district"]]


def alerts_at_budget(score: pd.Series, budget: float) -> pd.Series:
    """Alert on the top `budget` share of district-days, so every method spends the same."""
    return score >= score.quantile(1 - budget)


def caught(alerts: pd.Series, events: pd.DataFrame, min_lead: int, window: int = 7) -> np.ndarray:
    """For each flood onset, did an alert fire between `window` and `min_lead` days before it?"""
    wide = alerts.unstack("district")
    out = []
    for e in events.itertuples():
        days = pd.date_range(
            e.date - pd.Timedelta(days=window), e.date - pd.Timedelta(days=min_lead),
        )
        out.append(bool(wide[e.district].reindex(days).fillna(False).any()))
    return np.array(out)


def lead_times(alerts: pd.Series, events: pd.DataFrame, window: int = 7) -> np.ndarray:
    """Days of warning for each onset: how early the first alert in the window fired."""
    wide = alerts.unstack("district")
    out = []
    for e in events.itertuples():
        days = pd.date_range(e.date - pd.Timedelta(days=window), e.date - pd.Timedelta(days=1))
        hits = wide[e.district].reindex(days).fillna(False)
        out.append((e.date - hits[hits].index[0]).days if hits.any() else 0)
    return np.array(out)


def precision_of_alerts(alerts: pd.Series, flooded: pd.DataFrame, window: int = 7) -> float:
    """Share of alert days followed by a recorded flood within `window` days."""
    ahead = flooded.astype(float).iloc[::-1].rolling(window, min_periods=1).max().iloc[::-1]
    ahead = ahead.shift(-1).fillna(0).stack()
    ahead.index.names = ["date", "district"]
    fired = alerts[alerts].index
    return float(ahead.reindex(fired).fillna(0).mean())
