from datetime import date

import pandas as pd

from sajag.geo import key
from sajag.sources.ifi import flood_days, repair_dates, repair_sequence, split_districts


def test_swapped_month_and_day_is_repaired_using_duration():
    # Stored as 7 Nov to 13 Jul with a 3-day duration: really 11 to 13 July.
    s, e, changed = repair_dates("07-11-2017 00:00", "13-07-2017 00:00", 3.0)
    assert (s, e) == (date(2017, 7, 11), date(2017, 7, 13))
    assert changed


def test_swapped_single_day_event_moves_into_the_season():
    # "10-01-2019" for one day: 1 October, not 10 January.
    s, e, changed = repair_dates("10-01-2019 00:00", "10-01-2019 00:00", 1.0)
    assert (s, e) == (date(2019, 10, 1), date(2019, 10, 1))
    assert changed


def test_long_event_start_is_repaired():
    s, e, _ = repair_dates("08-01-2020 00:00", "20-08-2020 00:00", 20.0)
    assert (s, e) == (date(2020, 8, 1), date(2020, 8, 20))


def test_correct_row_is_left_alone():
    s, e, changed = repair_dates("13-08-2017 00:00", "15-08-2017 00:00", 3.0)
    assert (s, e) == (date(2017, 8, 13), date(2017, 8, 15))
    assert not changed


def test_ambiguous_but_valid_monsoon_row_keeps_day_month_order():
    s, e, changed = repair_dates("05-09-2017 00:00", "05-09-2017 00:00", 1.0)
    assert (s, e) == (date(2017, 9, 5), date(2017, 9, 5))
    assert not changed


def test_district_spelling_variants_fold_together():
    assert key("Purbi Champaran") == "east_champaran"
    assert key(" Kaimur (Bhabua) ") == "kaimur"
    assert split_districts("Begusarai , Pashchim Champaran,Purnea") == [
        "begusarai", "west_champaran", "purnia",
    ]


def test_flood_days_marks_inclusive_ranges_only_for_named_districts():
    events = pd.DataFrame({
        "district": ["patna"],
        "start": pd.to_datetime(["2020-07-02"]),
        "end": pd.to_datetime(["2020-07-03"]),
    })
    idx = pd.date_range("2020-07-01", "2020-07-04")
    t = flood_days(events, idx, ["patna", "gaya"])
    assert t["patna"].tolist() == [False, True, True, False]
    assert not t["gaya"].any()


def test_neighbouring_rows_settle_a_date_valid_both_ways():
    # Bihar, 2017, in inventory order. Alone, "07-05-2017" reads as 7 May.
    rows = [
        ("07-01-2017 00:00", "07-02-2017 00:00", 2.0),
        ("07-05-2017 00:00", "07-05-2017 00:00", 1.0),
        ("07-11-2017 00:00", "13-07-2017 00:00", 3.0),
    ]
    fixed = repair_sequence(rows)
    assert fixed[1][:2] == (date(2017, 7, 5), date(2017, 7, 5))
    assert [f[0].month for f in fixed] == [7, 7, 7]


def test_november_reading_loses_to_the_monsoon_reading():
    s, _, changed = repair_dates("07-11-2019 00:00", "07-11-2019 00:00", 1.0)
    assert s == date(2019, 7, 11)
    assert changed
