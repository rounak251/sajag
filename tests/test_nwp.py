import pandas as pd

from sajag.sources.nwp import issued_sums


def test_issued_sum_uses_only_the_forecast_made_on_the_issue_date():
    idx = pd.date_range("2024-09-01", periods=6)
    # Column k at valid date v: forecast for v made k days earlier.
    valid = pd.DataFrame({1: [1.0, 2, 3, 4, 5, 6], 2: [10.0, 20, 30, 40, 50, 60]}, index=idx)
    s = issued_sums(valid, 2)
    # Issued on 1 Sept: 1-day forecast for 2 Sept (2) plus 2-day forecast for 3 Sept (30).
    assert s.loc["2024-09-01"] == 32
    assert pd.isna(s.loc["2024-09-05"])  # the 2-day forecast for 7 Sept is not in the table
