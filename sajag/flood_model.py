"""Flood probability model and the baselines it has to beat."""
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from sajag.features import FEATURES

PARAMS = dict(
    objective="binary", n_estimators=250, learning_rate=0.03, num_leaves=15,
    min_child_samples=300, subsample=0.7, subsample_freq=1, colsample_bytree=0.6,
    reg_lambda=10.0, verbose=-1, n_jobs=4, random_state=7,
)


def fit(train: pd.DataFrame, target: str, seed: int = 7) -> lgb.LGBMClassifier:
    model = lgb.LGBMClassifier(**{**PARAMS, "random_state": seed})
    model.fit(train[FEATURES], train[target])
    return model


def years_of(df: pd.DataFrame) -> np.ndarray:
    return df.index.get_level_values("date").year.values


def year_blocks(years: list[int], size: int = 3) -> list[list[int]]:
    """Consecutive years held out together, so one big flood year cannot leak across folds."""
    ordered = sorted(years)
    return [ordered[i : i + size] for i in range(0, len(ordered), size)]


def out_of_fold(table: pd.DataFrame, target: str) -> pd.Series:
    """A prediction for every row from a model that never saw that row's years."""
    years = years_of(table)
    pred = pd.Series(np.nan, index=table.index)
    for block in year_blocks(sorted(set(years))):
        held = np.isin(years, block)
        model = fit(table[~held], target)
        pred[held] = model.predict_proba(table.loc[held, FEATURES])[:, 1]
    return pred


def climatology(train: pd.DataFrame, test: pd.DataFrame, target: str) -> pd.Series:
    """How often this district floods at this time of year: the no-skill reference."""
    t = train.reset_index()
    rate = t.groupby(["district", "doy"])[target].mean().unstack("doy")
    rate = rate.reindex(columns=range(150, 310)).T.rolling(15, center=True, min_periods=1).mean().T
    rate = rate.interpolate(axis=1, limit_direction="both")
    d = test.index.get_level_values("district")
    doy = test["doy"].clip(150, 309).values
    return pd.Series(
        [rate.at[a, b] for a, b in zip(d, doy)], index=test.index, dtype="float64",
    )


def logistic(train: pd.DataFrame, test: pd.DataFrame, target: str) -> pd.Series:
    cols = ["r3", "r7", "up_r3", "q_max", "q_log_p99", "soil_root"]
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500))
    model.fit(train[cols].fillna(0), train[target])
    return pd.Series(model.predict_proba(test[cols].fillna(0))[:, 1], index=test.index)


def scores(y: pd.Series, p: pd.Series) -> dict:
    return {"pr_auc": average_precision_score(y, p), "roc_auc": roc_auc_score(y, p)}


def brier_skill(y: pd.Series, p: pd.Series, ref: pd.Series) -> float:
    return 1 - float(((p - y) ** 2).mean()) / float(((ref - y) ** 2).mean())


def compare(train: pd.DataFrame, test: pd.DataFrame, target: str) -> pd.DataFrame:
    """Score the model and every baseline on the same held-out rows."""
    model = fit(train, target)
    runs = {
        "Sajag (LightGBM)": pd.Series(
            model.predict_proba(test[FEATURES])[:, 1], index=test.index,
        ),
        "Climatology": climatology(train, test, target),
        "3-day rain only": test["r3"],
        "River level only": test["q_max"].fillna(0),
        "Logistic regression": logistic(train, test, target),
    }
    onset = test["active"] == 0
    rows = []
    for name, p in runs.items():
        s = scores(test[target], p)
        o = scores(test.loc[onset, target], p[onset])
        rows.append({
            "model": name, "pr_auc": s["pr_auc"], "roc_auc": s["roc_auc"],
            "onset_pr_auc": o["pr_auc"], "onset_roc_auc": o["roc_auc"],
        })
    out = pd.DataFrame(rows).set_index("model")
    out.attrs["base_rate"] = float(test[target].mean())
    out.attrs["onset_base_rate"] = float(test.loc[onset, target].mean())
    out.attrs["model"] = model
    return out
