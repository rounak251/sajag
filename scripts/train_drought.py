"""Train the one-month drought forecast and test it against years Bihar really declared drought."""
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from sajag import dataset
from sajag import drought as D
from sajag import flood_model as M
from sajag.config import ARTIFACTS, PROCESSED, ROOT
from sajag.geo import bihar_districts


def main() -> None:
    districts = bihar_districts()
    points = dataset.load_points()
    table = D.monthly_table(points["rain"], points["soil_root"], districts)
    table = table[table.index.get_level_values("month_start").year >= 1986]

    season = D.season_rows(table).dropna(subset=["spi6"])
    years = season.index.get_level_values("month_start").year.values
    chance = pd.Series(np.nan, index=season.index)
    for block in M.year_blocks(sorted(set(years))):
        held = np.isin(years, block)
        model = D.fit(season[~held])
        chance[held] = model.predict_proba(season.loc[held, D.FEATURES])[:, 1]

    scored = season["target"].notna()
    y = season.loc[scored, "target"]
    persistence = (-season.loc[scored, "spi3"]).fillna(0)
    forecast = {
        "base_rate": float(y.mean()),
        "ap_model": float(average_precision_score(y, chance[scored])),
        "ap_persistence": float(average_precision_score(y, persistence)),
        "auc_model": float(roc_auc_score(y, chance[scored])),
        "auc_persistence": float(roc_auc_score(y, persistence)),
    }
    print(json.dumps(forecast, indent=1))

    declared_rows = pd.read_csv(ROOT / "data" / "reference" / "declared_droughts.csv")
    declared = set(declared_rows["year"])
    summary = D.year_summary(season, chance, declared)
    summary = summary[summary["year"] >= 1997]
    print(summary.round(3).to_string())
    labels = summary["declared"].astype(int)
    known = summary["july_chance"].notna()
    result = {
        "forecast": forecast,
        "auc_august": float(roc_auc_score(labels, summary["aug_share"])),
        "auc_july_forecast": float(roc_auc_score(labels[known], summary.loc[known, "july_chance"])),
        "rows": summary.to_dict("records"),
        "note": (
            "Six declared years among the seasons scored, so these scores are rough. Declarations "
            "are political and administrative decisions as well as rainfall ones."
        ),
    }
    print({k: round(v, 3) for k, v in result.items() if k.startswith("auc")})
    (ARTIFACTS / "metrics_drought.json").write_text(json.dumps(result, indent=1))

    final = D.fit(season)
    final.booster_.save_model(str(ARTIFACTS / "drought.txt"))
    out = table[["spi3"]].copy()
    out["chance"] = final.predict_proba(table[D.FEATURES])[:, 1]
    out.loc[chance.index, "chance"] = chance  # past seasons show the honest out-of-fold value
    out.to_parquet(PROCESSED / "drought.parquet")


if __name__ == "__main__":
    main()
