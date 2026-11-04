"""Drought from rainfall deficit, using the Standardised Precipitation Index (SPI).

SPI is the WMO-recommended drought index: rainfall over a window, expressed as standard
deviations from what is normal for that calendar month. Reference years stop before the test
years, so a future drought cannot change how past months are scored.
"""
import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy import stats

REF_YEARS = (1985, 2014)
DROUGHT_SPI = -1.0
FEATURES = ["spi1", "spi3", "spi6", "soil", "month", "lat", "lon"]
SEASON = (6, 7, 8, 9, 10)
PARAMS = dict(
    n_estimators=120, learning_rate=0.05, num_leaves=7, min_child_samples=60, subsample=0.8,
    subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0, verbose=-1, n_jobs=4, random_state=7,
)


def spi(monthly: pd.Series, window: int) -> pd.Series:
    """Fit a gamma curve per calendar month on the reference years, then map to a normal score."""
    total = monthly.rolling(window).sum()
    out = pd.Series(np.nan, index=total.index)
    lo, hi = REF_YEARS
    for month in range(1, 13):
        here = total.index.month == month
        ref = total[here & (total.index.year >= lo) & (total.index.year <= hi)].dropna()
        wet = ref[ref > 0]
        p_zero = 1 - len(wet) / max(len(ref), 1)
        if len(wet) < 8:
            continue
        shape, _, scale = stats.gamma.fit(wet, floc=0)
        cdf = p_zero + (1 - p_zero) * stats.gamma.cdf(total[here].clip(lower=0), shape, scale=scale)
        out[here] = stats.norm.ppf(np.clip(cdf, 0.001, 0.999))
    return out


def monthly_table(rain: pd.DataFrame, soil: pd.DataFrame, districts: pd.DataFrame) -> pd.DataFrame:
    """One row per district per month, indexed by (month, district)."""
    month_rain = rain.resample("MS").sum(min_count=20)
    month_soil = soil.resample("MS").mean()
    frames = []
    for d in districts.itertuples():
        f = pd.DataFrame({
            "spi1": spi(month_rain[d.key], 1),
            "spi3": spi(month_rain[d.key], 3),
            "spi6": spi(month_rain[d.key], 6),
            "soil": month_soil[d.key],
        })
        norm = f["soil"].groupby(f.index.month).transform("mean")
        f["soil"] = f["soil"] - norm
        f["month"] = f.index.month
        f["lat"], f["lon"] = d.lat, d.lon
        f["district"] = d.key
        f["target"] = (f["spi3"].shift(-1) <= DROUGHT_SPI).astype(float).where(
            f["spi3"].shift(-1).notna()
        )
        frames.append(f)
    out = pd.concat(frames)
    out.index.name = "month_start"
    return out.reset_index().set_index(["month_start", "district"]).sort_index()


def fit(train: pd.DataFrame) -> lgb.LGBMClassifier:
    keep = train["target"].notna() & train["spi6"].notna()
    model = lgb.LGBMClassifier(**PARAMS)
    model.fit(train.loc[keep, FEATURES], train.loc[keep, "target"])
    return model


def season_rows(table: pd.DataFrame) -> pd.DataFrame:
    months = table.index.get_level_values("month_start").month
    return table[np.isin(months, (5, 6, 7, 8, 9))]  # issue month: forecasts June to October


def year_summary(table: pd.DataFrame, chance: pd.Series, declared: set[int]) -> pd.DataFrame:
    """How dry each season looked, against the years Bihar really declared drought.

    `aug_share` is what was known at the end of August, before most declarations were made:
    the share of districts in drought by SPI-3. `july_chance` is the forecast from the end of
    July: the mean chance of drought a month later.
    """
    dates = table.index.get_level_values("month_start")
    rows = []
    for year in sorted(set(dates.year)):
        aug = table[(dates.year == year) & (dates.month == 8)]
        jul = chance[(dates.year == year) & (dates.month == 7)]
        if aug.empty or aug["spi3"].isna().all():
            continue
        rows.append({
            "year": int(year),
            "declared": year in declared,
            "aug_share": float((aug["spi3"] <= DROUGHT_SPI).mean()),
            "july_chance": float(jul.mean()) if len(jul) else float("nan"),
        })
    return pd.DataFrame(rows)
