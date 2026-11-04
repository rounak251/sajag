"""Stage 1: forecast each river's peak flow over the next few days.

Recorded disasters are too few to teach a model how rivers behave, but river flow is dense:
27 sites x 29 years of daily values. This stage learns the hydrology. Stage 2 (impact_model.py)
then learns which river states actually hurt people.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd

from sajag import features as F

LEADS = (1, 3, 5, 7)
SITE_FEATURES = [
    "q_pct", "q_over", "rise1", "rise3", "rise7", "up_over", "up_rise1", "up_rise3",
    "b_r1", "b_r3", "b_r7", "b_r15", "l_r1", "l_r3", "l_r7", "l_soil", "size", "doy",
]
# More rain or more water upstream can never lower the forecast.
RISING = {
    "q_pct", "q_over", "up_over", "b_r1", "b_r3", "b_r7", "b_r15",
    "l_r1", "l_r3", "l_r7", "l_soil",
}
PARAMS = dict(
    n_estimators=220, learning_rate=0.05, num_leaves=31, min_child_samples=200,
    subsample=0.7, subsample_freq=1, colsample_bytree=0.7, reg_lambda=5.0, verbose=-1,
    n_jobs=4, random_state=7, monotone_constraints_method="intermediate",
)


def _constraints() -> list[int]:
    return [1 if f in RISING else 0 for f in SITE_FEATURES]


def upstream_of(sites: pd.DataFrame) -> dict[str, list[str]]:
    """Sites listed earlier on the same river lie upstream. Config lists them top to bottom."""
    out: dict[str, list[str]] = {}
    for _river, group in sites.groupby("river", sort=False):
        ids = group["site_id"].tolist()
        for i, sid in enumerate(ids):
            out[sid] = ids[:i]
    return out


def site_table(
    q: pd.DataFrame,
    ref: dict[str, np.ndarray],
    upstream_rain: pd.DataFrame,
    rain: pd.DataFrame,
    soil_root: pd.DataFrame,
    sites: pd.DataFrame,
    districts: pd.DataFrame,
) -> pd.DataFrame:
    """Long table indexed by (date, site)."""
    tables = F.river_tables(q, ref)
    basins = F.basin_rain(upstream_rain)
    sums = {n: basins.rolling(n, min_periods=1).sum() for n in (1, 3, 7, 15)}
    local = {n: rain.rolling(n, min_periods=1).sum() for n in (1, 3, 7)}
    above = upstream_of(sites)
    frames = []
    for s in sites.itertuples():
        dist = np.hypot(districts["lat"] - s.lat, districts["lon"] - s.lon)
        near = districts.iloc[int(np.argmin(dist.values))]["key"]
        basin = s.river if s.river in basins.columns else "Ganga"
        f = pd.DataFrame({
            "q_pct": tables["pct"][s.site_id],
            "q_over": tables["over"][s.site_id],
            "rise1": tables["rise1"][s.site_id],
            "rise3": tables["rise3"][s.site_id],
            "rise7": tables["rise7"][s.site_id],
        })
        ups = above[s.site_id]
        f["up_over"] = tables["over"][ups].max(axis=1) if ups else np.nan
        f["up_rise1"] = tables["rise1"][ups].max(axis=1) if ups else np.nan
        f["up_rise3"] = tables["rise3"][ups].max(axis=1) if ups else np.nan
        for n in (1, 3, 7, 15):
            f[f"b_r{n}"] = sums[n][basin].reindex(f.index)
        for n in (1, 3, 7):
            f[f"l_r{n}"] = local[n][near].reindex(f.index)
        f["l_soil"] = soil_root[near].reindex(f.index)
        f["size"] = np.log(np.quantile(ref[s.site_id], 0.99))
        f["doy"] = f.index.day_of_year
        f["site"] = s.site_id
        for lead in LEADS:
            ahead = tables["over"][s.site_id].iloc[::-1].rolling(lead, min_periods=lead).max()
            f[f"peak{lead}"] = ahead.iloc[::-1].shift(-1)
        frames.append(f)
    out = pd.concat(frames)
    out.index.name = "date"
    return out.reset_index().set_index(["date", "site"]).sort_index()


def fit_peak(train: pd.DataFrame, lead: int) -> lgb.LGBMRegressor:
    keep = train[f"peak{lead}"].notna()
    model = lgb.LGBMRegressor(**PARAMS, monotone_constraints=_constraints())
    model.fit(train.loc[keep, SITE_FEATURES], train.loc[keep, f"peak{lead}"])
    return model


def fit_exceed(train: pd.DataFrame, lead: int) -> lgb.LGBMClassifier:
    keep = train[f"peak{lead}"].notna()
    model = lgb.LGBMClassifier(**PARAMS, monotone_constraints=_constraints())
    model.fit(train.loc[keep, SITE_FEATURES], (train.loc[keep, f"peak{lead}"] >= 0).astype(int))
    return model


def predict_block(models: dict, table: pd.DataFrame) -> pd.DataFrame:
    """Predicted peak and exceedance probability for every lead."""
    out = {}
    for lead in LEADS:
        out[f"pk{lead}"] = models[("peak", lead)].predict(table[SITE_FEATURES])
        out[f"ex{lead}"] = models[("exceed", lead)].predict_proba(table[SITE_FEATURES])[:, 1]
    return pd.DataFrame(out, index=table.index)


def fit_all(train: pd.DataFrame) -> dict:
    models = {}
    for lead in LEADS:
        models[("peak", lead)] = fit_peak(train, lead)
        models[("exceed", lead)] = fit_exceed(train, lead)
    return models


def to_district(pred: pd.DataFrame, near: dict[str, list[str]]) -> pd.DataFrame:
    """Each district takes the worst predicted state among its nearest river sites."""
    wide = pred.unstack("site")
    frames = {}
    for district, ids in near.items():
        block = {}
        for col in pred.columns:
            block[col] = wide[col][ids].max(axis=1)
        frames[district] = pd.DataFrame(block)
    out = pd.concat(frames, names=["district"]).swaplevel().sort_index()
    out.index.names = ["date", "district"]
    return out
