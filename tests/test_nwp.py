import pandas as pd

from sajag.sources.nwp import issued_sums


def test_issued_sum_uses_runs_public_by_the_issue_time():
    idx = pd.date_range("2024-09-01", periods=6)
    # Column k at valid date v: forecast for v from about k days earlier.
    valid = pd.DataFrame({
        1: [1.0, 2, 3, 4, 5, 6], 2: [10.0, 20, 30, 40, 50, 60], 3: [100.0, 200, 300, 400, 500, 600],
    }, index=idx)
    s = issued_sums(valid, 2)
    # Issued 1 Sept: column 2 for 2 Sept (20) plus column 3 for 3 Sept (300). Column 1 for 2 Sept
    # would use runs from later on 1 Sept, unpublished at 08:00 IST.
    assert s.loc["2024-09-01"] == 320
    assert pd.isna(s.loc["2024-09-05"])
