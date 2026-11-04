"""Load the saved models. Used by the blind test and the live forecast, so both run the exact
files that training froze."""
import json
from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd

from sajag import impact_model as I
from sajag import river_model as R
from sajag.config import ARTIFACTS

LEVELS = ("watch", "warning", "severe")


@dataclass
class Frozen:
    impact: dict
    river: dict
    reference: dict

    def score(self, table: pd.DataFrame, lead: int) -> pd.Series:
        """Raw model score: the mean over the seed bag."""
        x = table[I.FEATURES]
        raw = np.mean([b.predict(x) for b in self.impact[lead]], axis=0)
        return pd.Series(raw, index=table.index)

    def calibrate(self, score: pd.Series, lead: int) -> pd.Series:
        c = self.reference["calibration"][str(lead)]
        return pd.Series(np.interp(score, c["x"], c["y"]), index=score.index)

    def level(self, score7: pd.Series) -> pd.Series:
        """0 Normal, 1 Watch, 2 Warning, 3 Severe, from the 7-day score."""
        t = self.reference["thresholds"]
        out = pd.Series(0, index=score7.index, dtype="int64")
        for i, name in enumerate(LEVELS, start=1):
            out[score7 >= t[name]] = i
        return out

    def reasons(self, table: pd.DataFrame) -> pd.DataFrame:
        """SHAP values for the 7-day score, summed into groups a person can read."""
        x = table[I.FEATURES]
        raw = np.mean([b.predict(x, pred_contrib=True) for b in self.impact[7]], axis=0)
        c = pd.DataFrame(raw[:, :-1], columns=I.FEATURES, index=table.index)
        return pd.DataFrame({
            g: c[[f for f in cols if f in c.columns]].sum(axis=1)
            for g, cols in self.reference["reason_groups"].items()
        })

    def river_forecast(self, table: pd.DataFrame) -> pd.DataFrame:
        """Predicted peak (log ratio to the site's p99) and exceedance chance per lead."""
        x = table[R.SITE_FEATURES]
        out = {}
        for lead in R.LEADS:
            out[f"pk{lead}"] = self.river[("peak", lead)].predict(x)
            out[f"ex{lead}"] = self.river[("exceed", lead)].predict(x)
        return pd.DataFrame(out, index=table.index)


def load() -> Frozen:
    impact = {
        lead: [
            lgb.Booster(model_file=str(ARTIFACTS / f"impact_{lead}_{i}.txt"))
            for i in range(len(I.SEEDS))
        ]
        for lead in R.LEADS
    }
    river = {
        (kind, lead): lgb.Booster(model_file=str(ARTIFACTS / f"river_{kind}_{lead}.txt"))
        for kind in ("peak", "exceed") for lead in R.LEADS
    }
    reference = json.loads((ARTIFACTS / "reference.json").read_text())
    return Frozen(impact, river, reference)
