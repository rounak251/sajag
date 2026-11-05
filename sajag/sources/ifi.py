"""Recorded Bihar floods from the India Flood Inventory (IIT Delhi and IMD).

The inventory stores dates as dd-mm-yyyy, but many rows arrived from a mm-dd source and were
never converted: "07-11-2017" to "13-07-2017" with a duration of 3 days is 11 to 13 July, not
7 November to 13 July. Read naively, those rows put monsoon floods in winter. `repair_dates`
uses the recorded duration and the season to pick the reading that makes sense.
"""
from datetime import date

import pandas as pd

from sajag.geo import key


def _readings(text: str) -> list[date]:
    """Every valid date a dd-mm-yyyy or mm-dd-yyyy string could mean, dd-mm first."""
    head = str(text).split(" ")[0]
    a, b, y = (int(p) for p in head.split("-"))
    out = []
    for day, month in ((a, b), (b, a)):
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if d not in out:
            out.append(d)
    return out


def _options(start: str, end: str, duration: float | None) -> list[tuple[date, date, float]]:
    """Every (start, end) reading of a row, with a cost for how badly it fits."""
    out = []
    for i, s in enumerate(_readings(start)):
        for j, e in enumerate(_readings(end)):
            span = (e - s).days + 1
            cost = 1000.0 if span < 1 else 0.0
            if pd.notna(duration):
                cost += min(abs(span - duration), 400)
            elif span > 60:
                cost += span
            # Almost every Bihar flood falls between May and October.
            cost += 0 if 5 <= s.month <= 10 else 45
            cost += 0.01 * (i + j)  # ties keep the stored dd-mm reading
            out.append((s, e, cost))
    return out


def repair_dates(start: str, end: str, duration: float | None) -> tuple[date, date, bool]:
    """Pick the reading of one row that best fits its duration and the flood season."""
    return repair_sequence([(start, end, duration)])[0]


def repair_sequence(rows: list[tuple[str, str, float | None]]) -> list[tuple[date, date, bool]]:
    """Repair one year of rows at once.

    Inventory IDs run in date order within a year, so a row that is valid both ways round
    ("07-05-2017": 7 May or 5 July?) is settled by its neighbours. Dynamic programming picks
    the cheapest reading for each row, charging for every step back in time.
    """
    order_penalty = 30.0
    options = [_options(*r) for r in rows]
    best = [[o[2] for o in options[0]]]
    back: list[list[int]] = [[-1] * len(options[0])]
    for prev, cur in zip(options, options[1:]):
        scores, links = [], []
        for s, _e, cost in cur:
            steps = [
                best[-1][k] + (order_penalty if s < prev[k][0] else 0.0)
                for k in range(len(prev))
            ]
            k = min(range(len(steps)), key=steps.__getitem__)
            scores.append(steps[k] + cost)
            links.append(k)
        best.append(scores)
        back.append(links)
    k = min(range(len(best[-1])), key=best[-1].__getitem__)
    picks = [0] * len(rows)
    for i in range(len(rows) - 1, -1, -1):
        picks[i] = k
        k = back[i][k]
    out = []
    for row, opts, k in zip(rows, options, picks):
        s, e, _ = opts[k]
        stored = (_readings(row[0])[0], _readings(row[1])[0])
        out.append((s, e, (s, e) != stored))
    return out


def split_districts(text: str) -> list[str]:
    return [key(p) for p in str(text).split(",") if p.strip()]


def load_events(path, known_districts: set[str], max_days: int = 45) -> pd.DataFrame:
    """One row per recorded event and district, with repaired dates.

    Rows that still span more than `max_days` days are whole-season summaries rather than
    dated events, so they are dropped instead of marking a full season as flooded.
    """
    df = pd.read_csv(path, encoding="utf-8-sig")
    bihar = df[df["State"].astype(str).str.contains("Bihar", case=False)]
    bihar = bihar[bihar["Districts"].notna()].copy()
    parts = bihar["UEI"].str.extract(r"(\d{4})-(\d+)$").astype(int)
    bihar["uei_year"], bihar["uei_seq"] = parts[0], parts[1]
    rows = []
    for _, year in bihar.sort_values("uei_seq").groupby("uei_year"):
        raw = list(zip(year["Start Date"], year["End Date"], year["Duration(Days)"]))
        for r, (s, e, changed) in zip(year.to_dict("records"), repair_sequence(raw)):
            if (e - s).days + 1 > max_days:
                continue
            for d in split_districts(r["Districts"]):
                if d in known_districts:
                    rows.append({
                        "uei": r["UEI"], "district": d, "start": s, "end": e,
                        "repaired": changed, "deaths": r["Human fatality"],
                    })
    out = pd.DataFrame(rows).drop_duplicates(["uei", "district"])
    out["start"] = pd.to_datetime(out["start"])
    out["end"] = pd.to_datetime(out["end"])
    return out.sort_values("start").reset_index(drop=True)


RIVER_WORDS = r"flood|inundat|breach|embank|barrage|washed away|river|nepal"
STATEWIDE = 30  # a row naming this many districts is a state summary, not a located event


def river_text(raw: pd.DataFrame) -> pd.Series:
    """All the descriptive text of a row. Blanks must be filled first: on pandas 3 one empty cell
    otherwise makes the whole joined text NaN, which silently dropped 9 real floods."""
    columns = ["Main Cause", "Extent of damage ", "Description of Casualties/injured"]
    return raw[columns].fillna("").astype(str).agg(" ".join, axis=1).str.lower()


def load_river_floods(path, known_districts: set[str], first_year: int = 2006) -> pd.DataFrame:
    """Dated, located river floods: the events a warning system should be judged on.

    Before about 2005 IMD logged month-long rows covering every district, and about 40% of
    later rows are heavy-rain deaths with no flooding. Both are dropped here. `first_year`
    marks where the record becomes event by event.
    """
    events = load_events(path, known_districts)
    raw = pd.read_csv(path, encoding="utf-8-sig").set_index("UEI")
    is_river = river_text(raw).str.contains(RIVER_WORDS)
    events = events[events["uei"].map(is_river).fillna(False).astype(bool)]
    named = events.groupby("uei")["district"].transform("size")
    keep = (
        (named < STATEWIDE)
        & (events["start"].dt.year >= first_year)
        & events["start"].dt.month.between(6, 10)
    )
    return events[keep].reset_index(drop=True)


def unmatched_names(path, known_districts: set[str]) -> dict[str, int]:
    """Names in the inventory that map to no district, for a data-quality check."""
    df = pd.read_csv(path, encoding="utf-8-sig")
    bihar = df[df["State"].astype(str).str.contains("Bihar", case=False)]
    counts: dict[str, int] = {}
    for text in bihar["Districts"].dropna():
        for d in split_districts(text):
            if d not in known_districts:
                counts[d] = counts.get(d, 0) + 1
    return counts


def flood_days(events: pd.DataFrame, index: pd.DatetimeIndex, districts: list[str]) -> pd.DataFrame:
    """Boolean table of date x district: was a flood on record that day?"""
    table = pd.DataFrame(False, index=index, columns=districts)
    for r in events.itertuples():
        table.loc[r.start : r.end, r.district] = True
    return table
